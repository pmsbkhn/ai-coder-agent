"""Domain models — pure Pydantic data structures crossing port boundaries.

Pydantic is a data-modeling library (a runtime type system), not infrastructure,
so it is allowed in the domain. Real SDKs (anthropic, mcp, psycopg, ...) are NOT
— that boundary is enforced by .importlinter and test_arch_fitness.py.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SessionState(str, Enum):
    """Lifecycle of one AgentSession (the linear saga)."""

    INIT = "INIT"
    PLANNING = "PLANNING"
    ANALYZING = "ANALYZING"              # ADR-08 analysis: restate prose req + surface ambiguity
    AWAITING_CLARIFICATION = "AWAITING_CLARIFICATION"  # human gate on an ambiguous requirement
    DESIGNING = "DESIGNING"              # M07 design-first: producing the design + test plan
    AWAITING_APPROVAL = "AWAITING_APPROVAL"  # human gate on the design + proposed tests
    CODING = "CODING"
    VERIFYING = "VERIFYING"
    HEALING = "HEALING"
    DONE = "DONE"
    HEALING_FAILED = "HEALING_FAILED"  # circuit breaker tripped (TC-CORE-06)
    BLOCKED = "BLOCKED"                # escalated to a human


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"


class ISO25010(str, Enum):
    """Quality-attribute vocabulary for NFRs — fixed so the categories are not
    re-invented per requirement (mirrors the design-flow doc's ISO 25010 list)."""

    PERFORMANCE = "Performance"
    RELIABILITY = "Reliability"
    SECURITY = "Security"
    SCALABILITY = "Scalability"
    MAINTAINABILITY = "Maintainability"
    COMPATIBILITY = "Compatibility"
    USABILITY = "Usability"
    PORTABILITY = "Portability"


# --------------------------------------------------------------------------- #
# Structured requirements intake (Slice A) — the human-authored contract that
# replaces vague prose. User Stories + acceptance criteria + measurable NFRs are
# the ONLY part the agent does not invent; everything downstream (design, tests,
# event flow) must trace back to an AC-/NFR- id here.
# --------------------------------------------------------------------------- #


class AcceptanceCriterion(BaseModel):
    """One acceptance criterion of a User Story, ideally in Gherkin form. `text`
    is an escape hatch for a non-Gherkin one-liner; `as_text()` renders either."""

    id: str                                   # "AC-01"
    given: str = ""
    when: str = ""
    then: str = ""
    text: str = ""                            # free-form alternative to given/when/then

    def as_text(self) -> str:
        if self.text.strip():
            return self.text.strip()
        return f"Given {self.given}, When {self.when}, Then {self.then}."


class UserStory(BaseModel):
    """A User Story (template A1): `As a <as_a>, I want <i_want>, so that <so_that>`
    plus its acceptance criteria. The criteria are the binding 'done' conditions."""

    id: str                                   # "US-01"
    title: str = ""
    as_a: str = ""
    i_want: str = ""
    so_that: str = ""
    priority: str = "Medium"                  # High | Medium | Low
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)


class NFR(BaseModel):
    """A measurable non-functional requirement (template A3): a quality attribute
    with a metric + how it is measured + its source. If it is not measurable it is a
    wish, not an NFR — `metric` should carry a number and a unit."""

    id: str                                   # "NFR-01"
    category: ISO25010
    metric: str                               # measurable target, e.g. "p95 < 300ms"
    measurement: str = ""                     # how/where measured
    source: str = ""                          # SLA / compliance / story id
    scope: str = ""                           # affected context / endpoint


