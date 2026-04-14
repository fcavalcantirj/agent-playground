-- 002_sessions.sql
-- Phase 2 plan 04: minimal sessions table for the stub session API.
-- Phase 5 will add: expires_at, last_activity_at, heartbeat_at, billing_mode, tier.
-- Phase 4 may add: agent_id FK → agents.id once the recipe → agent → session
-- chain is fully wired.

CREATE TABLE IF NOT EXISTS sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_name    TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_id       TEXT NOT NULL,
    container_id   TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status  ON sessions(status);

-- Phase 2 enforces "1 active session per user" via this partial unique index.
-- Phase 5 adds a Redis SETNX layer on top for race resolution (SES-09).
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active_per_user
    ON sessions(user_id)
    WHERE status IN ('pending', 'provisioning', 'running');
