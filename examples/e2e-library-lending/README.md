# Example E2E run — Digital Library (multi bounded-context, greenfield)

A captured end-to-end run of the agent's design-first pipeline on a **new** system
described in prose, spanning **3 bounded contexts** (Catalog, Membership, Lending).
Kept as a reviewable artifact — design documents + generated code + metrics.

## Contents

| Path | What |
|---|---|
| [`METRICS.md`](METRICS.md) | Evaluated metrics: outcome per phase, verdict, event counts, root-cause analysis |
| `project/docs/design/` | **Generated design docs** — `AD.md` (SAD-style) + `techspec-<bc>.md` (1 per context) + `testcases-<bc>.md` (TC-XXX-NN cases) |
| `project/src/main/` | **Generated production code** (incomplete — see METRICS: did not compile clean) |
| `project/src/test/` | The **architect-approved, locked** test oracle the coder implemented against |
| `project/pom.xml` | Framework-free Java 21 + JUnit5 build |
| `run-trace.txt` | Full execution trace (the prose requirement is in its header) |

## TL;DR

The **design half** worked end-to-end on a genuinely multi-context system (analysis →
AD + per-BC Tech Specs + TC-XXX-NN test cases → adversarial review → architect gate →
locked oracle). The **code half reached `HEALING_FAILED`** after 8 heals: the local
30B coder couldn't keep cross-bounded-context types consistent on a from-scratch
3-context build (it duplicated `Copy`/`CopyStatus` across packages). The locked test
oracle held (25 blocked write attempts) — so the red verdict is honest, not faked.

See [`METRICS.md`](METRICS.md) for the full breakdown.
