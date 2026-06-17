"""Prompt-budget guard (anti silent-truncation). estimate/prompt_fits + the warning
generate_structured emits when the prompt likely overflows the model's window."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from aicoder.adapters.llm.budget import estimate_tokens, prompt_fits
from aicoder.adapters.llm.structured import generate_structured


class _Tiny(BaseModel):
    summary: str = ""


class _LLM:
    """A fake client; sets `context_tokens` only when a window is given."""
    model = "fake"

    def __init__(self, ctx: int | None = None) -> None:
        if ctx is not None:
            self.context_tokens = ctx

    def complete_json(self, *, system, user, json_schema, tool_name="emit") -> dict:
        return {"summary": "ok"}

    def complete_text(self, *, system, user, max_tokens=2048) -> str:  # pragma: no cover
        return ""


# --- pure helpers -------------------------------------------------------------

def test_estimate_tokens_is_roughly_chars_over_four() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100


def test_prompt_fits_unknown_budget_never_guards() -> None:
    fits, est, usable = prompt_fits("a" * 100000, "b" * 100000, context_tokens=None)
    assert fits is True and usable == 0 and est > 0


def test_prompt_fits_detects_overflow() -> None:
    fits, _, _ = prompt_fits("x" * 40000, "y" * 40000, context_tokens=4096)
    assert fits is False


# --- the guard inside generate_structured -------------------------------------

def test_warns_and_still_returns_on_overflow(caplog) -> None:
    client = _LLM(ctx=256)
    with caplog.at_level(logging.WARNING, logger="aicoder.llm"):
        out = generate_structured(client, system="s" * 20000, user="u" * 20000, model_cls=_Tiny)
    assert out.summary == "ok"                     # guard warns, never blocks
    assert any("TRUNCATED" in r.getMessage() for r in caplog.records)


def test_no_warning_when_prompt_fits(caplog) -> None:
    client = _LLM(ctx=200_000)
    with caplog.at_level(logging.WARNING, logger="aicoder.llm"):
        generate_structured(client, system="s", user="u", model_cls=_Tiny)
    assert not [r for r in caplog.records if "TRUNCATED" in r.getMessage()]


def test_no_guard_when_client_exposes_no_context_tokens(caplog) -> None:
    client = _LLM(ctx=None)  # no context_tokens attribute at all
    with caplog.at_level(logging.WARNING, logger="aicoder.llm"):
        generate_structured(client, system="s" * 20000, user="u" * 20000, model_cls=_Tiny)
    assert not [r for r in caplog.records if "TRUNCATED" in r.getMessage()]
