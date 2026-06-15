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
