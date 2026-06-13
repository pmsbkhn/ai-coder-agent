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
