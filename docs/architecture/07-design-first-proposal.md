# 07 — Proposal / ADR: Explicit Design-First Phase

**Status:** **IMPLEMENTED — all 4 slices done** (Designer role + DesignSpec/TestPlan;
human gate + approved tests locked as the oracle; complexity tiering; adversarial
test review). Promote to an accepted AD. **Viewpoint:** Decision. **Supersedes
nothing; extends** AD-8/AD-9/AD-11/AD-15 (`05-decisions.md`).

> This document is itself the "design output before code" that the proposal
> advocates — written and reviewable *before* any implementation.

## Context — the implicit shortcut

Today the pipeline is `requirement (text) → Planner → Coder → verify`. The Planner
emits a thin `Plan` (tasks + target files + constraints) but the agent **does not
produce a reviewable design** (architecture/interface decisions) nor **design the
tests** — in eval the tests are pre-written by humans (the oracle); in normal runs
the target's existing tests verify. So "design + test cases as first-class outputs"
is skipped / implicit.

**Principle to preserve:** this system's strength is that *spec is checkable by
machine*. The two highest-value "design" artifacts here are already **executable** —
**test cases** (behavioral oracle) and **ArchUnit rules** (M4, architecture-as-test).
Prose design that isn't tied to a check is decoration ("design theater").

## Decision

Add an **explicit Design phase** (a new *role/phase* in the existing orchestrator —
**not a separate agent**) that, for non-trivial requirements, produces:
1. a **DesignSpec** — a *delta* design: affected components/interfaces, contract
   changes, short ADR notes (prose, kept lightweight); and
2. a **TestPlan** — **executable proposed test cases** (test files) that encode the
   acceptance criteria.

A **human approval gate** sits on the DesignSpec+TestPlan. On approval, the proposed
tests are written into the worktree and **locked as the oracle** (`protected_globs`);
the Coder then implements to make them pass — reusing the exact tests-as-oracle
mechanism, but with **agent-proposed + human-approved** tests instead of pre-written
ones. **Tiered:** trivial changes skip design (fast path); complex/novel ones take
the design-first path.

### Why a phase, not a new agent
The hexagonal core + per-role LLM split already support this with minimal addition;
a separate deployable agent only pays off if the design process must be
independently owned/scaled (a later option, not now). See `05-decisions.md` AD-13's
reasoning style.

## Proposed flow

```mermaid
flowchart TD
    req["requirement (text)"] --> tier{"complexity tier<br/>(trivial?)"}
    tier -->|trivial| plan["Planner → Coder (current fast path)"]
    tier -->|complex / design_mode=always| des["Designer (reasoner role)<br/>→ DesignSpec + TestPlan"]
    des --> writet["write proposed tests into worktree<br/>(candidate oracle)"]
    writet --> gate{"ApprovalPort<br/>human reviews design + tests"}
    gate -->|reject| blocked["BLOCKED — design recorded for revision"]
    gate -->|approve| lock["lock tests (protected_globs)"]
    lock --> code["Coder implements → verify (functional + arch) → heal"]
    plan --> code
    code --> done["commit → deliver → deploy gate"]
```

## Extended session state machine

```mermaid
stateDiagram-v2
    [*] --> PLANNING
    PLANNING --> DESIGNING: design-first tier
    PLANNING --> CODING: trivial / design disabled
    DESIGNING --> AWAITING_APPROVAL: DesignSpec + TestPlan ready
    AWAITING_APPROVAL --> CODING: approved (tests locked as oracle)
    AWAITING_APPROVAL --> BLOCKED: rejected
    CODING --> VERIFYING
    VERIFYING --> DONE
    VERIFYING --> HEALING
    HEALING --> CODING
    HEALING --> HEALING_FAILED
```

## What it reuses (low marginal cost)

| New need | Reuses |
|---|---|
| Designer runs on a strong reasoner | **per-role LLM split** (`AICODER_DESIGNER_*`, falls back like planner/coder) |
| Validated DesignSpec/TestPlan output | **`structured.generate_structured()`** (Pydantic + repair) |
| Human review of design + tests | **`ApprovalPort` (M6)** — generalize from "deploy gate" to a typed gate (`design` / `deploy`) |
| Agent-proposed tests become the oracle | **`protected_globs` + tests-as-oracle** (AD-11) — write proposed tests, then protect them |
| Architecture intent enforced | **M4 ArchUnit dual gate** — the design's arch constraints can be emitted as rules |
| Auditable artifacts | **append-only execution log** — `DESIGN_PROPOSED`, `DESIGN_APPROVED/REJECTED`, `TESTS_LOCKED` events |

## New elements to add (when implemented)

