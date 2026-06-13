"""Outbound ports — the only way the core reaches infrastructure.

Every concrete dependency (LLM SDK, MCP gateway, Postgres) sits behind one of
these Protocols. The Orchestrator depends on these names, never on a concrete
class — that is what TC-ARCH-02 enforces.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aicoder.domain.models import (
    ExecutionTrace,
    Plan,
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
class BuildToolPort(Protocol):
    """Generic build/test abstraction — the seam for going beyond MSFW.

    Maven is one implementation; Gradle/npm/pytest can be added later behind the
    same interface. Returns a deterministic verdict (parsed from real test output),
    independent of any LLM.
    """

    def run_tests(self, module: str | None = None, test: str | None = None) -> VerificationResult:
        ...
