"""PostgresMemory integration test — runs only against a live Postgres.

Skipped unless AICODER_LIVE_PG=1 (mirrors the live-MCP tests). Bring the DB up
first:  docker compose up -d   (applies db/migrations/*.sql on a fresh volume).

Proves the durable MemoryPort contract AND the runtime append-only guarantee:
connected as agent_app, the DB itself denies UPDATE/DELETE on the execution log.
"""

from __future__ import annotations

import os
import uuid

import pytest

from aicoder.domain.models import ExecutionTrace, Plan, Task
from aicoder.domain.session import AgentSession

pytestmark = pytest.mark.skipif(
    os.environ.get("AICODER_LIVE_PG") != "1",
    reason="set AICODER_LIVE_PG=1 (and `docker compose up -d`) for the live Postgres test",
)


def _mem():
    from aicoder.adapters.memory_postgres import PostgresMemory

    return PostgresMemory()


def test_execution_log_is_append_only_and_ordered() -> None:
    mem = _mem()
    sid = f"sess_{uuid.uuid4().hex[:12]}"
    for i in range(3):
        mem.append_log(ExecutionTrace(session_id=sid, seq=i, event_type=f"E{i}", payload={"i": i}))

    traces = mem.get_traces(sid)
    assert [t.seq for t in traces] == [0, 1, 2]
    assert [t.event_type for t in traces] == ["E0", "E1", "E2"]
    assert traces[1].payload == {"i": 1}


def test_session_roundtrips_and_upserts() -> None:
    mem = _mem()
    sid = f"sess_{uuid.uuid4().hex[:12]}"
    assert mem.load_session(sid) is None

    s = AgentSession(session_id=sid, max_attempts=6)
    s.start_planning()
    s.set_plan(Plan(tasks=[Task(id="t1", description="do x", target_files=["A.java"])]))
    mem.save_session(s)

    loaded = mem.load_session(sid)
    assert loaded is not None
    assert loaded.session_id == sid and loaded.max_attempts == 6
    assert loaded.plan is not None and loaded.plan.tasks[0].id == "t1"

    # upsert: state advances, same row
    s.start_coding()
    mem.save_session(s)
    assert mem.load_session(sid).state == s.state


def test_db_denies_update_and_delete_on_log() -> None:
    """The immutability guarantee is enforced by the DB, not by convention:
    agent_app has no UPDATE/DELETE privilege (and no RLS policy) on the log."""
    import psycopg

    from aicoder.adapters.memory_postgres import DEFAULT_DSN

    mem = _mem()
    sid = f"sess_{uuid.uuid4().hex[:12]}"
    mem.append_log(ExecutionTrace(session_id=sid, seq=0, event_type="E0", payload={}))

    dsn = os.environ.get("AICODER_PG_DSN", DEFAULT_DSN)
    with psycopg.connect(dsn, autocommit=True) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("UPDATE agent_execution_log SET event_type = 'HACKED' WHERE session_id = %s", (sid,))
    with psycopg.connect(dsn, autocommit=True) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM agent_execution_log WHERE session_id = %s", (sid,))