- **Port** `DesignPort` (outbound): `propose_design(requirement, repo_map) -> DesignSpec`.
- **Adapter** `adapters/designer_llm.py` (`LLMDesigner`, reasoner role).
- **Domain models**: `DesignSpec { summary, affected, interface_changes[], adr_notes, test_plan: ProposedTest[] }`, `ProposedTest { path, content, rationale }`.
- **Session states**: `DESIGNING`, `AWAITING_APPROVAL` (+ transitions); `ApprovalPort.request_approval(kind, summary)` gains a `kind`.
- **Config**: `design.mode = off | auto | always` in the Project Profile; `AICODER_DESIGN` env override; complexity heuristic (or Designer self-classifies) for `auto`.
- **Orchestrator**: a `DESIGNING → approval → lock-tests → CODING` segment before the coding phase.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Weak/wrong oracle** (agent writes easy tests, then passes them) | Human approves the **TEST CASES** specifically (the load-bearing gate). Optional **adversarial review** pass (second model / different role): "does this test actually constrain the requirement? edge cases? trivially-satisfiable?" before locking. |
| **Design theater** (pretty prose, no constraint) | Keep prose minimal; the binding artifacts are the **executable tests + arch rules**, which the deterministic Verifier enforces. |
| **Over-process** on small changes | **Tiering** — trivial tier skips design entirely (current path). |
| **Bootstrapping** (who guards the guard?) | Human gate + the existing immutable audit log; tests, once locked, are uneditable by the Coder. |
| **Latency/cost** | Extra reasoner passes only on the complex tier; reuse cached repo map. |

## Phased implementation plan

1. **Slice 1 — Designer role + DesignSpec (no gate yet) — ✅ DONE.** `DesignPort` +
   `LLMDesigner` (reasoner role, `AICODER_DESIGNER_*`); emit a schema-validated
   `DesignSpec` + `TestPlan` and log `DESIGN_PROPOSED`. Opt-in via `design.mode` /
   `AICODER_DESIGN` (default `off` → current fast path, unchanged). No gate / no
   test-locking yet. Unit-tested (`tests/test_designer.py`) + proven e2e: with a
   real reasoner (gpt-oss:120b) the agent produced a valid DesignSpec
   (summary, affected file, a proposed `AccountWithdrawTest`) before coding, then
   reached DONE without disruption.
2. **Slice 2 — Approval gate + lock-as-oracle — ✅ DONE.** `ApprovalPort` generalized
   with `kind` (`design`/`deploy`, kind-specific `AICODER_{KIND}_APPROVE`). New
   session states `DESIGNING` / `AWAITING_APPROVAL` (+ transitions). The Designer
   writes its proposed tests into the worktree; a human gates them; **on approve they
   are LOCKED** (added to the protected set → the Coder reads them as the oracle but
   cannot overwrite them) and the run proceeds to CODING; **on reject → BLOCKED**
   before any coding. Unit-tested (gate approve→`WRITE_BLOCKED` on tamper, reject→
   BLOCKED, kind-specific approval). Proven e2e: gpt-oss proposed an
   `AccountWithdrawTest`, it was approved + locked, and the Coder implemented
   `withdraw` to pass its own approved test → green at 0 heals.
   **Materialized artifacts:** the design is written as explicit, reviewable files in
   the target worktree — one umbrella **Architecture Description** (`docs/design/AD.md`)
   plus **one Tech Spec per bounded context** (`docs/design/techspec-<bc>.md`; **1 BC
   = 1 Tech Spec**) — committed with the change; the architect reviews these at the
   gate. Docs + locked tests are recorded in the cumulative `applied` set so a
   reset-to-clean heal cannot wipe them. (`profile.design.docs_dir`, default `docs/design`.)
3. **Slice 3 — Tiering + config — ✅ DONE.** `design.mode = off | auto | always`.
   `auto` designs only **complex** changes (the deterministic heuristic `_is_complex`:
   more than one task OR more than one touched file — single-file/single-task changes
   skip design and log `DESIGN_SKIPPED`, since the Coder reliably one-shots those);
   `always` bypasses the heuristic; `off` is the fast path. No extra LLM call — the
   decision is derived from the plan already in hand. Unit-tested (auto-skips-trivial,
   auto-designs-complex, always-overrides).
4. **Slice 4 — Adversarial test review — ✅ DONE.** A `ReviewPort` + `LLMReviewer`
   (the `reviewer` role, ideally a DIFFERENT model from the Designer) critiques the
   proposed TestPlan before locking: trivially-satisfiable? missing edge cases?
   asserting implementation details? actually tied to the requirement? `TEST_REVIEW`
   is logged and the concerns are surfaced into the approval request. Default
   **advisory** (the human decides with concerns in hand); `design.review_strict`
   makes a failed review **auto-block** (BLOCKED) before the gate. Unit-tested
   (ok→gate, strict+weak→auto-block, advisory+weak→surface→approve). Proven e2e:
   with the Designer on gpt-oss and the reviewer on qwen3-coder, the reviewer found
   genuine weaknesses in a proposed AccountWithdrawTest (no balance-unchanged-after-
   exception check, missing zero/negative-amount cases, brittle message assertion)
   and surfaced them to the gate.

**Acceptance (e2e on the eval target):** given a non-trivial requirement, the agent
produces a DesignSpec + proposed tests → a human approves → the tests are locked →
the Coder implements until they pass → `mvn test` green (functional + arch). The
agent **authored** the oracle, a human **approved** it, and the Coder could **not**
edit it afterward.

## Correspondence (to update when built)

Implementing this updates: `02` (new `DesignPort` + adapter), `03` (a Designer
component in the agent process), `04` (a new design sequence + the extended state
machine here), `05` (promote this to an accepted AD), `06` (move from "weak/unbuilt"
to capability).
