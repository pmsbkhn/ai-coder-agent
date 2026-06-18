"""Unit test for the design-step eval's pure aggregation (no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from design_step_eval import Attribution, DesignGrade, StepGrade, aggregate  # noqa: E402


def test_aggregate_ranks_weakest_step_first_and_counts_flaws() -> None:
    grades = [
        DesignGrade(
            steps=[StepGrade(step=2, score=2), StepGrade(step=6, score=1), StepGrade(step=3, score=5)],
            attributions=[Attribution(finding="x", step=6), Attribution(finding="y", step=6)],
            worst_step=6),
        DesignGrade(
            steps=[StepGrade(step=2, score=3), StepGrade(step=6, score=2), StepGrade(step=3, score=5)],
            attributions=[Attribution(finding="z", step=2)],
            worst_step=6),
    ]
    rows = aggregate(grades)
    by_step = {r["step"]: r for r in rows}

    # step 6 is weakest (mean 1.5) -> ranked first; both runs flagged it worst; 2 flaws.
    assert rows[0]["step"] == 6
    assert by_step[6]["mean_score"] == 1.5
    assert by_step[6]["flaws"] == 2 and by_step[6]["times_worst"] == 2
    # scored-but-better steps
    assert by_step[2]["mean_score"] == 2.5 and by_step[2]["flaws"] == 1
    assert by_step[3]["mean_score"] == 5.0
    # unscored steps (1, 4, 5) have no mean and sort last
    assert by_step[1]["mean_score"] is None and by_step[1]["n_scores"] == 0
    assert rows[-1]["mean_score"] is None


def test_aggregate_empty_is_all_none() -> None:
    rows = aggregate([])
    assert len(rows) == 6
    assert all(r["mean_score"] is None and r["flaws"] == 0 for r in rows)
