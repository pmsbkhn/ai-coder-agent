# CLAUDE.md — AI Coder Agent

Guidance for Claude Code (and any new session, on any machine) working in this repo.
This file is the **durable handoff**: the rich design history lived in machine-local
agent memory that does NOT travel with the code, so the essentials are captured here.

## What this is
An autonomous coding agent (hexagonal + MCP orchestrator) that builds/modifies
microservices, **MSFW-first** (the user's Java 21 / Spring Boot 4 framework, a sibling
repo). The agent core is **Python**; tools (code reader, Maven, Git) are plugged in over
**MCP** (JSON-RPC), so the core is language/build-system agnostic.

## Architecture (hexagonal — boundaries are enforced, not just documented)
```
src/aicoder/
  domain/        pure Python: models (Pydantic), AgentSession state machine, errors. NO infra imports.
  application/   use-cases + ports (Protocol) + Project Profile loader. Talks to the world ONLY via ports.
  adapters/      concrete impls (LLM, MCP gateway, Maven build, in-memory store). The ONLY layer that may import SDKs.
  mcp_servers/   standalone MCP servers (code_reader, maven, git) + pure libs (repo_map via tree-sitter, surefire parser).
  app.py         composition root + CLI (`python -m aicoder "<requirement>" --profile profiles/msfw.yaml`).
```
- Ports (`application/ports/`): `RequirementPort`, `FeedbackPort` (in); `PlannerPort`, `CoderPort`,
  `MemoryPort`, `MCPGatewayPort`, `BuildToolPort` (out).
- **Enforcement**: `.importlinter` (layered + forbidden-module contracts) + `tests/test_arch_fitness.py`
  (self-contained AST backstop). Domain may not import infra SDKs; application may not import adapters/SDKs.
  Run `uv run lint-imports`. This implements the project's own TC-ARCH-01/02/03 fitness rules.

## Locked decisions (and why)
- **Python core, tools over MCP** — MCP makes tools language-agnostic; the core never depends on a tool's stack.
- **Provider-agnostic LLM** (`adapters/llm/`): `LLMClient` with `AnthropicClient` (default) + `OpenAICompatibleClient`
  (Ollama/vLLM). Swap via env, never code. **Robustness primitive = `structured.generate_structured()`**:
  Pydantic-validate model output and feed errors back for a bounded repair retry — this is what lets a weak local
  model be usable.
- **Single Postgres + pgvector** (append-only execution log w/ RLS + RAG). Graph DB deferred (use jdeps/LSP on demand).
- **Verifier is deterministic-first**: functional verdict = parsed surefire XML / exit code; the LLM only *explains*
  failures, never flips pass/fail. (Architecture gate via ArchUnit is M4.)
- **No LangGraph**: the control loop is plain Python in `application/orchestrator.py`. Reason: import-linter forbids
  application→langgraph, the loop is simple+deterministic, and state is externalized to `MemoryPort` — so a framework
  adds nothing here. Could return as an adapter-level runner if checkpointer/streaming is ever needed.
- **Coder emits WHOLE-FILE contents**, not diffs (avoids fragile diff-apply). Aider-style search/replace is a later optimization.
- **Project Profile** (`profiles/*.yaml`) holds everything stack-specific. Extending beyond MSFW = a new profile + a
  `BuildToolPort` adapter, not a core change. Don't truly generalize until a 2nd real target exists.

## Control loop (orchestrator.py)
`run_requirement`: INIT → PLANNING (skeleton-first repo map → plan) → CODING (apply ALL tasks, each Coder call sees the
current state of every plan file) → **verify ONCE** → heal-to-green (re-code with the compiler error + context-widened
files until pass or circuit breaker) → commit. The AgentSession state machine (`domain/session.py`) is the linear saga;
Orchestrator holds NO state (loads/saves session via MemoryPort each step). Per-attempt circuit breaker
(`healing.max_attempts`) + no-progress early-trip (same error signature twice).

## How to run
```bash
uv sync --extra dev --extra tools --extra adapters
uv run pytest          # 38 passed, 2 skipped
uv run lint-imports    # 3 contracts kept

# Real e2e with a local model (free):
export AICODER_LLM_PROVIDER=ollama
export AICODER_LLM_MODEL=qwen2.5-coder:14b   # or 32b / qwen2.5:72b / llama3.3:70b on a big machine
export AICODER_LLM_NUM_CTX=16384             # Ollama defaults to 4096 — too small for repo map + files
export AICODER_REPO_PATH=/abs/path/to/msfw   # overrides profiles/msfw.yaml target.repo_path (portable across machines)
# Optional per-role split (M3): a strong reasoner plans, a fast code model codes.
# Each falls back to AICODER_LLM_* if unset; provider can differ per role too.
export AICODER_PLANNER_MODEL=gpt-oss:120b    # reasoner — also does the heal reflection
export AICODER_CODER_MODEL=qwen3-coder:30b   # fast code model for the heal loop
uv run python -m aicoder "Add a nullable String field 'note' to the Order aggregate..." --profile profiles/msfw.yaml
# Needs: ollama serving a pulled model; Java 21 + Maven; `mvn install -DskipTests` once in the MSFW repo to populate ~/.m2; git.
# Default provider is anthropic (set ANTHROPIC_API_KEY) — Console: console.anthropic.com, separate billing from claude.ai.
```

