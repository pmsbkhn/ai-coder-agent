"""TC-ARCH-03 / TC-INT-03 (static side): the execution log is append-only.

Two guards:
  1. The migration must grant the app role only SELECT+INSERT on the log and must
     NOT expose an UPDATE/DELETE policy for it.
  2. No adapter source may issue an UPDATE/DELETE SQL statement against
     agent_execution_log.
The live RLS "permission denied" assertion lives in tests/test_postgres_memory.py
(runs against a real Postgres under AICODER_LIVE_PG=1).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "001_init.sql"
ADAPTERS = ROOT / "src" / "aicoder" / "adapters"


def test_migration_grants_log_insert_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "grant select, insert on agent_execution_log to agent_app" in sql
    # No UPDATE/DELETE policy may target the log.
    assert not re.search(r"policy[^;]*on\s+agent_execution_log\s+for\s+(update|delete)", sql)
    assert "enable row level security" in sql


def test_no_adapter_mutates_the_log() -> None:
    # Match an actual mutating SQL statement on the log — `UPDATE agent_execution_log`
    # or `DELETE FROM ... agent_execution_log` — not the words "update"/"delete" in
    # prose/comments (which is a false positive, e.g. a docstring describing the
    # append-only guarantee).
    pattern = re.compile(
        r"update\s+agent_execution_log\b|delete\s+from\s+[^\n;]*agent_execution_log\b",
        re.IGNORECASE,
    )
    for f in ADAPTERS.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert not pattern.search(text), (
            f"{f.name} appears to UPDATE/DELETE the append-only log"
        )
