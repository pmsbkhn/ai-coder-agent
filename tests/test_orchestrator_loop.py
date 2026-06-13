"""Control-loop behavior, fully hermetic (fake ports — no LLM, git, or mvn).

Proves the deterministic orchestration: plan -> code -> verify -> commit, the
per-task self-healing retry, and the circuit breaker. This is the logic that must
stay correct regardless of which model sits behind the Coder/Planner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.application.orchestrator import Orchestrator
from aicoder.application.profile import load_profile
from aicoder.domain.errors import ToolInvocationError
from aicoder.domain.models import (
    CodeChange,
    FileEdit,
    Plan,
    SessionState,
    Task,
    ToolResponse,
    VerificationResult,
)

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")


def _passed() -> VerificationResult:
    return VerificationResult(passed=True, functional_passed=True, arch_passed=True)


def _failed(sig: str) -> VerificationResult:
    return VerificationResult(
        passed=False, functional_passed=False, arch_passed=True,
        failed_tests=["com.example.T.x"], evidence="boom", error_signature=sig,
    )


class FakePlanner:
    def __init__(self, plan: Plan) -> None:
        self._plan = plan

    def generate_plan(self, requirement: str, repo_map: str) -> Plan:
        return self._plan


class FakeCoder:
    def __init__(self) -> None:
        self.contexts: list[str] = []

    def apply_task(self, task, files, error_context: str = "") -> CodeChange:
        self.contexts.append(error_context)
        return CodeChange(edits=[FileEdit(path="A.java", content="class A { int x; }")])


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def execute_tool_call(self, request) -> ToolResponse:
        self.calls.append((request.server, request.method))
        s, m = request.server, request.method
        if s == "code-reader" and m == "get_repo_map":
            return ToolResponse(ok=True, result={"repo_map": "# map\nclass A"})
        if s == "git" and m == "start_task":
            return ToolResponse(ok=True, result={"worktree": "/tmp/wt", "branch": "b"})
        if s == "git" and m == "read_file":
            return ToolResponse(ok=True, result={"exists": True, "content": "class A {}"})
        if s == "git" and m in ("write_file", "commit"):
            return ToolResponse(ok=True, result={"ok": True, "commit": "abc123"})
        return ToolResponse(ok=False, error_code=-32601, error_message=f"unknown {s}.{m}")


class FakeBuild:
    def __init__(self, results: list[VerificationResult]) -> None:
        self._results = list(results)

    def run_tests(self, module=None, test=None, workdir=None) -> VerificationResult:
        return self._results.pop(0)


def _orchestrator(plan, build, *, coder=None, gateway=None, memory=None):
    return Orchestrator(
        profile=_PROFILE,
        planner=FakePlanner(plan),
        coder=coder or FakeCoder(),
        memory=memory or InMemoryMemory(),
        gateway=gateway or FakeGateway(),
        build=build,
    )


def test_happy_path_plans_codes_verifies_commits() -> None:
    plan = Plan(tasks=[Task(id="t1", description="add x", target_files=["A.java"])])
    mem, gw = InMemoryMemory(), FakeGateway()
    orch = _orchestrator(plan, FakeBuild([_passed()]), gateway=gw, memory=mem)

    session = orch.run_requirement("add field x")

    assert session.state is SessionState.DONE
    assert ("git", "commit") in gw.calls
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert events[0] == "SESSION_CREATED"
    assert "PLAN_CREATED" in events and "VERIFY_PASS" in events and "SESSION_DONE" in events


def test_self_heals_then_passes() -> None:
    plan = Plan(tasks=[Task(id="t1", description="add x", target_files=["A.java"])])
    coder = FakeCoder()
    orch = _orchestrator(plan, FakeBuild([_failed("s1"), _passed()]), coder=coder)

    session = orch.run_requirement("add field x")

    assert session.state is SessionState.DONE
    assert session.attempts == 1
    # the second coding attempt received the distilled error context
    assert coder.contexts[0] == "" and "Failed tests" in coder.contexts[1]


def test_circuit_breaker_trips_after_n_attempts() -> None:
    plan = Plan(tasks=[Task(id="t1", description="add x", target_files=["A.java"])])
    # distinct signatures so it's the attempt count (N=3), not no-progress, that trips
    build = FakeBuild([_failed("s1"), _failed("s2"), _failed("s3")])
    mem = InMemoryMemory()
    orch = _orchestrator(plan, build, memory=mem)

    session = orch.run_requirement("add field x")

    assert session.state is SessionState.HEALING_FAILED
    assert session.attempts == 3
    assert "HEALING_FAILED" in [t.event_type for t in mem.get_traces(session.session_id)]


def test_multi_task_advances_between_tasks() -> None:
    plan = Plan(
        tasks=[
            Task(id="t1", description="step 1", target_files=["A.java"]),
            Task(id="t2", description="step 2", target_files=["A.java"]),
        ]
    )
    session = _orchestrator(plan, FakeBuild([_passed(), _passed()])).run_requirement("two steps")
    assert session.state is SessionState.DONE


def test_empty_plan_blocks() -> None:
    session = _orchestrator(Plan(tasks=[]), FakeBuild([])).run_requirement("nothing")
    assert session.state is SessionState.BLOCKED


def test_tool_business_failure_is_not_swallowed() -> None:
    """A tool that reports ok=False (e.g. a commit that aborted) must surface,
    not pass as success (regression for the silent-commit-failure bug)."""

    class FailingCommitGateway(FakeGateway):
        def execute_tool_call(self, request):
            if request.server == "git" and request.method == "commit":
                return ToolResponse(ok=True, result={"ok": False, "error": "identity unknown"})
            return super().execute_tool_call(request)

    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    orch = _orchestrator(plan, FakeBuild([_passed()]), gateway=FailingCommitGateway())
    with pytest.raises(ToolInvocationError):
        orch.run_requirement("x")
