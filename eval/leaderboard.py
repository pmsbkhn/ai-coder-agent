"""Multi-model leaderboard for the AI Coder Agent.

Runs the SAME eval suite against several (planner, coder) model configurations and
tabulates the results, so you can compare model setups objectively (tests are the
oracle — pass/fail is deterministic). Each config just sets AICODER_PLANNER_MODEL /
AICODER_CODER_MODEL and re-runs eval/run_eval.py.

Usage:
    uv run python eval/leaderboard.py                 # lite suite, default configs
    uv run python eval/leaderboard.py --suite msfw    # msfw suite (slow)
    uv run python eval/leaderboard.py --suite lite total-balance  # subset of tasks

Set JAVA_HOME (JDK 21) and, for msfw, AICODER_EVAL_MSFW_TARGET, as for run_eval.
Provider defaults to ollama; override per-config in CONFIGS below.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RUN_EVAL = _REPO_ROOT / "eval" / "run_eval.py"

# (label, provider, planner_model, coder_model). Coder fixed to the fast code model
# so the comparison isolates the Planner/reasoner; "solo" uses one model for both.
CONFIGS = [
    ("gptoss120b -> qwen3coder", "ollama", "gpt-oss:120b", "qwen3-coder:30b"),
    ("glm45air -> qwen3coder", "ollama", "gurubot/GLM-4.5-Air-Derestricted:Q4_K_M", "qwen3-coder:30b"),
    ("gemma4-31b -> qwen3coder", "ollama", "gemma4:31b-it-q8_0", "qwen3-coder:30b"),
    ("qwen3coder solo", "ollama", "qwen3-coder:30b", "qwen3-coder:30b"),
]

# run_eval progress lines (robust key=value form):
#   "▶ running account-withdraw ..."
#   "  PASS  state=DONE  heals=0  blocked=2  42.9s"
_RUN_RE = re.compile(r"^▶ running (\S+)")
_RES_RE = re.compile(r"^(PASS|FAIL)\s+state=(\S+)\s+heals=(\d+)\s+blocked=(\d+)\s+([\d.]+)s")


def _run_config(label: str, provider: str, planner: str, coder: str,
                suite: str, tasks: list[str]) -> dict:
    env = {
        **os.environ,
        "AICODER_LLM_PROVIDER": provider,
        "AICODER_PLANNER_MODEL": planner,
        "AICODER_CODER_MODEL": coder,
    }
    cmd = [sys.executable, str(_RUN_EVAL), "--suite", suite, *tasks]
    # Stream the child live (don't buffer) so a long run stays observable and a
    # kill mid-run still shows everything printed so far.
    proc = subprocess.Popen(
        cmd, cwd=str(_REPO_ROOT), env={**env, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    tasks_out: dict[str, dict] = {}
    current = None
    assert proc.stdout is not None
    for raw in proc.stdout:
        sys.stdout.write(raw)
        sys.stdout.flush()
        s = raw.strip()
        run = _RUN_RE.match(s)
        if run:
            current = run.group(1)
            continue
        res = _RES_RE.match(s)
        if res and current:
            tasks_out[current] = {
                "passed": res.group(1) == "PASS",
                "state": res.group(2),
                "heals": int(res.group(3)),
                "blocked": int(res.group(4)),
                "secs": float(res.group(5)),
            }
            current = None
    proc.wait()
    return {"label": label, "planner": planner, "coder": coder, "tasks": tasks_out}


def _print_table(rows: list, suite: str) -> None:
    task_ids: list[str] = []
    for r in rows:
        for tid in r["tasks"]:
            if tid not in task_ids:
                task_ids.append(tid)
    print("\n" + "=" * 78)
    print(f"LEADERBOARD (suite={suite}) — cell = P/F(heals)")
    print("=" * 78)
    header = f"{'CONFIG':<26}{'PASS':<7}{'HEALS':<7}{'SECS':<8}" + "".join(f"{t[:14]:<16}" for t in task_ids)
    print(header)
    print("-" * len(header))
    for r in sorted(rows, key=lambda x: (-sum(t["passed"] for t in x["tasks"].values()),
                                         sum(t["heals"] for t in x["tasks"].values()))):
        t = r["tasks"]
        npass = sum(v["passed"] for v in t.values())
        heals = sum(v["heals"] for v in t.values())
        secs = sum(v["secs"] for v in t.values())
        cells = "".join(
            f"{(('P' if t[tid]['passed'] else 'F') + '(' + str(t[tid]['heals']) + ')'):<16}"
            if tid in t else f"{'-':<16}"
            for tid in task_ids
        )
        print(f"{r['label']:<26}{f'{npass}/{len(t)}':<7}{heals:<7}{secs:<8.0f}{cells}")
    print("-" * len(header), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="leaderboard")
    parser.add_argument("tasks", nargs="*", help="task ids to run (default: all in suite)")
    parser.add_argument("--suite", default="lite", choices=["lite", "msfw"])
    args = parser.parse_args(argv)

    print(f"# Leaderboard — suite={args.suite}, {len(CONFIGS)} configs\n", flush=True)
    rows = []
    for i, (label, provider, planner, coder) in enumerate(CONFIGS, 1):
        print(f"\n===== CONFIG {i}/{len(CONFIGS)}: {label}  "
              f"(planner={planner}, coder={coder}) =====", flush=True)
        rows.append(_run_config(label, provider, planner, coder, args.suite, args.tasks))
        _print_table(rows, args.suite)  # running partial table after each config
    return 0


if __name__ == "__main__":
    sys.exit(main())
