"""Eval harness for the AI Coder Agent.

Two suites:
  - lite  : the framework-free target in eval/target/ (fast general-coding signal)
  - msfw  : the real MSFW sample-service (true MSFW-idiom signal: outbox,
            event-sourcing). Target source is the machine-local sample-service;
            set AICODER_EVAL_MSFW_TARGET or pass --target.

For each golden task under the suite's tasks dir this:
  1. copies the target into a fresh temp repo,
  2. overlays the task's pre-written tests (the immutable acceptance oracle),
  3. git-inits + commits a clean baseline,
  4. runs the agent (`python -m aicoder <prompt> --profile <suite profile>`,
     AICODER_REPO_PATH pointed at the temp repo),
  5. records pass/fail (exit 0 == reached DONE == `mvn test` green with the tests
     unmodified) plus heal attempts and any blocked test-writes,
then prints a scoreboard.

The model is whatever the environment selects (AICODER_LLM_PROVIDER / *_MODEL).
JAVA_HOME must point at a JDK 21 (mvn runs the real tests).

Usage:
    uv run python eval/run_eval.py                       # lite suite, all tasks
    uv run python eval/run_eval.py --suite msfw          # msfw suite, all tasks
    uv run python eval/run_eval.py --suite msfw order-priority   # one task
    uv run python eval/run_eval.py --keep                # don't delete temp repos
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_STATE_RE = re.compile(r"=== Session \S+: (\w+) ===")
_DEFAULT_MSFW_TARGET = "/Users/evolarc/Projects/msfw/sample-service"


def _suites() -> dict:
    msfw_target = os.environ.get("AICODER_EVAL_MSFW_TARGET", _DEFAULT_MSFW_TARGET)
    return {
        "lite": {
            "target": _REPO_ROOT / "eval" / "target",
            "profile": _REPO_ROOT / "profiles" / "eval.yaml",
            "tasks": _REPO_ROOT / "eval" / "tasks",
        },
        "msfw": {
            "target": Path(msfw_target),
            "profile": _REPO_ROOT / "profiles" / "eval-msfw.yaml",
            "tasks": _REPO_ROOT / "eval" / "tasks-msfw",
        },
    }


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args],
        cwd=str(cwd), check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )


def _overlay(src: Path, dst: Path) -> None:
    """Copy every file under src into dst, preserving relative paths."""
    for path in src.rglob("*"):
        if path.is_file():
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _prepare_repo(task_dir: Path, base: Path, target: Path) -> Path:
    proj = base / "project"
    shutil.copytree(
        target, proj,
        ignore=shutil.ignore_patterns("target", ".git", "*.class"),
    )
    _overlay(task_dir / "given", proj)
    _git(["init", "-q"], proj)
    _git(["add", "-A"], proj)
    _git(
        ["-c", "user.name=Eval Harness", "-c", "user.email=eval@aicoder.local",
         "commit", "-q", "-m", "eval baseline"],
        proj,
    )
    return proj


def _run_task(task_dir: Path, keep: bool, target: Path, profile: Path, timeout: int) -> dict:
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    base = Path(tempfile.mkdtemp(prefix=f"aicoder-eval-{task['id']}-"))
    started = time.monotonic()
    try:
        proj = _prepare_repo(task_dir, base, target)
        env = {**os.environ, "AICODER_REPO_PATH": str(proj)}
        proc = subprocess.run(
            [sys.executable, "-m", "aicoder", task["prompt"], "--profile", str(profile)],
            cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True, timeout=timeout,
        )
        out = proc.stdout + "\n" + proc.stderr
        m = _STATE_RE.search(out)
        return {
            "id": task["id"],
            "passed": proc.returncode == 0,
            "state": m.group(1) if m else "NO_STATE",
            "heals": out.count("'task': 'heal'"),
            "reflections": out.count("REFLECTION:"),
            "blocked_writes": out.count("WRITE_BLOCKED"),
            "seconds": round(time.monotonic() - started, 1),
        }
    except subprocess.TimeoutExpired:
        return {"id": task["id"], "passed": False, "state": "TIMEOUT",
                "heals": 0, "reflections": 0, "blocked_writes": 0,
                "seconds": round(time.monotonic() - started, 1)}
    finally:
        if not keep:
            shutil.rmtree(base, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_eval")
    parser.add_argument("tasks", nargs="*", help="task ids to run (default: all in suite)")
    parser.add_argument("--suite", default="lite", choices=["lite", "msfw"])
    parser.add_argument("--target", help="override the suite's target source dir")
    parser.add_argument("--timeout", type=int, default=3000,
                        help="per-task wall-clock cap in seconds (a hung config fails fast)")
    parser.add_argument("--keep", action="store_true", help="keep temp repos for inspection")
    args = parser.parse_args(argv)

    suite = _suites()[args.suite]
    target = Path(args.target) if args.target else suite["target"]
    profile, tasks_dir = suite["profile"], suite["tasks"]

    if not os.environ.get("JAVA_HOME"):
        print("WARNING: JAVA_HOME is not set — mvn may fail to find a JDK 21.\n")
    if not target.exists():
        print(f"ERROR: target source not found: {target}\n"
              f"(set AICODER_EVAL_MSFW_TARGET or pass --target for the msfw suite)")
        return 2

    all_dirs = sorted(d for d in tasks_dir.iterdir() if (d / "task.yaml").exists())
    if args.tasks:
        wanted = set(args.tasks)
        all_dirs = [d for d in all_dirs if d.name in wanted]
    if not all_dirs:
        print(f"No matching tasks in {tasks_dir}.")
        return 1

    provider = os.environ.get("AICODER_LLM_PROVIDER", "anthropic")
    planner = os.environ.get("AICODER_PLANNER_MODEL") or os.environ.get("AICODER_LLM_MODEL", "(default)")
    coder = os.environ.get("AICODER_CODER_MODEL") or os.environ.get("AICODER_LLM_MODEL", "(default)")
    print(f"Suite={args.suite}  target={target}")
    print(f"Provider={provider}  planner={planner}  coder={coder}  tasks={len(all_dirs)}\n")

    results = []
    for d in all_dirs:
        print(f"▶ running {d.name} ...", flush=True)
        r = _run_task(d, args.keep, target, profile, args.timeout)
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  {mark}  state={r['state']}  heals={r['heals']}  "
              f"blocked={r['blocked_writes']}  {r['seconds']}s")
        results.append(r)

    passed = sum(1 for r in results if r["passed"])
    print("\n" + "=" * 64)
    print(f"{'TASK':<24}{'RESULT':<8}{'STATE':<14}{'HEALS':<7}{'SECS':<7}")
    print("-" * 64)
    for r in results:
        print(f"{r['id']:<24}{('PASS' if r['passed'] else 'FAIL'):<8}"
              f"{r['state']:<14}{r['heals']:<7}{r['seconds']:<7}")
    print("-" * 64)
    print(f"PASS RATE ({args.suite}): {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
