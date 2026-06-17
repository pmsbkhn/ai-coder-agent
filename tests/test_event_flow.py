"""Slice C — event-flow (B2) + derived Glossary/Use-Cases (B1). Models, the advisory
event-flow linter (T4), and the renderers. Pure functions, fully hermetic."""

from __future__ import annotations

from aicoder.application.design_lint import lint_event_flow
from aicoder.application.design_docs import render_ad, render_tech_spec
from aicoder.domain.models import (
    AcceptanceCriterion,
    Command,
    DesignSpec,
    DomainEvent,
    GlossaryTerm,
    ISO25010,
    NFR,
    Policy,
    ReadModel,
    RequirementSpec,
    TechSpec,
    UseCase,
    UserStory,
)


def _req() -> RequirementSpec:
    return RequirementSpec(
        stories=[UserStory(id="US-01", acceptance=[AcceptanceCriterion(id="AC-01")])],
        nfrs=[NFR(id="NFR-01", category=ISO25010.RELIABILITY, metric="0% oversell")],
    )


def _flow_ctx(*, traces: bool = True, policy_evt: str = "EVT-01", policy_cmd: str = "CMD-01"):
    tr = ["AC-01"] if traces else []
    return TechSpec(
        bounded_context="Order", summary="order",
        commands=[Command(id="CMD-01", name="Place order", aggregate="Order", traces_to=tr)],
        events=[DomainEvent(id="EVT-01", name="Order placed", aggregate="Order", traces_to=tr)],
        policies=[Policy(id="POL-01", rule="When EVT-01 then CMD-01",
                         when_event=policy_evt, then_command=policy_cmd, traces_to=tr)],
        read_models=[ReadModel(id="RM-01", name="My orders", source_events=["EVT-01"],
                               serves="orders screen", traces_to=tr)],
    )


def _has(issues, *needles):
    return any(all(n in i for n in needles) for i in issues)


# --- T4 event-flow consistency ------------------------------------------------

def test_clean_event_flow_has_no_findings() -> None:
    design = DesignSpec(summary="s", tech_specs=[_flow_ctx()])
    assert lint_event_flow(design, _req()) == []


def test_t4_policy_references_undeclared_event() -> None:
    design = DesignSpec(summary="s", tech_specs=[_flow_ctx(policy_evt="EVT-99")])
    assert _has(lint_event_flow(design, _req()), "T4", "POL-01", "EVT-99")


def test_t4_policy_references_undeclared_command() -> None:
    design = DesignSpec(summary="s", tech_specs=[_flow_ctx(policy_cmd="CMD-99")])
    assert _has(lint_event_flow(design, _req()), "T4", "POL-01", "CMD-99")


def test_t4c_flow_element_without_traces_is_advised() -> None:
    design = DesignSpec(summary="s", tech_specs=[_flow_ctx(traces=False)])
    issues = lint_event_flow(design, _req())
    assert _has(issues, "T4", "CMD-01") and _has(issues, "T4", "EVT-01")


def test_t4c_skipped_without_req_spec_but_consistency_still_runs() -> None:
    # no req_spec → no traces_to advisory, but the undeclared-event check still fires
    design = DesignSpec(summary="s", tech_specs=[_flow_ctx(traces=False, policy_evt="EVT-99")])
    issues = lint_event_flow(design)  # req_spec defaults None
    assert _has(issues, "T4", "EVT-99")
    assert not _has(issues, "T4", "CMD-01", "traces")


def test_empty_event_flow_is_clean() -> None:
    design = DesignSpec(summary="s", tech_specs=[TechSpec(bounded_context="Order", summary="s")])
    assert lint_event_flow(design, _req()) == []


# --- renderers ----------------------------------------------------------------

def test_render_tech_spec_includes_event_flow_when_present() -> None:
    doc = render_tech_spec(_flow_ctx())
    assert "5.1 Event flow" in doc
    for token in ("CMD-01", "EVT-01", "POL-01", "RM-01", "Order placed", "My orders"):
        assert token in doc


def test_render_tech_spec_omits_event_flow_when_empty() -> None:
    doc = render_tech_spec(TechSpec(bounded_context="Order", summary="plain CRUD"))
    assert "5.1 Event flow" not in doc


def test_render_ad_includes_glossary_and_use_cases() -> None:
    design = DesignSpec(
        summary="s",
        glossary=[GlossaryTerm(id="GL-01", term="Order", definition="confirmed purchase",
                               bounded_context="Order", aliases_to_avoid=["cart"])],
        use_cases=[UseCase(id="UC-01", name="Place order", primary_actor="customer",
                           main_flow=["select items", "confirm"], traces_to=["US-01"])],
    )
    doc = render_ad(design, "req prose")
    assert "Ubiquitous Language" in doc and "GL-01" in doc and "Order" in doc
    assert "Use Cases" in doc and "UC-01" in doc and "from US-01" in doc


def test_render_ad_omits_b1_sections_when_empty() -> None:
    doc = render_ad(DesignSpec(summary="s"), "req prose")
    assert "Ubiquitous Language" not in doc and "## Use Cases" not in doc
