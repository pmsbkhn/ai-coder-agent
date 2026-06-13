"""LLMClient protocol — the seam both providers implement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class LLMError(Exception):
    """Any failure producing usable output from a model."""


@runtime_checkable
class LLMClient(Protocol):
    model: str

    def complete_json(
        self, *, system: str, user: str, json_schema: dict, tool_name: str = "emit"
    ) -> dict:
        """Return a JSON object the model produced for the given schema.

        Implementations use the most reliable structured-output mechanism the
        provider offers (Anthropic tool-use; OpenAI json_object mode). Validation
        against a Pydantic model is the CALLER's job (see structured.py).
        """
        ...

    def complete_text(self, *, system: str, user: str, max_tokens: int = 2048) -> str:
        """Free-form text completion (used by the Coder / reflection step)."""
        ...
