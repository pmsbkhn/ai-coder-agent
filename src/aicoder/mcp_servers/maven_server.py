"""Maven/Test MCP server — runs `mvn test` and returns a DETERMINISTIC verdict.

Run as: python -m aicoder.mcp_servers.maven_server
Repo is fixed via AICODER_REPO_PATH; the mvn executable can be overridden via
AICODER_MVN (defaults to whatever `mvn` resolves to on PATH, incl. mvn.cmd).
The verdict comes from parsing surefire XML, never from interpreting stdout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from aicoder.mcp_servers.lib import surefire

mcp = FastMCP("maven")
_REPO = Path(os.environ.get("AICODER_REPO_PATH", ".")).resolve()
_MVN = shutil.which(os.environ.get("AICODER_MVN", "mvn")) or os.environ.get("AICODER_MVN", "mvn")


@mcp.tool()
def run_tests(module: str = "", test: str = "", workdir: str = "") -> dict:
    """Run `mvn test` (optionally scoped to a module / single test) and parse results.

    workdir overrides the repo root (e.g. a git worktree); defaults to AICODER_REPO_PATH.
    """
    root = Path(workdir).resolve() if workdir else _REPO
    cmd = [_MVN, "test"]
    if module:
        cmd += ["-pl", module]
    if test:
        cmd += [f"-Dtest={test}"]

    proc = subprocess.run(  # noqa: S603 — mvn path resolved above
        cmd, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace",
        stdin=subprocess.DEVNULL,
    )
    summary = surefire.parse_reports(root, module=module or None)
    return {
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        **summary,
    }


if __name__ == "__main__":
    mcp.run()
