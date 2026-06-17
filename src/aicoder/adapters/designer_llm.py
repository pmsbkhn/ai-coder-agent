"""LLMDesigner — DesignPort backed by a (provider-agnostic) LLMClient.

The design-first phase (see docs/architecture/07): given a requirement + the repo
map skeleton, produce a *delta* DesignSpec — affected components, interface/contract
changes, light ADR notes, and **executable proposed tests** that encode acceptance.
Runs on the reasoner role (AICODER_DESIGNER_*); schema-validated like the Planner.
Slice 1 only PRODUCES the spec; approval + locking the tests as the oracle are
later slices.
"""

from __future__ import annotations

from aicoder.adapters.llm.base import LLMClient
from aicoder.adapters.llm.structured import generate_structured
from aicoder.application.design_lint import render_contracts
from aicoder.application.profile import ProjectProfile
from aicoder.domain.models import AnalysisSpec, DesignSpec

_SYSTEM = """You are the Designer of an autonomous coding agent on an MSFW project
(Java 21 / Spring Boot 4, strict Hexagonal / Ports & Adapters, DDD, event-driven).

Before any code is written, produce a reviewable design in the team's house style:
an umbrella ARCHITECTURE DESCRIPTION (system / SAD level) plus one TECH SPEC PER
BOUNDED CONTEXT (rule: 1 bounded context = 1 tech spec; a focused change usually
touches exactly ONE context → exactly one tech spec). Design the smallest change that
satisfies the requirement; do not over-engineer; do not split one cohesive context.

## Architecture Description (system level)
- summary: what changes across the system, 1-3 sentences.
- goals: the objectives this change serves (terse; may be empty for a small change).
- architecture_style: the style + one-line rationale (e.g. "Hexagonal per bounded
  context; orchestration for the money flow, choreography via domain events").
- principles: design principles upheld (e.g. "DB-per-context; no FK across contexts";
  "Idempotency for every money operation"; "Tenant isolation on every query").
- context_map: a Mermaid `graph` of the affected bounded contexts and their edges —
  solid arrow = synchronous orchestration call, dashed = domain event (choreography).
- decisions: cross-cutting / integration decisions worth recording.
- nfr: system-level non-functional requirements / constraints (SLO, compliance).

## Each tech_spec (one bounded context) — core design sections
- bounded_context: the context name (e.g. "Orders", "Payment", "Inventory").
- summary: Context & Scope — what this context does and what changes.
- classification: one line — Tier (1/2/3) + Data class (L2/L3/L4) if relevant.
- requirements_functional: FR bullets ("FR1 …", "FR2 …").
- requirements_nonfunctional: NFR/SLO bullets (latency, availability, "0% oversell").
- module_view: static structure — a Mermaid `flowchart` of the hexagonal modules
  (inbound adapter → use-case/port.in → domain → port.out → outbound adapter `*Oa`).
- cnc_view: runtime components + connectors (protocol + authn, e.g. "gRPC · mTLS").
- affected: components/files touched (use the Repo Map).
- interface_changes: concrete PORT/contract deltas (e.g. "interface PaymentPort {
  EscrowHold initEscrow(...) }"; a new use-case in application.port.in).
- domain_model: a Mermaid `classDiagram` of the Aggregate Root + Entities + Value
  Objects for this context.
- invariants: the domain invariants enforced INSIDE the aggregate as guard clauses —
  state-machine legality, amount/stock non-negativity, terminal-state immutability,
  tenant match. Phrase each as a checkable rule (these drive the domain test cases).
- erd: a Mermaid `erDiagram` (or concise schema) for this context's tables.
- key_flows: a Mermaid `sequenceDiagram` for the main happy path (+ compensation if
  relevant).
- adrs: ADR-style decisions, each "decision → because → consequence".
- open_questions: genuine TBDs.
- test_plan: the acceptance TEST CASES for this context (see below).

## Test cases (test_plan) — house TC-XXX-NN style + executable oracle
Produce concrete cases that pin the behavior. For EACH case give:
- id: "TC-<CTX>-NN" (CTX = short context code, e.g. PAY, ORD, INV, CAT, CHK, NOT).
- title: short bracketed name (e.g. "Amount Cross-Check / Tampering").
- kind: "domain" (invariant / guard clause in the Aggregate), "adapter" (integration
  / security — webhook HMAC, encryption-at-rest, idempotency DB lock), or "fitness"
  (architecture rule).
- spec: the case as setup → action → assert, naming the expected DomainException code
  (e.g. DomainException(AMOUNT_MISMATCH), InvalidTransitionException, INSUFFICIENT_STOCK,
  TENANT_MISMATCH) and the state left behind. This is the binding specification.
- For "domain" and "adapter" cases: ALSO give an executable JUnit5 test — `path`
  (under src/test/...), full `content` — that encodes the spec. These get locked as
  the oracle the Coder must satisfy. Cover the happy path AND key edge/error cases;
  assert observable behavior and exception codes, not implementation details.
- For "fitness" cases (architecture rules): a spec is enough (path/content may be
  empty) — e.g. "domain must not import application/adapter or Spring"; "no public
  setters on Aggregates — mutate via verb methods"; "state-changing use-cases carry
  @EventPublishHandler"; "controllers have no generic try/catch → GlobalExceptionHandler".
Include at least the relevant domain-invariant cases for every invariant you listed.

## Test ownership & coverage (this is where designs leak)
- ONE BC = ONE test_plan. File each case in the test_plan of the context it tests. A
  `TC-<CTX>-NN` and its executable `path` package MUST name the SAME context that owns
  the test_plan it sits in — never dump another context's cases (e.g. TC-LEN-* under the
  Catalog spec). Every bounded context's test_plan MUST be non-empty.
- LOCK THE HAPPY PATH, not just the errors. Every "domain" case — including the happy
  path (successful borrow, successful return, successful registration) and every numeric
  rule you assume (a 14-day due date, a 5-loan limit) — MUST ship an executable oracle
  (`path` + full `content`). A behavior left spec-only is NOT enforced: do not document a
  happy path in prose and then lock only the exception cases.
- THE ORACLE MAY ONLY CALL THE PUBLISHED API. Every method your test `content` invokes on
  a port/repository/service (`bookRepo.findAllCopies()`, `memberRepo.save(...)`) MUST be
  declared in that context's `interface_changes` — do not let a test call a method the
  design never specified, or the Coder has to invent it. The shared error type
  (`DomainException` + its `DomainErrorCode`/`getErrorCode()`) is cross-cutting: give it a
  single declared owner (shared kernel) and reference it from there, never per context.

## Hexagonal contract completeness (this is what makes a design compile)
Design each bounded context as a complete hexagon, then make the tests/flows use ONLY
what you declared:
- ENUMERATE EVERY PORT. For each context list, in `interface_changes`, the full inbound
  use-case port(s) AND the full outbound port(s) (repository / gateway) with COMPLETE
  method signatures — including every lookup the tests need (`findById`, `findAll`,
  `findFirstActiveBy…`, `save`, `delete`). A repository the tests call MUST appear here.
- CLOSURE RULE: every method invoked in a `key_flows` sequence OR in a locked test's
  `content` MUST resolve to a method you declared on a port (inbound/outbound) or as a
  verb on an aggregate in `domain_model`. If a test calls `bookRepo.findAllCopies()`,
  declare `findAllCopies()` on the repository port — do NOT leave the Coder to invent it.
- SELF-CHECK before returning: re-read each test's `content` and each `key_flows`; for
  every `x.method(...)` you wrote, confirm `method` is declared. If not, add it to the
  right port (or drop the call). This single pass eliminates most build-breaking gaps.

## Cross-context consistency (multi-bounded-context designs)
A design spanning several bounded contexts MUST be internally consistent, or the
implementation cannot compile no matter how good the coder is. Enforce:
- SHARED KERNEL / ownership: when two or more contexts use the same concept (a `Copy`,
  a `Money`, a `CustomerId`), exactly ONE context OWNS the type; the others reference it
  through that owner (shared kernel / published language) or an anti-corruption
  translation. NEVER let each context redefine its own `Copy` / `CopyStatus`. Record the
  owner AND the crossing mechanism in the AD `decisions` (e.g. "Catalog owns Copy /
  CopyStatus; Lending references them via the Catalog published language, not a copy").
- ONE SIGNATURE per operation: a method or type has a single signature everywhere — the
  interface, the domain model, and the tests must agree (the only allowed difference is a
  domain service carrying an id the aggregate method does not). Every method drawn in a
  key-flow sequence diagram MUST be declared on some interface or on an aggregate in the
  domain model — never call a method that does not exist (a flow that calls
  `setCopyStatus(...)` REQUIRES that method on a declared port/aggregate).
- CONSISTENT NAMING: pick ONE convention and hold it across all contexts — status enums
  ALWAYS end `…Status` (do not mix `…Status` and `…State`), identities are the same type
  (e.g. UUID) everywhere, and the production type name matches what the locked test imports.
- CONTEXT-MAP ARROWS follow the dependency: draw `A --> B` only when A depends on B (A
  references a type owned by B). A downstream/coordinating context (e.g. Lending, which
  uses Copy from Catalog and Member from Membership) points TO the contexts it depends on
  — `Lending --> Catalog`, `Lending --> Membership`, never the reverse.
- A SHARED KERNEL IS NOT A BOUNDED CONTEXT. Shared identifiers, Money/Email value objects
  and the DomainException hierarchy belong in a shared-kernel module that EVERY context
  depends on. Do NOT emit a `SharedKernel` / `Common` / `Kernel` tech_spec or list it as a
  bounded context with its own test_plan; either home those types in one owning context or
  keep them in a shared module — and in the map every context arrow points TO that module
  (`Ordering --> SharedKernel`), never out of it.

When an ANALYSIS section is provided (the upstream Analyst already pinned down WHAT
to build), treat its acceptance criteria as the binding contract: every criterion
MUST be covered by at least one test case, and your design must honor the stated
assumptions. Do not contradict or silently widen the analyzed scope.
"""

