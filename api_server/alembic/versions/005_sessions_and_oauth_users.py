"""Phase 22c — sessions table + OAuth-facing users columns.

Phase 22c (oauth-google) — this migration lays the DB substrate needed by
the OAuth callback handler, the SessionMiddleware, /v1/users/me, and
/v1/auth/logout.

ADDITIVE ONLY. Migration 006 (in the same phase) is the destructive data
purge of every data-bearing table — see `006_purge_anonymous.py`.

Adds:
  * users.sub TEXT (nullable) — OAuth provider's stable user identifier
  * users.avatar_url TEXT (nullable) — from provider's userinfo
  * users.last_login_at TIMESTAMPTZ (nullable) — updated per callback
  * UNIQUE (provider, sub) WHERE sub IS NOT NULL — partial index so the
    seeded ANONYMOUS row (provider=NULL, sub=NULL) keeps validating. Full
    UNIQUE including NULL-rows would conflict on the NULL-sub seed pair.
  * sessions table — opaque session_id cookie target.

Schema details (sessions):
  id              UUID PK DEFAULT gen_random_uuid()
  user_id         UUID NOT NULL FK → users.id ON DELETE CASCADE
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
  expires_at      TIMESTAMPTZ NOT NULL
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
  revoked_at      TIMESTAMPTZ (nullable)
  user_agent      TEXT (nullable)
  ip_address      INET (nullable)

Index policy (D-22c-MIG-04):
  * PK on id covers the hot-path SELECT WHERE id = $1.
  * btree on user_id enables future "list my sessions" without a v2
    migration. No partial WHERE index — PG handles the expiry filter
    cheaply on the PK lookup.

Revision ID: 005_sessions_and_oauth_users
Revises: 004_agent_events
Create Date: 2026-04-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "005_sessions_and_oauth_users"
down_revision = "004_agent_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users: new columns ---
    op.add_column(
        "users",
        sa.Column("sub", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # --- users: UNIQUE (provider, sub) — partial so ANONYMOUS (sub=NULL) passes ---
    op.create_index(
        "uq_users_provider_sub",
        "users",
        ["provider", "sub"],
        unique=True,
        postgresql_where=sa.text("sub IS NOT NULL"),
    )

    # --- sessions table ---
    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sessions_user_id",
        "sessions",
        ["user_id"],
    )


def downgrade() -> None:
    # Reverse order of upgrade.
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("uq_users_provider_sub", table_name="users")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "sub")
