"""Phase 28 — workflow_id column + idempotency-key defense-in-depth.

Adds:
  1. ``inapp_messages.workflow_id`` (text, nullable) + partial index — for
     ops correlation between Temporal UI workflow IDs and ``inapp_messages``
     rows. Plan 28-06 (cutover) wires the route handler to persist the
     workflow ID at insert time so Temporal UI searches for
     ``msg-{user_id}-*`` (D-08) line up with row IDs in the audit trail.

  2. ``inapp_messages.idempotency_key`` (text, nullable) — Option A
     column-add path. The Pre-step inspection confirmed 007 did NOT add
     this column; Plan 28-05 owns the schema add here. Even though the
     existing ``IdempotencyMiddleware`` keys off the separate
     ``idempotency_keys`` table (Phase 19's Pattern 3), Phase 28 adds a
     SECOND defense layer at the row level so a duplicate insert that
     bypasses the middleware (cache TTL boundary, request body byte
     mismatch racing the same key, etc.) cannot orphan a Temporal
     workflow.

  3. UNIQUE partial index ``ix_inapp_messages_idempotency_key_unique`` on
     ``(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL`` —
     Option A defense-in-depth for RESEARCH §7 R3. The route handler in
     Plan 28-06 must catch the resulting ``UniqueViolationError`` on
     duplicate insert and return the pre-existing row.

Defense-in-depth (D-14):

  Layer 1 (Option A — this migration): column-level UNIQUE constraint on
    ``(user_id, idempotency_key)``. A duplicate Idempotency-Key insert
    that bypasses middleware cache will fire the constraint and the
    route's ``insert_pending`` must catch the ``UniqueViolation`` and
    return the pre-existing row (Plan 28-06 owns that wiring).

  Layer 2 (Option B — existing): ``IdempotencyMiddleware`` TTL.
    ``services/idempotency.py:23`` documents the 24h default TTL
    (parameter default ``ttl_hours=24`` at ``write_idempotency``).
    24h ≥ 5min D-13 workflow ``execution_timeout``, so the middleware
    cache outlives every workflow run by a 288× margin — confirmed by
    reading the file end-to-end during Plan 28-05's Pre-step.

  Both layers coexist post-migration. This is "AND", not "OR" — the
  defense pattern is identical to Stripe's documented approach: app-level
  cache for the hot path + DB-level uniqueness as the safety net.

Pre-step inspection result (Plan 28-05 truths):
  * ``inapp_messages.idempotency_key`` did NOT exist before this
    migration. 007's column list is id/agent_id/user_id/content/status/
    attempts/last_error/last_attempt_at/bot_response/created_at/
    completed_at — confirmed by ``\\d+ inapp_messages`` against
    ``deploy-postgres-1`` while alembic head sat at
    ``010_usage_logs_cost_weights``. Therefore Option A's
    ``op.add_column`` for ``idempotency_key`` IS executed; ``downgrade``
    drops the column accordingly.

  * ``services/idempotency.py:23`` carries the canonical 24h TTL line
    (``"24h TTL default matches CONTEXT.md §D-01"``), implemented by the
    ``ttl_hours: int = 24`` default in ``write_idempotency`` (line 118).
    No lowering observed since Phase 22c.3, so the ≥5min D-13 floor
    holds. If a future PR drops the default below 5 minutes, defense-
    in-depth degrades to Option A only — surface in code review.

Revision ID: 011_phase28_workflow_id_idem
Revises: 010_usage_logs_cost_weights
Create Date: 2026-05-05

NOTE on revision ID length: ``alembic_version.version_num`` is
``varchar(32)`` (Alembic's historical default). The fully-spelled
``011_phase28_workflow_id_idempotency`` is 35 characters, which fails
to write at ``UPDATE alembic_version SET version_num=...`` time with
``StringDataRightTruncationError: value too long for type character
varying(32)``. The shortened form below is 28 characters — same
pattern used by ``008_idempotency_relax_run_fk`` and ``005_sessions_
and_oauth_users``. The FILE name keeps the long name because filesystem
identity is unconstrained; the ``revision`` string (the DB identity) is
the abbreviated form. Plan 28-05 truths reference this discrepancy as
a Rule 1 fix-during-execution deviation.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
# NOTE: must fit within varchar(32) (Alembic default for alembic_version.
# version_num). The longer human-readable form is in the file name +
# docstring; the column-stored identity is the abbreviated string below.
revision = "011_phase28_workflow_id_idem"
down_revision = "010_usage_logs_cost_weights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add workflow_id + idempotency_key columns and their indexes."""

    # 1. Nullable workflow_id text column on inapp_messages.
    #    NULL stays valid for legacy rows (pre-Phase-28) and for any
    #    code path that inserts without a workflow handle. Plan 28-06's
    #    route handler is the only writer that populates this column.
    op.add_column(
        "inapp_messages",
        sa.Column("workflow_id", sa.Text(), nullable=True),
    )

    # Partial btree on workflow_id WHERE workflow_id IS NOT NULL — keeps
    # the index tiny by skipping the long tail of NULL legacy rows. The
    # ops use case is "look up the row for this Temporal workflow id"
    # which is selective enough not to need a full-table index.
    op.create_index(
        "ix_inapp_messages_workflow_id",
        "inapp_messages",
        ["workflow_id"],
        unique=False,
        postgresql_where=sa.text("workflow_id IS NOT NULL"),
    )

    # 2. Defense-in-depth column-add (Option A). 007 did NOT include
    #    idempotency_key on inapp_messages (Pre-step inspection
    #    confirmed against the live deploy-postgres-1 schema while
    #    head = 010_usage_logs_cost_weights). Add it as nullable text.
    op.add_column(
        "inapp_messages",
        sa.Column("idempotency_key", sa.Text(), nullable=True),
    )

    # 3. UNIQUE partial index on (user_id, idempotency_key) WHERE
    #    idempotency_key IS NOT NULL — the primary defense-in-depth
    #    for RESEARCH §7 R3. The partial WHERE excludes NULL rows so
    #    the legacy-row tail stays unconstrained while genuine
    #    Idempotency-Key duplicates fire UniqueViolation at insert time.
    op.create_index(
        "ix_inapp_messages_idempotency_key_unique",
        "inapp_messages",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop indexes + columns added in upgrade(), reverse order.

    Drops idempotency_key unconditionally — this migration owned the
    column-add (Pre-step inspection); reverting must give it back.
    """
    op.drop_index(
        "ix_inapp_messages_idempotency_key_unique",
        table_name="inapp_messages",
    )
    op.drop_column("inapp_messages", "idempotency_key")
    op.drop_index(
        "ix_inapp_messages_workflow_id",
        table_name="inapp_messages",
    )
    op.drop_column("inapp_messages", "workflow_id")