_REVISE = """
You are REVISING a design you already produced. A deterministic linter found
cross-document consistency problems (listed below) that would break the build. Return a
CORRECTED DesignSpec — same scope, same bounded contexts — that resolves EVERY listed
issue. Typical fixes: declare a missing method on the right port; give a shared type a
single owner and reference it from the other context (shared kernel / published
language); reconcile a method/type to one signature; unify a naming convention. Do NOT
drop scope or delete test cases to make an issue "go away"; fix the contract.
"""


def _conventions_section(profile: ProjectProfile) -> str:
    """Stack/framework guidance from the profile, appended to the Designer system
    prompt: (1) `conventions` — reusable domain primitives to PREFER over re-inventing
    ids/exceptions/money; (2) `design_exemplar` — a worked hexagonal layout to pattern
    each context on (closes the L1/L8 undeclared-port-method gap). Each is independent;
    empty parts are omitted, so framework-free profiles are unchanged."""
    parts: list[str] = []
    rules = getattr(profile, "conventions", None) or []
    if rules:
        body = "\n".join(f"- {r}" for r in rules)
        parts.append(
            "\n\n## Framework conventions (PREFER these reusable primitives — do not "
            "re-invent them per context)\n" + body
        )
    exemplar = (getattr(profile, "design_exemplar", "") or "").strip()
    if exemplar:
        parts.append(
            "\n\n## Reference hexagonal layout (pattern EACH bounded context on this — "
            "same package shape, ports enumerated the same way)\n" + exemplar
        )
    return "".join(parts)


