"""Baseline schema for Phase 19 API foundation.

Creates the 5 platform tables per `.planning/phases/19-api-foundation/19-CONTEXT.md`
D-06 plus the Pitfall 6 mitigation column (`idempotency_keys.request_body_hash`)
and the `pgcrypto` extension required for `gen_random_uuid()`.

Table order matches FK dependency direction on upgrade, and the reverse on
downgrade. The `pgcrypto` extension is intentionally NOT dropped on downgrade
— it is shared infrastructure that other databases/schemas may depend on.

Revision ID: 001_baseline
Revises:
Create Date: 2026-04-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgcrypto provides gen_random_uuid() for UUID PK defaults.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ---- users ----
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    # Seed the anonymous user per CONTEXT.md D-06. Phase 19 has no auth yet —
    # every request is attributed to this row until Phase 21 lands OAuth.
    op.execute(
        "INSERT INTO users (id, display_name) VALUES "
        "('00000000-0000-0000-0000-000000000001', 'anonymous')"
    )

    # ---- agent_instances ----
    op.create_table(
        "agent_instances",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("recipe_name", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "total_runs", sa.Integer, nullable=False, server_default="0"
        ),
        sa.UniqueConstraint(
            "user_id",
            "recipe_name",
            "model",
            name="uq_agent_instances_user_recipe_model",
        ),
    )

    # ---- runs ----
    # runs.id is TEXT (ULID 26-char), NOT UUID — ULIDs are sortable by time
    # and minted at the application layer (Plan 04).
    op.create_table(
        "runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column(
            "agent_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_instances.id"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("verdict", sa.Text, nullable=True),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("wall_time_s", sa.Numeric, nullable=True),
        sa.Column("filtered_payload", sa.Text, nullable=True),
        sa.Column("stderr_tail", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_runs_agent_instance", "runs", ["agent_instance_id"]
    )

    # ---- idempotency_keys ----
    # request_body_hash (NOT NULL) mitigates Pitfall 6 per RESEARCH.md —
    # same Idempotency-Key + different request body must return 422, not
    # silently replay a stale response.
    op.create_table(
        "idempotency_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column(
            "run_id", sa.Text, sa.ForeignKey("runs.id"), nullable=False
        ),
        sa.Column("verdict_json", postgresql.JSONB, nullable=False),
        sa.Column("request_body_hash", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id", "key", name="uq_idempotency_keys_user_key"
        ),
    )
    op.create_index(
        "idx_idempotency_expires", "idempotency_keys", ["expires_at"]
    )

    # ---- rate_limit_counters ----
    # subject is TEXT (holds either a user UUID as text, or an IP string).
    # Composite PK prevents duplicate rows for the same window.
    op.create_table(
        "rate_limit_counters",
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("bucket", sa.Text, nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint(
            "subject", "bucket", "window_start"
        ),
    )
    op.create_index(
        "idx_rate_limit_gc", "rate_limit_counters", ["window_start"]
    )


def downgrade() -> None:
    # Drop in reverse FK order. Indexes on tables go away with their table;
    # pgcrypto is intentionally left installed (shared infrastructure).
    op.drop_table("rate_limit_counters")
    op.drop_table("idempotency_keys")
    op.drop_table("runs")
    op.drop_table("agent_instances")
    op.drop_table("users")
