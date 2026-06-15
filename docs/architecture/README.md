# AI Coder Agent — Architecture Description (AD)

> Conforms to the structure of **ISO/IEC/IEEE 42010** (*Systems and software
> engineering — Architecture description*). This folder IS the architecture
> description: it identifies stakeholders and their concerns, defines the
> architecture **viewpoints**, presents the **views** that frame those concerns
> (with Mermaid models), records **architecture decisions** and their rationale,
> and states **correspondences** and known limitations.

## AD identification & overview

| Field | Value |
|---|---|
| System | **AI Coder Agent** — an autonomous coding agent that builds/modifies microservices, **MSFW-first** (a Java 21 / Spring Boot 4 framework) |
| Architecture style | **Hexagonal (Ports & Adapters)** + an MCP tool plane (JSON-RPC over stdio); plain-Python deterministic control loop |
| Core language | Python (agent core); tools speak MCP, so the core is language/build-agnostic |
| Status | Core roadmap **M0–M6 DONE & green** (see `06-status-and-roadmap.md`) |
| Source of truth | This AD + `/CLAUDE.md` (durable handoff). Code under `src/aicoder/`. |

The agent turns a natural-language **requirement** into a verified, committed
change on a target repository: it plans, writes whole-file edits, runs the real
build/tests as a **deterministic verdict**, self-heals to green, then commits and
(optionally) delivers/deploys behind a human gate.

## Stakeholders & concerns (42010 §5.3)

| Stakeholder | Key concerns | Framed by (view) |
|---|---|---|
| **Agent developer / maintainer** | Module boundaries, testability, where to extend | Module view (`02`) |
| **Operator running the agent** | Runtime topology, processes, external deps, config (env) | C&C view (`03`), Decisions (`05`) |
| **Integrator (new target stack)** | What is stack-specific vs core; extension seams | Module view (`02`), Decisions (`05`) |
| **Reviewer / safety owner** | Determinism of the verdict, append-only audit, the deploy gate, sandboxing | Behavioral views (`04`), Decisions (`05`) |
| **Researcher (model capability)** | How quality is measured; reliability; headroom | Behavioral views (`04` eval), Status (`06`) |
| **Future contributor** | What exists, what's weak, what's next | Status & roadmap (`06`) |

Driving quality concerns: **determinism of pass/fail**, **architectural integrity**
of generated code, **safety** (no host blast radius, no unapproved deploy),
**auditability** (immutable execution log), **portability** (swap model/stack via
config), and **measurability** (objective eval).

## Viewpoint catalog (42010 §5.5) & document map

| # | View (file) | Viewpoint / model kind | Concerns framed |
|---|---|---|---|
| 01 | [Context](01-context.md) | Context viewpoint — system-in-environment (Mermaid flowchart) | scope, external actors & dependencies |
| 02 | [Module view](02-module-view.md) | Module/decomposition viewpoint — layers, packages, allowed dependencies (Mermaid graph) | structure, boundaries, testability, extension |
| 03 | [Component-and-Connector view](03-component-connector-view.md) | C&C / runtime viewpoint — processes, connectors, external systems (Mermaid flowchart) | runtime topology, deployment, config |
| 04 | [Behavioral views](04-behavioral-views.md) | Behavioral viewpoint — sequence diagrams of key flows (Mermaid sequenceDiagram) | control flow, heal loop, eval, sandbox, parallel, deploy gate |
| 05 | [Architecture decisions](05-decisions.md) | Decision viewpoint — ADR-style records | rationale, trade-offs, locked choices |
| 06 | [Status & roadmap](06-status-and-roadmap.md) | — | what exists, what's weak, what's next |
| 07 | [Proposal: design-first phase](07-design-first-proposal.md) | Decision (Implemented) | making design + test cases explicit, human-gated outputs |
| 08 | [Proposal: analysis phase](08-analysis-phase-proposal.md) | Decision (Slices 1–3 implemented) | making requirement analysis + a clarification gate explicit, fed forward to design |

## Correspondences & consistency rules (42010 §5.7)

- **Module → C&C**: each adapter module (`adapters/*`) realizes exactly one
  outbound port and appears at runtime either in the orchestrator process or as
  an MCP server process. The `domain`/`application` layers have **no** runtime
  component of their own — they execute inside the orchestrator process.
- **Decisions → views**: every "locked decision" in `05` is observable in the
  module boundaries (`02`) and/or the runtime wiring (`03`).
- **Enforced consistency**: the layered dependency rule in `02` is **machine-checked**
  by `.importlinter` (3 contracts) + `tests/test_arch_fitness.py`, run in CI.
  Drift between this AD and the code surfaces as a red gate.

## How to read the diagrams

All models are **Mermaid** fenced code blocks; GitHub and most Markdown viewers
render them inline. Each view states the viewpoint it answers and gives a
responsibilities table for its elements.
