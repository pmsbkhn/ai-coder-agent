"""AgentSession — the linear-saga state machine at the heart of the control loop.

DESIGN NOTE (resolves the "stateless Orchestrator vs. Saga" contradiction):
the Orchestrator holds NO state. All state lives in this AgentSession aggregate,
which the Orchestrator loads from / saves to the MemoryPort each step. The class
below is pure domain logic — it validates transitions and raises on illegal ones;
persistence is somebody else's job.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from aicoder.domain.errors import InvalidStateTransitionException
from aicoder.domain.models import Plan, SessionState

# Legal state transitions. Anything not listed here is rejected.
_ALLOWED: dict[SessionState, set[SessionState]] = {
    SessionState.INIT: {SessionState.PLANNING},
    SessionState.PLANNING: {SessionState.CODING, SessionState.BLOCKED},
    SessionState.CODING: {SessionState.VERIFYING},
    SessionState.VERIFYING: {SessionState.DONE, SessionState.HEALING},
    SessionState.HEALING: {SessionState.CODING, SessionState.HEALING_FAILED},
    # terminal states
    SessionState.DONE: set(),
    SessionState.HEALING_FAILED: set(),
    SessionState.BLOCKED: set(),
}


class AgentSession(BaseModel):
    session_id: str
    idempotency_key: str | None = None
    state: SessionState = SessionState.INIT
    plan: Plan | None = None
    current_task_index: int = 0
    attempts: int = 0
    max_attempts: int = 3                       # circuit breaker N (TC-CORE-06)
    error_signatures: list[str] = Field(default_factory=list)

    # -- low-level guarded transition -------------------------------------
    def transition_to(self, target: SessionState) -> None:
        if target not in _ALLOWED.get(self.state, set()):
            raise InvalidStateTransitionException(self.state.value, target.value)
        self.state = target

    # -- intent-revealing transitions -------------------------------------
    def start_planning(self) -> None:
        self.transition_to(SessionState.PLANNING)

    def set_plan(self, plan: Plan) -> None:
        if self.state is not SessionState.PLANNING:
            raise InvalidStateTransitionException(self.state.value, "set_plan")
        self.plan = plan

    def start_coding(self) -> None:
        """Hand a task to the Coder. Illegal before a plan exists (TC-CORE-01)."""
        if self.plan is None or self.plan.is_empty:
            # cannot code without a plan, regardless of nominal state
            raise InvalidStateTransitionException(self.state.value, SessionState.CODING.value)
        self.transition_to(SessionState.CODING)

    def start_verifying(self) -> None:
        self.transition_to(SessionState.VERIFYING)

    def record_pass(self) -> None:
        self.transition_to(SessionState.DONE)

    def record_failure(self, error_signature: str) -> None:
        """Move into HEALING and bump the attempt counter."""
        self.transition_to(SessionState.HEALING)
        self.attempts += 1
        self.error_signatures.append(error_signature)

    # -- circuit breaker (TC-CORE-06) + no-progress detection (M3) ---------
    def should_trip_breaker(self) -> bool:
        if self.attempts >= self.max_attempts:
            return True
        # no-progress: the same failure signature twice in a row -> stop early.
        sigs = self.error_signatures
        return len(sigs) >= 2 and sigs[-1] == sigs[-2]

    def trip_breaker(self) -> None:
        self.transition_to(SessionState.HEALING_FAILED)

    def retry_coding(self) -> None:
        """Re-enter CODING for another healing attempt."""
        self.transition_to(SessionState.CODING)

    @property
    def is_terminal(self) -> bool:
        return self.state in (
            SessionState.DONE,
            SessionState.HEALING_FAILED,
            SessionState.BLOCKED,
        )
