"""Phase 22b-02 — agent_events table (durable event stream).

Adds the per-container append-only event log Phase 22b's watcher_service
writes to, and the long-poll endpoint reads from.

Design — separate table, NOT additive columns on agent_containers:
events are 1-to-many per container (the lifetime of a container can
emit hundreds of reply_sent rows), and the access pattern is
``SELECT ... WHERE agent_container_id=$1 AND seq>$2`` ordered by seq.
A composite UNIQUE on (agent_container_id, seq) plus a descending-seq
index on the same columns serve both write-time gap-free seq
allocation (D-16: pg_advisory_xact_lock + MAX(seq)+1 + UNIQUE backstop)
and read-time MAX(seq) lookup for the watcher resume cursor.

Columns:
  - id BIGSERIAL PK — surrogate, monotonic across all containers
  - agent_container_id UUID FK(agent_containers.id) ON DELETE CASCADE
      Retention hook (D-17): deleting a stopped container's row purges
      its events automatically.
  - seq BIGINT NOT NULL — per-container monotonic, gap-free.
      Allocated under pg_advisory_xact_lock(hashtext(container_id))
      via SELECT MAX(seq)+1 inside the same transaction. The composite
      UNIQUE below is the DB-layer backstop — concurrent writers that
      somehow bypass the lock (or from a parallel API replica) cannot
      double-allocate the same seq.
  - kind TEXT NOT NULL CHECK (4 values) — D-05 enumeration
  - payload JSONB NOT NULL DEFAULT '{}'::jsonb
      D-06: metadata only — never reply_text/body/message/content.
      Pydantic ConfigDict(extra='forbid') in models/events.py is the
      app-layer enforcement; this column has no schema validator —
      the kind CHECK is the cheap DB-layer guard.
  - correlation_id TEXT NULL — opaque app-supplied trace id (4-32 chars
      typical from agent_harness uuid4().hex[:4]); indexed only via the
      composite seq idx (range queries dominate; correlation_id is rarely
      a primary filter).
  - ts TIMESTAMPTZ NOT NULL DEFAULT NOW() — server clock; UTC.

Indexes:
  - uq_agent_events_container_seq (agent_container_id, seq) UNIQUE —
      backstop for the advisory-locked seq allocator + supports the
      "read-after-since_seq" range scan in fetch_events_after_seq.
  - ix_agent_events_container_seq_desc (agent_container_id, seq DESC) —
      MAX(seq) lookup for the watcher's resume cursor on lifespan
      re-attach (D-11). Composite + DESC keeps the planner cheap.

Revision ID: 004_agent_events
Revises: 003_agent_containers
Create Date: 2026-04-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "004_agent_events"
down_revision = "003_agent_containers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_events",
        sa.Column(
            "id",
            sa.BigInteger,
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "agent_container_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_containers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.BigInteger, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("correlation_id", sa.Text, nullable=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_check_constraint(
        "ck_agent_events_kind",
        "agent_events",
        "kind IN ('reply_sent', 'reply_failed', "
        "'agent_ready', 'agent_error')",
    )
    op.create_unique_constraint(
        "uq_agent_events_container_seq",
        "agent_events",
        ["agent_container_id", "seq"],
    )
    op.create_index(
        "ix_agent_events_container_seq_desc",
        "agent_events",
        ["agent_container_id", sa.text("seq DESC")],
    )


def downgrade() -> None:
    # Drop indexes + constraints before the table.
    op.drop_index(
        "ix_agent_events_container_seq_desc",
        table_name="agent_events",
    )
    op.drop_constraint(
        "uq_agent_events_container_seq",
        "agent_events",
        type_="unique",
    )
    op.drop_constraint(
        "ck_agent_events_kind",
        "agent_events",
        type_="check",
    )
    op.drop_table("agent_events")
