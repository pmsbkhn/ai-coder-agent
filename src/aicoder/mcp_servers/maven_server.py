"""Maven/Test MCP server — runs `mvn test` and returns a DETERMINISTIC verdict.

Run as: python -m aicoder.mcp_servers.maven_server
Repo is fixed via AICODER_REPO_PATH; the mvn executable can be overridden via
AICODER_MVN (defaults to whatever `mvn` resolves to on PATH, incl. mvn.cmd).
The verdict comes from parsing surefire XML, never from interpreting stdout.

SANDBOX (M5): with AICODER_SANDBOX=docker the build runs inside a throwaway
container instead of on the host — model-generated code and Maven plugins
execute with no host filesystem access (only the worktree + ~/.m2 are mounted)
and no network (--network none, so the build must resolve offline from the
mounted ~/.m2). Surefire reports land on the bind-mounted worktree and are parsed
on the host exactly as before.
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
_DEFAULT_IMAGE = "maven:3.9-eclipse-temurin-21"


def _mvn_command(root: Path, module: str, test: str, *, sandbox: str, image: str, m2: str) -> list[str]:
    """Build the argv for `mvn test`. Direct on the host, or inside an isolated
    Docker container when sandbox == 'docker' (no host FS beyond worktree + ~/.m2,
    no network → offline resolve from the mounted ~/.m2)."""
    if sandbox == "docker":
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",                      # no exfiltration / callouts
            "--memory", os.environ.get("AICODER_SANDBOX_MEMORY", "4g"),
            "-v", f"{root}:/work", "-w", "/work",     # only the worktree is writable
            "-v", f"{m2}:/root/.m2",                  # dependency cache (resolve offline)
            image, "mvn", "-o", "test",               # -o: offline; deps must be in ~/.m2
        ]
    else:
        cmd = [_MVN, "test"]
    if module:
        cmd += ["-pl", module]
    if test:
        cmd += [f"-Dtest={test}"]
    return cmd


@mcp.tool()
def run_tests(module: str = "", test: str = "", workdir: str = "") -> dict:
    """Run `mvn test` (optionally scoped to a module / single test) and parse results.

    workdir overrides the repo root (e.g. a git worktree); defaults to AICODER_REPO_PATH.
    Set AICODER_SANDBOX=docker to run the build in an isolated container.
    """
    root = Path(workdir).resolve() if workdir else _REPO
    sandbox = os.environ.get("AICODER_SANDBOX", "").lower()
    image = os.environ.get("AICODER_SANDBOX_IMAGE", _DEFAULT_IMAGE)
    m2 = os.environ.get("AICODER_M2", str(Path.home() / ".m2"))
    cmd = _mvn_command(root, module, test, sandbox=sandbox, image=image, m2=m2)

    proc = subprocess.run(  # noqa: S603 — mvn/docker path from env, not user input
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
