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
