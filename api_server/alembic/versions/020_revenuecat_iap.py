"""020 — RevenueCat webhook idempotency table for IAP integration.

Sibling to stripe_webhook_events (added in 014). RevenueCat's webhook
posts JSON events on every iOS/Android IAP transition (INITIAL_PURCHASE,
RENEWAL, CANCELLATION, EXPIRATION, REFUND, …); our handler dedupes on
``rc_event_id`` so a 5xx retry from RC can't double-credit the ledger.

The ledger itself doesn't need schema changes — credit_transactions
already has a partial UNIQUE(reference_id, reference_type) WHERE
reference_id IS NOT NULL (migration 014). Tier-change rows from IAP
just use reference_type='revenuecat_event' instead of 'stripe_event';
the existing UNIQUE handles cross-source idempotency for free.

Revision ID: 020_revenuecat_iap
Revises: 019_merge_fragmented_users
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "020_revenuecat_iap"
down_revision = "019_merge_fragmented_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add revenuecat_webhook_events table for IAP webhook idempotency."""
    op.create_table(
        "revenuecat_webhook_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("rc_event_id", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "rc_event_id", name="uq_revenuecat_webhook_events_event_id",
        ),
    )


def downgrade() -> None:
    """Reverse upgrade()."""
    op.drop_table("revenuecat_webhook_events")
