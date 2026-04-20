"""006_purge_anonymous — IRREVERSIBLE data purge.

Phase 22c AMD-04: all current DB data is dev mock from Phase 19/22 execution.
Zero real customer data exists. This migration TRUNCATEs every data-bearing
table so OAuth users start with a clean slate.

PRESERVED:
  - Schema (all tables, columns, indexes, FKs stay)
  - alembic_version table (this very migration's row lands here on upgrade)

DESTROYED (CASCADE order not strictly needed with TRUNCATE ... CASCADE, but
document the FK graph for the reader):
  - agent_events (FK -> agent_containers ON DELETE CASCADE)
  - runs (FK -> agent_instances)
  - agent_containers (FK -> agent_instances + users)
  - agent_instances (FK -> users, UNIQUE user_id + recipe_name + model)
  - idempotency_keys (FK -> users + runs)
  - rate_limit_counters (no FK)
  - sessions (FK -> users, added in 005)
  - users (includes ANONYMOUS row; post-AMD-03)

IRREVERSIBLE: downgrade() raises NotImplementedError. Restore from backup
if needed. (Dev/mock-only data; no backup strategy.)

Revision ID: 006_purge_anonymous
Revises: 005_sessions_and_oauth_users
Create Date: 2026-04-19
"""
from alembic import op

revision = "006_purge_anonymous"
down_revision = "005_sessions_and_oauth_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TRUNCATE ... CASCADE is transactional + fast. One statement covers the
    # full dependency graph because every data table's FKs either point
    # into this set or aren't enforced (rate_limit_counters).
    op.execute(
        "TRUNCATE TABLE "
        "agent_events, runs, agent_containers, agent_instances, "
        "idempotency_keys, rate_limit_counters, sessions, users "
        "CASCADE"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "006_purge_anonymous is irreversible. "
        "Data was dev-mock only; restore from PG dump if truly needed."
    )
