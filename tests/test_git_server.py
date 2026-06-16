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


def test_start_task_reuses_live_worktree(repo) -> None:
    # in-run idempotency: a second start_task for the same branch reuses the dir.
    a = git_server.start_task("feature/sess_x")
    b = git_server.start_task("feature/sess_x")
    assert a["ok"] and b["ok"]
    assert a["worktree"] == b["worktree"] and b["reused"] is True
    git_server.cleanup_task(a["worktree"])


def test_start_task_recovers_when_branch_exists_but_worktree_gone(repo) -> None:
    # the deterministic-session-id re-run: branch `feature/sess_y` survives a prior
    # run but its worktree was removed. start_task must NOT fail with
    # "a branch named ... already exists" — it attaches the branch to a fresh worktree.
    first = git_server.start_task("feature/sess_y")
    git_server.cleanup_task(first["worktree"])  # remove the worktree, branch stays
    _git(["branch", "--list", "feature/sess_y"], repo)  # (branch still present)

    again = git_server.start_task("feature/sess_y")
    assert again["ok"], again
    assert again["worktree"] and (repo.parent / ".aicoder-worktrees").exists()
    # the worktree is usable
    git_server.write_file(again["worktree"], "A.java", "class A {}")
    assert git_server.read_file(again["worktree"], "A.java")["exists"]
    git_server.cleanup_task(again["worktree"])


def test_start_task_clears_stale_non_worktree_dir(repo) -> None:
    # a leftover directory at the worktree path that is NOT a registered worktree
    # (e.g. files left by a killed run) must be cleared, not cause a failure.
    wt = git_server._worktree_dir("feature/sess_z")
    wt.mkdir(parents=True)
    (wt / "junk.txt").write_text("leftover", encoding="utf-8")
    ws = git_server.start_task("feature/sess_z")
    assert ws["ok"] and (wt / ".git").exists()
    git_server.cleanup_task(ws["worktree"])
