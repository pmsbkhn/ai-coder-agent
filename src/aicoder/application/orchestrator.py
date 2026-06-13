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

        # ---- execute tasks ----
        session.start_coding()  # PLANNING -> CODING (first task)
        tasks = plan.tasks
        for index, task in enumerate(tasks):
            self._execute_task_with_healing(session, task, workdir)
            self._memory.save_session(session)
            if session.state is SessionState.HEALING_FAILED:
                return session
            # task passed (we are in VERIFYING)
            if index < len(tasks) - 1:
                session.start_next_task()  # VERIFYING -> CODING (reset attempts)

        session.record_pass()  # VERIFYING -> DONE
        self._tool("git", "commit", workdir=workdir, message=f"agent: {prompt[:60]}")
        self._log(session, "SESSION_DONE", {})
        self._memory.save_session(session)
        return session

    # ------------------------------------------------------------------ #
    # Per-task self-healing loop
    # ------------------------------------------------------------------ #
    def _execute_task_with_healing(self, session: AgentSession, task: Task, workdir: str) -> None:
        error_context = ""
        read_paths = list(task.target_files)  # widens to whatever the compiler blames
        while True:
            files = self._read_files(workdir, read_paths)
            change = self._coder.apply_task(task, files, error_context)
            for edit in change.edits:
                self._tool("git", "write_file", workdir=workdir, path=edit.path, content=edit.content)
            self._log(session, "DIFF_APPLIED", {"task": task.id, "files": [e.path for e in change.edits]})

            session.start_verifying()  # CODING -> VERIFYING
            result = self._build.run_tests(
                module=self._profile.target.sandbox_module, workdir=workdir
            )

            if result.passed:
                self._log(session, "VERIFY_PASS", {"task": task.id})
                return

            signature = result.error_signature or _signature(result.evidence)
            self._log(
                session,
                "VERIFY_FAIL",
                {"task": task.id, "failed_tests": result.failed_tests, "signature": signature},
            )
            session.record_failure(signature)  # VERIFYING -> HEALING

            if session.should_trip_breaker():
                session.trip_breaker()  # HEALING -> HEALING_FAILED
                self._log(session, "HEALING_FAILED", {"task": task.id, "attempts": session.attempts})
                return

            # Widen the Coder's view to every file the compiler blamed, so it can
            # fix a break in a file the task didn't nominally target (the common
            # case when a plan splits a cross-cutting change across tasks).
            for path in _files_from_evidence(workdir, result.evidence):
                if path not in read_paths:
                    read_paths.append(path)
                    self._log(session, "CONTEXT_WIDENED", {"task": task.id, "added": path})

            session.retry_coding()  # HEALING -> CODING
            error_context = _distill(result.failed_tests, result.evidence)

    # ------------------------------------------------------------------ #
    # Port helpers
    # ------------------------------------------------------------------ #
    def _fetch_repo_map(self) -> str:
        module = self._profile.target.sandbox_module or ""
        result = self._tool("code-reader", "get_repo_map", subpath=module)
        repo_map = result.get("repo_map", "")
        return repo_map

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
