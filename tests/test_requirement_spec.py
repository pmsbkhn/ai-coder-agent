"""Structured requirements intake (Slice A): parse a requirements YAML into a
RequirementSpec, render it as prose / a prompt section, and prove it threads through
the Orchestrator into the Analyst and Designer. Fully hermetic (no LLM/git/mvn)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from aicoder.adapters.analyst_llm import LLMAnalyst
from aicoder.adapters.designer_llm import LLMDesigner
from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.application.orchestrator import Orchestrator
from aicoder.application.profile import load_profile
from aicoder.application.requirement_spec import (
    load_requirement_spec,
    render_requirement_section,
)
from aicoder.domain.models import (
    AcceptanceCriterion,
    ISO25010,
    NFR,
    Plan,
    RequirementSpec,
    SessionState,
    Task,
    UserStory,
)

from tests.test_analyst import FakeAnalyst, _CLEAR
from tests.test_designer import FakeDesigner, _VALID_DESIGN
from tests.test_orchestrator_loop import FakeBuild, FakeCoder, FakeGateway, FakePlanner

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")

_YAML = """\
meta:
  title: "Order note feature"
stories:
  - id: US-01
    title: "Customer notes an order"
    as_a: "customer"
    i_want: "attach a note to an order"
    so_that: "the courier sees special instructions"
    priority: High
    acceptance:
      - id: AC-01
        given: "an order in PLACED state"
        when:  "the customer sets a note <= 280 chars"
        then:  "the note is stored and appears on OrderPlaced"
      - id: AC-02
        given: "a note longer than 280 chars"
        when:  "the customer submits"
        then:  "it is rejected with DomainException(NOTE_TOO_LONG)"
nfrs:
  - id: NFR-01
    category: Performance
    metric: "p95 < 300ms for POST /orders"
    measurement: "measured at the API gateway"
    source: "US-01"
    scope: "BC-Order"
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "req.yaml"
    p.write_text(text, encoding="utf-8")
    return p


# --- model --------------------------------------------------------------------

def test_acceptance_criterion_renders_gherkin_or_freeform() -> None:
    gherkin = AcceptanceCriterion(id="AC-1", given="g", when="w", then="t")
    assert gherkin.as_text() == "Given g, When w, Then t."
    free = AcceptanceCriterion(id="AC-2", text="just this")
    assert free.as_text() == "just this"


def test_ids_helpers() -> None:
    spec = RequirementSpec(
        stories=[UserStory(id="US-01", acceptance=[
            AcceptanceCriterion(id="AC-01"), AcceptanceCriterion(id="AC-02")])],
        nfrs=[NFR(id="NFR-01", category=ISO25010.SECURITY, metric="m")],
    )
    assert spec.acceptance_ids == ["AC-01", "AC-02"]
    assert spec.nfr_ids == ["NFR-01"]


def test_to_prose_contains_ids_story_and_nfr() -> None:
    spec = RequirementSpec(
        title="T",
        stories=[UserStory(id="US-01", title="note", as_a="customer",
                           i_want="x", so_that="y", priority="High",
                           acceptance=[AcceptanceCriterion(id="AC-01", text="works")])],
        nfrs=[NFR(id="NFR-01", category=ISO25010.PERFORMANCE, metric="p95<300ms",
                  measurement="gw", source="US-01", scope="BC-Order")],
    )
    prose = spec.to_prose()
    assert "US-01" in prose and "AC-01: works" in prose
    assert "NFR-01 [Performance] p95<300ms" in prose
    assert "measure: gw" in prose and "scope: BC-Order" in prose


# --- loader -------------------------------------------------------------------

def test_load_parses_meta_title_stories_and_nfrs(tmp_path: Path) -> None:
    spec = load_requirement_spec(_write(tmp_path, _YAML))
    assert spec.title == "Order note feature"
    assert [s.id for s in spec.stories] == ["US-01"]
    assert spec.stories[0].priority == "High"
    assert spec.acceptance_ids == ["AC-01", "AC-02"]
    assert spec.nfrs[0].category is ISO25010.PERFORMANCE


