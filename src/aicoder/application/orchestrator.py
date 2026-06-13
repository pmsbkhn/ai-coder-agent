"""Orchestrator — the stateless application core.

It owns NO mutable state: every step loads the AgentSession from MemoryPort,
advances the state machine, and saves it back. It reaches infrastructure only
through the injected ports. The full control loop (plan -> code -> verify -> heal)
is built out in M2/M3; M0 wires the skeleton and proves the boundaries.
"""

from __future__ import annotations

from aicoder.application.ports.outbound import (
    BuildToolPort,
    MCPGatewayPort,
    MemoryPort,
    PlannerPort,
)
from aicoder.application.profile import ProjectProfile
from aicoder.domain.errors import DomainException
from aicoder.domain.models import ExecutionTrace
from aicoder.domain.session import AgentSession


class Orchestrator:
    def __init__(
        self,
        *,
        profile: ProjectProfile,
        planner: PlannerPort,
        memory: MemoryPort,
        gateway: MCPGatewayPort,
        build: BuildToolPort,
    ) -> None:
        self._profile = profile
        self._planner = planner
        self._memory = memory
        self._gateway = gateway
        self._build = build

    # ------------------------------------------------------------------
    # Inbound: RequirementPort.submit_requirement
    # ------------------------------------------------------------------
    def submit_requirement(self, prompt: str, idempotency_key: str | None = None) -> str:
        """Create a session and move it to PLANNING. (Planning logic = M2.)"""
        session_id = idempotency_key or _new_session_id(prompt)

        # TC-CORE-02 (idempotency): if a live session already exists, do not
        # re-plan. Full distributed-lock semantics arrive with the real
        # MemoryAdapter; here we honour the existing-session short-circuit.
        existing = self._memory.load_session(session_id)
        if existing is not None and not existing.is_terminal:
            return session_id

        session = AgentSession(
            session_id=session_id,
            idempotency_key=idempotency_key,
            max_attempts=self._profile.healing.max_attempts,
        )
        session.start_planning()
        self._memory.append_log(
            ExecutionTrace(
                session_id=session_id,
                seq=0,
                event_type="SESSION_CREATED",
                payload={"prompt": prompt},
            )
        )
        self._memory.save_session(session)
        return session_id

    def _heal_or_stop(self, session: AgentSession, error_signature: str) -> bool:
        """Decide whether to retry the Coder or trip the circuit breaker.

        Returns True if another coding attempt should run, False if we stopped.
        """
        session.record_failure(error_signature)
        if session.should_trip_breaker():
            session.trip_breaker()
            self._memory.save_session(session)
            return False
        session.retry_coding()
        self._memory.save_session(session)
        return True


def _new_session_id(seed: str) -> str:
    """Deterministic-ish id from the requirement text (no wall clock here)."""
    import hashlib

    return "sess_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


__all__ = ["Orchestrator", "DomainException"]
