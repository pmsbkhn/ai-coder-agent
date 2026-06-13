"""Validate-and-repair: the core robustness primitive for weaker models.

Ask the model for JSON, validate against a Pydantic model, and on failure feed
the validation errors back for a bounded number of repair attempts. A strong
model passes first try; a weak one usually self-corrects within one retry. This
is what lets the harness stay reliable as model IQ drops.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from aicoder.adapters.llm.base import LLMClient, LLMError

T = TypeVar("T", bound=BaseModel)


def generate_structured(
    client: LLMClient,
    *,
    system: str,
    user: str,
    model_cls: type[T],
    retries: int = 1,
) -> T:
    schema = model_cls.model_json_schema()
    tool_name = f"emit_{model_cls.__name__.lower()}"
    current_user = user
    last_error: Exception | None = None

    for _ in range(retries + 1):
        data = client.complete_json(
            system=system, user=current_user, json_schema=schema, tool_name=tool_name
        )
        try:
            return model_cls.model_validate(data)
        except ValidationError as exc:
            last_error = exc
            current_user = (
                f"{user}\n\nYour previous output failed validation:\n{exc}\n"
                "Return corrected JSON that satisfies the schema."
            )

    raise LLMError(
        f"structured output for {model_cls.__name__} invalid after "
        f"{retries + 1} attempt(s): {last_error}"
    )
