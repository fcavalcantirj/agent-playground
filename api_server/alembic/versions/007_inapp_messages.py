"""Phase 22c.3 — inapp_messages + agent_events.published + agent_containers.inapp_auth_token + 3 new event kinds.

Adds the durable state-machine table for in-app chat messages (D-27),
the outbox column for transactional Redis publish semantics (D-33),
the per-session bearer-token slot for the http_localhost dispatcher
(consumed by Plan 22c.3-08 when forwarding to bots requiring auth),
and extends ``ck_agent_events_kind`` to accept 3 new kinds (D-13, D-24):
``inapp_inbound``, ``inapp_outbound``, ``inapp_outbound_failed``.

Schema details (``inapp_messages``):
  id              UUID PK DEFAULT gen_random_uuid()
  agent_id        UUID NOT NULL FK → agent_instances.id ON DELETE CASCADE
  user_id         UUID NOT NULL FK → users.id ON DELETE CASCADE
  content         TEXT NOT NULL
  status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','forwarded','done','failed'))
  attempts        INT  NOT NULL DEFAULT 0
  last_error      TEXT (nullable)
  last_attempt_at TIMESTAMPTZ (nullable)
  bot_response    TEXT (nullable)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
  completed_at    TIMESTAMPTZ (nullable)

Indexes:
  * ``ix_inapp_messages_agent_status`` btree on (agent_id, status) —
    serves "list my chat history for this agent" + status filtering on
    the dashboard side.
  * ``ix_inapp_messages_status_attempts`` partial btree on
    (status, last_attempt_at) WHERE status IN ('pending','forwarded') —
    powers the dispatcher's
    ``SELECT ... ORDER BY created_at FOR UPDATE SKIP LOCKED`` pump
    AND the reaper's stuck-row sweep without scanning terminal
    ``done``/``failed`` rows.

``agent_events.published``: outbox flag for D-33's transactional Redis
publish pattern. Every event INSERT starts ``published=false``; the
outbox pump (Plan 22c.3-07) flips it to ``true`` after a successful
``redis.publish``. Backed by a partial index on ``WHERE published=false``
so the pump's ``SELECT id FROM agent_events WHERE published=false`` stays
cheap even when the table holds millions of historical rows.

``agent_containers.inapp_auth_token``: per-session bearer token consumed
by Plan 22c.3-08's ``http_localhost`` dispatcher when the recipe declares
``channels.inapp.auth: bearer``. Nullable because most recipes (D-22 dumb
pipe) won't require bot-side auth.

``ck_agent_events_kind``: extended from 4 kinds (Phase 22b — reply_sent /
reply_failed / agent_ready / agent_error) to 7 kinds (+inapp_inbound /
inapp_outbound / inapp_outbound_failed). Implemented as DROP + CREATE so
the constraint name stays canonical and the ``REPLACE`` semantics are
explicit in DDL.

Revision ID: 007_inapp_messages
Revises: 006_purge_anonymous
Create Date: 2026-04-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "007_inapp_messages"
down_revision = "006_purge_anonymous"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. inapp_messages table (D-27).
    op.create_table(
        "inapp_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("bot_response", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_inapp_messages_status",
        "inapp_messages",
        "status IN ('pending','forwarded','done','failed')",
    )
    op.create_index(
        "ix_inapp_messages_agent_status",
        "inapp_messages",
        ["agent_id", "status"],
    )
    op.create_index(
        "ix_inapp_messages_status_attempts",
        "inapp_messages",
        ["status", "last_attempt_at"],
        postgresql_where=sa.text("status IN ('pending','forwarded')"),
    )

    # 2. agent_events outbox column (D-33). NOT NULL DEFAULT FALSE so
    #    historical rows backfill cleanly to the "needs publish" state
    #    only if the outbox pump should re-attempt them — but those rows
    #    were already published synchronously pre-22c.3, so the partial
    #    index below masks them out.
    op.add_column(
        "agent_events",
        sa.Column(
            "published",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    # Pre-22c.3 rows are de-facto published — backfill TRUE so the outbox
    # pump doesn't re-publish them on first start.
    op.execute("UPDATE agent_events SET published = TRUE")
    op.create_index(
        "ix_agent_events_published",
        "agent_events",
        ["id"],
        postgresql_where=sa.text("published = FALSE"),
    )

    # 3. Per-session bearer token (D-22 dumb pipe — nullable, recipes opt in).
    op.add_column(
        "agent_containers",
        sa.Column("inapp_auth_token", sa.Text, nullable=True),
    )

    # 4. Extend ck_agent_events_kind (D-13). DROP + CREATE under the same
    #    name preserves the constraint identity for downstream tooling.
    op.drop_constraint(
        "ck_agent_events_kind", "agent_events", type_="check"
    )
    op.create_check_constraint(
        "ck_agent_events_kind",
        "agent_events",
        "kind IN ('reply_sent', 'reply_failed', 'agent_ready', 'agent_error',"
        " 'inapp_inbound', 'inapp_outbound', 'inapp_outbound_failed')",
    )


def downgrade() -> None:
    # Reverse exactly. Drop the extended CHECK first and re-create the
    # 4-kind shape so any orphan rows with new kinds would surface as a
    # constraint violation (we expect zero — Phase 22c.3 hasn't run yet
    # at the moment a downgrade would fire from CI).
    op.drop_constraint(
        "ck_agent_events_kind", "agent_events", type_="check"
    )
    op.create_check_constraint(
        "ck_agent_events_kind",
        "agent_events",
        "kind IN ('reply_sent', 'reply_failed', 'agent_ready', 'agent_error')",
    )
    op.drop_column("agent_containers", "inapp_auth_token")
    op.drop_index(
        "ix_agent_events_published", table_name="agent_events"
    )
    op.drop_column("agent_events", "published")
    op.drop_index(
        "ix_inapp_messages_status_attempts", table_name="inapp_messages"
    )
    op.drop_index(
        "ix_inapp_messages_agent_status", table_name="inapp_messages"
    )
    op.drop_constraint(
        "ck_inapp_messages_status", "inapp_messages", type_="check"
    )
    op.drop_table("inapp_messages")
