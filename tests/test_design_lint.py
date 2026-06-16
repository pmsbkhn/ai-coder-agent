"""Deterministic design linter (no LLM) — cross-document contract consistency.

Reproduces the multi-bounded-context self-inconsistencies that produced HEALING_FAILED
on the Digital Library e2e run and asserts the linter flags each class:
L1 undeclared method called in a flow, L2 conflicting arity, L3 cross-context type
ownership, L4 status-enum suffix drift. A consistent design must lint clean."""

from __future__ import annotations

from aicoder.application.design_lint import lint_design, render_contracts
from aicoder.domain.models import DesignSpec

# A Catalog + Lending design carrying every flaw the real run had.
_INCONSISTENT = {
    "summary": "Lending coordinates Catalog copies.",
    "decisions": [],
    "tech_specs": [
        {
            "bounded_context": "Catalog",
            "summary": "Titles and copies.",
            "affected": [
                "src/main/java/lib/catalog/Copy.java",
                "src/main/java/lib/catalog/CopyStatus.java",
                "src/main/java/lib/catalog/CatalogService.java",
            ],
            "interface_changes": [
                "interface CatalogService { Copy createCopy(String titleId); "
                "Optional<Copy> findCopy(UUID copyId); }"
            ],
        },
        {
            "bounded_context": "Lending",
            "summary": "Loans.",
            "affected": [
                "src/main/java/lib/lending/Loan.java",
                "src/main/java/lib/lending/LoanState.java",
                "src/main/java/lib/lending/LendingService.java",
            ],
            "interface_changes": [
                "interface LendingService { "
                "Loan createLoan(UUID memberId, UUID copyId, LocalDate loanDate); "
                "boolean isOverdue(UUID loanId, LocalDate currentDate); "
                # Lending wrongly re-declares Catalog's findCopy with a different arity
                "Optional<Copy> findCopy(UUID copyId, boolean includeLost); }"
            ],
            "domain_model": "classDiagram\n class Loan {\n  +isOverdue(LocalDate):boolean\n }",
            "key_flows": (
                "sequenceDiagram\n"
                "  LendingService->>CatalogService: findCopy(copyId)\n"
                "  LoanAggregate->>CatalogService: setCopyStatus(ON_LOAN)\n"
                "  CatalogService-->>LendingService: Copy(AVAILABLE)"
            ),
        },
    ],
}

_CLEAN = {
    "summary": "Add a nullable note to Order and thread it to OrderPlaced.",
    "decisions": ["Keep the 2-arg placeOrder working via an overload."],
    "tech_specs": [{
        "bounded_context": "Orders",
        "summary": "Order carries an optional note.",
        "affected": ["src/main/java/shop/orders/Order.java",
                     "src/main/java/shop/orders/OrderPlaced.java"],
        "interface_changes": ["interface OrderService { void placeOrder(UUID customer, Money amount, String note); }"],
        "domain_model": "classDiagram\n class Order {\n +placeOrder(Money, String)\n }",
        "key_flows": "sequenceDiagram\n  Client->>OrderService: placeOrder(c, amount, note)",
    }],
}


def _issues(design: dict) -> list[str]:
    return lint_design(DesignSpec.model_validate(design))


def test_clean_design_lints_clean() -> None:
    assert _issues(_CLEAN) == []


def test_l1_flags_method_called_in_flow_but_undeclared() -> None:
    found = _issues(_INCONSISTENT)
    assert any(i.startswith("L1") and "setCopyStatus" in i for i in found)
    # findCopy IS declared on CatalogService → not flagged
    assert not any("L1" in i and "findCopy" in i for i in found)


def test_l2_flags_conflicting_arity_across_interfaces() -> None:
    # findCopy: arity 1 on CatalogService, arity 2 on LendingService — contracts clash
    assert any(i.startswith("L2") and "findCopy" in i for i in _issues(_INCONSISTENT))


def test_l2_ignores_service_vs_aggregate_arity_split() -> None:
    # the clean design's placeOrder is 3-arg on the service, 2-arg on the aggregate —
    # a normal wrapper, NOT a clash; must not be flagged (false-positive guard)
    assert not any(i.startswith("L2") for i in _issues(_CLEAN))


def test_l3b_flags_cross_context_type_without_shared_kernel() -> None:
    found = _issues(_INCONSISTENT)
    assert any(i.startswith("L3") and "Copy" in i and "Lending" in i for i in found)
    # a service call target across contexts is expected orchestration, not flagged
    assert not any("CatalogService" in i and i.startswith("L3") for i in found)


def test_l3b_suppressed_when_shared_kernel_declared() -> None:
    spec = {**_INCONSISTENT, "decisions": ["Define a shared kernel for Copy / CopyStatus."]}
    found = _issues(spec)
    assert not any(i.startswith("L3") and "references type" in i for i in found)
    # the other findings still stand
    assert any(i.startswith("L1") for i in found)
    assert any(i.startswith("L2") for i in found)


def test_l3a_flags_type_owned_by_two_contexts() -> None:
    dup = {
        "summary": "x", "decisions": ["shared kernel exists"],  # silence L3b
        "tech_specs": [
            {"bounded_context": "Catalog", "summary": "c",
             "affected": ["catalog/Copy.java"]},
            {"bounded_context": "Lending", "summary": "l",
             "affected": ["lending/Copy.java"]},
        ],
    }
    assert any(i.startswith("L3") and "Copy" in i and "multiple contexts" in i
               for i in _issues(dup))


def test_l4_flags_status_enum_suffix_drift() -> None:
    # CopyStatus + CopyStatus vs LoanState
    assert any(i.startswith("L4") for i in _issues(_INCONSISTENT))


def test_render_contracts_includes_interfaces_and_flows() -> None:
    out = render_contracts(DesignSpec.model_validate(_INCONSISTENT))
    assert "## Catalog" in out and "## Lending" in out
    assert "CatalogService" in out and "isOverdue" in out
    assert "Key flows:" in out and "setCopyStatus" in out
