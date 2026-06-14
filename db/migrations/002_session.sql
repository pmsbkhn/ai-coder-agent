-- ============================================================================
-- Session state (the linear-saga aggregate). Unlike agent_execution_log this is
-- MUTABLE current-state (upserted each step), NOT part of the immutable audit
-- trail — so agent_app gets full CRUD here, while the log stays append-only.
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_session (
    session_id  TEXT PRIMARY KEY,
    state       TEXT        NOT NULL,           -- SessionState (denormalized for queries)
    data        JSONB       NOT NULL,           -- full AgentSession model (model_dump)
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON agent_session TO agent_app;
