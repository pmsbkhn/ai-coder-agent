"""Run several requirements CONCURRENTLY, each isolated in its own git worktree.

Each requirement runs as a separate `python -m aicoder` process: its own
orchestrator, its own MCP servers, its own session_id → its own
`feature/<session_id>` worktree (M2). Isolation is therefore by OS process +
per-session worktree — there is no shared mutable state and no shared MCP stdio
connection to serialize, so concurrency is safe. Each run commits to its own
branch off the same base repo.

    python -m aicoder.parallel "req one" "req two" --profile profiles/msfw.yaml

Set AICODER_REPO_PATH (the shared target) and the usual provider/model env, as
for a single run. Note the model server (Ollama) still serializes inference, so
the win is overlapping build/git/IO and isolation correctness, not Nx LLM speed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_STATE_RE = re.compile(r"=== Session (\S+): (\w+) ===")


def _run_one(requirement: str, profile: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "aicoder", requirement, "--profile", str(profile)],
        capture_output=True, text=True,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    m = _STATE_RE.search(out)
    return {
        "requirement": requirement[:60],
        "returncode": proc.returncode,
        "session": m.group(1) if m else None,
        "state": m.group(2) if m else "NO_STATE",
    }


def run_parallel(requirements, profile, max_workers=None, _runner=_run_one) -> list[dict]:
    """Run every requirement concurrently; return one result dict per requirement
    (order preserved). `_runner` is injectable for tests."""
    workers = max_workers or max(1, len(requirements))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_runner, r, profile) for r in requirements]
        return [f.result() for f in futures]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aicoder.parallel")
    parser.add_argument("requirements", nargs="+", help="one or more requirements to run concurrently")
    parser.add_argument("--profile", default="profiles/msfw.yaml")
    parser.add_argument("--max-workers", type=int, default=None)
    args = parser.parse_args(argv)

    print(f"Running {len(args.requirements)} requirement(s) concurrently...\n", flush=True)
    results = run_parallel(args.requirements, args.profile, args.max_workers)

    print(f"\n{'STATE':<16}{'RC':<5}{'SESSION':<22}REQUIREMENT")
    print("-" * 72)
    for r in results:
        print(f"{r['state']:<16}{r['returncode']:<5}{str(r['session']):<22}{r['requirement']}")
    done = sum(1 for r in results if r["state"] == "DONE")
    print("-" * 72)
    print(f"DONE: {done}/{len(results)}")
    return 0 if done == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