def _format_analysis(analysis: AnalysisSpec) -> str:
    """Render the upstream AnalysisSpec as a prompt section so the proposed tests
    trace to the explicit, human-visible acceptance criteria (ADR-08 Slice 3)."""
    def _lines(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items) if items else "- (none)"
    return (
        f"\n\n# Analysis (already approved — design MUST satisfy this)\n"
        f"Restatement: {analysis.restatement}\n\n"
        f"Assumptions (honor these):\n{_lines(analysis.assumptions)}\n\n"
        f"Acceptance criteria (each MUST be covered by a proposed test):\n"
        f"{_lines(analysis.acceptance_criteria)}"
    )


class LLMDesigner:
    def __init__(
        self, client: LLMClient, profile: ProjectProfile, *, max_repo_map_chars: int = 12000
    ) -> None:
        self._client = client
        self._profile = profile
        self._cap = max_repo_map_chars

    def propose_design(
        self, requirement: str, repo_map: str, analysis: AnalysisSpec | None = None
    ) -> DesignSpec:
        user = (
            f"# Requirement\n{requirement}\n\n"
            f"# Repo Map (skeleton — request full symbols later via zoom-in)\n"
            f"{repo_map[: self._cap]}"
        )
        if analysis is not None:
            user += _format_analysis(analysis)
        return generate_structured(
            self._client, system=_SYSTEM + _conventions_section(self._profile),
            user=user, model_cls=DesignSpec, retries=1,
        )

    def revise_design(
        self, requirement: str, repo_map: str, previous: DesignSpec,
        issues: list[str], analysis: AnalysisSpec | None = None,
    ) -> DesignSpec:
        """Re-emit a corrected DesignSpec that resolves the deterministic linter's
        consistency findings (design-heal, M07). Same scope/contexts as `previous`."""
        problems = "\n".join(f"- {i}" for i in issues) or "- (none)"
        user = (
            f"# Requirement\n{requirement}\n\n"
            f"# Repo Map (skeleton)\n{repo_map[: self._cap]}\n\n"
            f"# Your previous design (contracts digest — to be corrected)\n"
            f"{render_contracts(previous)}\n\n"
            f"# Consistency issues a deterministic linter found (FIX ALL)\n{problems}"
        )
        if analysis is not None:
            user += _format_analysis(analysis)
        return generate_structured(
            self._client, system=_SYSTEM + _conventions_section(self._profile) + _REVISE,
            user=user, model_cls=DesignSpec, retries=1,
        )
