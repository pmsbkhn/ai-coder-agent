# Example — Structured intake → design + Architecture-as-Code (Structurizr)

A captured **design-only** run of the agent's design-first pipeline on a marketplace
**escrow payments** core, driven by a **structured requirements intake** (User Stories
+ Acceptance Criteria + NFRs) instead of a prose blob, on a profile that emits both the
SAD-style Markdown set **and** Structurizr DSL (Architecture-as-Code).

Kept as a reviewable artifact — it shows the two new capabilities end-to-end:
1. **Structured intake (US/AC/NFR) + AC→test traceability** — every acceptance criterion
   is pinned by a locked oracle test.
2. **Architecture-as-Code** — a master `workspace.dsl` (≈ the AD) + one `.dsl` fragment
   per bounded context (≈ a Tech Spec), generated from the *same* validated DesignSpec.

## How it was produced

```bash
export AICODER_LLM_PROVIDER=ollama
export AICODER_ANALYST_MODEL=gpt-oss:120b AICODER_DESIGNER_MODEL=gpt-oss:120b \
       AICODER_REVIEWER_MODEL=gpt-oss:120b AICODER_PLANNER_MODEL=gpt-oss:120b
export AICODER_ANALYSIS=always AICODER_DESIGN=always AICODER_CLARIFICATION_APPROVE=1
# design-only: the architect gate is left to deny → BLOCKED after design, no coding
uv run python -m aicoder \
    --requirements requirements-intake.yaml \
    --profile profiles/msfw.yaml          # design.formats: [markdown, structurizr]
```

## Contents

| Path | What |
|---|---|
| [`requirements-intake.yaml`](requirements-intake.yaml) | The **binding contract**: 3 User Stories, **8 Acceptance Criteria**, 2 NFRs (ISO 25010) |
| `design/requirements.md` | US/AC/NFR tables + the **AC→test traceability matrix** (all 8 AC 🔒) |
| `design/AD.md` | SAD-style Architecture Description (system level) |
| `design/techspec-*.md` | One Tech Spec per bounded context (Seller / Order / Escrow) |
| `design/testcases-*.md` | TC-XXX-NN cases per context (the locked oracle) |
| `design/structurizr/workspace.dsl` | **Master AaC file (≈ AD)** — C4 model + System Context / Container / Component views, datastores (DB-per-service), `!docs` + `!adrs` |
| `design/structurizr/{seller,order,escrow}.dsl` | **Child AaC files (≈ Tech Specs)** — components per context, `!include`d by the master |
| `design/structurizr/styles.dsl` | Tag → shape/colour (form separated from content) |
| `design/structurizr/documentation/*.md` | Prose embedding the views via `embed:` (`!docs`) |
| `design/structurizr/adr/NNNN-*.md` | MADR-lite decisions, numbered-only (`!adrs`) |
| [`run-trace.txt`](run-trace.txt) | Full execution trace |

## Result

| Signal | Value |
|---|---|
| Bounded contexts | **3** — Seller, Order, Escrow |
| AC→test traceability | **8/8 acceptance criteria pinned by a locked test** (T1/T3 clean) |
| Framework primitives reused | `IdempotencyKey`, `Money`, `StringIdentity` (no `randomUUID` / `IdGeneratorPort`) |
| Structurizr | master `workspace.dsl` + 3 fragments; children `!include`d into their container (so each child depends on the master) |
| Final `DESIGN_LINT` | `ok=false`, **2 residual** (L1 a key-flow placeholder method; L8 a repo method the oracle calls but the port did not declare) — both genuine completeness gaps, surfaced for the architect; not converged in 2 heal passes |

## Notes / honesty

- The DSL is generated **deterministically from the validated `DesignSpec`** — the LLM
  never writes DSL, so it is valid by construction and the L/T consistency linter still
  governs the design. "Valid by construction" is now **checked, not asserted**: a
  pure-Python guard (`structurizr_lint`) runs at generation time and a real
  `structurizr/cli` parse runs in CI (pinned to a dated tag — never `:latest`, which is a
  no-op stub that would validate nothing).
- Deterministic-only fidelity gaps (honest): there is **no deployment/operations view**
  (replicas/namespaces aren't in the `DesignSpec`), ADRs are MADR-lite from free-text
  decisions, and datastore technology is generic (`Datastore`).
- Component identifiers are **namespaced by container** (`escrow_escrow`) because
  Structurizr identifiers are global.
- The Component views are derived from the free-text `interface_changes` / `domain_model`
  (a structured `components` field would make them exact — a deliberate future step).
- The 2 residual lint findings are the model (a local gpt-oss:120b) under-declaring a
  port method on a heavier multi-context intake — the linter caught them; a stronger
  model or more heal budget would close them.
