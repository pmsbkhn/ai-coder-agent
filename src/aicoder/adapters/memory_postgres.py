"""PostgresMemory — the durable MemoryPort (append-only log + session state).

Drop-in replacement for InMemoryMemory behind the same port; the control loop
never changes. Connects as the least-privilege `agent_app` role so the
append-only guarantee on agent_execution_log holds AT RUNTIME (the DB denies
UPDATE/DELETE — see db/migrations/001_init.sql), not just by convention.

  append_log  -> INSERT into agent_execution_log (never updates: append-only)
  get_traces  -> SELECT ... ORDER BY seq
  save_session-> UPSERT agent_session (mutable current-state, separate table)
  load_session-> SELECT data -> AgentSession

psycopg is imported lazily so importing this module never hard-requires the
`adapters` extra. repo_map is kept in-process (set per run, not durable state).
"""

from __future__ import annotations

import os

from aicoder.application.ports.outbound import MemoryPort
from aicoder.domain.models import ExecutionTrace
from aicoder.domain.session import AgentSession

DEFAULT_DSN = "postgresql://agent_app:agent_app@localhost:5433/aicoder"


class PostgresMemory(MemoryPort):
    def __init__(self, dsn: str | None = None, *, repo_map: str = "") -> None:
        import psycopg  # lazy: only needed when Postgres is actually selected

        self._connect = psycopg.connect
        self._dsn = dsn or os.environ.get("AICODER_PG_DSN", DEFAULT_DSN)
        self._repo_map = repo_map

    def _conn(self):
        # autocommit: each call is its own durable transaction (the orchestrator
        # saves state step-by-step and must see its own prior writes).
        return self._connect(self._dsn, autocommit=True)

    def append_log(self, trace: ExecutionTrace) -> None:
        from psycopg.types.json import Jsonb

        with self._conn() as c:
            c.execute(
                "INSERT INTO agent_execution_log (session_id, seq, event_type, payload) "
                "VALUES (%s, %s, %s, %s)",
                (trace.session_id, trace.seq, trace.event_type, Jsonb(trace.payload)),
            )

    def get_traces(self, session_id: str) -> list[ExecutionTrace]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT session_id, seq, event_type, payload FROM agent_execution_log "
                "WHERE session_id = %s ORDER BY seq",
                (session_id,),
            ).fetchall()
        return [
            ExecutionTrace(session_id=r[0], seq=r[1], event_type=r[2], payload=r[3])
            for r in rows
        ]

    def save_session(self, session: AgentSession) -> None:
        from psycopg.types.json import Jsonb

        with self._conn() as c:
            c.execute(
                "INSERT INTO agent_session (session_id, state, data, updated_at) "
                "VALUES (%s, %s, %s, now()) "
                "ON CONFLICT (session_id) DO UPDATE "
                "SET state = EXCLUDED.state, data = EXCLUDED.data, updated_at = now()",
                (session.session_id, session.state.value, Jsonb(session.model_dump(mode="json"))),
            )

    def load_session(self, session_id: str) -> AgentSession | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT data FROM agent_session WHERE session_id = %s", (session_id,)
            ).fetchone()
        return AgentSession.model_validate(row[0]) if row else None

    def get_repo_map(self) -> str:
        return self._repo_map

    def set_repo_map(self, repo_map: str) -> None:
        self._repo_map = repo_map
