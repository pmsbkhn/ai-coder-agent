"""Code-Reader MCP server — Repo Map (skeleton) + symbol zoom-in.

Run as: python -m aicoder.mcp_servers.code_reader_server
The repo it serves is fixed per-process via AICODER_REPO_PATH (set by the gateway
when it spawns this server), so tool calls pass only repo-relative paths.
"""

from __future__ import annotations

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from aicoder.mcp_servers.lib import repo_map

mcp = FastMCP("code-reader")
_REPO = Path(os.environ.get("AICODER_REPO_PATH", ".")).resolve()


@mcp.tool()
def get_repo_map(subpath: str = "", max_files: int = 400) -> dict:
    """Return a compact skeleton (types + signatures, no bodies) of the repo."""
    text = repo_map.build_repo_map(_REPO, subpath=subpath or None, max_files=max_files)
    return {"repo_map": text, "root": str(_REPO)}


@mcp.tool()
def get_symbol(path: str, name: str) -> dict:
    """Zoom-in: full source of a type/method named `name` in `path` (repo-relative)."""
    source = repo_map.get_symbol(_REPO, path, name)
    return {"path": path, "name": name, "found": source is not None, "source": source or ""}


if __name__ == "__main__":
    mcp.run()
