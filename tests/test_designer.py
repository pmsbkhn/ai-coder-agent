"""Design-first phase, Slice 1 (M07): the Designer produces a DesignSpec +
executable TestPlan, schema-validated; the orchestrator logs DESIGN_PROPOSED when
enabled and skips it (current fast path) by default. No gate / no test-locking yet."""

from __future__ import annotations

from pathlib import Path

from aicoder.adapters.designer_llm import LLMDesigner
from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.application.orchestrator import Orchestrator
from aicoder.application.profile import load_profile
from aicoder.domain.models import DesignSpec, Plan, SessionState, Task, VerificationResult

from tests.test_orchestrator_loop import FakeBuild, FakeCoder, FakeGateway, FakePlanner

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")

_VALID_DESIGN = {
    "summary": "Add a nullable note to Order and thread it to OrderPlaced.",
    "affected": ["Order.java", "OrderPlaced.java"],
    "interface_changes": ["OrderService.placeOrder(customer, amount, note)"],
    "adr_notes": "Overload keeps the 2-arg call working.",
    "test_plan": [
        {"path": "src/test/java/com/example/OrderNoteTest.java",
         "content": "class OrderNoteTest {}", "rationale": "note flows to the event"},
    ],
}


class FakeLLM:
    model = "fake"

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)

    def complete_json(self, *, system, user, json_schema, tool_name="emit") -> dict:
        return self._payloads.pop(0)

    def complete_text(self, *, system, user, max_tokens=2048) -> str:  # pragma: no cover
        return ""


def _passed() -> VerificationResult:
    return VerificationResult(passed=True, functional_passed=True, arch_passed=True)


class FakeDesigner:
    def __init__(self) -> None:
        self.calls = 0

    def propose_design(self, requirement: str, repo_map: str) -> DesignSpec:
        self.calls += 1
        return DesignSpec.model_validate(_VALID_DESIGN)


def test_llm_designer_returns_valid_spec() -> None:
    designer = LLMDesigner(FakeLLM([_VALID_DESIGN]), _PROFILE)
    spec = designer.propose_design("add a note field", "# Repo Map\nclass Order")
    assert isinstance(spec, DesignSpec)
    assert spec.test_plan[0].path.endswith("OrderNoteTest.java")
    assert "OrderService" in spec.interface_changes[0]


def _orch(design_mode, designer, mem):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=designer, design_mode=design_mode,
    )


def test_design_logged_when_enabled() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch("always", designer, mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert designer.calls == 1
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_PROPOSED" in events
    payload = next(t.payload for t in mem.get_traces(session.session_id)
                   if t.event_type == "DESIGN_PROPOSED")
    assert payload["proposed_tests"] == ["src/test/java/com/example/OrderNoteTest.java"]


def test_design_skipped_by_default() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch("off", designer, mem).run_requirement("x")  # default fast path
    assert session.state is SessionState.DONE
    assert designer.calls == 0
    assert "DESIGN_PROPOSED" not in [t.event_type for t in mem.get_traces(session.session_id)]


# --- Slice 2: human gate + lock the approved tests as the oracle ----------------

class _Approval:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def request_approval(self, kind: str, summary: str) -> bool:
        return self.ok


class _TamperingCoder(FakeCoder):
    """Tries to overwrite the design-locked test — must be refused."""
    def apply_task(self, task, files, error_context: str = ""):
        from aicoder.domain.models import CodeChange, FileEdit
        return CodeChange(edits=[
            FileEdit(path="A.java", content="class A {}"),
            FileEdit(path="src/test/java/com/example/OrderNoteTest.java", content="// tamper"),
        ])


def _gated_orch(approval, mem, coder=None):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=coder or FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=FakeDesigner(), design_mode="always", approval=approval,
    )


def test_approved_design_locks_proposed_tests() -> None:
    mem = InMemoryMemory()
    session = _gated_orch(_Approval(True), mem, coder=_TamperingCoder()).run_requirement("x")
    assert session.state is SessionState.DONE
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert events.count("DESIGN_PROPOSED") == 1
    assert "APPROVAL_REQUESTED" in events and "DESIGN_APPROVED" in events
    # the Coder tried to overwrite the locked test and was refused
    assert "WRITE_BLOCKED" in events


