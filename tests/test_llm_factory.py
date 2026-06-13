"""The provider swap is env-driven (the answer to "what if I switch to a local model")."""

from __future__ import annotations

import pytest

from aicoder.adapters.llm.base import LLMError
from aicoder.adapters.llm.factory import build_llm_from_env


def test_openai_provider_selected_without_key(monkeypatch) -> None:
    monkeypatch.setenv("AICODER_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AICODER_LLM_MODEL", "qwen2.5-coder:14b")
    client = build_llm_from_env()
    assert client.model == "qwen2.5-coder:14b"


def test_anthropic_requires_key(monkeypatch) -> None:
    monkeypatch.setenv("AICODER_LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError):
        build_llm_from_env()


def test_unknown_provider_rejected(monkeypatch) -> None:
    monkeypatch.setenv("AICODER_LLM_PROVIDER", "gpt5-on-toast")
    with pytest.raises(ValueError):
        build_llm_from_env()
