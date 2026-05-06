"""012_cost_weights_extra_models — seed cost_weights for in-use OpenRouter models

Closes the `usage_recorder.weights_missing` warning that fires for any model
not in the original Phase 27 seed (migration 010). Without a row, cost
computation falls through to Decimal("0") and the BYOK usage ticker shows
$0 forever despite real token consumption.

Adds two rows live-confirmed against OpenRouter /api/v1/models on
2026-05-05:

  - xiaomi/mimo-v2.5         (zeroclaw recipe default — paid)
  - minimax/minimax-m2.5:free (free tier — genuinely $0/$0, but the row
                                must exist so the lookup returns instead
                                of warning + returning Decimal("0"))

Migration 010's docstring (lines 300-305) documents the seed evolution
discipline: every new (provider, model) tuple ships via Alembic. This
migration follows that pattern exactly.

Note: minimax/minimax-m2.5:free's :free suffix is preserved in
usage_logs.model with no normalization (Phase 28 verifier confirmed end-
to-end strings match exactly). The cost_weights primary key (provider,
model) must use the same exact string for the lookup to hit.

Revision ID: 012_cost_weights_extra
Revises: 011_phase28_workflow_id_idem
Created: 2026-05-05
"""

from alembic import op


revision = "012_cost_weights_extra"
down_revision = "011_phase28_workflow_id_idem"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add cost_weights rows for xiaomi/mimo-v2.5 and minimax/minimax-m2.5:free.

    Prices sourced from OpenRouter /api/v1/models (2026-05-05). Cache_read
    rates included where the model exposes them; cache_creation is NULL for
    both (OpenRouter does not surface a separate cache-write fee for these
    models).
    """
    op.execute(
        """
        INSERT INTO cost_weights
            (provider, model, input_per_1m_usd, output_per_1m_usd,
             cache_read_per_1m_usd, cache_creation_per_1m_usd, ap_multiplier)
        VALUES
            ('openrouter', 'xiaomi/mimo-v2.5',          0.400000, 2.000000, 0.080000, NULL, 1.0000),
            ('openrouter', 'minimax/minimax-m2.5:free', 0.000000, 0.000000, NULL,     NULL, 1.0000)
        ON CONFLICT (provider, model) DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove only the rows this migration added."""
    op.execute(
        """
        DELETE FROM cost_weights
        WHERE (provider, model) IN (
            ('openrouter', 'xiaomi/mimo-v2.5'),
            ('openrouter', 'minimax/minimax-m2.5:free')
        )
        """
    )
