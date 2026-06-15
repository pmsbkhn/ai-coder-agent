"""Plan-free complexity tiering (ADR-08 Slice 4): a deterministic heuristic that
`auto` mode uses to skip the reasoning phases on clearly-trivial changes. It tiers on
SCOPE (multi-step) and VAGUENESS, not implementation size — and leans COMPLEX, since a
false 'trivial' (skipping analysis on a vague req) is worse than a false 'complex'."""

from __future__ import annotations

import pytest

from aicoder.application.tiering import estimate_complexity

_TRIVIAL = [
    "x",
    "Add a nullable note field to Order and include it on the OrderPlaced event.",
    "Rename the field amount to total on Order.",
    "Set the default page size to 50.",
]
_COMPLEX = [
    "Make orders better for our customers.",                 # vague: "better"
    "Let customers manage their orders after placing them.",  # multi-step: "manage"
    "Refactor and migrate the order workflow.",               # multi-step: refactor/migrate/workflow
    # multiple concerns across several sentences:
    "Add a CANCELLED status. Cancelling publishes OrderCancelled. Only PLACED orders "
    "can be cancelled. Refund the payment when an order is cancelled.",
]


@pytest.mark.parametrize("req", _TRIVIAL)
def test_trivial_requirements_are_not_complex(req: str) -> None:
    assert estimate_complexity(req).is_complex is False


@pytest.mark.parametrize("req", _COMPLEX)
def test_nontrivial_requirements_are_complex(req: str) -> None:
    assert estimate_complexity(req).is_complex is True


def test_vagueness_alone_trips_complex() -> None:
    # short + crisp-looking but aspirational → must be flagged (the danger case).
    s = estimate_complexity("Improve the checkout.")
    assert s.is_complex is True and "improve" in s.vague_hits


def test_payload_is_transparent() -> None:
    p = estimate_complexity("Let customers manage their orders.").as_payload()
    assert p["is_complex"] is True
    assert "manage" in p["multistep_hits"]
    assert set(p) == {"is_complex", "words", "sentences", "multistep_hits", "vague_hits"}