def test_load_rejects_non_mapping(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_requirement_spec(_write(tmp_path, "- just\n- a list\n"))


def test_load_rejects_unknown_nfr_category(tmp_path: Path) -> None:
    bad = "nfrs:\n  - id: NFR-1\n    category: Snappiness\n    metric: fast\n"
    with pytest.raises(ValidationError):
        load_requirement_spec(_write(tmp_path, bad))


# --- prompt rendering ---------------------------------------------------------

def test_render_section_labels_every_id() -> None:
    spec = load_requirement_spec_from_text(_YAML)
    section = render_requirement_section(spec)
    assert "BINDING" in section
    for token in ("US-01", "AC-01", "AC-02", "NFR-01", "Performance"):
        assert token in section


def load_requirement_spec_from_text(text: str) -> RequirementSpec:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.yaml"
        p.write_text(text, encoding="utf-8")
        return load_requirement_spec(p)


# --- adapter wiring (structured mode changes the prompt) ----------------------

class CapturingLLM:
    model = "fake"

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.system = ""
        self.user = ""

    def complete_json(self, *, system, user, json_schema, tool_name="emit") -> dict:
        self.system, self.user = system, user
        return self._payload

    def complete_text(self, *, system, user, max_tokens=2048) -> str:  # pragma: no cover
        return ""


def test_analyst_structured_mode_injects_contract() -> None:
    spec = load_requirement_spec_from_text(_YAML)
    llm = CapturingLLM(_CLEAR)
    LLMAnalyst(llm, _PROFILE).analyze("ignored prose", "# Repo Map", spec)
    assert "Structured input mode" in llm.system        # the verdict-inverting addendum
    assert "AC-01" in llm.user and "NFR-01" in llm.user  # the binding contract is visible


def test_designer_structured_mode_injects_contract() -> None:
    spec = load_requirement_spec_from_text(_YAML)
    llm = CapturingLLM(_VALID_DESIGN)
    LLMDesigner(llm, _PROFILE).propose_design("ignored prose", "# Repo Map", None, spec)
    assert "DESIGN CONTRACT" in llm.user
    assert "AC-01" in llm.user and "AC-02" in llm.user and "NFR-01" in llm.user


# --- orchestrator wiring ------------------------------------------------------

def _spec() -> RequirementSpec:
    return load_requirement_spec_from_text(_YAML)


def _orch(mem, analyst, designer):
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    return Orchestrator(
        profile=_PROFILE, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=mem, gateway=FakeGateway(), build=FakeBuild([_passed()]),
        analyst=analyst, analysis_mode="always",
        designer=designer, design_mode="always",
    )


def _passed():
    from aicoder.domain.models import VerificationResult
    return VerificationResult(passed=True, functional_passed=True, arch_passed=True)


def test_run_requirement_threads_spec_to_analyst_and_designer() -> None:
    mem = InMemoryMemory()
    analyst, designer = FakeAnalyst(_CLEAR), FakeDesigner()
    spec = _spec()
    session = _orch(mem, analyst, designer).run_requirement("", spec=spec)

    assert session.state is SessionState.DONE
    assert analyst.req_spec is spec           # structured contract reached the Analyst
    assert designer.seen_spec is spec         # ...and the Designer
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "REQUIREMENTS_LOADED" in events


def test_run_requirement_without_spec_is_unchanged() -> None:
    mem = InMemoryMemory()
    analyst, designer = FakeAnalyst(_CLEAR), FakeDesigner()
    session = _orch(mem, analyst, designer).run_requirement("add a note field")
    assert session.state is SessionState.DONE
    assert analyst.req_spec is None
    assert designer.seen_spec is None
    events = [t.event_type for t in mem.get_traces(session.session_id)]
    assert "REQUIREMENTS_LOADED" not in events
