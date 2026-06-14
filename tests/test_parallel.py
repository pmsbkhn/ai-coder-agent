"""Parallel requirements (M5): concurrent execution + per-worktree isolation."""

from __future__ import annotations

import threading
import time

from aicoder.mcp_servers import git_server
from aicoder.parallel import run_parallel


def test_run_parallel_executes_concurrently_and_aggregates() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def stub(requirement: str, profile: str) -> dict:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.2)
        with lock:
            active -= 1
        return {"requirement": requirement, "returncode": 0, "session": "s", "state": "DONE"}

    results = run_parallel(["r1", "r2", "r3"], "p.yaml", max_workers=3, _runner=stub)

    assert len(results) == 3
    assert {r["requirement"] for r in results} == {"r1", "r2", "r3"}
    assert peak >= 2, "requirements should run concurrently, not one at a time"


def test_distinct_sessions_get_distinct_worktrees() -> None:
    """The isolation that makes parallelism safe: a different session_id (a
    different requirement) maps to a different worktree directory."""
    wt_a = git_server._worktree_dir("feature/sess_aaaaaaaaaaaa")
    wt_b = git_server._worktree_dir("feature/sess_bbbbbbbbbbbb")
    assert wt_a != wt_b
    assert ".aicoder-worktrees" in str(wt_a) and ".aicoder-worktrees" in str(wt_b)
    # branch slashes are flattened into the dir name (no nested-path collisions)
    assert "/" not in wt_a.name and wt_a.name.endswith("feature_sess_aaaaaaaaaaaa")
