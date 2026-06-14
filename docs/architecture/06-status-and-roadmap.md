# 06 — Status, Limitations & Roadmap

A candid inventory: **what exists**, **what's weak**, **what's next**. (42010
treats the limitations as *known inconsistencies / risks* against the concerns.)

## 6.1 What exists (capability inventory)

| Area | Capability | Where | Proven |
|---|---|---|---|
| Core loop | plan → code-all → verify-once → reflect/heal → commit | `application/orchestrator.py` | e2e on MSFW sample-service + eval suites |
| State | linear-saga state machine, circuit breaker, 3-strikes no-progress | `domain/session.py` | unit + e2e |
| LLM layer | provider-agnostic (Anthropic / Ollama / OpenAI-compat), **per-role split**, validate-and-repair | `adapters/llm/*` | lite 3/3 with gpt-oss→qwen3 |
| Self-heal (M3) | reflection sees failing code + history; reset-to-clean restores cumulative; reasoning-channel fallback | orchestrator + `planner_llm.reflect` | `note` converges at heal attempt 2 |
| Verifier (M4) | deterministic surefire verdict, **functional vs architecture** (ArchUnit) dual gate | `adapters/maven_build.py` | gate bites on injected violation; eval green |
| Tools (MCP) | repo map (tree-sitter), git worktree/IO/commit/push/PR, maven test ± sandbox | `mcp_servers/*` | e2e |
| Eval | tests-as-oracle, **lite + msfw** suites, protected tests, `--repeat` reliability, `--timeout` | `eval/run_eval.py` | lite 3/3, msfw 1/2 |
| Leaderboard | multi-model sweep, partial tables, kill-resilient | `eval/leaderboard.py` | per-role split validated empirically |
| Memory | append-only execution log + sessions; **Postgres** (RLS) or in-memory | `adapters/memory_*`, `db/migrations/*` | live integration test; e2e saga persisted |
| Delivery (M5.1) | push branch + open PR (`gh`), best-effort, env-gated | `git_server` + orchestrator | push to local bare remote |
| Sandbox (M5.2) | isolated Docker build (`--network none`, offline) | `maven_server._mvn_command` | eval/target green in-container; agent e2e |
| Parallel (M5.3) | concurrent requirements, process + worktree isolation | `parallel.py` | 2 concurrent reqs → 2 isolated branches |
| CD (M6) | human-approval-gated deploy, deny-by-default | `adapters/approval.py`, `deploy.py` | unit + real-adapter tests |
| CI | repo's own fitness gates on push/PR | `.github/workflows/ci.yml` | lint-imports + pytest |

**Test/fitness status:** `uv run pytest` → 59 passed, 8 skipped; `uv run
lint-imports` → 3 contracts kept. Milestones **M0–M6 DONE**, all on `main`.

## 6.2 What's weak / known limitations

| # | Limitation | Impact | Note |
|---|---|---|---|
| L1 | **Whole-file regeneration** on every heal | token cost ∝ file size; risk of dropping unrelated content | Mitigated by reset-to-clean restore; targeted search/replace is future work |
| L2 | **temp-0 local models are non-deterministic** (MoE/GPU) | heal-count & latency vary; rare tail failures of even easy tasks | Surfaced by `--repeat`; lite is 3/3 *fully-reliable* over 5 runs, but variance is real |
| L3 | **Model headroom**: `escrow-close` (event-sourcing) currently **FAILS** with gpt-oss+qwen3 | a real MSFW idiom the current local pair can't land in-budget | A *deliberate* discriminating task; a reference solution passes → it's headroom, not a broken task |
| L4 | **GLM-4.5-Air unusable as Planner** | ~30 min/task then NO_STATE | too slow / can't emit the structured Plan; eliminated from the leaderboard |
| L5 | **RAG not wired into the loop** | `knowledge_chunk`/pgvector + profile `seed_docs` exist, but the Planner does not yet embed/query them | the store is provisioned; retrieval is unbuilt |
| L6 | **Sandbox hardening partial** | container runs as **root**; offline needs a pre-populated `~/.m2`; no CPU/cgroup pin beyond `--memory` | `--network none` + FS isolation is the main boundary; non-root + resource caps pending |
| L7 | **No real remote CI/CD wired** | push/PR/deploy mechanisms exist but aren't connected to an actual remote/cluster | by design opt-in; never auto-push/deploy to `pmsbkhn/msfw` or a cluster |
| L8 | **InMemory is the default memory** | execution log/sessions are lost on exit unless `AICODER_MEMORY=postgres` | Postgres path is built + tested; not yet the default; no resume/checkpointer beyond load_session |
| L9 | **Small eval suites** (lite 3, msfw 2) | limited coverage of idioms/difficulty | grow with bugfix-style, budget-stressing, more event-sourcing tasks |
| L10 | **Repo map is a static skeleton** | no call-graph / dependency intelligence | graph-DB deferred; jdeps/LSP on demand (AD-12) |
| L11 | **No security review of generated code** beyond arch + tests | a passing change could still be insecure | future: a security-lint gate in the Verifier |
| L12 | **Single-target generality unproven** | only MSFW + the framework-free eval target exist | don't generalize until a 2nd real stack (AD-7) |

## 6.3 Roadmap (next) — core M0–M6 done; remaining is depth & polish

**Near-term (low cost, high leverage)**
- **L1 → targeted heal edits**: aider-style search/replace to cut token cost and content-drop risk.
- **L9 → grow eval + run the leaderboard with `--repeat`** across configs for a trustworthy, flakiness-aware comparison; finish testing `gemma4` as planner.
- **L8 → make PostgresMemory the default** (with `docker compose up`) and add **resume** (re-enter a non-terminal session) for free durability.

**Medium-term (depth)**
- **L5 → wire RAG**: embed profile `seed_docs` into `knowledge_chunk`, retrieve top-k into the Planner/Coder context (the store + schema already exist).
- **L6 → harden the sandbox**: non-root user, read-only rootfs, CPU/pids limits; a dedicated offline `.m2` volume.
- **L3 → close model headroom**: re-run `escrow-close` as models improve; it's the standing "did we get better?" probe.

**Longer-term (reach)**
- **L7 → real CI/CD opt-in**: connect push/PR to a remote and `deploy.command` to a cluster, behind the existing human gate.
- **L11 → a security gate** in the dual-assessment Verifier (alongside functional + arch).
- **L12 → a 2nd target stack** (e.g. Gradle/npm) to validate the Profile + `BuildToolPort` generality, then truly generalize.
- Optional: a checkpointer/streaming runner as an adapter (AD-5) if long-horizon resumability is needed.

## 6.4 How to verify the current state yourself

```bash
uv sync --extra dev --extra tools --extra adapters
uv run pytest -q        # 59 passed, 8 skipped
uv run lint-imports     # 3 contracts kept

# objective eval (set provider/model + JAVA_HOME as for a normal run)
uv run python eval/run_eval.py --suite lite --repeat 5     # reliability table
uv run python eval/leaderboard.py --suite lite             # multi-model sweep
```

For the full env matrix and gotchas, see `/CLAUDE.md`; for *why* each piece is
shaped this way, `05-decisions.md`.
