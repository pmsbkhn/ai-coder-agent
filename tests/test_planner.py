"""Planner + structured-output robustness — hermetic (no network, no API key).

Proves the validate-and-repair loop that protects against weak models: a client
that first emits invalid JSON then valid JSON must yield a Plan; one that never
complies must raise instead of returning garbage.
"""

from __future__ import annotations

import pytest

from aicoder.adapters.llm.base import LLMError
from aicoder.adapters.llm.structured import generate_structured
from aicoder.adapters.planner_llm import LLMPlanner
from aicoder.application.profile import load_profile
from aicoder.domain.models import Plan
from pathlib import Path

_PROFILE = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml")

_VALID = {
    "tasks": [
        {"id": "t1", "description": "Add field", "target_files": ["A.java"], "constraints": []}
    ],
    "rationale": "because",
}


class FakeLLM:
    """Returns queued JSON payloads, one per complete_json call."""

    model = "fake"

    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = list(payloads)
        self.calls = 0

    def complete_json(self, *, system, user, json_schema, tool_name="emit") -> dict:
        self.calls += 1
        return self._payloads.pop(0)

    def complete_text(self, *, system, user, max_tokens=2048) -> str:  # pragma: no cover
        return ""


def test_planner_returns_valid_plan() -> None:
    planner = LLMPlanner(FakeLLM([_VALID]), _PROFILE)
    plan = planner.generate_plan("add a description field", "# Repo Map\nclass A")
    assert isinstance(plan, Plan)
    assert plan.tasks[0].id == "t1"


def test_structured_repairs_invalid_then_valid() -> None:
    client = FakeLLM([{"tasks": "not-a-list"}, _VALID])  # invalid, then corrected
    plan = generate_structured(
        client, system="s", user="u", model_cls=Plan, retries=1
    )
    assert plan.tasks[0].id == "t1"
    assert client.calls == 2  # it retried exactly once


def test_structured_raises_when_never_valid() -> None:
    client = FakeLLM([{"tasks": "bad"}, {"tasks": 123}])
    with pytest.raises(LLMError):
        generate_structured(client, system="s", user="u", model_cls=Plan, retries=1)
