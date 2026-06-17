"""Validate-and-repair: the core robustness primitive for weaker models.

Ask the model for JSON, validate against a Pydantic model, and on failure feed
the validation errors back for a bounded number of repair attempts. A strong
model passes first try; a weak one usually self-corrects within one retry. This
is what lets the harness stay reliable as model IQ drops.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from aicoder.adapters.llm.base import LLMClient, LLMError
from aicoder.adapters.llm.budget import prompt_fits

T = TypeVar("T", bound=BaseModel)

_log = logging.getLogger("aicoder.llm")


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

    # Context-budget guard: if the assembled prompt likely exceeds the model's usable
    # window, WARN loudly rather than let the provider silently truncate it (which would
    # make the model "forget" part of the contract with no error). The schema is part of
    # the system prompt for json_object providers, so count it too.
    ctx = getattr(client, "context_tokens", None)
    fits, est, usable = prompt_fits(system + str(schema), user, context_tokens=ctx)
    if not fits:
        _log.warning(
            "prompt for %s (~%d tokens) likely exceeds the model's usable context "
            "(~%d of %s tokens) — output may be SILENTLY TRUNCATED. Raise "
            "AICODER_LLM_NUM_CTX or shrink inputs (e.g. the repo-map cap).",
            model_cls.__name__, est, usable, ctx,
        )

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
