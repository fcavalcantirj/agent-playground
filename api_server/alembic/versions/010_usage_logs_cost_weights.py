"""Phase 27 — usage_logs (per-call BYOK ledger) + cost_weights (admin-mutable pricing).

Phase 27 (Phase A from the 2026-05-04 solidity audit) is the BYOK Usage
Visibility layer — what does this agent cost the user, in real USD,
right now? Not a paywall, not a debit, no Stripe. Pure read-only display
over an append-only per-call ledger.

This migration creates:

  1. ``usage_logs`` — one row per upstream LLM call. Token counts +
     authoritative USD cost are written by ``UsageRecorder`` (services/
     usage_recorder.py, Plan 27 Change 2) immediately after the bot's
     reply lands in ``inapp_messages.bot_response``. Append-only; no
     UPDATE path.

  2. ``cost_weights`` — admin-mutable per-(provider, model) pricing.
     OpenRouter calls don't strictly need it (post-hoc fetch of
     ``/api/v1/generation`` returns canonical USD), but Anthropic-direct
     and OpenAI-direct paths do — they parse the upstream ``usage`` block
     for tokens then multiply by these per-1M-token weights. The
     ``ap_multiplier`` column carries the Phase B markup (defaults 1.0
     for visibility-only Phase A; will rise per-row when Phase B's pay-
     upfront paywall ships).

Schema details (``usage_logs``):

  id                     UUID PK DEFAULT gen_random_uuid()
  user_id                UUID FK → users.id ON DELETE CASCADE
                            denormalized so the AppBar ticker hot path
                            doesn't have to JOIN through agent_instances
                            on every screen mount.
  agent_instance_id      UUID FK → agent_instances.id ON DELETE CASCADE
                            cascade matches inapp_messages — when an
                            agent is deleted its history goes with it.
  message_id             UUID NULL — inapp_messages.id when the call
                            originated from an in-app chat. NULL for
                            telegram path (no inapp_messages row).
                            No FK declared (loose coupling — telegram
                            path will never join, and a hard FK would
                            block the row when chat history is purged).
  provider               TEXT NOT NULL  ('openrouter' | 'anthropic' | 'openai')
  model                  TEXT NOT NULL  (the upstream id, e.g.
                            'anthropic/claude-haiku-4.5' or
                            'claude-haiku-4-5')
  upstream_request_id    TEXT NULL — OpenRouter generation id (for the
                            post-hoc /api/v1/generation lookup) OR
                            Anthropic msg_* id OR OpenAI request id.
                            Phase B will add a UNIQUE constraint here
                            for billing idempotency; Phase A leaves it
                            unconstrained (best-effort observability).
  input_tokens           INT NOT NULL DEFAULT 0
  output_tokens          INT NOT NULL DEFAULT 0
  cache_read_tokens      INT NOT NULL DEFAULT 0 — Anthropic prompt-cache
                            hits (priced ~10× cheaper than fresh input).
  cache_creation_tokens  INT NOT NULL DEFAULT 0 — Anthropic prompt-cache
                            writes; collapses 5m and 1h ephemeral TTL
                            buckets into one column. Phase A seeds the
                            cost_weights with the 5m rate (1.25× input);
                            1h-cache calls will under-price by ~37%
                            until/unless a TTL column is added (no
                            current recipe uses 1h caching).
  cost_usd               NUMERIC(14, 8) NOT NULL DEFAULT 0 — canonical
                            USD. NUMERIC(14,8) handles ~$1M aggregates
                            with sub-cent precision. Anthropic haiku at
                            14 input + 4 output tokens costs $0.000034 —
                            integer cents would round to 0; that's why
                            we picked NUMERIC over BIGINT-micros.
  latency_ms             INT NULL — wall-clock between dispatcher
                            forwarding the prompt and bot's reply
                            arrival (recorded by inapp_dispatcher).
  status                 TEXT NOT NULL DEFAULT 'success'
                            CHECK (status IN ('success','error','unknown'))
                            'unknown' covers the case where the bot
                            returned no usage block (a2a_jsonrpc / native
                            shapes that strip token counts).
  status_code            INT NULL — HTTP status from upstream when
                            available; mostly NULL until openai_compat
                            adapters surface it.
  stop_reason            TEXT NULL — Anthropic 'end_turn'/'max_tokens'/
                            'stop_sequence' OR OpenAI 'stop'/'length'/
                            'content_filter'/'tool_calls'. Useful debug
                            signal even pre-Phase-B.
  source                 TEXT NOT NULL DEFAULT 'inapp'
                            CHECK (source IN ('inapp','telegram','run'))
                            'run' covers /v1/runs one-shots; 'telegram'
                            covers persistent-channel paths if/when we
                            wire usage capture there.
  created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()

Indexes:

  * ``ix_usage_logs_user_created`` — btree on (user_id, created_at DESC)
    INCLUDE (cost_usd). Powers the AppBar ticker hot path
    (SUM(cost_usd) WHERE user_id = $1) as an index-only scan. INCLUDE
    avoids the heap fetch that aggregating cost_usd would otherwise
    force on every screen mount.

  * ``ix_usage_logs_agent_created`` — btree on (agent_instance_id,
    created_at DESC). Powers per-agent breakdown queries (cumulative
    sums + last 7d/30d daily series).

A third composite index on (user_id, agent_instance_id, created_at)
was considered and DROPPED — Postgres uses the leading-column prefix
of ``ix_usage_logs_user_created`` for user-only queries, and no current
read pattern filters on (user_id, agent_instance_id) jointly with a
sort. Add later if needed.

Schema details (``cost_weights``):

  provider                  TEXT NOT NULL
  model                     TEXT NOT NULL
  input_per_1m_usd          NUMERIC(12, 6) NOT NULL
  output_per_1m_usd         NUMERIC(12, 6) NOT NULL
  cache_read_per_1m_usd     NUMERIC(12, 6) NULL — Anthropic only; OpenAI
                                charges only on write side
  cache_creation_per_1m_usd NUMERIC(12, 6) NULL — Anthropic only
  ap_multiplier             NUMERIC(6, 4) NOT NULL DEFAULT 1.0 —
                                Phase B markup vehicle (left at 1.0
                                for Phase A; raise per-row to charge
                                more than upstream cost)
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
  PRIMARY KEY (provider, model)

Seed rows: 6 baseline weights covering the recipes' verified_cells
matrix. Three OpenRouter rows are LIVE-CONFIRMED against
``/api/v1/models`` pricing (probed 2026-05-04, costs reconcile to the
penny against real chat completions). Two Anthropic-direct rows are
LIVE-CONFIRMED against the Messages API (haiku-4-5 + sonnet-4-5
returned full ``usage`` blocks 2026-05-04). One OpenAI gpt-4o-mini row
is doc-confirmed (no OPENAI_API_KEY in dev env at probe time; pricing
mirrors OpenRouter's catalog values which match OpenAI's published
list price). Cache multipliers (1.25× write, 0.10× read) verified from
``platform.claude.com/docs/en/about-claude/pricing``.

Decision references:

  * memory/project_phase_27_constraints.md — locked schema (cost in
    USD not Pokens; cost_weights table required; ap_multiplier carries
    Phase B markup; no money flow in Phase A)
  * memory/feedback_ap_proxy_is_not_msv_proxy.md — why we don't mirror
    MSV's egress proxy (BYOK = user pays upstream; we only need
    visibility)
  * .planning/ROADMAP.md Phase 27 — USE-01 / USE-02 / USE-03 +
    8 success criteria

Revision ID: 010_usage_logs_cost_weights
Revises: 009_auth_events_revoked_reason
Create Date: 2026-05-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010_usage_logs_cost_weights"
down_revision = "009_auth_events_revoked_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create usage_logs + cost_weights and seed 6 baseline weight rows."""

    # --- usage_logs ----------------------------------------------------
    op.create_table(
        "usage_logs",
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
            "agent_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("upstream_request_id", sa.Text, nullable=True),
        sa.Column(
            "input_tokens",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "output_tokens",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cache_read_tokens",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cache_creation_tokens",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(14, 8),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'success'"),
        ),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("stop_reason", sa.Text, nullable=True),
        sa.Column(
            "source",
            sa.Text,
            nullable=False,
            server_default=sa.text("'inapp'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_check_constraint(
        "ck_usage_logs_status",
        "usage_logs",
        "status IN ('success','error','unknown')",
    )
    op.create_check_constraint(
        "ck_usage_logs_source",
        "usage_logs",
        "source IN ('inapp','telegram','run')",
    )

    # ix_usage_logs_user_created — INCLUDE (cost_usd) makes the ticker
    # hot path (SUM(cost_usd) WHERE user_id = $1) an index-only scan.
    # alembic op.create_index forwards postgresql_include to the dialect.
    op.create_index(
        "ix_usage_logs_user_created",
        "usage_logs",
        ["user_id", sa.text("created_at DESC")],
        postgresql_include=["cost_usd"],
    )
    op.create_index(
        "ix_usage_logs_agent_created",
        "usage_logs",
        ["agent_instance_id", sa.text("created_at DESC")],
    )

    # --- cost_weights --------------------------------------------------
    op.create_table(
        "cost_weights",
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("input_per_1m_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("output_per_1m_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("cache_read_per_1m_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "cache_creation_per_1m_usd",
            sa.Numeric(12, 6),
            nullable=True,
        ),
        sa.Column(
            "ap_multiplier",
            sa.Numeric(6, 4),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("provider", "model", name="cost_weights_pkey"),
    )

    # Seed: 6 baseline weight rows. Live-confirmed against OpenRouter
    # /api/v1/models pricing + Anthropic Messages API direct probes
    # (2026-05-04). Cache multipliers from the Anthropic pricing page
    # (5m write = 1.25× input, read = 0.10× input). OpenAI gpt-4o-mini
    # cache_creation is NULL because OpenAI auto-caches without a
    # separate write fee (NULL distinguishes "no charge" from "unknown").
    op.execute(
        """
        INSERT INTO cost_weights
            (provider, model, input_per_1m_usd, output_per_1m_usd,
             cache_read_per_1m_usd, cache_creation_per_1m_usd, ap_multiplier)
        VALUES
            ('openrouter', 'anthropic/claude-haiku-4.5',  1.000000,  5.000000, 0.100000, 1.250000, 1.0000),
            ('openrouter', 'anthropic/claude-sonnet-4.5', 3.000000, 15.000000, 0.300000, 3.750000, 1.0000),
            ('openrouter', 'openai/gpt-4o-mini',          0.150000,  0.600000, 0.075000, NULL,     1.0000),
            ('anthropic',  'claude-haiku-4-5',            1.000000,  5.000000, 0.100000, 1.250000, 1.0000),
            ('anthropic',  'claude-sonnet-4-5',           3.000000, 15.000000, 0.300000, 3.750000, 1.0000),
            ('openai',     'gpt-4o-mini',                 0.150000,  0.600000, 0.075000, NULL,     1.0000)
        """
    )


def downgrade() -> None:
    """Drop cost_weights and usage_logs (in dependency-safe order)."""
    op.drop_table("cost_weights")
    op.drop_index("ix_usage_logs_agent_created", table_name="usage_logs")
    op.drop_index("ix_usage_logs_user_created", table_name="usage_logs")
    op.drop_constraint("ck_usage_logs_source", "usage_logs", type_="check")
    op.drop_constraint("ck_usage_logs_status", "usage_logs", type_="check")
    op.drop_table("usage_logs")
