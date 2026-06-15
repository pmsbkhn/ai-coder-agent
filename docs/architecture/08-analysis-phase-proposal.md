# 08 — Proposal / ADR: Explicit Analysis (Requirement-Clarification) Phase

**Status:** **IMPLEMENTED — all 4 slices done** (Analyst role + AnalysisSpec, run
before design; clarification gate on ambiguous requirements; analysis→design hand-off
so the proposed tests trace to the analyzed acceptance criteria; plan-free complexity
tiering shared by the analysis & design phases). Promote to an accepted AD.
**Viewpoint:** Decision. **Complements** ADR-07 (`07-design-first-proposal.md`):
ADR-07 made *design* (HOW) explicit; this makes *analysis* (WHAT) explicit, one phase
earlier, and feeds it forward.

> Like ADR-07, this document is itself the design-before-code artifact it advocates.

## Context — analysis is still implicit

After ADR-07 the pipeline is `requirement → Planner → Designer → Coder → verify`.
But there is no explicit **analysis** step in the classic sense — *understand and
pin down WHAT before deciding HOW*: restate the requirement, surface assumptions,
flag ambiguities / open questions, and derive acceptance criteria. Today the raw
requirement text flows straight into planning/design; "analysis" is folded
implicitly into the Planner (decompose) and Designer (summary + test plan). A
genuinely under-specified requirement is therefore only discovered *after* design
or coding effort is spent — or silently resolved by the model's unstated guesses.

Mapping to a classic SDLC (see `06`):

| Phase | In the agent | Explicit? |
|---|---|---|
| Requirements | input text + Project Profile | input |
| **Analysis** (restate · assumptions · open questions · acceptance) | implicit in Planner/Designer | ❌ |
| Design | Designer → DesignSpec + TestPlan (ADR-07) | ✅ |
| Implementation / Test / Deploy | Coder / Verifier / gated deploy | ✅ |

## Decision

