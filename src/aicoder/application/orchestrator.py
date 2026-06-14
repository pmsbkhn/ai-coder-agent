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
    BuildToolPort,
    CoderPort,
    MCPGatewayPort,
    MemoryPort,
    PlannerPort,
)
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
    ) -> None:
        self._profile = profile
        self._planner = planner
        self._coder = coder
        self._memory = memory
        self._gateway = gateway
        self._build = build

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

        # ---- PLANNING (skeleton-first: TC-CORE-03) ----
        session.start_planning()
        repo_map = self._fetch_repo_map()
        plan = self._planner.generate_plan(prompt, repo_map)
        session.set_plan(plan)
        self._log(session, "PLAN_CREATED", {"tasks": [t.id for t in plan.tasks]})
        self._memory.save_session(session)

        if plan.is_empty:
            session.transition_to(SessionState.BLOCKED)
            self._log(session, "EMPTY_PLAN", {})
            self._memory.save_session(session)
            return session

        # ---- workspace (isolated worktree) ----
        branch = f"feature/{session_id}"
        ws = self._tool("git", "start_task", branch=branch)
        workdir = ws.get("worktree") or self._profile.target.repo_path

        # ---- coding phase: apply every task, each seeing the CURRENT state of
        # ALL plan files (so a later task coordinates with earlier edits). We do
        # NOT verify between tasks: a weak model over-decomposes a cohesive change
        # into per-file tasks, and per-task verification fails on the unavoidable
        # intermediate non-compiling states (and later tasks would undo earlier
        # ones). Apply everything, then verify once and heal to green.
        # Protected spec files (e.g. pre-written tests) are read-only context: the
        # Coder sees them to know what "done" means, but can never overwrite them.
        protected = self._protected_files(workdir)
        all_targets = _unique(
            [f for task in plan.tasks for f in task.target_files] + protected
        )
        # Cumulative change (latest content per path). Tracked so a heal that
        # re-emits only SOME files never loses correct edits from earlier ones
        # when the worktree is reset to clean (M3).
        applied: dict[str, str] = {}
        session.start_coding()  # PLANNING -> CODING
        for task in plan.tasks:
            files = self._read_files(workdir, all_targets)
            change = self._coder.apply_task(task, files)
            self._apply_change(change, workdir, applied, session)
            self._log(
                session, "DIFF_APPLIED", {"task": task.id, "files": [e.path for e in change.edits]}
            )
        self._memory.save_session(session)

        # ---- verify + self-heal the whole change ----
        if not self._verify_and_heal(session, prompt, all_targets, workdir, applied):
            self._memory.save_session(session)
            return session

        session.record_pass()  # VERIFYING -> DONE
        self._tool("git", "commit", workdir=workdir, message=f"agent: {prompt[:60]}")
        self._log(session, "SESSION_DONE", {})
        self._memory.save_session(session)
        return session

    # ------------------------------------------------------------------ #
    # Per-task self-healing loop
    # ------------------------------------------------------------------ #
    def _apply_change(
        self, change, workdir: str, applied: dict[str, str], session: AgentSession
    ) -> None:
        for edit in change.edits:
            if self._is_protected(edit.path):
                # The agent tried to edit a protected spec file (e.g. a test that
                # defines the task). Refuse — the oracle must stay immutable.
                self._log(session, "WRITE_BLOCKED", {"path": edit.path})
                continue
            self._tool("git", "write_file", workdir=workdir, path=edit.path, content=edit.content)
            applied[edit.path] = edit.content  # remember for reset-to-clean restore

    def _verify_and_heal(
        self, session: AgentSession, requirement: str, targets: list[str], workdir: str,
        applied: dict[str, str],
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
                self._apply_change(change, workdir, applied, session)
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

    def _protected_files(self, workdir: str) -> list[str]:
        """Repo-relative files matching the profile's protected globs (read-only)."""
        if not self._profile.protected_globs:
            return []
        res = self._tool("git", "list_files", workdir=workdir, glob="**/*")
        return [p for p in res.get("files", []) if self._is_protected(p)]

    def _is_protected(self, rel_path: str) -> bool:
        rel = rel_path.replace("\\", "/")
        return any(fnmatch(rel, g) for g in self._profile.protected_globs)

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
