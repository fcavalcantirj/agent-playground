"""Phase B Wave 0 — DRAFT migration 014 (NOT yet in alembic/versions).

This is the body Wave 1 will copy into
``api_server/alembic/versions/014_credit_balances_and_ledger.py``. Spike H
exercises it end-to-end (upgrade → downgrade → upgrade) against a real
Postgres testcontainer to prove the migration is idempotent and reversible
BEFORE it gets committed to the production migration chain.

Schema scope (per CONTEXT D-01, D-04, D-08, D-16, D-17, D-26):
  * users.tier TEXT NOT NULL DEFAULT 'free' with CHECK ('free','pro','ultra')
  * users.stripe_customer_id TEXT NULL
  * users.refund_writeoff_cents BIGINT NOT NULL DEFAULT 0
  * credit_balances (user_id PK FK ON DELETE CASCADE, balance_cents, updated_at)
  * credit_transactions (id, user_id FK ON DELETE CASCADE, kind CHECK, amount_cents,
    reference_id, reference_type, created_at) + UNIQUE(reference_id, reference_type)
    partial WHERE reference_id IS NOT NULL + ix_credit_transactions_user_created
  * stripe_webhook_events (id, stripe_event_id UNIQUE, event_type, payload, created_at)
  * Data migration: cost_weights.ap_multiplier 1.0 → 1.15 (D-08)

Spike H runs this migration as ``014_phase_b_ledger_and_tier`` chained
on top of ``013_phase29_proxy_columns``.
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
    op.execute(
        "UPDATE cost_weights SET ap_multiplier = 1.15 "
        "WHERE ap_multiplier = 1.0"
    )


def downgrade() -> None:
    """Reverse upgrade(). The cost_weights data migration is reversed too."""
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
