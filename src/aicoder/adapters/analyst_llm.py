"""LLMAnalyst — AnalysisPort backed by a (provider-agnostic) LLMClient.

The analysis phase (see docs/architecture/08): given a prose business requirement
that has NOT yet been broken into clear use cases + the repo map skeleton, produce
an explicit AnalysisSpec — a restatement, the assumptions taken, open questions /
ambiguities, acceptance criteria, and an ambiguity verdict — BEFORE any design.
Runs on the reasoner role (AICODER_ANALYST_*); schema-validated like the Planner.
This is the step that turns vague prose into something checkable; the orchestrator
gates on `ambiguous` (ADR-08 Slice 2).
"""

from __future__ import annotations

from aicoder.adapters.llm.base import LLMClient
from aicoder.adapters.llm.structured import generate_structured
from aicoder.application.profile import ProjectProfile
from aicoder.domain.models import AnalysisSpec

_SYSTEM = """You are the Analyst of an autonomous coding agent on an MSFW project
(Java 21 / Spring Boot 4, strict Hexagonal / Ports & Adapters, DDD).

You receive a business requirement written as PROSE — it may be vague, may not be
broken into clear use cases, and may leave decisions implicit. BEFORE any design or
code, make the implicit explicit. Produce:
- restatement: the requirement in your own words — the scope and intent as you
  understand it, in 1-4 sentences.
- assumptions: the concrete assumptions you must take to fill gaps in the prose
  (e.g. defaults, out-of-scope items, chosen behavior where the text is silent).
- open_questions: GENUINE ambiguities a human should resolve — things where a wrong
  guess would build the wrong thing. Omit nitpicks you can responsibly assume.
- acceptance_criteria: observable, verifiable "done" conditions (the basis for the
  later test cases). Each should be checkable, not aspirational.
- ambiguous: the verdict that drives a human clarification gate. Decide with this
  one test — CAN YOU NAME A CONCRETE DELIVERABLE? i.e. the specific entity/component,
  the change to it, and at least one observable behavior you could write a test for.
    * If YES → ambiguous = FALSE, even if refinements remain (max length? API shape?
      extra edge cases?). Those are normal open questions; capture them and proceed on
      stated assumptions. A clear core with detail questions is NOT ambiguous.
    * If NO → the requirement is pure intent with an INVENTED scope (e.g. "make X
      better", "improve Y", "manage Z" with no operations named) → ambiguous = TRUE.
  Litmus: "add a nullable `note` field to Order and put it on OrderPlaced" → FALSE
  (concrete). "make orders better for customers" → TRUE (you had to invent what to
  build). Do not flag a concrete requirement just because details remain, and do not
  rubber-stamp a vague one as clear just to keep moving.

Be decisive about ASSUMPTIONS — state them rather than asking — but be honest about
the VERDICT itself.
"""


class LLMAnalyst:
    def __init__(
        self, client: LLMClient, profile: ProjectProfile, *, max_repo_map_chars: int = 12000
    ) -> None:
        self._client = client
        self._profile = profile
        self._cap = max_repo_map_chars

    def analyze(self, requirement: str, repo_map: str) -> AnalysisSpec:
        user = (
            f"# Requirement (prose)\n{requirement}\n\n"
            f"# Repo Map (skeleton — request full symbols later via zoom-in)\n"
            f"{repo_map[: self._cap]}"
        )
        return generate_structured(
            self._client, system=_SYSTEM, user=user, model_cls=AnalysisSpec, retries=1
        )