class RequirementSpec(BaseModel):
    """The structured input contract for one change: User Stories + NFRs. Replaces
    the single prose blob; `to_prose()` renders a canonical text so every downstream
    consumer that still takes a `requirement: str` keeps working unchanged."""

    title: str = ""
    stories: list[UserStory] = Field(default_factory=list)
    nfrs: list[NFR] = Field(default_factory=list)

    @property
    def acceptance_ids(self) -> list[str]:
        return [ac.id for us in self.stories for ac in us.acceptance]

    @property
    def nfr_ids(self) -> list[str]:
        return [n.id for n in self.nfrs]

    def to_prose(self) -> str:
        """A readable canonical rendering — the back-compat `requirement: str` fed to
        the Planner/Coder/logs and used to seed the session id."""
        parts: list[str] = []
        if self.title:
            parts.append(self.title)
        for us in self.stories:
            head = " ".join(p for p in [us.id, f"— {us.title}" if us.title else ""] if p)
            if us.priority:
                head += f" [{us.priority}]"
            parts.append(head)
            if us.as_a or us.i_want or us.so_that:
                parts.append(f"As a {us.as_a}, I want {us.i_want}, so that {us.so_that}.")
            if us.acceptance:
                parts.append("Acceptance criteria:")
                parts += [f"  - {ac.id}: {ac.as_text()}" for ac in us.acceptance]
        if self.nfrs:
            parts.append("Non-functional requirements:")
            for n in self.nfrs:
                extra = "; ".join(
                    x for x in [
                        f"measure: {n.measurement}" if n.measurement else "",
                        f"source: {n.source}" if n.source else "",
                        f"scope: {n.scope}" if n.scope else "",
                    ] if x
                )
                line = f"  - {n.id} [{n.category.value}] {n.metric}"
                parts.append(line + (f" ({extra})" if extra else ""))
        return "\n".join(parts)


class Task(BaseModel):
    """A single sub-task produced by the Planner."""

    id: str
    description: str
    target_files: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING


class Plan(BaseModel):
    """Structured decomposition returned by the PlannerPort."""

    tasks: list[Task] = Field(default_factory=list)
    rationale: str = ""

    @property
    def is_empty(self) -> bool:
        return len(self.tasks) == 0


# --------------------------------------------------------------------------- #
# Event-flow building blocks (Slice C, design-flow template A5). Per bounded
# context: the Command → Aggregate → Domain Event → Policy → (next Command) chain
# plus the Read Models. Empty by default — a simple CRUD change need not model them,
# only event-driven contexts do (graceful degradation for 1-service changes).
# --------------------------------------------------------------------------- #


class Command(BaseModel):
    """An imperative the system executes (template A5 Commands). `aggregate` is the
    target aggregate name; `traces_to` links it to the US/AC that motivates it."""

    id: str                                   # "CMD-01"
    name: str = ""                            # imperative, e.g. "Place order"
    actor: str = ""
    aggregate: str = ""                       # target aggregate
    input: str = ""                           # carried data
    precondition: str = ""                    # invariant / guard before execution
    traces_to: list[str] = Field(default_factory=list)


class DomainEvent(BaseModel):
    """A past-tense fact emitted after a Command succeeds (template A5 Domain Events)."""

    id: str                                   # "EVT-01"
    name: str = ""                            # past tense, e.g. "Order placed"
    aggregate: str = ""                       # emitting aggregate
    data: str = ""                            # payload it carries
    traces_to: list[str] = Field(default_factory=list)


class Policy(BaseModel):
    """A reaction: `When <event> then <command>` (template A5 Policies) — the direct
    source of an async flow at integration time. `when_event`/`then_command` reference
    the EVT-/CMD- ids so the linter can check they are declared (event-flow advisory)."""

    id: str                                   # "POL-01"
    rule: str = ""                            # "When EVT-01 then CMD-Reserve-stock"
    when_event: str = ""                      # EVT-id this reacts to
    then_command: str = ""                    # CMD-id it triggers
    traces_to: list[str] = Field(default_factory=list)


class ReadModel(BaseModel):
    """A query-side projection serving a screen/report (template A5 Read Models)."""

    id: str                                   # "RM-01"
    name: str = ""
    source_events: list[str] = Field(default_factory=list)  # EVT-ids it projects from
    serves: str = ""                          # the query / screen it backs
    traces_to: list[str] = Field(default_factory=list)


class GlossaryTerm(BaseModel):
    """One Ubiquitous-Language term (template A4). `bounded_context` is mandatory because
    the SAME term can mean different things in two contexts — that divergence is the
    signal to split a context (design-flow Bước 3)."""

    id: str                                   # "GL-01"
    term: str = ""
    definition: str = ""
    bounded_context: str = ""
    aliases_to_avoid: list[str] = Field(default_factory=list)
    example: str = ""


