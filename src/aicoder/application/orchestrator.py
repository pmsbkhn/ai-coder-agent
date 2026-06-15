r"""Orchestrator — the stateless control loop (pure Python, ports only).

Drives one requirement through the AgentSession state machine:

    INIT -> PLANNING -> [ per task: CODING -> VERIFYING -> (heal | next) ] -> DONE
                                                       \-> HEALING_FAILED

It holds no mutable state: each step mutates the loaded AgentSession and saves it
back via MemoryPort. Tools (code-reader, git, maven) are reached through ports;
the verdict is deterministic (BuildToolPort), the model only generates code/plans.
No orchestration framework — the loop is plain Python so it stays testable and
provider-independent.
"""

from __future__ import annotations

import hashlib
import re
from fnmatch import fnmatch
from pathlib import Path

from aicoder.application.ports.outbound import (
    AnalysisPort,
    ApprovalPort,
    BuildToolPort,
    CoderPort,
    DeployPort,
    DesignPort,
    MCPGatewayPort,
    MemoryPort,
    PlannerPort,
    ReviewPort,
)
from aicoder.application.design_docs import ad_path, render_ad, render_tech_spec, tech_spec_path
from aicoder.application.profile import ProjectProfile
from aicoder.domain.errors import ToolInvocationError
from aicoder.domain.models import ExecutionTrace, SessionState, Task, ToolRequest
from aicoder.domain.session import AgentSession


