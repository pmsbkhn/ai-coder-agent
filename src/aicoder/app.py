"""Composition root + CLI — the one place allowed to know every concrete adapter.

    python -m aicoder "add a 'description' field to Order" --profile profiles/msfw.yaml

Requires, for a real run:
  - ANTHROPIC_API_KEY (or AICODER_LLM_PROVIDER=ollama + a local model),
  - a working `mvn` on PATH (the verdict comes from real `mvn test`),
  - git (the workspace uses worktrees).
The control loop and all adapters are unit-tested with fakes; this wiring is what
turns it into an end-to-end run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aicoder.adapters.coder_llm import LLMCoder
from aicoder.adapters.llm.factory import build_llm_from_env
from aicoder.adapters.maven_build import MavenBuildTool
from aicoder.adapters.mcp_gateway import build_gateway_from_profile
from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.adapters.planner_llm import LLMPlanner
from aicoder.application.orchestrator import Orchestrator
from aicoder.application.profile import load_profile


def build_orchestrator(profile_path: str | Path) -> Orchestrator:
    profile = load_profile(profile_path)
    gateway = build_gateway_from_profile(profile)
    llm = build_llm_from_env()
    return Orchestrator(
        profile=profile,
        planner=LLMPlanner(llm, profile),
        coder=LLMCoder(llm),
        memory=InMemoryMemory(),
        gateway=gateway,
        build=MavenBuildTool(gateway),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aicoder")
    parser.add_argument("requirement", help="what the agent should implement")
    parser.add_argument("--profile", default="profiles/msfw.yaml")
    args = parser.parse_args(argv)

    orch = build_orchestrator(args.profile)
    session = orch.run_requirement(args.requirement)

    print(f"\n=== Session {session.session_id}: {session.state.value} ===")
    if session.plan:
        print(f"Plan: {len(session.plan.tasks)} task(s)")
        for t in session.plan.tasks:
            print(f"  - {t.id}: {t.description}  {t.target_files}")
    print("Trace:")
    for tr in orch.get_log(session.session_id):
        print(f"  [{tr.seq}] {tr.event_type}: {tr.payload}")
    return 0 if session.state.name == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