class UseCase(BaseModel):
    """A Use Case (template A2) the agent DERIVES by grouping User Stories — `traces_to`
    names the US-ids it gathers. Light B1 artifact; empty when not derived."""

    id: str                                   # "UC-01"
    name: str = ""                            # verb + object, e.g. "Place order"
    primary_actor: str = ""
    secondary_actors: list[str] = Field(default_factory=list)
    preconditions: str = ""
    postconditions: str = ""
    main_flow: list[str] = Field(default_factory=list)
    alt_flows: list[str] = Field(default_factory=list)
    traces_to: list[str] = Field(default_factory=list)        # US-ids gathered


# --------------------------------------------------------------------------- #
# Integration building blocks (Slice D, design-flow Bước 3 + 5 / templates A6, A8).
# Context relationships are typed with the fixed DDD vocabulary; APIs (sync) and event
# schemas (async) are per-context contracts; sagas model distributed consistency. All
# empty by default — a single-context CRUD change models none of them.
# --------------------------------------------------------------------------- #


class ContextRelationshipKind(str, Enum):
    """The fixed DDD integration-pattern vocabulary (template A6) — so the relationship
    TYPE is named, not just Upstream/Downstream. The pattern dictates the integration
    mechanism at design time (Bước 5)."""

    PARTNERSHIP = "Partnership"
    CUSTOMER_SUPPLIER = "Customer/Supplier"
    CONFORMIST = "Conformist"
    ANTI_CORRUPTION_LAYER = "Anti-Corruption Layer"
    SHARED_KERNEL = "Shared Kernel"
    OPEN_HOST_SERVICE = "Open Host Service / Published Language"


class ContextRelationship(BaseModel):
    """A typed edge on the Context Map (template A6): who is upstream/downstream, the DDD
    pattern, and the concrete integration mechanism (e.g. 'sync (REST)' / 'async (event)').
    `mechanism` carrying 'sync' is what the integration linter (T5) counts."""

    id: str                                   # "REL-01"
    upstream: str = ""
    downstream: str = ""
    kind: ContextRelationshipKind = ContextRelationshipKind.CUSTOMER_SUPPLIER
    mechanism: str = ""                       # "sync (REST)" | "async (event)" | ...
    notes: str = ""


class ApiSpec(BaseModel):
    """A synchronous endpoint summary (template A8.1, OpenAPI digest). Lives on the owning
    context's Tech Spec; `traces_to` links it to the CMD it fronts / the UC it serves."""

    id: str                                   # "API-01"
    method: str = ""                          # POST | GET | ...
    path: str = ""                            # /v1/orders
    summary: str = ""
    request: str = ""
    response: str = ""
    auth: str = ""
    idempotency: str = ""                     # e.g. "Idempotency-Key header (POST)"
    errors: list[str] = Field(default_factory=list)
    traces_to: list[str] = Field(default_factory=list)


class EventSchema(BaseModel):
    """An async message contract (template A8.2, CloudEvents envelope). Lives on the
    producer context's Tech Spec; consumers name the BCs that subscribe."""

    id: str                                   # "EVS-01"
    event_name: str = ""                      # "order.created.v1"
    consumers: list[str] = Field(default_factory=list)
    channel: str = ""                         # topic / queue
    partition_key: str = ""
    payload_schema: str = ""
    versioning: str = ""                      # ".vN, backward-compatible"
    reliability: str = ""                     # "retry n → DLQ; consumer idempotent"
    traces_to: list[str] = Field(default_factory=list)  # ← EVT / POL ; executes REL


class SagaStep(BaseModel):
    """One step of a Saga (template A8.3): the service action, its success event, and the
    compensating action that undoes it on rollback."""

    service: str = ""
    action: str = ""
    success_event: str = ""
    compensation: str = ""


class SagaSpec(BaseModel):
    """A Saga / Process Manager for distributed consistency (template A8.3) — orchestration
    or choreography, with a compensating action per step. System-level (spans services)."""

    id: str                                   # "SAGA-01"
    name: str = ""
    trigger: str = ""
    kind: str = "Orchestration"               # Orchestration | Choreography
    timeout: str = ""
    steps: list[SagaStep] = Field(default_factory=list)
    traces_to: list[str] = Field(default_factory=list)  # ← REL / POL


