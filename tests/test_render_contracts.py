"""render_contracts digest — fed to the Reviewer AND to the Designer on a design-heal
revise. It must name every droppable element (event flow, integration, test traces,
system-level relationships/sagas) so a revise pass does not silently forget them."""

from __future__ import annotations

from aicoder.application.design_lint import render_contracts
from aicoder.domain.models import (
    ApiSpec,
    Command,
    ContextRelationship,
    ContextRelationshipKind,
    DesignSpec,
    DomainEvent,
    EventSchema,
    GlossaryTerm,
    Policy,
    ProposedTest,
    ReadModel,
    SagaSpec,
    SagaStep,
    TechSpec,
    UseCase,
)


def test_digest_names_every_droppable_element() -> None:
    ts = TechSpec(
        bounded_context="Order", summary="s",
        interface_changes=["interface OrderPort { void place() }"],
        commands=[Command(id="CMD-01", name="Place order", traces_to=["AC-01"])],
        events=[DomainEvent(id="EVT-01", name="Order placed")],
        policies=[Policy(id="POL-01", when_event="EVT-01", then_command="CMD-02")],
        read_models=[ReadModel(id="RM-01", name="My orders")],
        apis=[ApiSpec(id="API-01", method="POST", path="/v1/orders")],
        event_schemas=[EventSchema(id="EVS-01", event_name="order.created.v1",
                                   consumers=["Billing"])],
        test_plan=[ProposedTest(id="TC-ORD-01", title="happy", path="x.java",
                                content="class X {}", traces_to=["AC-01"])],
    )
    design = DesignSpec(
        summary="s", tech_specs=[ts],
        relationships=[ContextRelationship(
            id="REL-01", upstream="Order", downstream="Billing",
            kind=ContextRelationshipKind.ANTI_CORRUPTION_LAYER, mechanism="sync (REST)")],
        sagas=[SagaSpec(id="SAGA-01", name="Complete", steps=[SagaStep()])],
        glossary=[GlossaryTerm(id="GL-01", term="Order", bounded_context="Order")],
        use_cases=[UseCase(id="UC-01", name="Place order", traces_to=["US-01"])],
    )
    out = render_contracts(design)
    for token in ("## System", "REL-01", "SAGA-01", "GL-01", "UC-01",
                  "CMD-01", "EVT-01", "POL-01", "RM-01", "API-01", "EVS-01",
                  "TC-ORD-01", "→ AC-01"):
        assert token in out, token
    assert "class X {}" not in out          # test BODIES stay out (token-cheap digest)


def test_minimal_design_has_no_system_block() -> None:
    design = DesignSpec(summary="s", tech_specs=[
        TechSpec(bounded_context="Order", summary="s", interface_changes=["x()"])])
    out = render_contracts(design)
    assert "## System" not in out and "## Order" in out
