"""LLMDesigner — DesignPort backed by a (provider-agnostic) LLMClient.

The design-first phase (see docs/architecture/07): given a requirement + the repo
map skeleton, produce a *delta* DesignSpec — affected components, interface/contract
changes, light ADR notes, and **executable proposed tests** that encode acceptance.
Runs on the reasoner role (AICODER_DESIGNER_*); schema-validated like the Planner.
Slice 1 only PRODUCES the spec; approval + locking the tests as the oracle are
later slices.
"""

from __future__ import annotations

from aicoder.adapters.llm.base import LLMClient
from aicoder.adapters.llm.structured import generate_structured
from aicoder.application.profile import ProjectProfile
from aicoder.domain.models import AnalysisSpec, DesignSpec

_SYSTEM = """You are the Designer of an autonomous coding agent on an MSFW project
(Java 21 / Spring Boot 4, strict Hexagonal / Ports & Adapters, DDD).

Before any code is written, produce a delta design as an umbrella ARCHITECTURE
DESCRIPTION plus one TECH SPEC PER BOUNDED CONTEXT (rule: 1 bounded context = 1
tech spec; most changes touch exactly ONE context → exactly one tech spec).

Top level (the Architecture Description):
- summary: what changes across the system, in 1-3 sentences.
- decisions: cross-cutting / integration decisions worth recording (terse; may be empty).
- tech_specs: one entry per affected bounded context.

Each tech_spec (one bounded context):
- bounded_context: the context name (e.g. "Orders", "Payment").
- summary: what changes in this context.
- affected: the components / files it touches (use the Repo Map).
- interface_changes: concrete contract/signature deltas (e.g. a new method on a port).
- adr_notes: short rationale / decisions for this context.
- test_plan: EXECUTABLE acceptance tests that define "done" FOR THIS CONTEXT. For
  each, give the test file `path` (under src/test/...), full JUnit5 `content`, and a
  one-line `rationale`. Tests are the binding spec — concrete, verifiable, covering
  the happy path AND key edge/error cases, asserting observable behavior (not
  implementation details). Respect MSFW idioms.

Design the smallest change that satisfies the requirement; do not over-engineer.
Do not split one cohesive context into several tech specs.

When an ANALYSIS section is provided (the upstream Analyst already pinned down WHAT
to build), treat its acceptance criteria as the binding contract: every criterion
MUST be covered by at least one proposed test, and your design must honor the stated
assumptions. Do not contradict or silently widen the analyzed scope.
"""


def _format_analysis(analysis: AnalysisSpec) -> str:
    """Render the upstream AnalysisSpec as a prompt section so the proposed tests
    trace to the explicit, human-visible acceptance criteria (ADR-08 Slice 3)."""
    def _lines(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items) if items else "- (none)"
    return (
        f"\n\n# Analysis (already approved — design MUST satisfy this)\n"
        f"Restatement: {analysis.restatement}\n\n"
        f"Assumptions (honor these):\n{_lines(analysis.assumptions)}\n\n"
        f"Acceptance criteria (each MUST be covered by a proposed test):\n"
        f"{_lines(analysis.acceptance_criteria)}"
    )


class LLMDesigner:
    def __init__(
        self, client: LLMClient, profile: ProjectProfile, *, max_repo_map_chars: int = 12000
    ) -> None:
        self._client = client
        self._profile = profile
        self._cap = max_repo_map_chars

    def propose_design(
        self, requirement: str, repo_map: str, analysis: AnalysisSpec | None = None
    ) -> DesignSpec:
        user = (
            f"# Requirement\n{requirement}\n\n"
            f"# Repo Map (skeleton — request full symbols later via zoom-in)\n"
            f"{repo_map[: self._cap]}"
        )
        if analysis is not None:
            user += _format_analysis(analysis)
        return generate_structured(
            self._client, system=_SYSTEM, user=user, model_cls=DesignSpec, retries=1
        )
