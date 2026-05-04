"""Phase 26 — auth_events audit table + sessions.revoked_reason column.

Closes H2 from the 2026-05-04 solidity audit (logout-everywhere). Two
additive changes that enable POST /v1/auth/logout-all (revoke every
sessions row for the calling user_id) plus a queryable audit trail
for incident response.

Schema details (``auth_events``):
  id                     UUID PK DEFAULT gen_random_uuid()
  user_id                UUID FK → users.id ON DELETE SET NULL
                            NULL allowed so audit rows survive the
                            user being purged — the historical fact
                            "someone logged out N devices on date X"
                            is durable beyond user deletion.
  kind                   TEXT NOT NULL
                            initial value ``'logout_all'``; expand
                            later (admin_revoke, suspicious_login,
                            etc.). Plain TEXT not Postgres enum so
                            new kinds don't require a migration.
  ip                     INET (nullable — proxies + tests may not
                            populate)
  user_agent             TEXT (nullable — same reason)
  device_count_revoked   INT NOT NULL DEFAULT 0
                            zero is a meaningful value (logout-all
                            on a user with no live sessions); keeping
                            the column NOT NULL eliminates the "did we
                            forget to record this?" ambiguity.
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indexes:
  * ``ix_auth_events_user_id_created_at`` btree on (user_id,
    created_at DESC) — primary read pattern is "show me logout-all
    events for user X in the last N days" (incident response).

Schema changes (``sessions``):
  * Adds nullable column ``revoked_reason TEXT`` (no DB-side CHECK;
    Pydantic Literal at the API boundary enforces the enum:
    ``'logout' | 'logout_all' | 'admin' | 'expired'``). Legacy revoked
    rows leave the column NULL — acceptable per D-10. Postgres 11+
    ALTER TABLE ADD COLUMN of a nullable column with no default is
    instant — no rewrite, no exclusive lock blocking live traffic.

Decision references (``.planning/phases/26-logout-everywhere/26-CONTEXT.md``):
  * D-02 — auth_events table + lean column set
  * D-03 — no per-revoked-session JSONB / no geo / no caller_session_id
  * D-10 — sessions.revoked_reason column (Pydantic Literal at API)
  * D-11 — single-device logout updates revoked_reason but does NOT
            write auth_events (table stays signal-rich)
  * D-12 — additive only; legacy rows leave revoked_reason NULL
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009_auth_events_revoked_reason"
down_revision = "008_idempotency_relax_run_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create auth_events + add sessions.revoked_reason."""

    # --- auth_events ---------------------------------------------------
    op.create_table(
        "auth_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "device_count_revoked",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_auth_events_user_id_created_at",
        "auth_events",
        ["user_id", sa.text("created_at DESC")],
    )

    # --- sessions.revoked_reason ---------------------------------------
    op.add_column(
        "sessions",
        sa.Column("revoked_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Reverse — drop sessions.revoked_reason + auth_events."""
    op.drop_column("sessions", "revoked_reason")
    op.drop_index(
        "ix_auth_events_user_id_created_at",
        table_name="auth_events",
    )
    op.drop_table("auth_events")
