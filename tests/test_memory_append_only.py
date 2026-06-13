"""TC-ARCH-03 / TC-INT-03 (static side): the execution log is append-only.

Two guards:
  1. The migration must grant the app role only SELECT+INSERT on the log and must
     NOT expose an UPDATE/DELETE policy for it.
  2. No adapter source may issue UPDATE/DELETE against agent_execution_log.
The live RLS "permission denied" assertion is an integration test added in M5.
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
    pattern = re.compile(r"(update|delete)\s+.*agent_execution_log", re.IGNORECASE | re.DOTALL)
    for f in ADAPTERS.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert not pattern.search(text), (
            f"{f.name} appears to UPDATE/DELETE the append-only log"
        )
