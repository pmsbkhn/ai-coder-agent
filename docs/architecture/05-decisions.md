# 05 — Architecture Decisions & Rationale

**Viewpoint:** Decision. ADR-style records of the load-bearing choices, each with
the forces and the trade-off accepted. These are the decisions that, if reversed,
would change the module (`02`) or runtime (`03`) structure.

| ID | Decision | Rationale | Trade-off / status |
|---|---|---|---|
| **AD-1** | **Python core; tools over MCP** (JSON-RPC) | The core stays language/build-agnostic; a tool's stack never leaks into the loop. Adding a tool = a new server, not a new port. | Extra process + serialization per tool call. Accepted. |
| **AD-2** | **Hexagonal + machine-enforced boundaries** | Domain stays pure; the loop depends on ports, not SDKs → testable with fakes, swappable infra. | Enforced by `.importlinter` (3 contracts) + AST fitness test in CI. The agent eats its own dog food (TC-ARCH). |
| **AD-3** | **Provider-agnostic LLM; `structured.generate_structured()` is the robustness primitive** | Validate model output against a Pydantic schema and feed errors back for a bounded repair retry — this is what makes a weak local model usable. Provider/model swap via env, never code. | One extra round-trip on malformed output. Accepted. |
| **AD-4** | **Deterministic-first Verifier; dual verdict (M4)** | The functional pass/fail comes from parsed surefire / exit code — the LLM only *explains*, never flips the verdict. M4 splits **architecture** failures (ArchUnit rules) from functional ones. | Needs a real build toolchain. The defining safety property. |
| **AD-5** | **No LangGraph — plain-Python control loop** | The loop is simple + deterministic and state is externalized to `MemoryPort`; a framework adds nothing and would violate the import boundary. | Could return as an adapter-level runner if checkpointer/streaming is ever needed. |
| **AD-6** | **Coder emits WHOLE files, not diffs** | Avoids fragile diff-apply against model output. | Token cost ∝ file size; targeted search/replace is a known future optimization (see `06`). |
| **AD-7** | **Project Profile (YAML) holds everything stack-specific; env for runtime swap** | Extending beyond MSFW = a new profile + a `BuildToolPort` adapter, not a core change. Runtime knobs (model, repo path, memory, sandbox, delivery) are env so the same profile is portable. | Don't truly generalize until a 2nd real target exists. |
| **AD-8** | **Verify ONCE at the end, then heal-to-green** (not per-task) | A weak model over-decomposes a cohesive change; per-task verification fails on unavoidable non-compiling intermediates and later tasks undo earlier ones. | A broken plan is only caught at the end. Accepted (heal recovers). |
| **AD-9** | **Heal VARIES its input each attempt** (reflection + reset-to-clean restore) | At temperature 0 a fixed prompt yields the same broken output forever. A reasoning pass that sees the failing code + history hands the Coder a different concrete strategy each attempt; reset-to-clean **restores** the cumulative change so a partial re-emit never drops correct earlier edits. | More LLM calls per heal. This is what makes local models converge. |
| **AD-10** | **Per-role LLM split** (reasoner plans, fast model codes) | Empirically: `gpt-oss:120b → qwen3-coder:30b` scores lite 3/3; `qwen3-coder` planning for itself scores 1/3. A strong planner is the deciding factor. | Two models resident/loaded. Falls back to one shared model. |
| **AD-11** | **Eval = tests-as-oracle; tests are an immutable protected artifact** | Pre-written tests define "done"; the agent implements code to pass them and is **refused** any write to a test file (`protected_globs`). Closes the "agent dropped the test, mvn still green" false positive. | Authoring good oracle tasks is manual. |
| **AD-12** | **Single Postgres (append-only log + RLS + pgvector); graph DB deferred** | One store carries the immutable audit trail *and* RAG. Append-only is enforced by the DB (the `agent_app` role lacks UPDATE/DELETE + no RLS policy), not by convention. | RAG retrieval not yet wired into the loop (see `06`). Graph code-intel via jdeps/LSP on demand. |
| **AD-13** | **Parallelism is PROCESS-level (worktrees), not in-process threads** | The MCP gateway holds one stdio connection per server — not concurrency-safe. One process per requirement + a per-session `feature/<sid>` worktree gives true isolation with no shared mutable state. | No shared model cache across runs; Ollama serializes inference anyway. |
| **AD-14** | **Sandbox via a throwaway Docker container** (`--network none`, offline) | The build executes model-generated code + arbitrary Maven plugins; in a container they get no host FS beyond the worktree + `~/.m2` and no network. The container carries its own JDK. | Requires a pre-populated `~/.m2` for offline; runs as root today (hardening pending). Off by default. |
| **AD-15** | **Deploy is a human gate, deny-by-default** | An autonomous agent must never deploy on its own. `ApprovalPort` denies unless an explicit signal (`AICODER_DEPLOY_APPROVE=1`) or an interactive human approves; deploy only runs for a green change with a configured command. | Manual step in the pipeline by design. |
| **AD-16** | **Structured requirements intake; the AC/NFR id is the load-bearing thread** | The input contract moves from a vague prose blob to a `RequirementSpec` (YAML: User Stories + Gherkin AC + measurable ISO-25010 NFRs). The human authors *what to build* (the only thing the agent does not invent); the agent derives B1–B5 (Glossary, Use Cases, Event Flow, typed Context Map, API/EVS/SAGA) and must trace every artifact back to an `AC-`/`NFR-` id. The linter enforces **AC→locked-test (T1)** + **test→requirement (T3)** as HARD (block under `review_strict`, drive design-heal); NFR coverage (T2), event-flow consistency (T4) and the saga/sync boundary smell (T5) are advisory. | Fully opt-in (`--requirements`): no file ⇒ prose path unchanged, all T-rules off. See `09`. |

## Integration bugs found by e2e and fixed (do NOT reintroduce)

These are decisions-by-scar — each was a real failure surfaced only by running end-to-end:

1. **`git worktree add` hang** — a background `git gc` inherited the server's stdout pipe → `capture_output` waited forever. Fix: git/maven subprocesses run with `-c gc.auto=0 -c maintenance.auto=false` and `stdin=DEVNULL`.
2. **Self-healing blind to compile errors** — Maven prints compiler errors to **stdout**, not surefire/stderr. Fix: `MavenBuildTool` evidence includes `[ERROR]`/`BUILD FAILURE` stdout lines.
3. **Cross-file breaks unfixable** — the Coder only saw a task's files. Fix: `_files_from_evidence()` widens the read set to every `.java` the compiler blamed (CONTEXT_WIDENED).
4. **Commit silently aborted** — target repo had no git identity. Fix: commit with explicit `-c user.name/-c user.email`.
5. **Tool failures swallowed** — a transport-OK response with `{"ok": false}` looked like success. Fix: `_tool` raises `ToolInvocationError`.
6. **Stale `~/.m2`** — even the pristine MSFW baseline failed to compile (missing framework package); the agent can't fix that by editing sample-service. Always `mvn install -DskipTests` at the MSFW root first.
7. **Append-only false positive in a guard test** — a crude grep matched the word "delete" in a docstring. Fix: match real `UPDATE/DELETE … agent_execution_log` SQL.

See `06-status-and-roadmap.md` for what remains weak or unbuilt.
