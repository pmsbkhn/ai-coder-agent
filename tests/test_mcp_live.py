"""Live MCP roundtrip: gateway spawns a real server over stdio and calls it.

Gated behind AICODER_LIVE_MCP=1 so the default suite stays fast and hermetic.
Run: AICODER_LIVE_MCP=1 uv run pytest tests/test_mcp_live.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aicoder.adapters.mcp_gateway import build_gateway_from_profile, raise_for_response
from aicoder.application.profile import load_profile
from aicoder.domain.models import ToolRequest

_LIVE = os.environ.get("AICODER_LIVE_MCP") == "1"
_PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml"
pytestmark = pytest.mark.skipif(not _LIVE, reason="set AICODER_LIVE_MCP=1 for live MCP roundtrip")


def _gateway():
    return build_gateway_from_profile(load_profile(_PROFILE))


def test_code_reader_repo_map_roundtrip() -> None:
    resp = _gateway().execute_tool_call(
        ToolRequest(
            server="code-reader",
            method="get_repo_map",
            params={"subpath": "sample-service"},
        )
    )
    data = raise_for_response(resp)
    assert "OrderService" in data["repo_map"]


def test_unknown_method_on_live_server_maps_to_minus_32601() -> None:
    resp = _gateway().execute_tool_call(
        ToolRequest(server="code-reader", method="no_such_tool", params={})
    )
    assert resp.ok is False
    assert resp.error_code == -32601
