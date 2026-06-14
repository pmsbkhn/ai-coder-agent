"""LLMPlanner — PlannerPort backed by a (provider-agnostic) LLMClient.

Grounds the model in the Repo Map skeleton + MSFW conventions and forces a
schema-validated Plan. Small, well-scoped tasks + hard validation are what keep
this working when the underlying model is weak.
"""

from __future__ import annotations

from aicoder.adapters.llm.base import LLMClient
from aicoder.adapters.llm.structured import generate_structured
from aicoder.application.profile import ProjectProfile
from aicoder.domain.models import Plan

_SYSTEM = """You are the Planner of an autonomous coding agent working on an MSFW project
(Java 21 / Spring Boot 4, strict Hexagonal / Ports & Adapters, DDD).

Decompose the requirement into ordered sub-tasks. CRITICAL for a compiled
language: each task must leave the module COMPILING and all tests PASSING on its
own. If a change breaks call sites (e.g. changing a constructor signature),
update ALL of them IN THE SAME TASK. Prefer ONE cohesive task over several
partial ones that would leave the code in a non-compiling intermediate state.

For each task:
- give a short imperative description,
- list EVERY file path it must touch to stay compilable (use the Repo Map),
- list architectural constraints it must respect.

MSFW rules you must never break:
- domain modules stay pure Java (no Spring / no jakarta.persistence in domain),
- depend in/outward only through ports; adapters wire concretes,
- prefer reusing framework building blocks (Aggregate, Factory, Repository,
  @EventPublishHandler outbox flow, the consumption pipeline) over new machinery.

Keep tasks minimal and concrete; a task a junior could verify by running mvn test.
"""

_REFLECT_SYSTEM = """You are the Reflection step of an autonomous coding agent on an
MSFW project (Java 21 / Spring Boot 4, Hexagonal, DDD). A heal attempt just failed
its build/tests.

Reason about the EXACT compiler/test output and say, concretely, what to change to
make it pass. You are NOT writing code — you are giving the Coder a precise strategy.

Be specific and actionable: name the file, the symbol, and the concrete edit (e.g.
"the value is a generic ?, wrap it in String.valueOf(...) before assigning to String").
Diagnose the root cause, do not just restate the error.

You are also given the strategies ALREADY TRIED that still failed. Do NOT repeat
them — propose a DIFFERENT angle each time. Answer in a few terse bullet points.
"""


class LLMPlanner:
    def __init__(
        self, client: LLMClient, profile: ProjectProfile, *, max_repo_map_chars: int = 12000
    ) -> None:
        self._client = client
        self._profile = profile
        self._cap = max_repo_map_chars

    def generate_plan(self, requirement: str, repo_map: str) -> Plan:
        user = (
            f"# Requirement\n{requirement}\n\n"
            f"# Repo Map (skeleton — request full symbols later via zoom-in)\n"
            f"{repo_map[: self._cap]}"
        )
        return generate_structured(
            self._client, system=_SYSTEM, user=user, model_cls=Plan, retries=1
        )

    def reflect(
        self, requirement: str, error_context: str, files: dict[str, str], history: list[str]
    ) -> str:
        tried = (
            "\n".join(f"- Attempt {i + 1}: {s}" for i, s in enumerate(history))
            or "(none yet — this is the first reflection)"
        )
        files_block = "\n\n".join(
            f"--- {path} ---\n{content[: self._cap]}" for path, content in files.items()
        ) or "(no files provided)"
        user = (
            f"# Goal\n{requirement}\n\n"
            f"# Latest failure (compiler / test output)\n{error_context}\n\n"
            f"# CURRENT content of the failing files (reason about THIS code, do not guess its shape)\n"
            f"{files_block}\n\n"
            f"# Strategies already tried that STILL failed\n{tried}\n\n"
            f"# Your task\nName the exact line(s) and the concrete edit. Give the Coder a "
            f"different, concrete fix strategy."
        )
        # Generous budget: gpt-oss-class reasoners spend most tokens in the hidden
        # thinking channel, so a small cap leaves the visible answer empty.
        return self._client.complete_text(system=_REFLECT_SYSTEM, user=user, max_tokens=3500)
