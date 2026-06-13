"""InMemoryMemory — a MemoryPort for the walking skeleton and tests.

Lets the control loop run without Docker. PostgresMemory (append-only log + RLS,
pgvector) is a drop-in replacement behind the same port — the loop never changes.
Append-only is honoured: append_log only ever extends the list; there is no
mutate/delete path.
"""

from __future__ import annotations

from aicoder.application.ports.outbound import MemoryPort
from aicoder.domain.models import ExecutionTrace
from aicoder.domain.session import AgentSession


class InMemoryMemory(MemoryPort):
    def __init__(self, repo_map: str = "") -> None:
        self._log: list[ExecutionTrace] = []
        self._sessions: dict[str, AgentSession] = {}
        self._repo_map = repo_map

    def append_log(self, trace: ExecutionTrace) -> None:
        self._log.append(trace)

    def get_traces(self, session_id: str) -> list[ExecutionTrace]:
        return [t for t in self._log if t.session_id == session_id]

    def save_session(self, session: AgentSession) -> None:
        # deep copy so callers can't mutate stored state by reference
        self._sessions[session.session_id] = session.model_copy(deep=True)

    def load_session(self, session_id: str) -> AgentSession | None:
        stored = self._sessions.get(session_id)
        return stored.model_copy(deep=True) if stored is not None else None

    def get_repo_map(self) -> str:
        return self._repo_map

    def set_repo_map(self, repo_map: str) -> None:
        self._repo_map = repo_map
