"""OpenAI-compatible provider — works against Ollama / vLLM / any /v1 endpoint.

Structured output uses json_object mode with the schema embedded in the prompt.
Combined with the validate-and-repair loop in structured.py, this is what makes
a weaker local model (e.g. Qwen2.5-Coder-14B on a 12GB GPU) usable: malformed
output is rejected and re-requested rather than trusted.
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

from aicoder.adapters.llm.base import LLMError

DEFAULT_MODEL = "qwen2.5-coder:14b"  # fits ~12GB VRAM at Q4; 32B/70B do not
DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama


class OpenAICompatibleClient:
    def __init__(
        self, model: str = DEFAULT_MODEL, *, base_url: str | None = None, max_tokens: int = 4096
    ) -> None:
        self._client = OpenAI(
            base_url=base_url or os.environ.get("AICODER_LLM_BASE_URL", DEFAULT_BASE_URL),
            api_key=os.environ.get("OPENAI_API_KEY", "ollama"),  # Ollama ignores the key
        )
        self.model = model
        self._max_tokens = max_tokens

    def complete_json(
        self, *, system: str, user: str, json_schema: dict, tool_name: str = "emit"
    ) -> dict:
        system_with_schema = (
            f"{system}\n\nReturn ONLY a JSON object conforming to this JSON Schema:\n"
            f"{json.dumps(json_schema)}"
        )
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_with_schema},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"model returned non-JSON content: {exc}") from exc

    def complete_text(self, *, system: str, user: str, max_tokens: int = 2048) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