Add an explicit **Analysis phase** (a new *role/phase*, not a separate agent) that
runs **before planning** and produces an **AnalysisSpec**: a restatement,
assumptions, open questions, and **acceptance criteria** (which then feed the
Designer's test plan). When the requirement is genuinely ambiguous, the agent
**asks the human** at a *clarification gate* rather than guessing — deny-by-default
(block for clarification), with an explicit "proceed on the stated assumptions"
override for autonomy. **Tiered & opt-in** (`analysis.mode`), exactly like design.

### Why a phase, not a new agent
Same reasoning as ADR-07: the hexagonal core + per-role LLM split + `ApprovalPort`
already make this cheap. A separate agent only pays off if analysis must be
independently owned/scaled.

## Proposed flow

```mermaid
flowchart TD
    req["requirement (text)"] --> amode{"analysis.mode"}
    amode -->|off| fast["Planner → Designer → Coder (unchanged)"]
    amode -->|auto / always| an["Analyst → AnalysisSpec<br/>restate · assumptions · open questions · acceptance criteria"]
    an --> amb{"genuinely ambiguous?"}
    amb -->|no| plan["→ DESIGNING → PLANNING → CODING"]
    amb -->|yes| cgate{"clarification gate (human)"}
    cgate -->|proceed on assumptions| plan
    cgate -->|needs clarification| blocked["BLOCKED — open questions logged; human refines the requirement and re-runs"]
    plan -.->|acceptance criteria| design["Designer test plan"]
```

## Extended session state machine (prefix to ADR-07's machine)

```mermaid
stateDiagram-v2
    [*] --> ANALYZING: analysis on
    [*] --> PLANNING: analysis off
    ANALYZING --> PLANNING: clear
    ANALYZING --> AWAITING_CLARIFICATION: ambiguous
    AWAITING_CLARIFICATION --> PLANNING: human → proceed on assumptions
    AWAITING_CLARIFICATION --> BLOCKED: human → needs clarification (re-run)
    PLANNING --> DESIGNING: design enabled (before plan; see ADR-07)
    PLANNING --> CODING: design off
```

## What it reuses

| New need | Reuses |
|---|---|
| Analyst on a reasoner | **per-role LLM split** (`AICODER_ANALYST_*`) |
| Validated AnalysisSpec | **`structured.generate_structured()`** |
| Clarification gate | **`ApprovalPort`** with `kind="clarification"` (deny → block; `AICODER_CLARIFICATION_APPROVE=1` → proceed on assumptions) |
| Acceptance criteria → tests | hand `AnalysisSpec.acceptance_criteria` to the **Designer** (ADR-07) so the proposed tests trace to explicit criteria |
| Audit | execution log events `ANALYSIS_DONE`, `NEEDS_CLARIFICATION`, `CLARIFICATION_*` |

## New elements (when implemented)

- **Domain** `AnalysisSpec { restatement, assumptions[], open_questions[], acceptance_criteria[], ambiguous: bool }`.
- **Port** `AnalysisPort` (outbound): `analyze(requirement, repo_map) -> AnalysisSpec`.
- **Adapter** `adapters/analyst_llm.py` (`LLMAnalyst`, analyst role).
- **Session states** `ANALYZING`, `AWAITING_CLARIFICATION` (+ transitions).
- **Config** `analysis.mode = off | auto | always`; `ApprovalPort.kind` gains `"clarification"`.
- **Orchestrator** `_run_analysis()` first (before `_run_design`, which is before planning); on ambiguous → clarification gate; pass acceptance criteria forward to `_run_design`. Analysis is the natural home for the plan-free complexity tiering that ADR-07's reorder removed.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Over-blocking** (analyst flags everything ambiguous) | Prompt it to flag `ambiguous` ONLY when it genuinely cannot proceed responsibly; default `mode=off`; the gate can always proceed-on-assumptions. Tier with `auto`. |
| **Analysis theater** (prose nobody uses) | The binding output is `acceptance_criteria`, which **feeds the executable test plan** (ADR-07) — analysis traces into tests, not just a doc. |
| **No answer-injection channel** | The clarification gate is proceed/block (not free-form Q&A): block → the human refines the *requirement text* and re-runs (clean, idempotent). A richer interactive Q&A loop is a later option. |
| **Latency/cost** | Opt-in + `auto` tiering; one reasoner pass; reuse the cached repo map. |

## Phased implementation plan

1. **Slice 1 — Analyst role + AnalysisSpec (no gate) — ✅ DONE.** `AnalysisPort` +
   `LLMAnalyst` (analyst role); runs BEFORE design when enabled; logs `ANALYSIS_DONE`
   (restatement / assumptions / open questions / acceptance criteria / ambiguity
   verdict). Opt-in via `analysis.mode` (`off|auto|always`, default off → unchanged) or
   `AICODER_ANALYSIS`. Unit-tested with a fake analyst (`tests/test_analyst.py`).
2. **Slice 2 — Clarification gate — ✅ DONE.** New states `ANALYZING` /
   `AWAITING_CLARIFICATION` (+ transitions; both hub through PLANNING). On `ambiguous`,
   gate via `ApprovalPort.request_approval("clarification", …)` (deny-by-default;
   `AICODER_CLARIFICATION_APPROVE=1` to proceed on the analyst's assumptions) →
   `CLARIFICATION_PROCEED` + resume PLANNING, or `CLARIFICATION_REQUIRED` + `BLOCKED`.
   With NO approval port wired the phase is audit-only (logs `NEEDS_CLARIFICATION`,
   proceeds on assumptions). Unit-tested (clear→proceed, ambiguous+deny→BLOCKED before
   coding, ambiguous+approve→proceed, advisory-without-gate, analysis-before-design).
3. **Slice 3 — Analysis → Design hand-off — ✅ DONE.** `DesignPort.propose_design`
   gained an optional `analysis: AnalysisSpec`; the Orchestrator threads the approved
   AnalysisSpec from `_run_analysis` into `_run_design`. `LLMDesigner` renders the
   restatement + assumptions + acceptance criteria into its prompt as a binding
   contract ("every criterion MUST be covered by a proposed test; honor the
   assumptions; do not widen scope"). The linkage is auditable via a `DESIGN_TRACE`
   event (acceptance criteria → proposed test paths). Unit-tested (`test_analyst.py`:
   criteria reach the Designer + trace logged; no trace when analysis is off). Proven
   e2e on gpt-oss:120b: the `note` requirement's 6 acceptance criteria mapped onto 3
   proposed tests (OrderTest / OrderPlacedTest / OrderServiceTest) covering each.
4. **Slice 4 — Tiering — ✅ DONE.** A plan-free, deterministic complexity heuristic
   (`application/tiering.py`, `estimate_complexity`) shared by BOTH the analysis and
   design phases: `auto` mode runs the phase only on non-trivial requirements and skips
   clearly-trivial ones (logs `ANALYSIS_SKIPPED` / `DESIGN_SKIPPED`); `always` ignores
   it; `off` never runs. It deliberately tiers on **scope** (multi-step keywords:
   manage / workflow / migrate / multiple sentences…) and **vagueness** (aspiration
   without a concrete change: better / improve / enhance…), NOT implementation size —
   because a short, vague requirement ("make orders better") is exactly the one that
   most needs analysis, while a length-only heuristic would wave it through. It leans
   **complex** on purpose: a false "trivial" (skipping analysis on an under-specified
   requirement) is worse than a false "complex" (a phase runs that wasn't strictly
   needed). The decision is transparent — the signals are logged in a `TIERING` event,
   not hidden in an LLM call. Unit-tested (`tests/test_tiering.py` + orchestrator
   auto-skip/auto-run tests in `test_analyst.py` / `test_designer.py`). Proven on the
   real model: "make orders better" → AMBIGUOUS-worthy (tiered complex), the `note`
   change → fast path. (Folding analysis+design into one combined gate when both are on
   remains a possible future refinement.)

**Acceptance (e2e on the eval target):** an under-specified requirement produces an
AnalysisSpec with open questions → the agent blocks at the clarification gate (or
proceeds on logged assumptions when approved); a well-specified one yields
acceptance criteria that the Designer's tests demonstrably cover.

## Correspondence (to update when built)

Implementing this updates `02` (new `AnalysisPort` + adapter), `03` (an Analyst
component), `04` (an analysis sequence + the extended state machine here), `05`
(promote to an accepted AD), `06` (move Analysis from implicit to explicit in the
SDLC table).
