"""Design-step quality eval — "which analysis step is most wrong?".

The Designer emits the whole DesignSpec in ONE call, so the design-flow steps (Bước 1–5)
are not separate executions; this measures quality by ATTRIBUTION. It runs the design
phase faithfully N times on one structured intake (propose → deterministic heal → adversarial
review, exactly like the orchestrator), then an LLM judge scores each step 1–5 and maps every
linter finding + reviewer concern to the step it ORIGINATES from (the symptom often surfaces
downstream of its cause — e.g. a wrong cap number in a test traces back to an under-specified
invariant). Aggregated over the N runs it ranks the steps weakest-first.

Steps graded (1–5 are the design-flow appendix; 6 is the agent's M07 oracle synthesis):
  1 Requirement discovery   2 Domain modeling   3 Strategic design (boundaries)
  4 Decomposition/physical  5 Integration design  6 Acceptance oracle & numeric consistency

Usage:
    AICODER_LLM_PROVIDER=ollama AICODER_LLM_MODEL=gpt-oss:120b AICODER_LLM_NUM_CTX=32768 \\
      uv run python eval/design_step_eval.py --requirements <intake>.yaml --runs 8

The judge model is the `grader` role (AICODER_GRADER_* → AICODER_LLM_*); use a DIFFERENT,
stronger model than the Designer for a less self-serving grade when you can.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from aicoder.adapters.designer_llm import LLMDesigner  # noqa: E402
from aicoder.adapters.llm.factory import build_llm_from_env  # noqa: E402
from aicoder.adapters.llm.structured import generate_structured  # noqa: E402
from aicoder.adapters.reviewer_llm import LLMReviewer  # noqa: E402
from aicoder.application.design_lint import lint_design, render_contracts  # noqa: E402
from aicoder.application.profile import load_profile  # noqa: E402
from aicoder.application.requirement_spec import load_requirement_spec  # noqa: E402

_STEPS = {
    1: "Requirement discovery (US→UC, actors, NFR extraction, glossary)",
    2: "Domain modeling (commands/events/aggregates/policies/read-models, invariants)",
    3: "Strategic design (bounded contexts + typed context map)",
    4: "Decomposition / physical architecture (service vs module, data ownership)",
    5: "Integration design (sync APIs, async events, sagas, retry/idempotency/DLQ)",
    6: "Acceptance oracle & numeric/unit consistency (the locked TC cases)",
}


# --------------------------------------------------------------------------- #
# Judge output schema
# --------------------------------------------------------------------------- #

class StepGrade(BaseModel):
    step: int                                   # 1..6
    score: int                                  # 1 (broken) .. 5 (excellent)
    rationale: str = ""


class Attribution(BaseModel):
    finding: str                                # a linter/reviewer concern (verbatim-ish)
    step: int                                   # the step it ORIGINATES from (1..6)


class DesignGrade(BaseModel):
    steps: list[StepGrade] = Field(default_factory=list)
    attributions: list[Attribution] = Field(default_factory=list)
    worst_step: int = 0
    summary: str = ""


_GRADER_SYSTEM = (
    "You are a senior architect grading the OUTPUT of an automated design phase against a "
    "fixed 6-step analysis-and-design process. Score each step 1–5 (1=broken/contradictory, "
    "3=usable with gaps, 5=correct and complete) with a one-line rationale. Then take the "
    "linter findings and reviewer concerns provided and map EACH to the single step it "
    "ORIGINATES from — the root cause, not where it surfaced (e.g. a wrong discount number in "
    "a test usually originates in step 2 if an invariant left the rule unspecified, or step 6 "
    "if the test itself is internally inconsistent). Pick worst_step = the lowest-quality step. "
    "Be strict and specific. The steps:\n"
    + "\n".join(f"  {k}. {v}" for k, v in _STEPS.items())
)


def _grade(grader, requirement: str, design, lint_issues: list[str], concerns: list[str]) -> DesignGrade:
    findings = "\n".join(f"- {x}" for x in [*lint_issues, *concerns]) or "- (none)"
    user = (
        f"# Requirement (binding contract)\n{requirement}\n\n"
        f"# Produced design (contracts digest: interfaces · invariants · domain · key flows · "
        f"event flow · integration · tests)\n{render_contracts(design)}\n\n"
        f"# Linter findings + reviewer concerns to attribute to a step\n{findings}\n\n"
        f"# Task\nScore steps 1–6, attribute every finding to its origin step, set worst_step."
    )
    return generate_structured(grader, system=_GRADER_SYSTEM, user=user,
                               model_cls=DesignGrade, retries=1)


# --------------------------------------------------------------------------- #
# Faithful design phase (mirrors orchestrator._repair_design + the review)
# --------------------------------------------------------------------------- #

def _run_design_once(designer: LLMDesigner, reviewer: LLMReviewer, profile, req_spec):
    prose = req_spec.to_prose()
    design = designer.propose_design(prose, repo_map="", analysis=None, spec=req_spec)
    lint = lint_design(design, req_spec)
    repairs = 0
    while lint and repairs < profile.design.max_design_repairs:
        design = designer.revise_design(prose, "", design, lint, analysis=None, spec=req_spec)
        lint = lint_design(design, req_spec)
        repairs += 1
    tests = [f"{t.id} [{t.title}] {t.spec}\n{t.content}".strip() for t in design.all_tests()]
    review = reviewer.review_tests(prose, design.summary, tests, contracts=render_contracts(design))
    return design, lint, review, repairs


# --------------------------------------------------------------------------- #
# Aggregation (pure — unit-tested)
# --------------------------------------------------------------------------- #

def aggregate(grades: list[DesignGrade], n_steps: int = 6) -> list[dict]:
    """Per-step rollup over N runs, sorted weakest-first (lowest mean score). Each row:
    step, name, mean_score, n_scores, flaws (attributions), times_worst."""
    rows: list[dict] = []
    for step in range(1, n_steps + 1):
        scores = [s.score for g in grades for s in g.steps if s.step == step]
        flaws = sum(1 for g in grades for a in g.attributions if a.step == step)
        worst = sum(1 for g in grades if g.worst_step == step)
        mean = round(sum(scores) / len(scores), 2) if scores else None
        rows.append({"step": step, "name": _STEPS.get(step, "?"), "mean_score": mean,
                     "n_scores": len(scores), "flaws": flaws, "times_worst": worst})
    # weakest first: lowest mean score, then most flaws. None scores sort last.
    rows.sort(key=lambda r: (r["mean_score"] if r["mean_score"] is not None else 99,
                             -r["flaws"]))
    return rows


def _render_report(rows: list[dict], n: int, grades: list[DesignGrade]) -> str:
    out = [f"# Design-step quality — {n} run(s)\n",
           "Steps ranked weakest-first (mean score 1–5; flaws = findings attributed to the step).\n",
           "| Rank | Step | Mean | Flaws | Times worst |", "|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        mean = r["mean_score"] if r["mean_score"] is not None else "—"
        out.append(f"| {i} | {r['step']}. {r['name']} | {mean} | {r['flaws']} | {r['times_worst']} |")
    out.append("")
    out.append("## Per-run summaries\n")
    for i, g in enumerate(grades, 1):
        out.append(f"- run {i}: worst=step {g.worst_step}; {g.summary}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="design_step_eval")
    p.add_argument("--requirements", required=True, help="structured intake YAML (US + NFR)")
    p.add_argument("--profile", default=str(_REPO_ROOT / "profiles" / "msfw.yaml"))
    p.add_argument("--runs", type=int, default=8)
    p.add_argument("--out", default=str(_REPO_ROOT / "eval" / "design-step-report.md"))
    args = p.parse_args(argv)

    profile = load_profile(args.profile)
    req_spec = load_requirement_spec(args.requirements)
    designer = LLMDesigner(build_llm_from_env(role="designer"), profile)
    reviewer = LLMReviewer(build_llm_from_env(role="reviewer"), profile)
    grader = build_llm_from_env(role="grader")

    grades: list[DesignGrade] = []
    for i in range(1, args.runs + 1):
        print(f"[run {i}/{args.runs}] designing…", flush=True)
        design, lint, review, repairs = _run_design_once(designer, reviewer, profile, req_spec)
        print(f"[run {i}/{args.runs}] repairs={repairs} lint={len(lint)} "
              f"concerns={len(review.concerns)}; grading…", flush=True)
        grades.append(_grade(grader, req_spec.to_prose(), design, lint, review.concerns))

    rows = aggregate(grades)
    report = _render_report(rows, args.runs, grades)
    Path(args.out).write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"(written to {args.out})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
