"""git delivery (M5): push a branch to a remote, degrade gracefully with none.

Self-contained — uses a LOCAL bare repo as the remote (file://), so it runs in CI
with no network and never touches any real GitHub remote.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from aicoder.mcp_servers import git_server


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def test_push_lands_branch_in_local_bare_remote(tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)

    work = tmp_path / "work"
    work.mkdir()
    _run(["init", "-q"], work)
    (work / "f.txt").write_text("hi", encoding="utf-8")
    git_server.commit(str(work), "init")              # commits with the agent identity
    _run(["remote", "add", "origin", str(bare)], work)
    _run(["checkout", "-qb", "feature/sess_x"], work)
    (work / "g.txt").write_text("more", encoding="utf-8")
    git_server.commit(str(work), "feat")

    res = git_server.push(str(work), remote="origin", branch="feature/sess_x")
    assert res["ok"] is True and res["pushed"] is True and res["branch"] == "feature/sess_x"

    branches = subprocess.run(
        ["git", "-C", str(bare), "branch", "--list", "feature/sess_x"],
        capture_output=True, text=True,
    ).stdout
    assert "feature/sess_x" in branches  # the branch really reached the remote


def test_push_without_remote_degrades_gracefully(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    _run(["init", "-q"], work)
    (work / "f.txt").write_text("hi", encoding="utf-8")
    git_server.commit(str(work), "init")

    res = git_server.push(str(work))  # no remote configured
    assert res["ok"] is False and res["pushed"] is False
    assert "remote" in res["error"].lower()
