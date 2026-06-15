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

When an ANALYSIS section is provided (the upstream Analyst already pinned down WHAT
to build), treat its acceptance criteria as the binding contract: every criterion
MUST be covered by at least one test case, and your design must honor the stated
assumptions. Do not contradict or silently widen the analyzed scope.
"""


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
            self._client, system=_SYSTEM, user=user, model_cls=DesignSpec, retries=1
        )
