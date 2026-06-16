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


# --------------------------------------------------------------------------- #
# L5–L7: oracle & traceability quality (separate from code-build consistency)
# --------------------------------------------------------------------------- #

def _domain_case(id_: str, path: str = "", content: str = "x") -> dict:
    return {"id": id_, "title": id_, "kind": "domain",
            "spec": "given x when y then z", "path": path,
            "content": content if path else ""}


# A clean two-context design: arrows follow ownership, each context owns its own cases,
# every domain case ships an executable oracle. Must lint clean (false-positive guard).
_CLEAN_MULTI = {
    "summary": "Lending borrows Catalog copies.",
    "decisions": ["Catalog owns Copy via a shared kernel; Lending references it."],
    "context_map": "graph TD\n  Lending -->|uses| Catalog",
    "tech_specs": [
        {
            "bounded_context": "Catalog", "summary": "Copies.",
            "affected": ["src/main/java/lib/catalog/Copy.java"],
            "domain_model": "classDiagram\n class Copy { +borrow() }",
            "test_plan": [_domain_case(
                "TC-CAT-01", "src/test/java/lib/catalog/CopyTest.java")],
        },
        {
            "bounded_context": "Lending", "summary": "Loans use Copy.",
            "affected": ["src/main/java/lib/lending/Loan.java"],
            "interface_changes": ["interface LendingService { Loan borrow(UUID copyId); }"],
            # references Copy (owned by Catalog) without re-declaring it
            "domain_model": "classDiagram\n class Loan { +copyId }\n Loan ..> Copy : borrows",
            "test_plan": [_domain_case(
                "TC-LEN-01", "src/test/java/lib/lending/LoanTest.java")],
        },
    ],
}


def test_clean_multicontext_lints_clean() -> None:
    assert _issues(_CLEAN_MULTI) == []


def test_l5_flags_case_filed_under_wrong_context_by_path() -> None:
    spec = {
        "summary": "x", "decisions": ["shared kernel"],
        "tech_specs": [
            {"bounded_context": "Catalog", "summary": "c",
             "affected": ["catalog/Copy.java"],
             "test_plan": [
                 _domain_case("TC-CAT-01", "src/test/java/lib/catalog/CopyTest.java"),
                 # a Membership case dumped into the Catalog test_plan
                 _domain_case("TC-MEM-01", "src/test/java/lib/membership/MemberTest.java"),
             ]},
            {"bounded_context": "Membership", "summary": "m",
             "affected": ["membership/Member.java"],
             "test_plan": [_domain_case(
                 "TC-MEM-02", "src/test/java/lib/membership/MemberStatusTest.java")]},
        ],
    }
    found = _issues(spec)
    assert any(i.startswith("L5") and "TC-MEM-01" in i and "Membership" in i for i in found)
    # the correctly-filed cases are not flagged
    assert not any(i.startswith("L5") and "TC-CAT-01" in i for i in found)
    assert not any(i.startswith("L5") and "TC-MEM-02" in i for i in found)


def test_l5_flags_by_tc_code_when_no_path() -> None:
    spec = {
        "summary": "x", "decisions": ["shared kernel"],
        "tech_specs": [
            {"bounded_context": "Catalog", "summary": "c",
             "affected": ["catalog/Copy.java"],
             "test_plan": [{"id": "TC-LEN-09", "kind": "domain",
                            "spec": "s", "path": "", "content": ""}]},
            {"bounded_context": "Lending", "summary": "l",
             "affected": ["lending/Loan.java"], "test_plan": []},
        ],
    }
    assert any(i.startswith("L5") and "TC-LEN-09" in i and "Lending" in i
               for i in _issues(spec))


def test_l6a_flags_domain_case_without_executable_oracle() -> None:
    spec = {
        "summary": "x", "decisions": ["shared kernel"],
        "tech_specs": [{"bounded_context": "Catalog", "summary": "c",
                        "affected": ["catalog/Copy.java"],
                        "test_plan": [_domain_case("TC-CAT-01")]}],  # no path/content
    }
    assert any(i.startswith("L6") and "TC-CAT-01" in i for i in _issues(spec))


def test_l6a_not_flagged_for_spec_only_fitness_case() -> None:
    spec = {
        "summary": "x", "decisions": ["shared kernel"],
        "tech_specs": [{"bounded_context": "Catalog", "summary": "c",
                        "affected": ["catalog/Copy.java"],
                        "test_plan": [{"id": "TC-FIT-01", "kind": "fitness",
                                       "spec": "domain must not import adapters",
                                       "path": "", "content": ""}]}],
    }
    assert not any(i.startswith("L6") for i in _issues(spec))


def test_l6b_flags_context_with_empty_test_plan() -> None:
    spec = {
        "summary": "x", "decisions": ["shared kernel"],
        "tech_specs": [
            {"bounded_context": "Catalog", "summary": "c",
             "affected": ["catalog/Copy.java"],
             "test_plan": [_domain_case(
                 "TC-CAT-01", "src/test/java/lib/catalog/CopyTest.java")]},
            {"bounded_context": "Lending", "summary": "l",
             "affected": ["lending/Loan.java"], "test_plan": []},  # empty
        ],
    }
    found = _issues(spec)
    assert any(i.startswith("L6") and "Lending" in i and "empty test_plan" in i
               for i in found)
    assert not any(i.startswith("L6") and "Catalog" in i and "empty" in i for i in found)


