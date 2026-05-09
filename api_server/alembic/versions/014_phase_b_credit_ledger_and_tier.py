"""Phase B Plan B-stripe-02 — credit ledger + tier columns + Stripe webhook idempotency.

Wave 1 of the Phase B (Stripe paywall) phase. This is the load-bearing
schema layer every later wave reads from. Body copied verbatim from the
Wave 0 spike H draft (``tests/_spikes/draft_014_migration.py``); the
draft was upgrade/downgrade/re-upgrade-tested against a real Postgres 17
testcontainer + asserted shape-equivalent on the round-trip BEFORE landing
here.

Schema scope (per CONTEXT D-01, D-04, D-08, D-16, D-17, D-23, D-26):

  * ``users.tier`` TEXT NOT NULL DEFAULT 'free' with CHECK
    ('free','pro','ultra'); D-26 backfills every existing row to 'free'
    via the NOT NULL DEFAULT clause (no separate UPDATE needed).
  * ``users.stripe_customer_id`` TEXT NULL — populated lazily by the
    StripeClient lifespan service on first Stripe-affecting click (D-11).
  * ``users.refund_writeoff_cents`` BIGINT NOT NULL DEFAULT 0 — sticky
    counter for admin-decided refund write-offs (D-16).
  * ``credit_balances`` (user_id PK FK ON DELETE CASCADE, balance_cents,
    updated_at) — denormalized cache rebuilt by every debit/credit
    inside the same transaction; ledger is the source of truth.
  * ``credit_transactions`` (id, user_id FK ON DELETE CASCADE, kind CHECK,
    amount_cents, reference_id, reference_type, created_at) — D-17
    ledger-as-truth. UNIQUE partial index on (reference_id, reference_type)
    WHERE reference_id IS NOT NULL gives the idempotency rail Phase B
    debits / topups / refunds rely on.
  * ``stripe_webhook_events`` (id, stripe_event_id UNIQUE, event_type,
    payload, created_at) — webhook idempotency (D-14 / AMD-02).
  * Data migration: ``cost_weights.ap_multiplier`` 1.0 → 1.15 across every
    pre-Phase-B seed row (D-08 — 15% markup; covers Stripe ~3% + OpenRouter
    ~5% + ~7% margin headroom).

NOTE on revision id: ``alembic_version.version_num`` is ``varchar(32)``.
``014_phase_b_ledger_and_tier`` is 27 chars and fits cleanly. The longer
``014_phase_b_credit_ledger_and_tier`` (33 chars) would truncate on the
INSERT and break the upgrade chain — DO NOT use the longer form. Spike H
discovered this on 2026-05-08; documented in the
B-stripe-01-SUMMARY.md "Deviations from RESEARCH.md" section.

Revision ID: 014_phase_b_ledger_and_tier
Revises: 013_phase29_proxy_columns
Create Date: 2026-05-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "014_phase_b_ledger_and_tier"
down_revision = "013_phase29_proxy_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Phase B credit ledger + tier columns + Stripe webhook idempotency."""

    # ---- users additive columns (D-01, D-11, D-16) -------------------
    # NOT NULL DEFAULT 'free' backfills every existing row to 'free' in
    # one shot — D-26's "migration backfill" requirement is satisfied by
    # the column definition itself; no separate UPDATE pass needed.
    op.add_column(
        "users",
        sa.Column(
            "tier",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'free'"),
        ),
    )
    op.create_check_constraint(
        "ck_users_tier",
        "users",
        "tier IN ('free','pro','ultra')",
    )
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "refund_writeoff_cents",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # ---- credit_balances (D-17 cache) --------------------------------
    op.create_table(
        "credit_balances",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "balance_cents",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ---- credit_transactions (D-17 ledger truth) ---------------------
    op.create_table(
        "credit_transactions",
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
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("reference_id", sa.Text(), nullable=True),
        sa.Column("reference_type", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_check_constraint(
        "ck_credit_transactions_kind",
        "credit_transactions",
        "kind IN ('topup','debit','refund','tier_change','admin_writeoff')",
    )
    # Idempotency on retry: UNIQUE(reference_id, reference_type) so a
    # second INSERT for the same usage_log raises UniqueViolationError.
    # Partial index (WHERE reference_id IS NOT NULL) leaves NULL-reference
    # ledger rows (e.g. admin_writeoff with no source event) unconstrained.
    op.create_index(
        "uq_credit_transactions_reference",
        "credit_transactions",
        ["reference_id", "reference_type"],
        unique=True,
        postgresql_where=sa.text("reference_id IS NOT NULL"),
    )
    op.create_index(
        "ix_credit_transactions_user_created",
        "credit_transactions",
        ["user_id", sa.text("created_at DESC")],
    )

    # ---- stripe_webhook_events (idempotency) -------------------------
    op.create_table(
        "stripe_webhook_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("stripe_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "stripe_event_id", name="uq_stripe_webhook_events_event_id",
        ),
    )

    # ---- D-08 — bump ap_multiplier from 1.0 to 1.15 ------------------
    # Targets only rows currently at exactly 1.0 (the migration-010 seed
    # baseline). Admin-mutated rows at any other value are left alone —
    # D-08 markup applies to the default vehicle, not to operator-tuned
    # per-row weights.
    op.execute(
        "UPDATE cost_weights SET ap_multiplier = 1.15 "
        "WHERE ap_multiplier = 1.0"
    )


def downgrade() -> None:
    """Reverse upgrade(). The ap_multiplier swap reverses by symmetry —
    rows still at exactly 1.15 (the value upgrade set) flip back to 1.0;
    rows that were admin-tuned to other values stay untouched.
    """
    op.execute(
        "UPDATE cost_weights SET ap_multiplier = 1.0 "
        "WHERE ap_multiplier = 1.15"
    )
    op.drop_table("stripe_webhook_events")
    op.drop_index(
        "ix_credit_transactions_user_created",
        table_name="credit_transactions",
    )
    op.drop_index(
        "uq_credit_transactions_reference",
        table_name="credit_transactions",
    )
    op.drop_constraint(
        "ck_credit_transactions_kind",
        "credit_transactions",
        type_="check",
    )
    op.drop_table("credit_transactions")
    op.drop_table("credit_balances")
    op.drop_column("users", "refund_writeoff_cents")
    op.drop_column("users", "stripe_customer_id")
    op.drop_constraint("ck_users_tier", "users", type_="check")
    op.drop_column("users", "tier")
