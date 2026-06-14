"""Git/Workspace MCP server — isolated worktree + file I/O + commit.

Run as: python -m aicoder.mcp_servers.git_server  (repo via AICODER_REPO_PATH)

Each task runs in its own `git worktree` so edits are isolated (enables M3
reset-to-clean and M5 parallelism). File read/write is scoped to a workdir the
caller passes (the worktree path returned by start_task).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("git")
_REPO = Path(os.environ.get("AICODER_REPO_PATH", ".")).resolve()
_GIT = os.environ.get("AICODER_GIT", "git")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    # gc.auto=0 / maintenance.auto=false: a background `git gc` spawned by
    # worktree/checkout inherits this server's stdout pipe and never closes it,
    # deadlocking capture_output on Windows. stdin=DEVNULL avoids any stdin wait.
    return subprocess.run(
        [_GIT, "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
        cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
    )


def _worktree_dir(branch: str) -> Path:
    safe = branch.replace("/", "_")
    return (_REPO.parent / ".aicoder-worktrees" / f"{_REPO.name}__{safe}").resolve()


@mcp.tool()
def start_task(branch: str) -> dict:
    """Create an isolated worktree on a new branch off HEAD. Returns its path."""
    wt = _worktree_dir(branch)
    wt.parent.mkdir(parents=True, exist_ok=True)
    # if a stale worktree exists, reuse it rather than failing
    if wt.exists():
        return {"worktree": str(wt), "branch": branch, "reused": True}
    proc = _git(["worktree", "add", "-b", branch, str(wt), "HEAD"], _REPO)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip(), "worktree": "", "branch": branch}
    return {"ok": True, "worktree": str(wt), "branch": branch, "reused": False}


@mcp.tool()
def read_file(workdir: str, path: str) -> dict:
    target = Path(workdir) / path
    if not target.exists():
        return {"exists": False, "content": ""}
    return {"exists": True, "content": target.read_text(encoding="utf-8", errors="replace")}


@mcp.tool()
def write_file(workdir: str, path: str, content: str) -> dict:
    target = Path(workdir) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "path": path}


@mcp.tool()
def list_files(workdir: str, glob: str = "**/*") -> dict:
    """List repo-relative file paths under the worktree matching a glob.
    Used to discover protected spec files (e.g. tests) to feed the Coder as
    read-only context."""
    base = Path(workdir)
    files = [
        str(p.relative_to(base)).replace("\\", "/")
        for p in base.glob(glob)
        if p.is_file() and ".git/" not in str(p.relative_to(base)).replace("\\", "/")
    ]
    return {"files": sorted(files)}


@mcp.tool()
def reset_clean(workdir: str) -> dict:
    """Discard ALL uncommitted changes in the worktree, back to its base commit
    (M3 reset-to-clean). Each heal attempt then starts from pristine files rather
    than compounding the previous attempt's broken output."""
    hard = _git(["reset", "--hard", "HEAD"], Path(workdir))
    clean = _git(["clean", "-fd"], Path(workdir))
    if hard.returncode != 0 or clean.returncode != 0:
        return {"ok": False, "error": (hard.stderr + clean.stderr).strip()}
    return {"ok": True}


@mcp.tool()
def commit(workdir: str, message: str) -> dict:
    """Stage everything in the worktree and commit. Returns the new commit sha."""
    add = _git(["add", "-A"], Path(workdir))
    if add.returncode != 0:
        return {"ok": False, "error": add.stderr.strip()}
    # Commit with an explicit agent identity so it never depends on the target
    # repo's (often unset) user.name/email — a missing identity silently aborts.
    done = _git(
        [
            "-c", "user.name=AI Coder Agent",
            "-c", "user.email=agent@aicoder.local",
            "commit", "-m", message,
        ],
        Path(workdir),
    )
    if done.returncode != 0:
        return {"ok": False, "error": (done.stderr or done.stdout).strip()}
    sha = _git(["rev-parse", "HEAD"], Path(workdir)).stdout.strip()
    return {"ok": True, "commit": sha}


@mcp.tool()
def cleanup_task(worktree: str) -> dict:
    proc = _git(["worktree", "remove", "--force", worktree], _REPO)
    return {"ok": proc.returncode == 0, "error": proc.stderr.strip()}


if __name__ == "__main__":
    mcp.run()
