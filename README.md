# AI Coder Agent — Hexagonal MCP Orchestrator

An autonomous coding agent that builds and modifies microservices, **MSFW-first**
(Java 21 / Spring Boot, the framework in `../msfw`). The agent core is pure Python;
tools (code reader, Maven, Git) are plugged in over **MCP** (JSON-RPC), so the core
never depends on any specific language or build system.

## Architecture (hexagonal)

```
domain/        pure Python — models, AgentSession state machine, errors
application/   use-cases + ports (Protocol) + Project Profile loader
adapters/      concrete impls (LLM, MCP gateway, Postgres) — the only layer that
               may import SDKs
```

Boundaries are enforced, not just documented:
- **`.importlinter`** — layered + forbidden-module contracts (CI).
- **`tests/test_arch_fitness.py`** — self-contained AST backstop (TC-ARCH-01/02).

### Going beyond MSFW
Everything stack-specific lives in a **Project Profile** (`profiles/*.yaml`) and in
adapters — never in the core. A new target stack is a new profile + a new
`BuildToolPort` adapter, not a core change.

## Status — M0 (foundation)
- [x] Hexagonal skeleton + ports (`PlannerPort`, `MemoryPort`, `MCPGatewayPort`, `BuildToolPort`)
- [x] `AgentSession` state machine (linear saga) — TC-CORE-01/06
- [x] Append-only execution log + pgvector (single Postgres) — TC-ARCH-03
- [x] Project Profile loader (`profiles/msfw.yaml`)
- [x] Arch fitness tests + import-linter contracts — TC-ARCH-01/02
- [ ] M1: MCP Gateway + Maven & Code-Reader servers
- [ ] M2: walking skeleton end-to-end on `sample-service`
- [ ] M3: smart self-healing loop (reset-to-clean, no-progress breaker, reflection)

## Develop

```powershell
# 1. Install deps (uv recommended)
uv sync --extra dev

# 2. Run the test suite + architecture fitness
uv run pytest
uv run lint-imports        # requires the package importable

# 3. Bring up memory (Postgres + pgvector)
docker compose up -d
```

Without `uv`, use any Python 3.11+: `pip install -e ".[dev]"` then `pytest`.