def test_rejected_design_blocks_before_coding() -> None:
    mem = InMemoryMemory()
    coder = FakeCoder()
    session = _gated_orch(_Approval(False), mem, coder=coder).run_requirement("x")
    assert session.state is SessionState.BLOCKED
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_REJECTED" in events
    assert "DIFF_APPLIED" not in events     # never reached coding
    assert coder.contexts == []             # Coder never called


# --- Slice 3: tiering — auto designs complex changes, skips trivial ones --------

_TRIVIAL = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
_COMPLEX = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java", "B.java"])])


def _orch_with_plan(plan, design_mode, designer, mem):
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=designer, design_mode=design_mode,
    )


def test_auto_skips_trivial_change() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch_with_plan(_TRIVIAL, "auto", designer, mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert designer.calls == 0
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "DESIGN_SKIPPED" in events and "DESIGN_PROPOSED" not in events


def test_auto_designs_complex_change() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    session = _orch_with_plan(_COMPLEX, "auto", designer, mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert designer.calls == 1
    assert "DESIGN_PROPOSED" in [t.event_type for t in mem.get_traces(session.session_id)]


def test_always_designs_even_trivial() -> None:
    mem, designer = InMemoryMemory(), FakeDesigner()
    _orch_with_plan(_TRIVIAL, "always", designer, mem).run_requirement("x")
    assert designer.calls == 1   # 'always' bypasses the tiering heuristic


# --- Slice 4: adversarial test review before locking ---------------------------

# aliased so pytest doesn't try to collect the "Test"-prefixed domain model as a test
from aicoder.domain.models import TestReview as _ReviewModel  # noqa: E402


class _Reviewer:
    def __init__(self, ok: bool, concerns=None) -> None:
        self.ok = ok
        self.concerns = concerns or []
        self.calls = 0

    def review_tests(self, requirement, design_summary, tests) -> _ReviewModel:
        self.calls += 1
        return _ReviewModel(ok=self.ok, concerns=self.concerns)


def _reviewed_orch(approval, reviewer, mem, profile=_PROFILE):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=profile, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        designer=FakeDesigner(), design_mode="always", approval=approval, reviewer=reviewer,
    )


def _strict_profile():
    return _PROFILE.model_copy(
        update={"design": _PROFILE.design.model_copy(update={"review_strict": True})})


def test_review_ok_proceeds_to_gate() -> None:
    mem, rev = InMemoryMemory(), _Reviewer(True)
    session = _reviewed_orch(_Approval(True), rev, mem).run_requirement("x")
    assert session.state is SessionState.DONE and rev.calls == 1
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "TEST_REVIEW" in events and "DESIGN_APPROVED" in events


def test_review_strict_auto_blocks_weak_tests() -> None:
    mem, rev = InMemoryMemory(), _Reviewer(False, ["assertTrue(true) — trivially satisfiable"])
    session = _reviewed_orch(_Approval(True), rev, mem, profile=_strict_profile()).run_requirement("x")
    assert session.state is SessionState.BLOCKED
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "TEST_REVIEW" in events and "DESIGN_REJECTED" in events
    assert "APPROVAL_REQUESTED" not in events   # blocked before the human gate
    assert "DIFF_APPLIED" not in events


def test_review_advisory_surfaces_concerns_then_human_approves() -> None:
    mem, rev = InMemoryMemory(), _Reviewer(False, ["missing the insufficient-funds case"])
    session = _reviewed_orch(_Approval(True), rev, mem).run_requirement("x")  # review_strict False
    assert session.state is SessionState.DONE
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "TEST_REVIEW" in events and "DESIGN_APPROVED" in events
    payload = next(t.payload for t in mem.get_traces(session.session_id)
                   if t.event_type == "APPROVAL_REQUESTED")
    assert payload["review_concerns"] == ["missing the insufficient-funds case"]
