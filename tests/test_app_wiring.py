"""The composition root wires real adapters without touching the network.

Uses the openai-compatible provider so no API key is required just to construct
the object graph.
"""

from __future__ import annotations

from pathlib import Path

from aicoder.app import build_orchestrator
from aicoder.application.orchestrator import Orchestrator

_PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "msfw.yaml"


def test_build_orchestrator_constructs(monkeypatch) -> None:
    monkeypatch.setenv("AICODER_LLM_PROVIDER", "ollama")
    orch = build_orchestrator(_PROFILE)
    assert isinstance(orch, Orchestrator)
