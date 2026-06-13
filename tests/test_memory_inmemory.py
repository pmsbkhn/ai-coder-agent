"""InMemoryMemory behaves as an append-only log + session store."""

from __future__ import annotations

from aicoder.adapters.memory_inmemory import InMemoryMemory
from aicoder.domain.models import ExecutionTrace
from aicoder.domain.session import AgentSession


def test_append_only_log_keeps_every_trace() -> None:
    mem = InMemoryMemory()
    mem.append_log(ExecutionTrace(session_id="s1", seq=0, event_type="A"))
    mem.append_log(ExecutionTrace(session_id="s1", seq=1, event_type="B"))
    mem.append_log(ExecutionTrace(session_id="s2", seq=0, event_type="C"))

    s1 = mem.get_traces("s1")
    assert [t.event_type for t in s1] == ["A", "B"]
    assert len(mem.get_traces("s2")) == 1


def test_session_round_trip_is_isolated() -> None:
    mem = InMemoryMemory()
    session = AgentSession(session_id="s1")
    session.start_planning()
    mem.save_session(session)

    loaded = mem.load_session("s1")
    assert loaded is not None
    assert loaded.state == session.state

    # mutating the loaded copy must not corrupt the stored one
    loaded.attempts = 99
    again = mem.load_session("s1")
    assert again.attempts == 0


def test_load_unknown_session_returns_none() -> None:
    assert InMemoryMemory().load_session("nope") is None
