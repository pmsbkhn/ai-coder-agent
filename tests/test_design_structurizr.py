"""Structurizr DSL renderer (Architecture-as-Code) — pure functions over a DesignSpec:
a master workspace.dsl (≈ AD) + one fragment per bounded context (≈ Tech Spec)."""

from __future__ import annotations

import re

from aicoder.application.design_structurizr import (
    context_path,
    render_context_dsl,
    render_structurizr,
    render_workspace_dsl,
    workspace_path,
)
from aicoder.domain.models import (
    ContextRelationship,
    ContextRelationshipKind,
    DesignSpec,
    TechSpec,
)

_SPEC = DesignSpec(
    summary="Marketplace escrow payments core",
    context_map="graph LR\n  order --> seller",
    relationships=[
        ContextRelationship(id="REL-01", upstream="Seller", downstream="Order",
                            kind=ContextRelationshipKind.CUSTOMER_SUPPLIER, mechanism="sync (lookup)"),
        ContextRelationship(id="REL-02", upstream="Order", downstream="Escrow",
                            kind=ContextRelationshipKind.CUSTOMER_SUPPLIER, mechanism="async (event)"),
    ],
    tech_specs=[
        TechSpec(bounded_context="Seller", summary="Seller onboarding",
                 interface_changes=["interface RegisterSellerUseCase { SellerId register(String e); }",
                                    "interface SellerRepository { void save(Seller s); }"],
                 domain_model="classDiagram\n class Seller { SellerId id }"),
        TechSpec(bounded_context="Order", summary="Place an order",
                 interface_changes=["interface PlaceOrderUseCase { OrderId place(SellerId s); }",
                                    "interface OrderRepository { Order findById(OrderId id); }"],
                 domain_model="classDiagram\n class Order { OrderId id }"),
        TechSpec(bounded_context="Escrow", summary="Escrow settlement",
                 interface_changes=["interface ReleaseEscrowUseCase { void release(EscrowId id); }",
                                    "interface EscrowRepository { void save(Escrow e); }"],
                 domain_model="classDiagram\n class Escrow { EscrowId id; void release() }"),
    ],
)


def test_files_are_master_plus_one_fragment_per_context() -> None:
    files = render_structurizr(_SPEC, "req")
    assert workspace_path() in files
    for ts in _SPEC.tech_specs:
        assert context_path(ts) in files
    assert len(files) == 1 + len(_SPEC.tech_specs)


def test_workspace_has_system_containers_and_includes() -> None:
    dsl = render_workspace_dsl(_SPEC, "req")
    assert dsl.startswith("workspace ")
    assert "softwareSystem" in dsl
    # one container per bounded context, each including its fragment
    for cid in ("seller", "order", "escrow"):
        assert f'{cid} = container ' in dsl
        assert f"!include {cid}.dsl" in dsl
        assert f"component {cid} " in dsl          # a component view per context
    assert "systemContext system" in dsl and "container system" in dsl


def test_relationship_edges_point_downstream_to_upstream() -> None:
    dsl = render_workspace_dsl(_SPEC, "req")
    # downstream depends on upstream: Order -> Seller, Escrow -> Order
    assert re.search(r"\border\s*->\s*seller\b", dsl)
    assert re.search(r"\bescrow\s*->\s*order\b", dsl)


def test_component_ids_are_namespaced_and_never_clash_with_containers() -> None:
    # the Escrow aggregate must NOT take the `escrow` id (that is the container) —
    # global Structurizr identifiers would collide. It is namespaced `escrow_escrow`.
    frag = render_context_dsl(_SPEC.tech_specs[2])  # Escrow
    assert "escrow_escrow = component" in frag
    assert "\nescrow = component" not in frag and not frag.startswith("escrow = component")
    # every component id in a fragment is prefixed by its container id
    comp_ids = re.findall(r"^([a-z][\w]*) = component", frag, re.MULTILINE)
    assert comp_ids and all(cid.startswith("escrow_") for cid in comp_ids)


def test_fragment_classifies_ports_and_links_them() -> None:
    frag = render_context_dsl(_SPEC.tech_specs[0])  # Seller
    assert '"port.in"' in frag and '"port.out"' in frag and '"domain"' in frag
    assert "-> " in frag  # at least one intra-context relationship


def test_falls_back_to_context_map_when_no_relationships() -> None:
    spec = _SPEC.model_copy(update={"relationships": []})
    dsl = render_workspace_dsl(spec, "req")
    assert re.search(r"\border\s*->\s*seller\b", dsl)  # from the context_map edge