class ProposedTest(BaseModel):
    """A test case the Designer proposes (M07 design-first), in the house TC-XXX-NN
    style: an explicit domain-invariant / adapter / fitness specification PLUS the
    executable test that encodes it.

    `spec` is the natural-language case (setup → action → assert, referencing
    DomainException codes / invariants) — it renders into the Test Cases document.
    `content` is the whole executable test-file source and `path` where it lives;
    once the architect approves, it is written + locked via protected_globs and
    becomes the oracle the Coder implements against. Fitness/architecture cases may
    be spec-only (no executable content) — they document a rule enforced elsewhere."""

    id: str = ""                                                 # e.g. "TC-PAY-01"
    title: str = ""                                              # e.g. "Amount Cross-Check / Tampering"
    kind: str = "domain"                                         # domain | adapter | fitness
    spec: str = ""                                               # TC-style: setup → action → assert
    path: str = ""                                               # executable test path (locked oracle)
    content: str = ""                                            # executable JUnit source
    rationale: str = ""
    # Slice B traceability: the AC-/NFR- id(s) from the RequirementSpec this case
    # covers. Empty when no structured intake was supplied (prose path). The linter
    # enforces AC→test (T1) and test→requirement (T3) against these ids.
    traces_to: list[str] = Field(default_factory=list)


class TechSpec(BaseModel):
    """The technical specification for ONE bounded context (1 BC = 1 Tech Spec),
    following the org's detailed-design template (core design sections). Carries that
    context's delta: requirements, static/runtime structure, domain model + invariants,
    data model, decisions, and the acceptance test cases for it."""

    bounded_context: str                                         # the BC this spec governs
    summary: str                                                 # Context & Scope (what changes here)
    classification: str = ""                                     # Tier + Data class (one line)
    requirements_functional: list[str] = Field(default_factory=list)     # FR list
    requirements_nonfunctional: list[str] = Field(default_factory=list)  # NFR / SLO list
    module_view: str = ""                                        # static structure (mermaid or bullets)
    cnc_view: str = ""                                           # runtime components + connectors
    affected: list[str] = Field(default_factory=list)            # components/files touched
    interface_changes: list[str] = Field(default_factory=list)   # contract/interface deltas (ports)
    domain_model: str = ""                                       # aggregate/value objects (mermaid)
    invariants: list[str] = Field(default_factory=list)          # domain invariants (guard clauses)
    # Event flow (Slice C, template A5) — empty for a non-event-driven change.
    commands: list[Command] = Field(default_factory=list)
    events: list[DomainEvent] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    read_models: list[ReadModel] = Field(default_factory=list)
    # Integration contracts (Slice D, template A8) — empty for an internal-only change.
    apis: list[ApiSpec] = Field(default_factory=list)            # sync endpoints (A8.1)
    event_schemas: list[EventSchema] = Field(default_factory=list)  # async messages (A8.2)
    erd: str = ""                                                # data model (mermaid erDiagram / schema)
    key_flows: str = ""                                          # sequence(s) for the main flow(s)
    adrs: list[str] = Field(default_factory=list)                # ADR-style decisions (decision → why)
    open_questions: list[str] = Field(default_factory=list)      # TBDs to resolve
    adr_notes: str = ""                                          # short rationale (legacy/free notes)
    test_plan: list[ProposedTest] = Field(default_factory=list)  # TC cases + executable oracle


