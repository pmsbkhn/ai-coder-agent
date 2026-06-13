-- ============================================================================
-- M0 schema: Immutable Memory + RAG store on a single Postgres.
-- Enforces TC-ARCH-03 / TC-INT-03 (append-only execution log) at the DB level.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ----------------------------------------------------------------------------
-- Append-only execution trace. The agent learns from this log (self-healing),
-- so it must never be overwritten. Immutability is enforced TWO ways:
--   1. Privilege:  the app role is granted only SELECT + INSERT (no UPDATE/DELETE).
--   2. RLS:        no UPDATE/DELETE policy exists, so even a future grant is denied.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_execution_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id  TEXT        NOT NULL,
    seq         INTEGER     NOT NULL,           -- per-session monotonic counter
    event_type  TEXT        NOT NULL,           -- PLAN_CREATED, DIFF_APPLIED, VERIFY_FAIL, ...
    payload     JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_exec_log_session ON agent_execution_log (session_id, seq);

-- ----------------------------------------------------------------------------
-- RAG knowledge chunks (seeded per Project Profile: MSFW docs, sample-service).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_chunk (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile    TEXT NOT NULL,                   -- e.g. 'msfw'
    source     TEXT NOT NULL,                   -- file path / doc id
    content    TEXT NOT NULL,
    embedding  vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_knowledge_profile ON knowledge_chunk (profile);

-- ----------------------------------------------------------------------------
-- Least-privilege application role. The agent connects as agent_app, NOT as the
-- superuser, so the immutability guarantee actually holds at runtime.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_app') THEN
        CREATE ROLE agent_app LOGIN PASSWORD 'agent_app';
    END IF;
END
$$;

-- execution log: append-only (SELECT + INSERT only — explicitly NO update/delete)
REVOKE ALL ON agent_execution_log FROM agent_app;
GRANT SELECT, INSERT ON agent_execution_log TO agent_app;

ALTER TABLE agent_execution_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_execution_log FORCE ROW LEVEL SECURITY;
CREATE POLICY exec_log_insert ON agent_execution_log FOR INSERT TO agent_app WITH CHECK (true);
CREATE POLICY exec_log_select ON agent_execution_log FOR SELECT TO agent_app USING (true);
-- intentionally NO policy for UPDATE or DELETE -> both are denied.

-- knowledge chunks: full read/write (re-indexable, not part of the audit trail)
GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_chunk TO agent_app;
