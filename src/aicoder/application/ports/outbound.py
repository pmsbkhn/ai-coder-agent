"""Outbound ports — the only way the core reaches infrastructure.

Every concrete dependency (LLM SDK, MCP gateway, Postgres) sits behind one of
these Protocols. The Orchestrator depends on these names, never on a concrete
class — that is what TC-ARCH-02 enforces.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aicoder.domain.models import (
    CodeChange,
    DesignSpec,
    ExecutionTrace,
    Plan,
    Task,
    ToolRequest,
    ToolResponse,
    VerificationResult,
)
from aicoder.domain.session import AgentSession


@runtime_checkable
class PlannerPort(Protocol):
    def generate_plan(self, requirement: str, repo_map: str) -> Plan:
        """Decompose a requirement into structured sub-tasks (stateless reasoning)."""
        ...

    def reflect(
        self, requirement: str, error_context: str, files: dict[str, str], history: list[str]
    ) -> str:
        """Analyse why the last heal attempt failed and propose a CONCRETE, fresh
        fix strategy for the Coder (M3).

        `files` is the CURRENT (failing) content of the relevant files, so the
        reflection reasons about the real code instead of guessing its shape.
        `history` is the strategies already tried-and-still-failed, so each call
        produces a DIFFERENT analysis — this is what lets a deterministic (temp 0)
        Coder escape the fixpoint where the same prompt yields the same broken
        output forever. Returns guidance text, not code.
        """
        ...


@runtime_checkable
class DesignPort(Protocol):
    """Design-first phase (M07): turn a requirement + repo map into a delta
    DesignSpec — affected components, interface changes, and executable proposed
    tests — BEFORE coding. Runs on the reasoner role (stateless reasoning)."""

    def propose_design(self, requirement: str, repo_map: str) -> DesignSpec:
        ...


@runtime_checkable
class CoderPort(Protocol):
    def apply_task(
        self, task: Task, files: dict[str, str], error_context: str = ""
    ) -> CodeChange:
        """Produce whole-file edits for one task.

        `files` maps target path -> current content. `error_context` carries the
        distilled prior failure during a self-healing retry (empty on first try).
        """
        ...


@runtime_checkable
class MemoryPort(Protocol):
    """Immutable memory + session persistence.

    State is externalized here so the Orchestrator stays stateless. Trace writes
    are append-only (TC-ARCH-03); there is deliberately no update/delete method.
    """

    def append_log(self, trace: ExecutionTrace) -> None: ...
    def get_traces(self, session_id: str) -> list[ExecutionTrace]: ...
    def save_session(self, session: AgentSession) -> None: ...
    def load_session(self, session_id: str) -> AgentSession | None: ...
    def get_repo_map(self) -> str: ...


@runtime_checkable
class MCPGatewayPort(Protocol):
    """The single unified tool port. The gateway fans out to MCP servers
    (code-reader, maven, git, ...) over JSON-RPC. Adding a tool = a new server,
    not a new port."""

    def execute_tool_call(self, request: ToolRequest) -> ToolResponse: ...


@runtime_checkable
class ApprovalPort(Protocol):
    """The human gate before an irreversible / outward action (deploy, M6).

    Implementations must DENY by default — the agent never deploys without an
    explicit human (or explicitly-configured) go-ahead."""

    def request_approval(self, summary: str) -> bool:
        """Return True to proceed with deploy, False to hold."""
        ...


@runtime_checkable
class DeployPort(Protocol):
    """Run the profile's deploy command for a verified change (M6)."""

    def deploy(self, workdir: str, command: str) -> dict:
        """Execute `command` in `workdir`; return {"ok": bool, "output"/"error": str}."""
        ...


@runtime_checkable
class BuildToolPort(Protocol):
    """Generic build/test abstraction — the seam for going beyond MSFW.

    Maven is one implementation; Gradle/npm/pytest can be added later behind the
    same interface. Returns a deterministic verdict (parsed from real test output),
    independent of any LLM.
    """

    def run_tests(
        self, module: str | None = None, test: str | None = None, workdir: str | None = None
    ) -> VerificationResult:
        ...
