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
from aicoder.application.structurizr_lint import validate_structurizr
from aicoder.domain.models import (
    ContextRelationship,
    ContextRelationshipKind,
    DesignSpec,
    EventSchema,
    GlossaryTerm,
    SagaSpec,
    SagaStep,
    TechSpec,
    UseCase,
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


def test_files_include_master_fragments_styles_docs_and_adrs() -> None:
    files = render_structurizr(_SPEC, "req")
    assert workspace_path() in files
    for ts in _SPEC.tech_specs:
        assert context_path(ts) in files
    # the richer A7 set: styles, a README index, embedded docs, and an ADR index
    assert "docs/design/structurizr/styles.dsl" in files
    assert "docs/design/structurizr/README.md" in files
    assert "docs/design/structurizr/documentation/01-introduction.md" in files
    assert "docs/design/structurizr/adr/0000-about-these-adrs.md" in files


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


# A richer, event-driven, multi-context spec exercising every new artifact type.
_RICH = DesignSpec(
    summary="Marketplace escrow payments core",
    goals=["Onboard sellers", "Hold funds in escrow"],
    architecture_style="Hexagonal microservices + events",
    principles=["DB per service"],
    decisions=["Use escrow to protect buyers", "Async settlement via events"],
    context_map="graph LR\n  order --> seller\n  order --> paymentgw",
    glossary=[GlossaryTerm(id="GL-01", term="Escrow", definition="Held funds",
                           bounded_context="Escrow")],
    use_cases=[UseCase(id="UC-01", name="Place order", primary_actor="Buyer",
                       secondary_actors=["Seller", "Payment Gateway"])],
    relationships=[
        ContextRelationship(id="REL-01", upstream="Seller", downstream="Order",
                            kind=ContextRelationshipKind.CUSTOMER_SUPPLIER, mechanism="sync (REST)"),
        ContextRelationship(id="REL-02", upstream="Order", downstream="Escrow",
                            kind=ContextRelationshipKind.CUSTOMER_SUPPLIER, mechanism="async (event)"),
        ContextRelationship(id="REL-03", upstream="Payment Gateway", downstream="Escrow",
                            kind=ContextRelationshipKind.ANTI_CORRUPTION_LAYER, mechanism="sync (HMAC)"),
    ],
    sagas=[SagaSpec(id="SAGA-01", name="Settle order", trigger="Order", kind="Orchestration", steps=[
        SagaStep(service="Order", action="Create pending order", success_event="OrderCreated",
                 compensation="Cancel order"),
        SagaStep(service="Escrow", action="Open escrow", success_event="EscrowOpened",
                 compensation="Refund"),
    ])],
    tech_specs=[
        TechSpec(bounded_context="Seller", summary="Seller onboarding",
                 interface_changes=["interface RegisterSellerUseCase { SellerId register(String e); }",
                                    "interface SellerRepository { void save(Seller s); }"],
                 domain_model="classDiagram\n class Seller { SellerId id }",
                 adrs=["Sellers identified by email"]),
        TechSpec(bounded_context="Order", summary="Place an order",
                 interface_changes=["interface PlaceOrderUseCase { OrderId place(SellerId s); }",
                                    "interface OrderRepository { Order findById(OrderId id); }"],
                 domain_model="classDiagram\n class Order { OrderId id }",
                 event_schemas=[EventSchema(id="EVS-01", event_name="order.created.v1",
                                            consumers=["Escrow"], channel="orders")]),
        TechSpec(bounded_context="Escrow", summary="Escrow settlement",
                 interface_changes=["interface ReleaseEscrowUseCase { void release(EscrowId id); }",
                                    "interface EscrowRepository { void save(Escrow e); }",
                                    "interface PaymentGateway { void charge(); }"],
                 domain_model="classDiagram\n class Escrow { EscrowId id }"),
    ],
)


def test_generated_set_passes_the_self_validator() -> None:
    # The strongest regression guard: a correct generator emits a structurally sound set.
    assert validate_structurizr(render_structurizr(_RICH, "req", with_ci=True)) == []
    assert validate_structurizr(render_structurizr(_SPEC, "req")) == []


def test_styles_emitted_and_included_last_in_views() -> None:
    files = render_structurizr(_RICH, "req")
    styles = files["docs/design/structurizr/styles.dsl"]
    assert 'element "Database"' in styles and 'element "Person"' in styles
    ws = files[workspace_path()]
    assert "!include styles.dsl" in ws


def test_db_per_service_only_with_a_persistence_port() -> None:
    ws = render_workspace_dsl(_RICH, "req")
    # Seller/Order/Escrow all have *Repository ports -> a DB container + ownership edge each
    for cid in ("seller", "order", "escrow"):
        assert f'{cid}_db = container ' in ws
        assert re.search(rf"{cid}_\w+ -> {cid}_db ", ws)
    # the Escrow PaymentGateway is a remote call, not a datastore — no DB edge from it
    assert "paymentgateway -> escrow_db" not in ws.lower()


def test_actors_and_externals_are_modeled() -> None:
    ws = render_workspace_dsl(_RICH, "req")
    assert 'actor_buyer = person "Buyer"' in ws         # a real person from a use case
    assert "actor_payment_gateway" not in ws            # "...Gateway" filtered as non-person
    assert re.search(r'ext_payment_gateway = softwareSystem ".*" "" "External"', ws)


def test_saga_dynamic_views_happy_path_and_compensation() -> None:
    ws = render_workspace_dsl(_RICH, "req")
    assert 'dynamic system "SettleOrder"' in ws
    assert 'dynamic system "SettleOrderCompensation"' in ws
    # happy path: order -> escrow labeled with the escrow step + its success event;
    # compensation reversed: escrow -> order with the undo action
    assert re.search(r'order -> escrow "1\..*EscrowOpened"', ws)
    assert re.search(r'escrow -> order "Undo: Refund"', ws)


def test_every_doc_embed_resolves_to_a_view_key() -> None:
    files = render_structurizr(_RICH, "req")
    ws = files[workspace_path()]
    view_keys = set(re.findall(r'(?:systemContext|container|component|dynamic) \S+ "([^"]+)"', ws))
    embeds = set()
    for path, content in files.items():
        if path.endswith(".md"):
            embeds |= set(re.findall(r"embed:([A-Za-z0-9_\-]+)", content))
    assert embeds and embeds <= view_keys


def test_adr_dir_contains_only_numbered_files_no_readme() -> None:
    files = render_structurizr(_RICH, "req")
    adr = [p.split("/")[-1] for p in files if "/adr/" in p]
    assert "0000-about-these-adrs.md" in adr
    assert all(re.match(r"^\d{4}-.*\.md$", n) for n in adr)
    assert "README.md" not in adr  # a README would break !adrs


def test_ci_workflow_pins_a_dated_tag_not_latest() -> None:
    files = render_structurizr(_RICH, "req", with_ci=True)
    wf = files[".github/workflows/aac.yml"]
    assert "structurizr/cli:2025.11.09" in wf
    assert "structurizr/cli:latest" not in wf


def test_single_context_crud_degrades_cleanly() -> None:
    spec = DesignSpec(summary="Add a health endpoint", tech_specs=[
        TechSpec(bounded_context="Ops", summary="health check",
                 interface_changes=["interface HealthUseCase { String ping(); }"], domain_model=""),
    ])
    files = render_structurizr(spec, "req")
    ws = files[workspace_path()]
    assert "dynamic system" not in ws         # no sagas
    assert "ops_db" not in ws                  # no persistence port -> no DB
    assert validate_structurizr(files) == []   # still a sound one-container workspace
