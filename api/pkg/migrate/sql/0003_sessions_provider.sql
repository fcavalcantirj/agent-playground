-- 0003_sessions_provider.sql
--
-- Phase 02.5 Plan 09 / D-53: introduce the `provider` field on the
-- POST /api/sessions payload.
--
-- Phase 2's 002_sessions.sql already added a `model_provider text NOT
-- NULL` column. This migration is therefore a no-op IF-NOT-EXISTS
-- ALTER — documented semantic shift only: the column now carries
-- whatever value the client sent in the D-53 `provider` field (with
-- `model_provider` accepted as a Phase 2 compat alias during one
-- rollout wave).
--
-- The ALTER + CREATE INDEX are idempotent so this migration is safe
-- to re-run during the usual bootstrap-migrate cycle. Keeping the
-- file in the embedded migration set also serves as an explicit audit
-- trail: future operators reading pkg/migrate/sql/ will see the D-53
-- decision point without having to cross-reference the PLAN.md.

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS model_provider TEXT NOT NULL DEFAULT 'anthropic';

CREATE INDEX IF NOT EXISTS idx_sessions_provider ON sessions (model_provider);
