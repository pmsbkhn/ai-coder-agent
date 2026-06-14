"""LLMReviewer — ReviewPort: an adversarial critique of a proposed TestPlan (M07
Slice 4). Runs on the `reviewer` role (AICODER_REVIEWER_*) — ideally a different
model from the Designer, so the design can't rubber-stamp its own tests. The point
is to catch a WEAK oracle (trivially-satisfiable, missing edge cases, asserting
implementation details, or not actually tied to the requirement) BEFORE it is
locked and the Coder starts implementing against it.
"""

from __future__ import annotations

from aicoder.adapters.llm.base import LLMClient
from aicoder.adapters.llm.structured import generate_structured
from aicoder.application.profile import ProjectProfile
from aicoder.domain.models import TestReview

_SYSTEM = """You are an adversarial Test Reviewer for an autonomous coding agent.
You are given a requirement, a one-line design summary, and PROPOSED test cases
that are about to become the immutable acceptance oracle. Your job is to find
weaknesses BEFORE they are locked.

Judge ONLY the tests, skeptically:
- Do they actually constrain the requirement, or would a wrong/empty implementation
  still pass? (trivially satisfiable, no meaningful assertions, asserting constants)
- Do they cover the key edge/error cases the requirement implies, not just the happy path?
- Do they assert observable behavior rather than implementation details?
- Are they internally consistent and compilable in intent?

Set ok=true ONLY if the tests are a faithful, non-trivial spec of the requirement.
List concrete `concerns` for every weakness (empty if none). Be terse and specific.
"""


class LLMReviewer:
    def __init__(self, client: LLMClient, profile: ProjectProfile, *, max_chars: int = 12000) -> None:
        self._client = client
        self._profile = profile
        self._cap = max_chars

    def review_tests(self, requirement: str, design_summary: str, tests: list[str]) -> TestReview:
        block = "\n\n".join(f"--- test {i + 1} ---\n{t}" for i, t in enumerate(tests)) or "(none)"
        user = (
            f"# Requirement\n{requirement}\n\n"
            f"# Design summary\n{design_summary}\n\n"
            f"# Proposed tests (the candidate oracle)\n{block[: self._cap]}\n\n"
            f"# Your task\nReview the tests adversarially; return ok + concerns."
        )
        return generate_structured(
            self._client, system=_SYSTEM, user=user, model_cls=TestReview, retries=1
        )
