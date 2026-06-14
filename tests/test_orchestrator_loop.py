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
        self.reflections: list[list[str]] = []

    def generate_plan(self, requirement: str, repo_map: str) -> Plan:
        return self._plan

    def reflect(
        self, requirement: str, error_context: str, files: dict[str, str], history: list[str]
    ) -> str:
        # Vary with history so each heal attempt gets a different strategy (M3).
        self.reflections.append(list(history))
        return f"strategy #{len(history) + 1}"


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
        if s == "git" and m in ("write_file", "commit", "reset_clean"):
            return ToolResponse(ok=True, result={"ok": True, "commit": "abc123"})
        if s == "git" and m == "push":
            return ToolResponse(ok=True, result={"ok": True, "remote": "origin",
                                                 "branch": "b", "pushed": True})
        if s == "git" and m == "open_pr":
            return ToolResponse(ok=True, result={"ok": True, "url": "https://example/pr/1"})
        if s == "git" and m == "list_files":
            return ToolResponse(ok=True, result={"files": [
                "src/main/java/A.java", "src/test/java/com/example/OrderNoteTest.java",
            ]})
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


def test_m3_heal_reflects_and_resets_to_clean() -> None:
    """M3: each heal attempt resets the worktree to clean and runs a reflection
    whose strategy is fed to the Coder — so a temp-0 Coder gets a varying prompt."""
    plan = Plan(tasks=[Task(id="t1", description="add x", target_files=["A.java"])])
    coder, gw = FakeCoder(), FakeGateway()
    planner = FakePlanner(plan)
    # two distinct failures then pass -> two heal attempts
    orch = Orchestrator(
        profile=_PROFILE, planner=planner, coder=coder,
        memory=InMemoryMemory(), gateway=gw,
        build=FakeBuild([_failed("s1"), _failed("s2"), _passed()]),
    )

    session = orch.run_requirement("add field x")

    assert session.state is SessionState.DONE
    # reflection ran once per failure, each seeing the growing history (M3 variation)
    assert planner.reflections == [[], ["strategy #1"]]
    # worktree was reset to clean before each re-code
    assert gw.calls.count(("git", "reset_clean")) == 2
    # the Coder received the reflection strategy in its heal prompts
    assert "# Fix strategy" in coder.contexts[1] and "strategy #1" in coder.contexts[1]


def test_deliver_local_does_not_push() -> None:
    """Default delivery is local commit only — no push, no PR (M5)."""
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    gw = FakeGateway()
    orch = _orchestrator(plan, FakeBuild([_passed()]), gateway=gw)  # deliver defaults to "local"
    session = orch.run_requirement("x")
    assert session.state is SessionState.DONE
    assert ("git", "push") not in gw.calls


def test_deliver_pr_pushes_and_opens_pr() -> None:
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    gw, mem = FakeGateway(), InMemoryMemory()
    orch = Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=gw, build=FakeBuild([_passed()]), deliver="pr",
    )
    session = orch.run_requirement("x")
    assert session.state is SessionState.DONE
    assert ("git", "push") in gw.calls and ("git", "open_pr") in gw.calls
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "PUSHED" in events and "PR_OPENED" in events


def test_circuit_breaker_trips_after_n_attempts() -> None:
    n = _PROFILE.healing.max_attempts
    plan = Plan(tasks=[Task(id="t1", description="add x", target_files=["A.java"])])
    # distinct signatures so it's the attempt count (N), not no-progress, that trips
    build = FakeBuild([_failed(f"s{i}") for i in range(n)])
    mem = InMemoryMemory()
    orch = _orchestrator(plan, build, memory=mem)

    session = orch.run_requirement("add field x")

    assert session.state is SessionState.HEALING_FAILED
    assert session.attempts == n
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


def test_protected_files_are_read_but_not_written() -> None:
    """Eval oracle: a pre-written test is fed to the Coder as context but writes
    to it are refused, so the agent can't cheat by editing the spec."""
    profile = _PROFILE.model_copy(update={"protected_globs": ["*src/test/*"]})
    plan = Plan(tasks=[Task(id="t1", description="impl", target_files=["A.java"])])

    class ProtectGateway(FakeGateway):
        def execute_tool_call(self, request):
            if request.server == "git" and request.method == "list_files":
                return ToolResponse(ok=True, result={"files": [
                    "src/main/java/A.java", "src/test/java/ATest.java",
                ]})
            return super().execute_tool_call(request)

    class TestEditingCoder(FakeCoder):
        def __init__(self) -> None:
            super().__init__()
            self.seen: list[str] = []

        def apply_task(self, task, files, error_context: str = "") -> CodeChange:
            self.seen = list(files)
            return CodeChange(edits=[
                FileEdit(path="A.java", content="class A {}"),
                FileEdit(path="src/test/java/ATest.java", content="// agent tampering"),
            ])

    coder, gw, mem = TestEditingCoder(), ProtectGateway(), InMemoryMemory()
    orch = Orchestrator(
        profile=profile, planner=FakePlanner(plan), coder=coder,
        memory=mem, gateway=gw, build=FakeBuild([_passed()]),
    )
    session = orch.run_requirement("impl")

    assert session.state is SessionState.DONE
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "WRITE_BLOCKED" in events  # the test-file write was refused
    assert "src/test/java/ATest.java" in coder.seen  # but it WAS in the Coder's context


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
