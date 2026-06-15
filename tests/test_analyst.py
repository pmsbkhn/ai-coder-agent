"""Analysis phase (ADR-08): the Analyst restates a prose business requirement and
surfaces ambiguity BEFORE design. Slice 1 logs ANALYSIS_DONE (auditable); Slice 2
gates a genuinely-ambiguous requirement on the human clarification gate."""

from __future__ import annotations

from pathlib import Path

from aicoder.adapters.analyst_llm import LLMAnalyst
from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.application.orchestrator import Orchestrator
from aicoder.application.profile import load_profile
from aicoder.domain.models import AnalysisSpec, Plan, SessionState, Task, VerificationResult

from tests.test_designer import FakeDesigner
from tests.test_orchestrator_loop import FakeBuild, FakeCoder, FakeGateway, FakePlanner

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")

_CLEAR = {
    "restatement": "Add a nullable note to Order.",
    "assumptions": ["note is optional and defaults to null"],
    "open_questions": [],
    "acceptance_criteria": ["an Order can be created with a note", "note reaches OrderPlaced"],
    "ambiguous": False,
}
_AMBIGUOUS = {
    "restatement": "Let customers 'manage their account' — scope unclear.",
    "assumptions": ["read-only profile view"],
    "open_questions": ["which fields are editable?", "does this include closing the account?"],
    "acceptance_criteria": [],
    "ambiguous": True,
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


class FakeAnalyst:
    def __init__(self, spec: dict) -> None:
        self.calls = 0
        self._spec = spec

    def analyze(self, requirement: str, repo_map: str) -> AnalysisSpec:
        self.calls += 1
        return AnalysisSpec.model_validate(self._spec)


class _Approval:
    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.kinds: list[str] = []

    def request_approval(self, kind: str, summary: str) -> bool:
        self.kinds.append(kind)
        return self.ok


def _orch(analysis_mode, analyst, mem, *, approval=None, designer=None, design_mode="off"):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        analyst=analyst, analysis_mode=analysis_mode,
        approval=approval, designer=designer, design_mode=design_mode,
    )


def _events(mem, sid):
    return [t.event_type for t in mem.get_traces(sid)]


# --- adapter ------------------------------------------------------------------

def test_llm_analyst_returns_valid_spec() -> None:
    analyst = LLMAnalyst(FakeLLM([_AMBIGUOUS]), _PROFILE)
    spec = analyst.analyze("let customers manage their account", "# Repo Map")
    assert isinstance(spec, AnalysisSpec)
    assert spec.ambiguous is True
    assert len(spec.open_questions) == 2


# --- Slice 1: analysis is opt-in and audited ----------------------------------

def test_analysis_off_by_default() -> None:
    mem, analyst = InMemoryMemory(), FakeAnalyst(_CLEAR)
    session = _orch("off", analyst, mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert analyst.calls == 0
    assert "ANALYSIS_DONE" not in _events(mem, session.session_id)


def test_clear_analysis_proceeds_to_done() -> None:
    mem, analyst = InMemoryMemory(), FakeAnalyst(_CLEAR)
    session = _orch("always", analyst, mem).run_requirement("x")
    assert session.state is SessionState.DONE
    assert analyst.calls == 1
    events = _events(mem, session.session_id)
    assert "ANALYSIS_DONE" in events
    assert "NEEDS_CLARIFICATION" not in events     # clear → no gate


# --- Slice 2: clarification gate on an ambiguous requirement -------------------

def test_ambiguous_blocks_when_clarification_denied() -> None:
    mem, analyst = InMemoryMemory(), FakeAnalyst(_AMBIGUOUS)
    approval = _Approval(False)
    coder = FakeCoder()
    orch = _orch("always", analyst, mem, approval=approval)
    orch._coder = coder  # observe the Coder was never reached
    session = orch.run_requirement("x")
    assert session.state is SessionState.BLOCKED
    events = _events(mem, session.session_id)
    assert "NEEDS_CLARIFICATION" in events and "CLARIFICATION_REQUIRED" in events
    assert "DIFF_APPLIED" not in events            # never reached coding
    assert approval.kinds == ["clarification"]     # gated on the right kind
    assert coder.contexts == []


def test_ambiguous_proceeds_when_clarification_approved() -> None:
    mem, analyst = InMemoryMemory(), FakeAnalyst(_AMBIGUOUS)
    approval = _Approval(True)
    session = _orch("always", analyst, mem, approval=approval).run_requirement("x")
    assert session.state is SessionState.DONE
    events = _events(mem, session.session_id)
    assert "CLARIFICATION_PROCEED" in events
    assert approval.kinds == ["clarification"]


def test_ambiguous_is_advisory_without_a_gate() -> None:
    # Analyst on but no ApprovalPort wired → audit-only: surface the questions, then
    # proceed on the analyst's assumptions (a gate REQUIRES an ApprovalPort).
    mem, analyst = InMemoryMemory(), FakeAnalyst(_AMBIGUOUS)
    session = _orch("always", analyst, mem, approval=None).run_requirement("x")
    assert session.state is SessionState.DONE
    events = _events(mem, session.session_id)
    assert "NEEDS_CLARIFICATION" in events
    assert "CLARIFICATION_REQUIRED" not in events


# --- ordering: analysis runs BEFORE design ------------------------------------

def test_analysis_runs_before_design() -> None:
    mem = InMemoryMemory()
    session = _orch(
        "always", FakeAnalyst(_CLEAR), mem, designer=FakeDesigner(), design_mode="always",
    ).run_requirement("x")
    assert session.state is SessionState.DONE
    events = _events(mem, session.session_id)
    assert events.index("ANALYSIS_DONE") < events.index("DESIGN_PROPOSED")