## Status — M0–M4 DONE & green; eval harness live; e2e PROVEN
- **M0** foundation: hexagonal skeleton, ports, AgentSession, Postgres migration (append-only RLS + pgvector), profile loader, arch fitness.
- **M1** tools over MCP: `MCPGatewayClient` (graceful JSON-RPC -32601), Code-Reader (tree-sitter repo map + symbol zoom-in), Maven (surefire parse), `MavenBuildTool`.
- **M2** walking skeleton: provider-agnostic LLM layer, `LLMPlanner`/`LLMCoder`, Git/Workspace MCP server (worktree/read/write/commit), the control loop, composition root/CLI. **Verified end-to-end on real MSFW `sample-service` with a free local 14B**: single-file and 4-file coordinated changes both reach `mvn test` PASS + a real commit.
- **M3** reflection-driven heal + per-role LLM split. The heal loop now VARIES its input each attempt so a deterministic (temp 0) local model escapes the same-prompt/same-error fixpoint: a `PlannerPort.reflect()` reasoning pass (runs on the reasoner model) sees the CURRENT failing file contents + accumulated strategy history and hands the Coder a concrete fix strategy; reset-to-clean restores the cumulative `applied` set (never drops correct earlier edits); the no-progress breaker is now 3-strikes + profile-gated. Per-role env (`AICODER_PLANNER_*` / `AICODER_CODER_*`, falling back to `AICODER_LLM_*`) lets the Planner run a strong reasoner and the Coder a fast code model. **Verified e2e on the 128GB M4 Max (Planner=gpt-oss:120b, Coder=qwen3-coder:30b)**: the 5-file `note` change converges at heal attempt 2 → real commit → `mvn test` 4/4 green, with the note test preserved.

- **M4** dual-assessment Verifier (architecture gate). ArchUnit rules run INSIDE `mvn test`; `MavenBuildTool` no longer hard-codes `arch_passed` — it splits failing tests into architecture-rule vs functional via `architecture.test_pattern` (a glob over `{FQCN}.{method}`, default `*Architecture*`, active only when `architecture.fitness == archunit`), so the verdict is genuinely dual (functional / arch / both). A compile failure is charged to the functional axis. Wired in `app.py` (`MavenBuildTool(gateway, arch_test_pattern=…)`); the `VERIFY_FAIL` trace now carries `functional_passed`/`arch_passed`. **Proven on `eval/target`**: a protected `HexagonalArchitectureTest` (domain depends on nothing; application never touches adapters) passes on clean code and FAILS the instant a domain→adapters dependency is injected — the gate bites, functional stays green. Profiles set the pattern; with no archunit opt-in the behavior is unchanged (back-compat unit-tested in `tests/test_maven_build.py`).

### Eval harness (`eval/`, `eval/run_eval.py`) — tests-as-oracle
Objective, repeatable scoring: golden tasks ship **pre-written tests that define "done"**; the agent implements code to make them pass and is REFUSED any write to a test file (`protected_globs` in the profile → orchestrator feeds tests to the Coder as read-only context and blocks writes, logging `WRITE_BLOCKED`). A green run is therefore a genuine pass — closes the "agent dropped the test, mvn still green" false positive. Two suites:
- **lite** — a framework-free Java/Maven/JUnit5 target in `eval/target/` (hexagonal, MSFW idiom, pure JDK → fast).
- **msfw** — the REAL `sample-service` (outbox/event-sourcing), copied standalone per run (framework jars + reactor parent resolve from `~/.m2`); target source via `AICODER_EVAL_MSFW_TARGET`.

Run: `uv run python eval/run_eval.py [--suite lite|msfw] [task-ids…]` (set the same provider/model + `JAVA_HOME` env as a normal run). Scoreboard reports PASS/FAIL, heal attempts (a difficulty signal), and blocked test-writes. Adding a task = a new `eval/tasks[-msfw]/<id>/` dir (`task.yaml` + `given/` test overlay). **Baselines (gpt-oss:120b + qwen3-coder:30b): lite 3/3, msfw 1/2.** `order-priority` passed at 0 heals with `blocked=2` (the coder twice tried to edit a test and was refused, then reached green via production code only — the oracle held on the real stack). `escrow-close` (event-sourcing: new EscrowClosed event + apply/fold + invariants) **currently FAILS** (HEALING_FAILED at the heal budget) even though a hand-written reference solution passes — a deliberate *discriminating* task and a target for future model/harness gains. A failing task in the suite is expected and wanted: it's how the suite measures headroom, not just confirms easy wins.

