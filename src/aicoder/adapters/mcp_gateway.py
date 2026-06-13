"""MCPGatewayClient — the single outbound seam to all tools (JSON-RPC over stdio).

Implements MCPGatewayPort. Routes a ToolRequest to the right MCP server, spawning
it on demand. Errors are mapped to JSON-RPC-style codes and wrapped so a missing
or broken server degrades gracefully instead of crashing the core (TC-INT-05).

M1 uses per-call connect (spawn → call → close): simple and correct. A persistent
session pool is an M2 optimization.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import dataclass, field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from aicoder.application.profile import ProjectProfile
from aicoder.domain.errors import ToolInvocationError
from aicoder.domain.models import ToolRequest, ToolResponse

# JSON-RPC error codes we surface across the port boundary.
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603


@dataclass
class ServerSpec:
    command: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)


class MCPGatewayClient:
    def __init__(self, servers: dict[str, ServerSpec]) -> None:
        self._servers = servers

    def execute_tool_call(self, request: ToolRequest) -> ToolResponse:
        return asyncio.run(self._call(request))

    async def _call(self, request: ToolRequest) -> ToolResponse:
        spec = self._servers.get(request.server)
        if spec is None:
            return ToolResponse(
                ok=False,
                error_code=METHOD_NOT_FOUND,
                error_message=f"Unknown server '{request.server}'",
            )

        params = StdioServerParameters(
            command=spec.command, args=spec.args, env=spec.env or None
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(request.method, request.params or {})
        except Exception as exc:  # spawn/connect failure == cannot dispatch the method
            return ToolResponse(
                ok=False,
                error_code=METHOD_NOT_FOUND,
                error_message=f"Cannot reach {request.server}.{request.method}: {exc!r}",
            )

        text = result.content[0].text if result.content else ""
        if result.isError:
            code = METHOD_NOT_FOUND if "unknown tool" in (text or "").lower() else INTERNAL_ERROR
            return ToolResponse(ok=False, error_code=code, error_message=text)

        data = getattr(result, "structuredContent", None)
        if not data:
            try:
                data = json.loads(text) if text else {}
            except json.JSONDecodeError:
                data = {"text": text}
        return ToolResponse(ok=True, result=data)


def raise_for_response(resp: ToolResponse) -> dict:
    """Unwrap a successful response, or raise a DomainException on failure.

    This is the safe-exit path of TC-INT-05: the core sees a typed
    ToolInvocationError, never a raw transport error or a crash.
    """
    if not resp.ok:
        raise ToolInvocationError(resp.error_message or "tool call failed", code=resp.error_code)
    return resp.result or {}


def build_gateway_from_profile(
    profile: ProjectProfile, *, python_executable: str | None = None
) -> MCPGatewayClient:
    """Wire the standard MSFW server set from a Project Profile.

    The child env inherits the current environment (so PATH + the installed
    package resolve) plus AICODER_REPO_PATH scoping the servers to the target repo.
    """
    py = python_executable or sys.executable
    env = dict(os.environ)
    env["AICODER_REPO_PATH"] = profile.target.repo_path

    servers = {
        "code-reader": ServerSpec(py, ["-m", "aicoder.mcp_servers.code_reader_server"], dict(env)),
        "maven": ServerSpec(py, ["-m", "aicoder.mcp_servers.maven_server"], dict(env)),
        "git": ServerSpec(py, ["-m", "aicoder.mcp_servers.git_server"], dict(env)),
    }
    return MCPGatewayClient(servers)
