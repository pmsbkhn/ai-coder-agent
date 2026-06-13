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

## Status
**M0 — foundation**
- [x] Hexagonal skeleton + ports (`PlannerPort`, `MemoryPort`, `MCPGatewayPort`, `BuildToolPort`, `CoderPort`)
- [x] `AgentSession` state machine (linear saga) — TC-CORE-01/06
- [x] Append-only execution log + pgvector (single Postgres) — TC-ARCH-03
- [x] Project Profile loader (`profiles/msfw.yaml`) + arch fitness + import-linter — TC-ARCH-01/02

**M1 — tools over MCP**
- [x] MCP Gateway client (graceful -32601 — TC-INT-05)
- [x] Code-Reader server (tree-sitter repo map + symbol zoom-in — TC-CORE-03/04)
- [x] Maven server (surefire parse = deterministic gate) + `MavenBuildTool`

**M2 — walking skeleton**
- [x] Provider-agnostic LLM layer (Anthropic + OpenAI-compatible) + validate-repair
- [x] `LLMPlanner`, `LLMCoder` (whole-file edits)
- [x] Git/Workspace server (worktree / read / write / commit)
- [x] Control loop (plan→code→verify→heal→commit) + composition root / CLI
- [ ] Real e2e on `sample-service` (gated: needs ANTHROPIC_API_KEY + mvn) · eval harness · PostgresMemory swap

**Next**
- [ ] M3: reset-to-clean per attempt + reflection step (no-progress breaker already in)
- [ ] M4: ArchUnit architecture gate in the verifier

## Run a real end-to-end (needs ANTHROPIC_API_KEY + mvn + git)

```powershell
$env:ANTHROPIC_API_KEY = "sk-..."
uv run python -m aicoder "add a 'note' field to Order" --profile profiles/msfw.yaml
# or point at a local model (Ollama):
$env:AICODER_LLM_PROVIDER = "ollama"
$env:AICODER_LLM_MODEL = "qwen2.5-coder:14b"
$env:AICODER_LLM_NUM_CTX = "16384"   # raise Ollama's 4096 default so the repo map + files fit
```

### Local model via Ollama
```powershell
winget install Ollama.Ollama          # server runs at http://localhost:11434
ollama pull qwen2.5-coder:14b         # ~9GB, fits a 12GB GPU at Q4
```
Then set the three env vars above. No API key, no cost. (`mvn` + `git` still needed for verify/commit.)

### Running on another machine (e.g. macOS)
The MSFW path is machine-specific. Instead of editing `profiles/msfw.yaml`, override it:
```bash
export AICODER_REPO_PATH=/Users/you/IdeaProjects/msfw   # overrides profile target.repo_path
```
Setup on the new machine: install `uv` + Ollama, `uv sync --extra dev --extra tools --extra adapters`,
pull a model (a 128GB Mac fits 70B-class, e.g. `ollama pull qwen2.5:72b` or `llama3.3:70b`;
`qwen2.5-coder` tops out at 32B). Do NOT copy `.venv/` (it is platform-specific — recreate with `uv sync`).
The target MSFW repo must also be present, and `mvn install -DskipTests` run once there to populate `~/.m2`.

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
