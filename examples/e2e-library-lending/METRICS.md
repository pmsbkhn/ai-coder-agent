# E2E run metrics — Digital Library (3 bounded contexts)

End-to-end run of the full design-first pipeline on a **new, multi-bounded-context**
greenfield system, captured for review. Output committed alongside: the generated
**design docs** (`project/docs/design/`), the generated **project code**
(`project/src/`), and the full **trace** (`run-trace.txt`).

## Run metadata

| | |
|---|---|
| Date | 2026-06-15 |
| System under test | Digital Library domain core (pure Java 21, no framework) |
| Bounded contexts | **3** — Catalog, Membership, Lending |
| Profile | `lib-profile.yaml` (framework-free; `design.mode=always`; `protected_globs=*src/test/*`; `healing.max_attempts=8`; no ArchUnit gate) |
| Models | Analyst/Designer/Reviewer/Planner = `gpt-oss:120b` · Coder = `qwen3-coder:30b` (Ollama, local) |
| Gates | clarification = approved · architect (design) = approved |
| Wall-clock | **1420 s (~23.7 min)** |
| **Final state** | **HEALING_FAILED** (functional verify never reached green within 8 heal attempts) |

## Pipeline outcome (per phase)

| Phase | Result |
|---|---|
| ANALYZE | ✅ `ambiguous=false`; restatement + 7 assumptions + 4 open questions + **9 acceptance criteria** |
| DESIGN | ✅ AD + **3 Tech Specs + 3 Test-Case docs** (1 BC = 1 spec); 3 bounded contexts |
| TEST REVIEW (adversarial) | ⚠️ `ok=false`, **9 concerns** (advisory — surfaced to the architect; e.g. spotted a duplicate test, a public-setter leak, an `isOveroverd` typo) |
| ARCHITECT GATE | ✅ approved → **9 tests locked** as the oracle |
| PLAN | ✅ 6 tasks |
| CODE + HEAL | ❌ 8 attempts, **0 green** → HEALING_FAILED |

## Verdict & event counts

| Signal | Value |
|---|---|
| Functional verdict | **FAIL** (compilation errors — never compiled clean) |
| Architecture verdict | PASS (no ArchUnit gate in this profile → trivially true) |
| `DIFF_APPLIED` (coder edits) | 13 |
| `CONTEXT_WIDENED` | 1 |
| `REFLECTION` (reasoner heal guidance) | 7 |
| `VERIFY_FAIL` / `VERIFY_PASS` | 8 / 0 |
| **`WRITE_BLOCKED`** | **25** — the coder repeatedly tried to edit locked test files; **every attempt was refused**. The oracle held → no false-green. |

## Why the code phase failed (root cause)

The design phase scaled to 3 bounded contexts cleanly. The **code** phase did not
converge — the failures are a textbook **cross-bounded-context coordination** problem
for a from-scratch multi-module build:

1. **Duplicate types across contexts.** The Catalog context owns `Copy` / `CopyStatus`,
   but the coder *re-created* them inside the `lending` package too →
   `incomparable types: lending.CopyStatus vs catalog.CopyStatus`. (Both
   `catalog/Copy.java` + `lending/Copy.java`, both `CopyStatus.java`, even a duplicated
   `MemberService` in `lending` and `membership` — visible in `project/src/`.)
2. **Naming drift.** `LoanState` vs `LoanStatus` used inconsistently between the locked
   test and the production code (the test imports one, the code defines the other).
3. **Interface not fully implemented.** `InMemoryCatalogService` didn't override
   `findCopiesByTitle(...)` declared on `CatalogService`.

`qwen3-coder:30b` could not hold a consistent cross-package type model across 3
greenfield contexts within the 8-heal budget — it kept "fixing" one context by
introducing a local duplicate, which broke another.

## Interpretation

- **Design-first is the strong half.** Analysis → AD → per-BC Tech Spec + TC-XXX-NN
  test cases → adversarial review → architect gate → locked oracle all worked on a
  genuinely multi-context system. The artifacts in `project/docs/design/` are the
  headline deliverable.
- **The oracle is trustworthy.** 25 `WRITE_BLOCKED` over 8 heals: the agent never
  weakened its own approved tests to fake a pass. A red run is an honest red.
- **Greenfield multi-BC code-gen is the discriminating hard case** — consistent with
  the project's prior finding that coordinated multi-file work costs iterations. Here
  the cost exceeded the budget for a 30B local coder.
- **Levers that would likely close the gap** (future work, not done here): a shared
  *kernel* contract so cross-context types (`Copy`, `CopyStatus`) are defined once and
  referenced; building one bounded context to green before starting the next
  (sequential per-BC verify instead of all-at-once); a stronger coder model; a larger
  heal budget. None change the harness's correctness — only its convergence on this
  class of task.

> Reproduce: `lib-profile.yaml` + the requirement in `run-trace.txt` header, with
> `AICODER_ANALYSIS=always AICODER_DESIGN=always AICODER_CLARIFICATION_APPROVE=1
> AICODER_DESIGN_APPROVE=1`, Ollama serving the two models. The generated tree here is
> a faithful copy of the agent's worktree at the end of the run (uncommitted, since
> HEALING_FAILED never reaches the commit step).
