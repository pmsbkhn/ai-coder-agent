"""Plan-free complexity tiering (ADR-08 Slice 4).

The pre-implementation reasoning phases (analysis, design) are the expensive part of
a run — a reasoner call plus a human gate each. For a trivial, crisply-specified
change they are overkill. `auto` mode uses a cheap, DETERMINISTIC heuristic over the
requirement text to skip them on trivial changes and run them on non-trivial ones;
`always` runs unconditionally, `off` never runs. The decision is transparent (the
signals are logged via a TIERING event), never a black-box LLM call — consistent with
the project's deterministic-first stance.

Why text, not file/task count (the old ADR-07 `_is_complex`): analysis & design run
BEFORE the plan, so there is no plan to count. And implementation size is the wrong
axis anyway — a SHORT, VAGUE requirement ("make orders better") is exactly the one
that needs analysis, while a length-only heuristic would wave it through. So we tier
on two signals that matter pre-plan: multi-step SCOPE and VAGUENESS.

Bias: a false "complex" only wastes a little cost (a phase runs that wasn't strictly
needed); a false "trivial" skips analysis on an under-specified requirement and builds
the wrong thing. So when in doubt we lean COMPLEX — `auto` skips only clearly-trivial
changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Multi-step / broad-scope intent: a change that spans operations, lifecycle, or
# several things benefits from explicit analysis + design.
_MULTISTEP_WORDS = (
    "manage", "workflow", "lifecycle", "orchestrate", "multiple", "several",
    "various", "redesign", "refactor", "migrate", "saga", "integrate", "end-to-end",
    "and then", "as well as", "pipeline", "across the", "report", "dashboard",
)
# Vague intent: aspiration without a concrete, testable change. These are the
# dangerous "specification gap" requirements — they MUST be analyzed.
_VAGUE_WORDS = (
    "better", "improve", "enhance", "optimi", "user-friendly", "robust",
    "scalable", "nicer", "cleaner", "somehow", "as needed", "etc",
)

_WORD_THRESHOLD = 30          # long prose ⇒ likely multi-faceted
_SENTENCE_THRESHOLD = 2       # >2 sentences ⇒ likely multiple concerns


@dataclass
class ComplexitySignals:
    words: int
    sentences: int
    multistep_hits: list[str] = field(default_factory=list)
    vague_hits: list[str] = field(default_factory=list)

    @property
    def is_complex(self) -> bool:
        return bool(
            self.words >= _WORD_THRESHOLD
            or self.sentences > _SENTENCE_THRESHOLD
            or self.multistep_hits
            or self.vague_hits
        )

    def as_payload(self) -> dict:
        return {
            "is_complex": self.is_complex,
            "words": self.words,
            "sentences": self.sentences,
            "multistep_hits": self.multistep_hits,
            "vague_hits": self.vague_hits,
        }


def estimate_complexity(requirement: str) -> ComplexitySignals:
    """Deterministic, plan-free tiering signal for a requirement. Leans COMPLEX."""
    text = requirement.strip()
    low = text.lower()
    words = len(text.split())
    sentences = len([s for s in re.split(r"[.;!?\n]+", text) if s.strip()])
    multistep = sorted({w for w in _MULTISTEP_WORDS if w in low})
    vague = sorted({w for w in _VAGUE_WORDS if w in low})
    return ComplexitySignals(
        words=words, sentences=sentences, multistep_hits=multistep, vague_hits=vague
    )
