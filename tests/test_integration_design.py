"""Slice D — integration design (B3 typed Context Map + B5 API/EVS/SAGA). Models, the
advisory boundary-smell linter (T5), and the renderers. Pure functions, hermetic."""

from __future__ import annotations

from aicoder.application.design_lint import lint_integration
from aicoder.application.design_docs import render_ad, render_tech_spec
from aicoder.domain.models import (
    ApiSpec,
    ContextRelationship,
    ContextRelationshipKind,
    DesignSpec,
    EventSchema,
    SagaSpec,
    SagaStep,
    TechSpec,
)


def _has(issues, *needles):
    return any(all(n in i for n in needles) for i in issues)


def _saga(n_steps: int, sid: str = "SAGA-01") -> SagaSpec:
    steps = [SagaStep(service=f"svc{i}", action="do", success_event="ok", compensation="undo")
             for i in range(n_steps)]
    return SagaSpec(id=sid, name="checkout", trigger="EVS-01", steps=steps)


def _rel(rid: str, mechanism: str) -> ContextRelationship:
    return ContextRelationship(id=rid, upstream="A", downstream="B",
                               kind=ContextRelationshipKind.CUSTOMER_SUPPLIER, mechanism=mechanism)


# --- T5 boundary smell --------------------------------------------------------

def test_t5_flags_long_saga() -> None:
    design = DesignSpec(summary="s", sagas=[_saga(6)])
    assert _has(lint_integration(design), "T5", "SAGA-01", "6 steps")


def test_t5_short_saga_is_clean() -> None:
    design = DesignSpec(summary="s", sagas=[_saga(3)])
    assert lint_integration(design) == []


def test_t5_flags_too_many_sync_relationships() -> None:
    design = DesignSpec(summary="s", relationships=[
        _rel("REL-01", "sync (REST)"), _rel("REL-02", "sync (gRPC)"),
        _rel("REL-03", "sync (REST)"), _rel("REL-04", "sync (REST)"),
    ])
    assert _has(lint_integration(design), "T5", "synchronous")


def test_t5_async_relationships_do_not_trip() -> None:
    design = DesignSpec(summary="s", relationships=[
        _rel("REL-01", "async (event)"), _rel("REL-02", "async (event)"),
        _rel("REL-03", "async (event)"), _rel("REL-04", "async (event)"),
    ])
    assert lint_integration(design) == []


def test_no_integration_modeled_is_clean() -> None:
    assert lint_integration(DesignSpec(summary="s")) == []


# --- renderers ----------------------------------------------------------------

def test_render_ad_includes_relationships_and_sagas() -> None:
    design = DesignSpec(
        summary="s",
        relationships=[ContextRelationship(
            id="REL-01", upstream="Order", downstream="Billing",
            kind=ContextRelationshipKind.ANTI_CORRUPTION_LAYER, mechanism="sync (REST)")],
        sagas=[SagaSpec(id="SAGA-01", name="Complete order", trigger="EVS-order.created",
                        kind="Orchestration",
                        steps=[SagaStep(service="Inventory", action="Reserve stock",
                                        success_event="stock.reserved", compensation="Release stock")])],
    )
    doc = render_ad(design, "req prose")
    assert "Context relationships" in doc and "REL-01" in doc and "Anti-Corruption Layer" in doc
    assert "Sagas / Process Managers" in doc and "SAGA-01" in doc
    assert "Release stock" in doc                 # compensation column rendered


def test_render_ad_omits_integration_when_empty() -> None:
    doc = render_ad(DesignSpec(summary="s"), "req prose")
    assert "Context relationships" not in doc and "Sagas / Process Managers" not in doc


def test_render_tech_spec_includes_api_and_event_contracts() -> None:
    ts = TechSpec(
        bounded_context="Order", summary="order",
        apis=[ApiSpec(id="API-01", method="POST", path="/v1/orders", summary="create",
                      auth="Bearer", idempotency="Idempotency-Key", traces_to=["CMD-01"])],
        event_schemas=[EventSchema(id="EVS-01", event_name="order.created.v1",
                                   consumers=["Billing"], channel="orders",
                                   versioning=".vN", reliability="retry→DLQ", traces_to=["EVT-01"])],
    )
    doc = render_tech_spec(ts)
    assert "5.2 Integration contracts" in doc
    assert "API-01" in doc and "/v1/orders" in doc
    assert "EVS-01" in doc and "order.created.v1" in doc and "Billing" in doc


def test_render_tech_spec_omits_integration_when_empty() -> None:
    doc = render_tech_spec(TechSpec(bounded_context="Order", summary="internal only"))
    assert "5.2 Integration contracts" not in doc
