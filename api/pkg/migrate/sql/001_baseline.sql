-- 001_baseline.sql
-- Plan 01-01 baseline schema: users, user_sessions, agents.
-- D-10 / D-17: agents table is created from day 1; v1 enforces 1 active per
-- user via the partial unique index `idx_agents_one_active_per_user`. Phase 4-5
-- bring the table to life; this file just plants the schema.

CREATE TABLE IF NOT EXISTS users (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider     TEXT,
    provider_sub TEXT,
    email        TEXT,
    display_name TEXT,
    avatar_url   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider_sub
    ON users(provider, provider_sub)
    WHERE provider IS NOT NULL AND provider_sub IS NOT NULL;

CREATE TABLE IF NOT EXISTS user_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

CREATE TABLE IF NOT EXISTS agents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    agent_type     TEXT NOT NULL,
    model_provider TEXT,
    model_id       TEXT,
    key_source     TEXT,
    status         TEXT NOT NULL DEFAULT 'stopped',
    webhook_url    TEXT,
    container_id   TEXT,
    ssh_port       INTEGER,
    config         JSONB DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agents_user_id ON agents(user_id);

-- D-17: v1 limits 1 active container per user. Schema enforces it via a
-- partial unique index on user_id where status is one of the "active" states.
-- Flipping the limit to N is a config change (drop the index), not a migration.
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_one_active_per_user
    ON agents(user_id)
    WHERE status IN ('provisioning', 'ready', 'running');
