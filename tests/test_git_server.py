"""Git/Workspace server against a real temp git repo (fast, hermetic)."""

from __future__ import annotations

import subprocess

import pytest

from aicoder.mcp_servers import git_server


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "repo"
    r.mkdir()
    _git(["init", "-b", "main"], r)
    _git(["config", "user.email", "t@example.com"], r)
    _git(["config", "user.name", "tester"], r)
    (r / "README.md").write_text("base", encoding="utf-8")
    _git(["add", "-A"], r)
    _git(["commit", "-m", "base"], r)
    monkeypatch.setattr(git_server, "_REPO", r)
    return r


def test_worktree_write_read_commit(repo) -> None:
    ws = git_server.start_task("feature/demo")
    workdir = ws["worktree"]
    assert workdir

    git_server.write_file(workdir, "src/New.java", "class New {}")
    read = git_server.read_file(workdir, "src/New.java")
    assert read["exists"] and "class New" in read["content"]

    result = git_server.commit(workdir, "add New")
    assert result["ok"] and result["commit"]

    git_server.cleanup_task(workdir)


def test_read_missing_file(repo) -> None:
    ws = git_server.start_task("feature/empty")
    assert git_server.read_file(ws["worktree"], "nope.java") == {"exists": False, "content": ""}
    git_server.cleanup_task(ws["worktree"])