class Orchestrator:
    def __init__(
        self,
        *,
        profile: ProjectProfile,
        planner: PlannerPort,
        coder: CoderPort,
        memory: MemoryPort,
        gateway: MCPGatewayPort,
        build: BuildToolPort,
        deliver: str = "local",
        approval: ApprovalPort | None = None,
        deployer: DeployPort | None = None,
        designer: DesignPort | None = None,
        design_mode: str = "off",
        reviewer: ReviewPort | None = None,
        analyst: AnalysisPort | None = None,
        analysis_mode: str = "off",
    ) -> None:
        self._profile = profile
        self._planner = planner
        self._coder = coder
        self._memory = memory
        self._gateway = gateway
        self._build = build
        # Delivery mode (M5): "local" = commit only (default), "push" = also push
        # the branch to its remote, "pr" = push + open a pull request. Delivery is
        # best-effort — it never fails an already-committed (DONE) run.
        self._deliver = deliver
        # M6: deploy gate. Deploy runs only when the profile defines a deploy
        # command AND a human approves (approval denies by default). Both None =>
        # no deploy step at all.
        self._approval = approval
        self._deployer = deployer
        # M07 design-first (Slice 1): when enabled, the Designer produces a
        # DesignSpec + executable TestPlan that is logged (auditable) BEFORE coding.
        # "off" (default) keeps the current fast path. Approval + locking the tests
        # as the oracle are later slices.
        self._designer = designer
        self._design_mode = design_mode
        # M07 Slice 4: adversarial reviewer of the proposed tests before locking.
        self._reviewer = reviewer
        # ADR-08 analysis phase: when enabled, the Analyst restates a prose
        # requirement + surfaces ambiguity BEFORE design; a genuinely ambiguous
        # requirement blocks on the clarification gate. "off" (default) keeps the
        # current behavior (straight to design/plan).
        self._analyst = analyst
        self._analysis_mode = analysis_mode

    # ------------------------------------------------------------------ #
    # Public entry point (RequirementPort)
    # ------------------------------------------------------------------ #
    def run_requirement(self, prompt: str, idempotency_key: str | None = None) -> AgentSession:
        session_id = idempotency_key or _new_session_id(prompt)

        # TC-CORE-02: a live session for the same key short-circuits (no re-plan).
        existing = self._memory.load_session(session_id)
        if existing is not None and not existing.is_terminal:
            return existing

        session = AgentSession(
            session_id=session_id,
            idempotency_key=idempotency_key,
            max_attempts=self._profile.healing.max_attempts,
            no_progress_breaker=self._profile.healing.no_progress_breaker,
        )
        self._log(session, "SESSION_CREATED", {"prompt": prompt})

        # Pre-implementation ordering (ADR-08 + M07): the pipeline is
        #   ANALYZE -> [clarification gate] -> DESIGN(AD+TechSpecs) -> [architect gate]
        #   -> PLAN -> CODE.
        # Both reasoning phases run BEFORE planning — a plan is the implementer's
        # decomposition, not a gate before analysis/design (a flaky/empty plan must
        # never block them).
        session.start_planning()
        repo_map = self._fetch_repo_map()

        # ---- workspace (isolated worktree, needed to write the design artifacts) ----
        branch = f"feature/{session_id}"
        ws = self._tool("git", "start_task", branch=branch)
        workdir = ws.get("worktree") or self._profile.target.repo_path

        # Cumulative change (latest content per path). Tracked so a reset-to-clean
        # heal (M3) restores everything — including the design docs + locked tests
        # written below, which are otherwise untracked and wiped by `git clean -fd`.
        applied: dict[str, str] = {}

        # ---- ANALYZE: restate a prose requirement + surface ambiguity. A genuinely
        # ambiguous requirement blocks on the human clarification gate (ADR-08). ----
        if not self._run_analysis(session, prompt, repo_map):
            self._memory.save_session(session)
            return session

        # ---- DESIGN: write the AD + one Tech Spec per bounded context and (if gated)
        # lock the architect-approved tests as the oracle the Coder must satisfy. ----
        locked, proceed = self._run_design(session, prompt, repo_map, workdir, applied)
        if not proceed:
            self._memory.save_session(session)
            return session

        # ---- PLAN: now decompose the (approved) work into implementation tasks. ----
        plan = self._planner.generate_plan(prompt, repo_map)
        session.set_plan(plan)
        self._log(session, "PLAN_CREATED", {"tasks": [t.id for t in plan.tasks]})
        self._memory.save_session(session)
        if plan.is_empty:
            session.transition_to(SessionState.BLOCKED)
            self._log(session, "EMPTY_PLAN", {})
            self._memory.save_session(session)
            return session

        # ---- coding phase: apply every task, each seeing the CURRENT state of
        # ALL plan files (so a later task coordinates with earlier edits). We do
        # NOT verify between tasks: a weak model over-decomposes a cohesive change
        # into per-file tasks, and per-task verification fails on the unavoidable
        # intermediate non-compiling states (and later tasks would undo earlier
        # ones). Apply everything, then verify once and heal to green.
        # Protected spec files (e.g. pre-written tests) are read-only context: the
        # Coder sees them to know what "done" means, but can never overwrite them.
        protected = self._protected_files(workdir, locked)
        all_targets = _unique(
            [f for task in plan.tasks for f in task.target_files] + protected
        )
        session.start_coding()  # PLANNING -> CODING
        for task in plan.tasks:
            files = self._read_files(workdir, all_targets)
            change = self._coder.apply_task(task, files)
            self._apply_change(change, workdir, applied, session, locked)
            self._log(
                session, "DIFF_APPLIED", {"task": task.id, "files": [e.path for e in change.edits]}
            )
        self._memory.save_session(session)

        # ---- verify + self-heal the whole change ----
        if not self._verify_and_heal(session, prompt, all_targets, workdir, applied, locked):
            self._memory.save_session(session)
            return session

        session.record_pass()  # VERIFYING -> DONE
        self._tool("git", "commit", workdir=workdir, message=f"agent: {prompt[:60]}")
        if self._deliver in ("push", "pr"):
            self._run_delivery(session, workdir, prompt)
        self._maybe_deploy(session, workdir, prompt)
        self._log(session, "SESSION_DONE", {})
        self._memory.save_session(session)
        return session

    def _run_analysis(self, session: AgentSession, prompt: str, repo_map: str) -> bool:
        """ADR-08 analysis phase — runs BEFORE design. Returns `proceed`.

        - analysis off / no analyst → True (straight to design): unchanged fast path.
        - analyst runs → restate the prose requirement + surface assumptions / open
          questions / acceptance criteria; log ANALYSIS_DONE (auditable).
        - NOT ambiguous → resume PLANNING, True.
        - ambiguous + no approval port → audit-only: log NEEDS_CLARIFICATION, proceed
          on the analyst's assumptions (True). (A gate requires an ApprovalPort.)
        - ambiguous + approval → clarification gate (deny-by-default): approve →
          proceed on assumptions (True); deny → BLOCKED (False).
        """
        if self._analyst is None or self._analysis_mode == "off":
            return True

        session.start_analyzing()  # PLANNING -> ANALYZING
        spec = self._analyst.analyze(prompt, repo_map)
        self._log(session, "ANALYSIS_DONE", {
            "restatement": spec.restatement[:500],
            "assumptions": spec.assumptions[:10],
            "open_questions": spec.open_questions[:10],
            "acceptance_criteria": spec.acceptance_criteria[:10],
            "ambiguous": spec.ambiguous,
        })
        if not spec.ambiguous:
            session.resume_planning()  # ANALYZING -> PLANNING
            return True

        session.await_clarification()  # ANALYZING -> AWAITING_CLARIFICATION
        self._log(session, "NEEDS_CLARIFICATION", {"open_questions": spec.open_questions[:10]})
        if self._approval is None:
            session.resume_planning()  # no gate wired → audit-only, proceed on assumptions
            return True
        summary = (f"clarify {len(spec.open_questions)} open question(s) before building — "
                   f"proceed on the analyst's assumptions?")
        if self._approval.request_approval("clarification", summary):
            self._log(session, "CLARIFICATION_PROCEED", {"assumptions": spec.assumptions[:10]})
            session.resume_planning()  # AWAITING_CLARIFICATION -> PLANNING
            return True
        session.transition_to(SessionState.BLOCKED)  # AWAITING_CLARIFICATION -> BLOCKED
        self._log(session, "CLARIFICATION_REQUIRED", {"open_questions": spec.open_questions[:10]})
        return False

    def _run_design(
        self, session: AgentSession, prompt: str, repo_map: str, workdir: str,
        applied: dict[str, str],
    ) -> tuple[set[str], bool]:
        """M07 design-first — runs BEFORE planning. Returns (locked_test_paths, proceed).

        - design off / no designer → ([], True): straight to planning (fast path).
        - designer but NO approval port → produce AD+TechSpecs + log only ([], True).
        - designer + approval → write the proposed tests, (adversarial review,) then
          gate on the ARCHITECT; on approve LOCK them as the oracle ([paths], True) and
          resume PLANNING; on reject → BLOCKED ([], False).

        (Complexity tiering used to live here keyed on the plan; with design moved
        ahead of the plan that signal is gone — tiering belongs to the future Analysis
        phase, ADR-08. `auto` therefore designs like `always` for now.)
        """
        if self._designer is None or self._design_mode == "off":
            return set(), True

        spec = self._designer.propose_design(prompt, repo_map)
        # Materialize the explicit design artifacts: one umbrella AD + one Tech Spec
        # per bounded context (1 BC = 1 Tech Spec), written into the worktree so they
        # are reviewable and commit alongside the change.
        docs = self._write_design_docs(workdir, spec, prompt, applied)
        self._log(session, "DESIGN_PROPOSED", {
            "summary": spec.summary[:500],
            "bounded_contexts": spec.bounded_contexts,
            "docs": docs,
            "proposed_tests": [t.path for t in spec.all_tests()],
        })
        if self._approval is None:
            return set(), True  # Slice-1 behavior: AD + Tech Specs written + logged, not gated

        # Slice 4: adversarial review of the proposed tests BEFORE locking. Advisory
        # by default (concerns surfaced to the architect); review_strict auto-blocks.
        review = None
        if self._reviewer is not None:
            review = self._reviewer.review_tests(
                prompt, spec.summary, [t.content for t in spec.all_tests()]
            )
            self._log(session, "TEST_REVIEW", {"ok": review.ok, "concerns": review.concerns[:10]})
            if not review.ok and self._profile.design.review_strict:
                self._log(session, "DESIGN_REJECTED",
                          {"reason": "failed adversarial test review", "concerns": review.concerns[:10]})
                session.transition_to(SessionState.BLOCKED)  # from PLANNING
                return set(), False

        # Write the proposed tests, then gate on the ARCHITECT before locking them.
        session.start_designing()  # PLANNING -> DESIGNING
        locked: set[str] = set()
        for t in spec.all_tests():
            self._tool("git", "write_file", workdir=workdir, path=t.path, content=t.content)
            locked.add(t.path.replace("\\", "/"))
            applied[t.path.replace("\\", "/")] = t.content  # survive reset-to-clean
        session.await_approval()  # DESIGNING -> AWAITING_APPROVAL
        concerns = review.concerns[:10] if review else []
        self._log(session, "APPROVAL_REQUESTED",
                  {"action": "architect_review", "docs": docs,
                   "tests": sorted(locked), "review_concerns": concerns})
        summary = (f"architect review — {len(spec.tech_specs)} tech spec(s) across "
                   f"{spec.bounded_contexts}; {len(locked)} test(s)"
                   + (f"; {len(concerns)} review concern(s)" if concerns else ""))
        if self._approval.request_approval("design", summary):
            self._log(session, "DESIGN_APPROVED", {"docs": docs, "locked_tests": sorted(locked)})
            session.resume_planning()  # AWAITING_APPROVAL -> PLANNING (decompose the design)
            return locked, True
        session.reject_design()  # AWAITING_APPROVAL -> BLOCKED
        self._log(session, "DESIGN_REJECTED", {})
        return set(), False

    def _write_design_docs(
        self, workdir: str, spec, requirement: str, applied: dict[str, str]
    ) -> list[str]:
        """Render + write the AD (umbrella) and one Tech Spec per bounded context.
        Recorded in `applied` so a reset-to-clean heal restores them and they commit
        with the change."""
        docs_dir = self._profile.design.docs_dir
        paths: list[str] = []

        def _write(path: str, content: str) -> None:
            self._tool("git", "write_file", workdir=workdir, path=path, content=content)
            applied[path] = content
            paths.append(path)

        _write(ad_path(docs_dir), render_ad(spec, requirement, docs_dir))
        for ts in spec.tech_specs:
            _write(tech_spec_path(ts, docs_dir), render_tech_spec(ts))
        return paths

    def _maybe_deploy(self, session: AgentSession, workdir: str, prompt: str) -> None:
        """M6 gated deploy: only for a green change, only with a configured deploy
        command, and only after explicit human approval. Safe by default — no
        command or no approval => nothing is deployed."""
        command = self._profile.deploy.command
        if not command or self._approval is None or self._deployer is None:
            return
        self._log(session, "APPROVAL_REQUESTED", {"action": "deploy", "command": command})
        if not self._approval.request_approval("deploy", f"deploy: {prompt[:60]}"):
            self._log(session, "DEPLOY_DENIED", {})  # held at the human gate
            return
        result = self._deployer.deploy(workdir, command)
        if result.get("ok"):
            self._log(session, "DEPLOYED", {"output": (result.get("output") or "")[:400]})
        else:
            self._log(session, "DEPLOY_FAILED", {"error": (result.get("error") or "")[:400]})

    def _run_delivery(self, session: AgentSession, workdir: str, prompt: str) -> None:
        """Push the branch (and optionally open a PR) — best-effort: a delivery
        failure (no remote, no auth) is logged but never fails the committed run."""
        push = self._gateway.execute_tool_call(
            ToolRequest(server="git", method="push", params={"workdir": workdir})
        )
        res = push.result or {}
        if not push.ok or not res.get("ok"):
            self._log(session, "DELIVERY_SKIPPED",
                      {"reason": res.get("error") or push.error_message or "push failed"})
            return
        self._log(session, "PUSHED", {"remote": res.get("remote"), "branch": res.get("branch")})
        if self._deliver != "pr":
            return
        pr = self._gateway.execute_tool_call(
            ToolRequest(server="git", method="open_pr",
                        params={"workdir": workdir, "title": f"agent: {prompt[:60]}"})
        )
        pres = pr.result or {}
        if pr.ok and pres.get("ok"):
            self._log(session, "PR_OPENED", {"url": pres.get("url")})
        else:
            self._log(session, "PR_SKIPPED", {"reason": pres.get("error") or "pr failed"})

    # ------------------------------------------------------------------ #
    # Per-task self-healing loop
    # ------------------------------------------------------------------ #
    def _apply_change(
        self, change, workdir: str, applied: dict[str, str], session: AgentSession,
        locked: set[str],
    ) -> None:
        for edit in change.edits:
            if self._is_protected(edit.path, locked):
                # The agent tried to edit a protected spec file (e.g. a test that
                # defines the task). Refuse — the oracle must stay immutable.
                self._log(session, "WRITE_BLOCKED", {"path": edit.path})
                continue
            self._tool("git", "write_file", workdir=workdir, path=edit.path, content=edit.content)
            applied[edit.path] = edit.content  # remember for reset-to-clean restore

    def _verify_and_heal(
        self, session: AgentSession, requirement: str, targets: list[str], workdir: str,
        applied: dict[str, str], locked: set[str],
    ) -> bool:
        """Verify the whole change; on failure, REFLECT then re-code, until green or
        the breaker trips. Returns True on pass. Leaves the session in VERIFYING
        (pass) or HEALING_FAILED.

        M3: before each heal re-code we (1) reset the worktree to clean so the Coder
        works from pristine files instead of compounding broken output, and (2) run a
        reflection step whose output VARIES with the accumulated attempt history — so
        a deterministic (temp 0) Coder gets a different prompt each attempt and can
        escape the same-prompt/same-error fixpoint."""
        read_paths = list(targets)
        error_context = ""
        strategies: list[str] = []
        first = True
        while True:
            if not first:  # re-code a fix over the whole change
                files = self._read_files(workdir, read_paths)
                fix_task = Task(id="heal", description=requirement, target_files=read_paths)
                change = self._coder.apply_task(fix_task, files, error_context)
                self._apply_change(change, workdir, applied, session, locked)
                self._log(
                    session, "DIFF_APPLIED", {"task": "heal", "files": [e.path for e in change.edits]}
                )
            first = False

            session.start_verifying()  # CODING -> VERIFYING
            result = self._build.run_tests(
                module=self._profile.target.sandbox_module, workdir=workdir
            )
            if result.passed:
                self._log(session, "VERIFY_PASS", {})
                return True

            signature = result.error_signature or _signature(result.evidence)
            self._log(
                session, "VERIFY_FAIL",
                {
                    "failed_tests": result.failed_tests,
                    "signature": signature,
                    # Dual verdict (M4): which gate failed — functional, architecture, or both.
                    "functional_passed": result.functional_passed,
                    "arch_passed": result.arch_passed,
                    # Surface the actual build evidence — a compile failure has no
                    # failed_tests, so without this the trace is unreadable.
                    "evidence_head": (result.evidence or "").strip()[:400],
                },
            )
            session.record_failure(signature)  # VERIFYING -> HEALING
            if session.should_trip_breaker():
                session.trip_breaker()  # HEALING -> HEALING_FAILED
                self._log(session, "HEALING_FAILED", {"attempts": session.attempts})
                return False

            for path in _files_from_evidence(workdir, result.evidence):
                if path not in read_paths:
                    read_paths.append(path)
                    self._log(session, "CONTEXT_WIDENED", {"added": path})

            distilled = _distill(result.failed_tests, result.evidence)
            # Snapshot the CURRENT (failing) code so reflection reasons about the
            # real source, not a guessed shape — taken BEFORE any reset-to-clean.
            failing_files = self._read_files(workdir, read_paths)
            # M3 reset-to-clean: purge the worktree of any abandoned/stray files,
            # then RESTORE the cumulative change. The coder re-emits whole files
            # for only a subset each attempt, so a bare reset would silently drop
            # correct edits from earlier attempts (e.g. a test it stops re-emitting).
            # Restoring `applied` keeps every correct edit; the coder overwrites
            # what it re-emits next iteration.
            if self._profile.healing.reset_to_clean:
                self._tool("git", "reset_clean", workdir=workdir)
                for path, content in applied.items():
                    self._tool("git", "write_file", workdir=workdir, path=path, content=content)
            # M3 reflection: a reasoning pass that varies with history -> a fresh,
            # concrete strategy that changes the Coder's prompt each attempt.
            strategy = (
                self._planner.reflect(requirement, distilled, failing_files, strategies) or ""
            ).strip()
            if not strategy:  # never feed empty guidance — fall back to the raw error
                strategy = "Focus precisely on the compiler/test output below and fix the exact line(s)."
            strategies.append(strategy)
            self._log(session, "REFLECTION", {"attempt": session.attempts, "strategy": strategy[:400]})

            session.retry_coding()  # HEALING -> CODING
            error_context = f"# Fix strategy\n{strategy}\n\n# Exact build output\n{distilled}"

    # ------------------------------------------------------------------ #
    # Port helpers
    # ------------------------------------------------------------------ #
    def _fetch_repo_map(self) -> str:
        module = self._profile.target.sandbox_module or ""
        result = self._tool("code-reader", "get_repo_map", subpath=module)
        repo_map = result.get("repo_map", "")
        return repo_map

    def _protected_files(self, workdir: str, locked: set[str]) -> list[str]:
        """Repo-relative files the Coder may READ but not WRITE: profile protected
        globs (e.g. pre-written tests) + design-locked approved tests (M07)."""
        if not self._profile.protected_globs and not locked:
            return list(locked)
        res = self._tool("git", "list_files", workdir=workdir, glob="**/*")
        found = [p for p in res.get("files", []) if self._is_protected(p, locked)]
        return _unique(found + sorted(locked))

    def _is_protected(self, rel_path: str, locked: set[str]) -> bool:
        rel = rel_path.replace("\\", "/")
        return rel in locked or any(fnmatch(rel, g) for g in self._profile.protected_globs)

    def _read_files(self, workdir: str, paths: list[str]) -> dict[str, str]:
        files: dict[str, str] = {}
        for path in paths:
            res = self._tool("git", "read_file", workdir=workdir, path=path)
            if res.get("exists"):
                files[path] = res.get("content", "")
        return files

    def _tool(self, server: str, method: str, **params) -> dict:
        resp = self._gateway.execute_tool_call(
            ToolRequest(server=server, method=method, params=params)
        )
        if not resp.ok:
            raise ToolInvocationError(resp.error_message or "tool call failed", code=resp.error_code)
        result = resp.result or {}
        # Transport succeeded, but the tool itself may report a business failure
        # (e.g. a commit that aborted). Don't let that pass as success.
        if result.get("ok") is False:
            raise ToolInvocationError(f"{server}.{method} failed: {result.get('error', 'unknown')}")
        return result

    def get_log(self, session_id: str) -> list[ExecutionTrace]:
        """Read the append-only trace for a session (observability)."""
        return self._memory.get_traces(session_id)

    def _log(self, session: AgentSession, event_type: str, payload: dict) -> None:
        seq = len(self._memory.get_traces(session.session_id))
        self._memory.append_log(
            ExecutionTrace(
                session_id=session.session_id, seq=seq, event_type=event_type, payload=payload
            )
        )


# ---------------------------------------------------------------------- #
def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _new_session_id(seed: str) -> str:
    return "sess_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _signature(evidence: str) -> str:
    return hashlib.sha1(evidence[:500].encode("utf-8", "replace")).hexdigest()[:12]


def _distill(failed_tests: list[str], evidence: str) -> str:
    head = ", ".join(failed_tests[:5])
    return f"Failed tests: {head}\n\nKey output:\n{evidence[:800]}"


_JAVA_TOKEN = re.compile(r"[^\s\[\]():]+\.java")


def _files_from_evidence(workdir: str, evidence: str) -> list[str]:
    """Repo-relative .java paths the compiler/test output blamed (inside workdir)."""
    wd = Path(workdir).resolve()
    out: list[str] = []
    seen: set[str] = set()
    for raw in _JAVA_TOKEN.findall(evidence):
        candidate = raw.lstrip("/")  # '/C:/...' -> 'C:/...'
        p = Path(candidate if Path(candidate).is_absolute() else raw)
        try:
            rel = str(p.resolve().relative_to(wd)).replace("\\", "/")
        except (ValueError, OSError):
            continue
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out