class DesignSpec(BaseModel):
    """The design output for one change — an umbrella **Architecture Description**
    (system/SAD level: goals, architecture style, principles, bounded-context map,
    cross-cutting decisions) plus one **Tech Spec per bounded context** (1 BC = 1
    Tech Spec). Materialized to files and reviewed by an architect before coding."""

    summary: str                                                 # AD-level: the change across the system
    goals: list[str] = Field(default_factory=list)               # objectives this change serves
    architecture_style: str = ""                                 # style + rationale (e.g. hexagonal + events)
    principles: list[str] = Field(default_factory=list)          # design principles upheld
    context_map: str = ""                                        # bounded-context map (mermaid)
    decisions: list[str] = Field(default_factory=list)           # cross-cutting / integration decisions
    nfr: list[str] = Field(default_factory=list)                 # system-level NFR / constraints
    # B1 artifacts the agent DERIVES (Slice C) — empty unless derived from a RequirementSpec.
    glossary: list[GlossaryTerm] = Field(default_factory=list)   # Ubiquitous Language (template A4)
    use_cases: list[UseCase] = Field(default_factory=list)       # UCs grouping US (template A2)
    # Integration design (Slice D) — empty for a single-context change.
    relationships: list[ContextRelationship] = Field(default_factory=list)  # typed Context Map (A6)
    sagas: list[SagaSpec] = Field(default_factory=list)          # distributed consistency (A8.3)
    tech_specs: list[TechSpec] = Field(default_factory=list)     # one per bounded context

    @property
    def bounded_contexts(self) -> list[str]:
        return [ts.bounded_context for ts in self.tech_specs]

    def all_tests(self) -> list[ProposedTest]:
        return [t for ts in self.tech_specs for t in ts.test_plan]

    def executable_tests(self) -> list[ProposedTest]:
        """Only the cases with an executable file — those become the locked oracle.
        Spec-only cases (e.g. fitness rules) document intent but write no test file."""
        return [t for t in self.all_tests() if t.path and t.content]


class AnalysisSpec(BaseModel):
    """The Analyst's output (ADR-08), produced BEFORE design from a prose business
    requirement that has not yet been broken into clear use cases. It makes the
    implicit explicit: a restatement (what the agent understood), the assumptions it
    took, open questions / ambiguities, and the acceptance criteria the design + tests
    must satisfy. `ambiguous` is the Analyst's verdict that it cannot responsibly
    proceed without human clarification — it drives the clarification gate."""

    restatement: str                                          # the requirement, in the agent's words
    assumptions: list[str] = Field(default_factory=list)      # taken to fill gaps in the prose
    open_questions: list[str] = Field(default_factory=list)   # genuine ambiguities for a human
    acceptance_criteria: list[str] = Field(default_factory=list)  # observable "done" conditions
    ambiguous: bool = False                                   # cannot proceed responsibly w/o clarification


class TestReview(BaseModel):
    """An adversarial critique of a proposed TestPlan (M07 Slice 4): do the tests
    actually constrain the requirement, or are they weak / trivially satisfiable /
    missing edge cases? Advisory by default (surfaced to the human gate); can
    auto-block when design.review_strict is set."""

    ok: bool                                              # tests adequately constrain the requirement
    concerns: list[str] = Field(default_factory=list)     # weaknesses found
    summary: str = ""


class ToolRequest(BaseModel):
    """A unified call routed through the MCP Gateway (JSON-RPC)."""

    server: str          # logical server name, e.g. "code-reader", "maven", "git"
    method: str          # e.g. "get_repo_map", "run_tests"
    params: dict = Field(default_factory=dict)


class ToolResponse(BaseModel):
    ok: bool
    result: dict | None = None
    error_code: int | None = None      # JSON-RPC error code if ok is False
    error_message: str | None = None


class VerificationResult(BaseModel):
    """The Verifier's verdict. Functional + architectural are DETERMINISTIC;
    `analysis` is the LLM's interpretation and may never flip `passed`."""

    passed: bool
    functional_passed: bool
    arch_passed: bool
    failed_tests: list[str] = Field(default_factory=list)
    evidence: str = ""                 # raw stdout/stderr/stack traces
    error_signature: str | None = None  # stable hash of the failure (no-progress check)
    analysis: str = ""                 # LLM root-cause explanation (advisory only)


class FileEdit(BaseModel):
    """A whole-file replacement produced by the Coder.

    Full content (not a diff) is deliberate for the walking skeleton: it removes
    the fragile diff-apply step. Aider-style search/replace is an M3 optimization.
    """

    path: str
    content: str


class CodeChange(BaseModel):
    """The Coder's output for one task: the files it wants to (re)write."""

    edits: list[FileEdit] = Field(default_factory=list)
    notes: str = ""


class ExecutionTrace(BaseModel):
    """One append-only record in the Immutable Memory."""

    session_id: str
    seq: int
    event_type: str
    payload: dict = Field(default_factory=dict)