def test_l7_flags_inverted_context_map_arrow() -> None:
    spec = {
        "summary": "x", "decisions": ["Catalog owns Copy (shared kernel)."],
        # WRONG: drawn Catalog --> Lending, but Lending is the one that uses Copy
        "context_map": "graph TD\n  Catalog -->|uses| Lending",
        "tech_specs": [
            {"bounded_context": "Catalog", "summary": "c",
             "affected": ["catalog/Copy.java"],
             "domain_model": "classDiagram\n class Copy"},
            {"bounded_context": "Lending", "summary": "l",
             "affected": ["lending/Loan.java"],
             "domain_model": "classDiagram\n class Loan\n Loan --> Copy : borrows"},
        ],
    }
    assert any(i.startswith("L7") and "Catalog --> Lending" in i for i in _issues(spec))


def test_l7_not_flagged_when_arrow_follows_dependency() -> None:
    # _CLEAN_MULTI draws Lending --> Catalog (correct) → no L7
    assert not any(i.startswith("L7") for i in _issues(_CLEAN_MULTI))


# L8 — locked test invokes an operation the design never declares.
_L8_BASE = {
    "summary": "x", "decisions": ["shared kernel"],
    "tech_specs": [{
        "bounded_context": "Lending", "summary": "l",
        "affected": ["lending/Loan.java"],
        "interface_changes": ["interface BorrowService { Loan borrow(UUID copyId); }"],
        "domain_model": "classDiagram\n class Loan { +borrow() }",
        "key_flows": "sequenceDiagram\n  Repo->>Svc: save(loan)",
    }],
}


def _with_test(content: str) -> dict:
    spec = {**_L8_BASE}
    spec["tech_specs"] = [{**_L8_BASE["tech_specs"][0], "test_plan": [
        {"id": "TC-LEN-01", "kind": "domain", "spec": "s",
         "path": "src/test/java/lib/lending/LoanTest.java", "content": content}]}]
    return spec


def test_l8_flags_undeclared_method_called_by_oracle() -> None:
    # `findAllCopies` is declared nowhere → flag; `borrow` and `save` are published.
    content = (
        "var loan = service.borrow(copyId);\n"
        "var copies = bookRepo.findAllCopies();\n"
    )
    found = _issues(_with_test(content))
    assert any(i.startswith("L8") and "findAllCopies" in i for i in found)
    assert not any(i.startswith("L8") and "borrow" in i for i in found)


def test_l8_ignores_getters_asserts_and_jdk_calls() -> None:
    # getStatus (getter), assertEquals (static, no receiver), Clock.fixed / Instant.parse
    # / plusDays (JDK), List.get — none are design operations → no L8 noise.
    content = (
        "var c = Clock.fixed(Instant.parse(\"2024-01-01T10:00:00Z\"), ZoneOffset.UTC);\n"
        "assertEquals(CopyStatus.AVAILABLE, copy.getStatus());\n"
        "var due = loanDate.plusDays(14);\n"
        "var first = repo.findAll().get(0);\n"  # findAll is undeclared → the ONLY flag
        "service.borrow(copyId);\n"
    )
    found = [i for i in _issues(_with_test(content)) if i.startswith("L8")]
    assert any("findAll(" in i for i in found)
    assert not any("getStatus" in i or "fixed" in i or "parse" in i
                   or "plusDays" in i or "assertEquals" in i for i in found)


def test_l8_clean_when_oracle_uses_only_published_api() -> None:
    content = "var loan = service.borrow(copyId);\nrepo.save(loan);\n"
    assert not any(i.startswith("L8") for i in _issues(_with_test(content)))


def test_l8_ignores_static_type_calls_and_record_accessors() -> None:
    # the false positives a real run surfaced: UUID.randomUUID() (static factory),
    # copy.status()/member.email() (zero-arg record accessors), rate.multiply(n)
    # (BigDecimal arithmetic) — none are undeclared DOMAIN operations.
    content = (
        "var id = UUID.randomUUID();\n"
        "assertEquals(Status.AVAILABLE, copy.status());\n"
        "assertEquals(\"a@b.c\", member.email());\n"
        "var total = rate.multiply(nights);\n"
        "service.borrow(copyId);\n"  # declared in _L8_BASE api → also clean
    )
    found = [i for i in _issues(_with_test(content)) if i.startswith("L8")]
    assert found == [], f"expected no L8 false positives, got: {found}"


def test_l8_keeps_zero_arg_repository_finder() -> None:
    # a zero-arg call is usually an accessor, EXCEPT finder-verb repo ops like findAll()
    content = "var all = repo.findAll();\nservice.borrow(copyId);\n"
    assert any(i.startswith("L8") and "findAll" in i
               for i in _issues(_with_test(content)))
