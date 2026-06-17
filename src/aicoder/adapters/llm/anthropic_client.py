"""Anthropic provider — structured output via forced tool-use (most reliable)."""

from __future__ import annotations

import os

from anthropic import Anthropic

from aicoder.adapters.llm.base import LLMError

DEFAULT_MODEL = "claude-sonnet-4-6"  # cost/quality sweet spot for a coding agent
_DEFAULT_CONTEXT_TOKENS = 200_000     # Claude models — large window; the guard rarely fires


class AnthropicClient:
    def __init__(
        self, model: str = DEFAULT_MODEL, *, max_tokens: int = 4096,
        context_tokens: int = _DEFAULT_CONTEXT_TOKENS,
    ) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self._client = Anthropic(api_key=api_key)
        self.model = model
        self._max_tokens = max_tokens
        # Usable context window for the prompt-budget guard (structured.py).
        self.context_tokens = context_tokens

    def complete_json(
        self, *, system: str, user: str, json_schema: dict, tool_name: str = "emit"
    ) -> dict:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {
                    "name": tool_name,
                    "description": "Emit the structured result for this step.",
                    "input_schema": json_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise LLMError("Anthropic returned no tool_use block")

    def complete_text(self, *, system: str, user: str, max_tokens: int = 2048) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content)
