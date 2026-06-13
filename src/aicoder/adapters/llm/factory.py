"""Pick the LLM provider from the environment — the swap point.

    AICODER_LLM_PROVIDER   anthropic (default) | openai | ollama
    AICODER_LLM_MODEL      provider-specific model id (optional)
    AICODER_LLM_BASE_URL   for openai-compatible (default Ollama localhost)
    ANTHROPIC_API_KEY      required for anthropic
    OPENAI_API_KEY         optional for openai-compatible (Ollama ignores it)
"""

from __future__ import annotations

import os

from aicoder.adapters.llm.base import LLMClient


def build_llm_from_env() -> LLMClient:
    provider = os.environ.get("AICODER_LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("AICODER_LLM_MODEL")

    if provider == "anthropic":
        from aicoder.adapters.llm.anthropic_client import DEFAULT_MODEL, AnthropicClient

        return AnthropicClient(model or DEFAULT_MODEL)

    if provider in ("openai", "ollama", "openai-compatible"):
        from aicoder.adapters.llm.openai_client import DEFAULT_MODEL, OpenAICompatibleClient

        return OpenAICompatibleClient(model or DEFAULT_MODEL)

    raise ValueError(f"unknown AICODER_LLM_PROVIDER: {provider!r}")
