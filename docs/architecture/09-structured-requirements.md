# 09 — Proposal / ADR: Structured Requirements Intake & Traceability

**Status:** **IMPLEMENTED — all 4 slices done** (RequirementSpec intake; AC/NFR fed to
Analyst + Designer; traceability linter T1/T3 hard + T2/T4/T5 advisory; the B1–B5 design
artifacts — Glossary, Use Cases, Event Flow, typed Context Map, API/EVS/SAGA — rendered
into reviewable docs). Promote to an accepted AD (recorded as **AD-16** in `05`).
**Viewpoint:** Decision. **Completes** ADR-08 (`08`): ADR-08 made *analysis* explicit when
the input is prose; this replaces the prose with a **human-authored contract** so the
agent no longer invents *what to build* — only *how* — and every design artifact traces
back to a requirement id.

> Like ADR-07/08, this document is the design-before-code artifact it advocates.

## Context — the input was still a vague blob

After ADR-08 the pipeline is `requirement(prose) → Analyst → Designer → Coder → verify`.
The single weakest link was the **input**: a one-line prose requirement. The Analyst's
whole job was to *fight that vagueness* — restate it, guess acceptance criteria, flag
ambiguity. NFRs were essentially absent. So "what to build" was agent-inferred, and the
design artifacts (test plan, domain model) had no anchor a reviewer could check them
against.

The user's system-design process (`docs/design/design-flow/`) prescribes a richer,
**traceable** flow: User Stories + measurable NFRs in (Bước 1), then Event Flow (Bước 2),
typed Context Map (Bước 3), decomposition (Bước 4), and integration specs (Bước 5) out —
every artifact carrying an ID that traces to the one before it.

## Decision

1. **Structured input.** A `RequirementSpec` (YAML via `--requirements`): `UserStory`
   (`US-`) with Gherkin `AcceptanceCriterion` (`AC-`) + measurable `NFR` (`NFR-`, ISO
   25010 category). This is the *binding contract* — the only thing the agent does not
   invent. `to_prose()` renders a canonical string so every str-typed consumer
   (Planner/Coder/logs/session-id) is unchanged.
2. **Analyst reframes.** With AC/NFR supplied, the Analyst stops inventing "done" and
   instead checks for **conflict / gaps**; `ambiguous` (the clarification gate) now fires
   on a real contradiction or hole, not on prose vagueness.
3. **The agent derives B1–B5, traced to the contract.** The Designer emits Glossary
   (`GL-`) + Use Cases (`UC-`), per-context Event Flow (`CMD-/EVT-/POL-/RM-`), typed
   Context Map relationships (`REL-`, fixed DDD vocabulary), and integration specs
   (`API-/EVS-/SAGA-`). Each carries `traces_to` an `AC-/NFR-` (or upstream) id. All are
   rendered into `requirements.md` (US/NFR tables + **AC→test matrix**), the AD (Glossary,
   Use Cases, Context Map, Sagas), and per-context Tech Specs (Event Flow §5.1,
   Integration §5.2).
4. **The linter enforces the thread.** In `design_lint`:
   - **T1 (hard)** every `AC-` is pinned by a *locked* oracle test whose `traces_to` names it.
   - **T3 (hard)** every locked test traces to a known requirement id (no orphan tests).
   - **T2 (advisory)** every `NFR-` is addressed by a test trace or a design note.
   - **T4 (advisory)** event-flow consistency (a Policy's event/command is declared) +
     every CMD/EVT/POL traces to a requirement.
   - **T5 (advisory)** the Bước-5→Bước-3 boundary smell: an over-long saga or too many
     synchronous cross-context relationships ⇒ the context boundaries are probably wrong.

   T1/T3 join the L-family in `lint_design`: they block under `design.review_strict` and
   drive the bounded design-heal loop. T2/T4/T5 are returned by separate functions
   (`lint_nfr_coverage` / `lint_event_flow` / `lint_integration`) and only logged.

## Mapping to the design-flow process

| Bước | Artifact (ID) | Where it lives | Linter |
|---|---|---|---|
| 1 | US / AC / NFR (`US-/AC-/NFR-`) | `RequirementSpec` (human input) | T1/T2/T3 |
| 1 (derived) | Glossary (`GL-`), Use Case (`UC-`) | `DesignSpec` | — |
| 2 | Command/Event/Policy/Read-Model (`CMD-/EVT-/POL-/RM-`) | `TechSpec` | T4 |
| 3 | Typed Context Map (`REL-`, DDD kinds) | `DesignSpec` | L3/L7 (hard) + T5 |
| 4 | Service/module + data ownership | `DesignSpec` style + ADRs (existing) | L9 |
| 5 | API / Event schema / Saga (`API-/EVS-/SAGA-`) | `TechSpec` / `DesignSpec` | T5 |

## Opt-in & graceful degradation

Fully opt-in: no `--requirements` ⇒ `RequirementSpec` is `None`, all T-rules are skipped,
and the prose path behaves exactly as before. A single-context CRUD change models no
event flow / relationships / sagas — those fields stay empty and their doc sections are
omitted (no empty-table padding), so the richness scales with the change.

## Slices (all done)

- **A** — `RequirementSpec` model + YAML loader + `--requirements` CLI + wire into
  Analyst/Designer + Analyst reframe.
- **B** — `traces_to` on tests; linter T1/T3 (hard) + T2 (advisory); `requirements.md`
  with the AC→test matrix; AD links it.
- **C** — Event Flow (`CMD/EVT/POL/RM`) + derived Glossary/Use-Cases; linter T4; renderers.
- **D** — typed Context Map (`REL-`) + API/EVS/SAGA contracts; linter T5; renderers.

## Consequences

- A green run now means *every human-authored acceptance criterion is pinned by a test the
  agent could not edit* — closing the last gap above ADR-11 (tests now trace to
  requirements, not just exist).
- The design docs are a genuine, reviewable B1–B5 artifact set with end-to-end ID
  traceability — defensible in front of an architect.
- Cost: a heavier Designer prompt + schema. Mitigated by opt-in + graceful degradation.
