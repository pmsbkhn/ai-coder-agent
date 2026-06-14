"""Domain invariant tests for the AgentSession state machine.

Covers TC-CORE-01 (linear-saga transition guard) and TC-CORE-06 (circuit breaker),
plus the no-progress early-trip that M3 builds on.
"""

from __future__ import annotations

import pytest

from aicoder.domain.errors import InvalidStateTransitionException
from aicoder.domain.models import Plan, SessionState, Task
from aicoder.domain.session import AgentSession


def _plan() -> Plan:
    return Plan(tasks=[Task(id="t1", description="do a thing")])


def test_tc_core_01_cannot_code_before_planning() -> None:
    """Asking the Coder to act from INIT (no plan) must raise."""
    session = AgentSession(session_id="s1")
    assert session.state is SessionState.INIT
    with pytest.raises(InvalidStateTransitionException):
        session.start_coding()


def test_happy_path_transitions() -> None:
    session = AgentSession(session_id="s2")
    session.start_planning()
    session.set_plan(_plan())
    session.start_coding()
    session.start_verifying()
    session.record_pass()
    assert session.state is SessionState.DONE
    assert session.is_terminal


def test_set_plan_requires_planning_state() -> None:
    session = AgentSession(session_id="s3")
    with pytest.raises(InvalidStateTransitionException):
        session.set_plan(_plan())


def test_tc_core_06_circuit_breaker_trips_after_n_attempts() -> None:
    """Three FAILs at N=3 -> HEALING_FAILED, no fourth coding attempt."""
    session = AgentSession(session_id="s4", max_attempts=3)
    session.start_planning()
    session.set_plan(_plan())

    session.start_coding()  # PLANNING -> CODING (once)
    for i in range(3):
        session.start_verifying()
        # distinct signatures so the no-progress path is NOT what trips it
        session.record_failure(f"err-{i}")
        if session.should_trip_breaker():
            session.trip_breaker()
            break
        session.retry_coding()  # HEALING -> CODING for the next attempt

    assert session.attempts == 3
    assert session.state is SessionState.HEALING_FAILED


def test_no_progress_breaker_trips_on_three_strikes() -> None:
    """M3: reflection varies the Coder's input between attempts, so a single repeat
    is not yet 'stuck'. Trip only after the SAME signature three times in a row,
    giving reflection two chances to change course."""
    session = AgentSession(session_id="s5", max_attempts=9)
    session.start_planning()
    session.set_plan(_plan())
    session.start_coding()

    def _fail(sig: str) -> None:
        session.start_verifying()
        session.record_failure(sig)

    _fail("same-error")
    assert not session.should_trip_breaker()  # 1 strike
    session.retry_coding()
    _fail("same-error")
    assert not session.should_trip_breaker()  # 2 strikes — reflection still has room
    session.retry_coding()
    _fail("same-error")
    assert session.should_trip_breaker()       # 3 strikes -> genuinely stuck
    assert session.attempts == 3               # tripped well before max_attempts=9


def test_no_progress_breaker_can_be_disabled() -> None:
    """With the flag off, only the attempt-count breaker (max_attempts) trips."""
    session = AgentSession(session_id="s6", max_attempts=5, no_progress_breaker=False)
    session.start_planning()
    session.set_plan(_plan())
    session.start_coding()
    for _ in range(3):  # same signature repeatedly
        session.start_verifying()
        session.record_failure("same-error")
        assert not session.should_trip_breaker()  # no-progress disabled
        session.retry_coding()
