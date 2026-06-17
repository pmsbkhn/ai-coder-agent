"""Slice B — requirements traceability. The deterministic linter enforces AC→locked-test
(T1) and locked-test→requirement (T3) as HARD findings, surfaces NFR coverage (T2) as
advisory, and the requirements.md renderer shows the AC→test matrix. All pure functions."""

from __future__ import annotations

from aicoder.application.design_lint import lint_design, lint_nfr_coverage
from aicoder.application.design_docs import render_ad, render_requirements
from aicoder.domain.models import (
    AcceptanceCriterion,
    DesignSpec,
    ISO25010,
    NFR,
    ProposedTest,
    RequirementSpec,
    TechSpec,
    UserStory,
)


def _req() -> RequirementSpec:
    return RequirementSpec(
        title="Order note",
        stories=[UserStory(id="US-01", acceptance=[
            AcceptanceCriterion(id="AC-01", text="note stored"),
            AcceptanceCriterion(id="AC-02", text="too-long rejected"),
        ])],
        nfrs=[NFR(id="NFR-01", category=ISO25010.PERFORMANCE, metric="p95<300ms")],
    )


def _locked(tc_id: str, traces: list[str], path: str = "src/test/java/order/XTest.java"):
    return ProposedTest(id=tc_id, kind="domain", spec="setup→act→assert",
                        path=path, content="class XTest {}", traces_to=traces)


def _design(tests: list[ProposedTest], *, nfr_note: str = "") -> DesignSpec:
    ts = TechSpec(bounded_context="Order", summary="order ctx", test_plan=tests,
                  requirements_nonfunctional=([nfr_note] if nfr_note else []))
    return DesignSpec(summary="add note", tech_specs=[ts])


def _has(issues: list[str], *needles: str) -> bool:
    return any(all(n in i for n in needles) for i in issues)


# --- T1: every AC must be pinned by a LOCKED test -----------------------------

def test_t1_flags_uncovered_acceptance_criterion() -> None:
    design = _design([_locked("TC-ORD-01", ["AC-01"])])  # AC-02 uncovered
    issues = lint_design(design, _req())
    assert _has(issues, "T1", "AC-02")
    assert not _has(issues, "T1", "AC-01")


def test_t1_spec_only_test_does_not_count_as_coverage() -> None:
    # an adapter case that mentions AC-02 but is NOT locked (no path/content)
    spec_only = ProposedTest(id="TC-ORD-02", kind="adapter", traces_to=["AC-02"])
    design = _design([_locked("TC-ORD-01", ["AC-01"]), spec_only])
    issues = lint_design(design, _req())
    assert _has(issues, "T1", "AC-02")          # still uncovered — only locked tests count


def test_t1_clean_when_all_acs_locked() -> None:
    design = _design([
        _locked("TC-ORD-01", ["AC-01"], "src/test/java/order/ATest.java"),
        _locked("TC-ORD-02", ["AC-02"], "src/test/java/order/BTest.java"),
    ])
    assert not [i for i in lint_design(design, _req()) if i.startswith("T1")]


# --- T3: every locked test must trace to a known requirement ------------------

def test_t3_flags_orphan_locked_test() -> None:
    design = _design([_locked("TC-ORD-01", ["AC-01"]),
                      _locked("TC-ORD-09", [], "src/test/java/order/Orphan.java")])
    assert _has(lint_design(design, _req()), "T3", "TC-ORD-09")


def test_t3_flags_unknown_requirement_id() -> None:
    design = _design([_locked("TC-ORD-01", ["AC-01"]),
                      _locked("TC-ORD-02", ["AC-99"], "src/test/java/order/BTest.java")])
    issues = lint_design(design, _req())
    assert _has(issues, "T3", "TC-ORD-02")      # AC-99 is not a known id


def test_t3_exempts_fitness_cases() -> None:
    fitness = ProposedTest(id="TC-ARCH-01", kind="fitness", spec="domain imports nothing")
    design = _design([_locked("TC-ORD-01", ["AC-01"]),
                      _locked("TC-ORD-02", ["AC-02"], "src/test/java/order/BTest.java"),
                      fitness])
    assert not [i for i in lint_design(design, _req()) if i.startswith("T3")]


# --- T2: NFR coverage is advisory (separate channel, never blocks) ------------

def test_t2_flags_unaddressed_nfr() -> None:
    design = _design([_locked("TC-ORD-01", ["AC-01"])])
    assert _has(lint_nfr_coverage(design, _req()), "T2", "NFR-01")
    # ...and T2 is NOT in the hard lint_design output
    assert not [i for i in lint_design(design, _req()) if i.startswith("T2")]


def test_t2_satisfied_by_traces_or_design_note() -> None:
    via_trace = _design([_locked("TC-ORD-01", ["AC-01", "NFR-01"])])
    assert not lint_nfr_coverage(via_trace, _req())
    via_note = _design([_locked("TC-ORD-01", ["AC-01"])], nfr_note="NFR-01: budgeted at p95<300ms")
    assert not lint_nfr_coverage(via_note, _req())


# --- back-compat: no req_spec => no traceability rules ------------------------

def test_no_req_spec_skips_all_traceability() -> None:
    design = _design([_locked("TC-ORD-01", [])])      # orphan, but no intake
    issues = lint_design(design)                      # req_spec defaults None
    assert not [i for i in issues if i.startswith(("T1", "T3"))]
    assert lint_nfr_coverage(design, None) == []


# --- renderers ----------------------------------------------------------------

def test_render_requirements_has_tables_and_matrix() -> None:
    design = _design([_locked("TC-ORD-01", ["AC-01"])])   # AC-02 uncovered
    doc = render_requirements(_req(), design)
    assert "## User Stories" in doc and "US-01" in doc
    assert "## Non-functional requirements" in doc and "NFR-01" in doc and "Performance" in doc
    assert "## Traceability" in doc
    assert "TC-ORD-01 🔒" in doc          # locked marker in the matrix
    assert "⚠️ uncovered" in doc          # AC-02 flagged


def test_render_ad_links_requirements_when_present() -> None:
    design = _design([_locked("TC-ORD-01", ["AC-01"])])
    assert "requirements.md" in render_ad(design, "req prose", requirements_link="requirements.md")
    assert "requirements.md" not in render_ad(design, "req prose")


# --- orchestrator wiring: a structured intake writes requirements.md ----------

def test_orchestrator_writes_requirements_doc_with_spec() -> None:
    from pathlib import Path

    from aicoder.adapters.memory_inmemory import InMemoryMemory
    from aicoder.application.orchestrator import Orchestrator
    from aicoder.application.profile import load_profile
    from aicoder.domain.models import Plan, Task, VerificationResult

    from tests.test_designer import FakeDesigner, _RecordingGateway
    from tests.test_orchestrator_loop import FakeBuild, FakeCoder, FakePlanner

    profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")
    plan = Plan(tasks=[Task(id="t1", description="x", target_files=["A.java"])])
    gw = _RecordingGateway()
    orch = Orchestrator(
        profile=profile, planner=FakePlanner(plan), coder=FakeCoder(),
        memory=InMemoryMemory(), gateway=gw,
        build=FakeBuild([VerificationResult(passed=True, functional_passed=True, arch_passed=True)]),
        designer=FakeDesigner(), design_mode="always",  # no approval => writes + logs only
    )
    orch.run_requirement("", spec=_req())
    assert "docs/design/requirements.md" in gw.writes
    assert "docs/design/AD.md" in gw.writes
