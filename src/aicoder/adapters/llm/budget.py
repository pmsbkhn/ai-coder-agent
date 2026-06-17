"""Prompt-size guard — detect (and loudly warn about) a prompt likely to overflow the
model's context window.

Silent truncation on a small-context local model is the failure this prevents: when the
assembled prompt (system + user) is larger than the model's window, the provider quietly
drops the overflow, so the model never sees part of the binding contract and "forgets" it
— with no error. A loud warning turns that silent failure into a visible one.

Heuristic only — ≈4 characters per token. Enough to flag "this will not fit"; it is not a
billing-grade tokenizer. The guard never raises and never trims: it warns, so the operator
can raise AICODER_LLM_NUM_CTX or shrink inputs.
"""

from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def prompt_fits(
    system: str, user: str, *, context_tokens: int | None, reserve_output: int = 4096
) -> tuple[bool, int, int]:
    """Return (fits, estimated_prompt_tokens, usable_budget).

    `context_tokens` is the model's window (a client may expose it as `.context_tokens`);
    `reserve_output` is held back for the model's own response. When `context_tokens` is
    falsy the budget is unknown → (True, est, 0): no guard, so large-window providers and
    test fakes are unaffected."""
    prompt = estimate_tokens(system) + estimate_tokens(user)
    if not context_tokens:
        return True, prompt, 0
    usable = max(0, context_tokens - reserve_output)
    return prompt <= usable, prompt, usable
