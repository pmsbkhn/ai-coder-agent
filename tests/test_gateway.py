"""TC-INT-05 (hermetic side): a missing/unreachable server degrades gracefully.

No subprocess is spawned here — an unregistered server short-circuits to a
JSON-RPC -32601, and raise_for_response surfaces it as a DomainException instead
of crashing the core.
"""

from __future__ import annotations

import pytest

from aicoder.adapters.mcp_gateway import MCPGatewayClient, raise_for_response
from aicoder.domain.errors import ToolInvocationError
from aicoder.domain.models import ToolRequest


def test_unknown_server_returns_method_not_found() -> None:
    gw = MCPGatewayClient(servers={})
    resp = gw.execute_tool_call(ToolRequest(server="code-reader", method="get_repo_map"))
    assert resp.ok is False
    assert resp.error_code == -32601


def test_raise_for_response_wraps_failure_in_domain_exception() -> None:
    gw = MCPGatewayClient(servers={})
    resp = gw.execute_tool_call(ToolRequest(server="nope", method="x"))
    with pytest.raises(ToolInvocationError) as ei:
        raise_for_response(resp)
    assert ei.value.code == -32601


def test_raise_for_response_unwraps_success() -> None:
    from aicoder.domain.models import ToolResponse

    data = raise_for_response(ToolResponse(ok=True, result={"k": "v"}))
    assert data == {"k": "v"}
