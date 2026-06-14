"""Pick the LLM provider/model from the environment — the swap point.

Two layers of env vars, resolved most-specific first:

  Per-role (optional)         Shared fallback        Meaning
  -------------------------   --------------------   -----------------------------
  AICODER_PLANNER_PROVIDER    AICODER_LLM_PROVIDER   anthropic (default)|openai|ollama
  AICODER_PLANNER_MODEL       AICODER_LLM_MODEL      provider-specific model id
  AICODER_CODER_PROVIDER      AICODER_LLM_PROVIDER
  AICODER_CODER_MODEL         AICODER_LLM_MODEL

This lets the Planner (design/reasoning) and the Coder (code generation, many heal
iterations) run on DIFFERENT models — e.g. a strong reasoner for planning and a fast
code model for coding — without a code change. Calling build_llm_from_env() with no
role keeps the original single-model behaviour exactly.

  AICODER_LLM_BASE_URL   for openai-compatible (default Ollama localhost)
  ANTHROPIC_API_KEY      required for anthropic
  OPENAI_API_KEY         optional for openai-compatible (Ollama ignores it)
"""

from __future__ import annotations

import os

from aicoder.adapters.llm.base import LLMClient


def _resolve(role: str | None, suffix: str) -> str | None:
    """AICODER_{ROLE}_{SUFFIX} if set, else AICODER_LLM_{SUFFIX}, else None."""
    if role:
        specific = os.environ.get(f"AICODER_{role.upper()}_{suffix}")
        if specific:
            return specific
    return os.environ.get(f"AICODER_LLM_{suffix}")


def build_llm_from_env(role: str | None = None) -> LLMClient:
    """Build an LLM client for a given role ("planner"/"coder"), or the shared one.

    The role only selects which env vars win; an unset role-specific var falls back
    to the shared AICODER_LLM_* var, which falls back to the provider default.
    """
    provider = (_resolve(role, "PROVIDER") or "anthropic").lower()
    model = _resolve(role, "MODEL")

    if provider == "anthropic":
        from aicoder.adapters.llm.anthropic_client import DEFAULT_MODEL, AnthropicClient

        return AnthropicClient(model or DEFAULT_MODEL)

    if provider in ("openai", "ollama", "openai-compatible"):
        from aicoder.adapters.llm.openai_client import DEFAULT_MODEL, OpenAICompatibleClient

        return OpenAICompatibleClient(model or DEFAULT_MODEL)

    raise ValueError(f"unknown LLM provider: {provider!r}")