### Five integration/feedback bugs found by e2e and fixed (do NOT reintroduce)
1. **Hang in `git worktree add`** inside the MCP git server — a background `git gc --auto` inherited the server's stdout
   pipe → `subprocess.run(capture_output=True)` waited for EOF forever on Windows. Fix: git/maven subprocesses run with
   `-c gc.auto=0 -c maintenance.auto=false` and `stdin=DEVNULL`.
2. **Self-healing blind to compile errors** — Maven prints compiler errors to STDOUT (not stderr/surefire). Fix:
   `MavenBuildTool` evidence includes `[ERROR]`/`BUILD FAILURE` lines from stdout.
3. **Cross-file breaks unfixable** — Coder only saw a task's files; a constructor change breaks other files. Fix:
   `_files_from_evidence()` widens the Coder's read set to every `.java` the compiler blamed (CONTEXT_WIDENED).
4. **Commit silently aborted** — target repo had no git identity. Fix: git server commits with explicit
   `-c user.name/-c user.email` (agent identity).
5. **Orchestrator swallowed tool failures** — a tool returning `{"ok": false}` inside a transport-OK response looked like
   success. Fix: `_tool` raises `ToolInvocationError` when `result["ok"] is False`.

### Empirical model finding (the user's central question: "will a weak open-source model be too dumb?")
- Single-file change: 14B → DONE + commit.
- 4-file coordinated change (`note` rippling Order ctor → OrderService iface → Impl → test): FAILED at
  `max_attempts=3`, but **PASSED at `max_attempts=6`** (converged on the 4th heal attempt). It was an attempt-budget
  artifact, not a hard ceiling. **Conclusion: a solid harness (verify-once + context-widening + compiler-error feedback)
  + enough retries lets a free local model do real coordinated multi-file work; the cost is iterations, not capability.**
  A stronger model (Claude / 70B) is expected to converge in fewer iterations — that's the measurable gap.

### M3 findings (gpt-oss:120b planner + qwen3-coder:30b coder, on the 128GB M4 Max)
- **Reflection is only useful if it SEES the code.** Given just the requirement + the distilled compiler error, gpt-oss
  hallucinated a `Map<?,?>` payload that did not exist and steered the Coder wrong for 6 attempts. Once `reflect()` was
  fed the current failing file contents it diagnosed exactly ("`outboxEvent.data().value()` returns a JSON string, not a
  Map") and the run converged at heal attempt 2. Pass code to the reasoner, don't make it guess.
- **Thinking models need a big token budget + a reasoning-channel fallback.** gpt-oss spends most tokens in the hidden
  thinking channel; with a small `max_tokens` the visible `content` came back empty, so reflection was a no-op. Fix:
  `max_tokens=3500` for reflect + `complete_text()` falls back to `reasoning_content` when `content` is empty.
- **Never bare-reset between heal attempts.** The Coder re-emits whole files for only a SUBSET each attempt; a plain
  `git reset --hard` dropped the correct test edits from an earlier attempt and `mvn` stayed green (note is nullable) →
  DONE but the deliverable was silently incomplete. reset-to-clean must restore the cumulative `applied` set.
- **Local temp-0 models are NOT perfectly deterministic** (MoE routing / GPU): identical runs varied (one trip-failed
  before the code-aware-reflection fix). `max_attempts=6` + 3-strikes gives the needed headroom.
- **Always `mvn install -DskipTests` at the MSFW root first** — a stale `~/.m2` made even the pristine baseline fail to
  compile (missing `tech.vsf.ptnt.msfw.domain.eventsourcing`), which the agent cannot fix by editing sample-service.

## Roadmap (next)
- **Grow the eval suites** (DONE: harness + lite 3/3 + msfw 1/1 — see Status): more golden tasks (event-sourcing on
  Escrow, bugfix-style, budget-stressing), and a per-model leaderboard (swap env, re-run, compare pass-rate + heals).
- **M5**: full git/PR flow + sandbox security boundary + parallel tasks (worktrees already in place).
- **M6**: CI/CD + deploy with human approval gate.
- Also pending: swap `InMemoryMemory` → PostgresMemory (Docker compose already provided); optional targeted single-file
  heal edits to cut whole-file regeneration cost.

## Gotchas
- Don't copy `.venv/` across machines (platform-specific); recreate with `uv sync`. `uv.lock` is committed.
- `requires-python = ">=3.11,<3.14"` (tree-sitter wheels lagged 3.14); uv picks a compatible interpreter.
- The MSFW checkout may carry macOS `._*` AppleDouble junk that breaks git + javac — delete all `._*` files if so.
- Git: no remote (local only). `main` holds scaffold→M2 + the CLAUDE.md handoff; **M3 lives on branch `m3-reflection-heal`**
  (commit "M3: reflection-driven heal loop + per-role LLM split"), not yet merged to `main`.
```
domain has no infra imports • application uses ports only • execution log is append-only — all enforced in CI.
```
