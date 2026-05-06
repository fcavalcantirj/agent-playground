"""Phase 29 — proxy columns + idempotency status + unknown-row wipe.

Adds the schema surface Phase 29's LLM egress proxy needs:

  1. ``agent_containers.bridge_ip`` (INET, nullable) — the docker bridge IP
     the proxy router uses to map an inbound proxy request back to a
     specific container session (AMD-04). Indexed via partial btree
     ``ix_agent_containers_bridge_ip_running`` with the predicate
     ``container_status='running' AND bridge_ip IS NOT NULL`` so the
     hot-path lookup stays index-only and the index size stays tiny.

  2. ``agent_containers.upstream_provider`` (TEXT, nullable) — the upstream
     LLM provider the proxy must dispatch to ('openrouter' | 'anthropic'
     | 'openai'). NULL pre-Phase-29 (rows pre-date the proxy era; the
     dispatcher rewrites NULL on first use). D-11.

  3. ``agent_containers.provider_key_enc`` (BYTEA, nullable) — encrypted
     BYOK upstream API key, age-cipher ciphertext keyed by the existing
     ``AP_CHANNEL_MASTER_KEY`` (Phase 22 audited primitive). NULL until
     the user supplies a key (BYOK opt-in). D-02.

  4. ``usage_logs.proxy_latency_ms`` + ``usage_logs.upstream_latency_ms``
     (INTEGER, nullable) — split timings recorded by the proxy for ops
     debugging (proxy_latency_ms = wall-clock inside the proxy router;
     upstream_latency_ms = wall-clock the upstream provider took). Both
     NULL until the proxy lands; legacy rows stay NULL. D-11.

  5. Widened ``ck_usage_logs_status`` to allow ``'failed'`` alongside the
     existing ('success','error','unknown'). The proxy records 'failed'
     when an upstream call errors out before any usage block is parseable
     (TLS error, 5xx, timeout). D-15.

  6. D-06 row wipe: ``DELETE FROM usage_logs WHERE status='unknown'``.
     Pre-Phase-29 'unknown' rows came from a2a_jsonrpc / native shapes
     that strip token counts; they cannot be cost-backfilled and are
     non-recoverable. The DELETE is irreversible — downgrade does NOT
     restore the rows; this is documented in
     ``test_migration_013_proxy_columns.py::test_round_trip_clean``.

  7. ``idempotency_keys.status`` (TEXT, NOT NULL DEFAULT 'success') with
     check constraint allowing ('success','failed','in_flight'). Plus
     ``verdict_json`` relaxed to NULLABLE so a placeholder reserved row
     can be inserted BEFORE the upstream call lands (AMD-03 in-flight
     reservation pattern). The watchdog sweeper later transitions
     'in_flight' rows that exceed their TTL to 'failed' or deletes them.

Revision ID: 013_phase29_proxy_columns
Revises: 012_cost_weights_extra
Create Date: 2026-05-06

NOTE on revision ID length: ``alembic_version.version_num`` is
``varchar(32)``. ``013_phase29_proxy_columns`` is 25 chars — fits cleanly.
The ``down_revision`` points to migration 012's DB-stored revision id
``012_cost_weights_extra`` (NOT the longer file name
``012_cost_weights_extra_models.py``); migration 012 itself uses the
shorter form for its ``revision`` string, mirroring 011's pattern.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "013_phase29_proxy_columns"
down_revision = "012_cost_weights_extra"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add proxy columns + idempotency status + unknown-row wipe."""

    # AMD-04: agent_containers.bridge_ip + partial index for IP-map hot path
    op.add_column(
        "agent_containers",
        sa.Column("bridge_ip", postgresql.INET(), nullable=True),
    )
    op.create_index(
        "ix_agent_containers_bridge_ip_running",
        "agent_containers",
        ["bridge_ip"],
        unique=False,
        postgresql_where=sa.text(
            "container_status = 'running' AND bridge_ip IS NOT NULL"
        ),
    )

    # D-11 + D-02: agent_containers.upstream_provider + provider_key_enc
    op.add_column(
        "agent_containers",
        sa.Column("upstream_provider", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_containers",
        sa.Column("provider_key_enc", sa.LargeBinary(), nullable=True),
    )

    # D-11: usage_logs.proxy_latency_ms + upstream_latency_ms
    op.add_column(
        "usage_logs",
        sa.Column("proxy_latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "usage_logs",
        sa.Column("upstream_latency_ms", sa.Integer(), nullable=True),
    )

    # D-15: widen status enum to include 'failed'
    op.drop_constraint("ck_usage_logs_status", "usage_logs", type_="check")
    op.create_check_constraint(
        "ck_usage_logs_status",
        "usage_logs",
        "status IN ('success','error','unknown','failed')",
    )

    # D-06: wipe legacy rows that can't be backfilled. Irreversible by
    # design (downgrade does NOT restore them — documented in tests).
    op.execute("DELETE FROM usage_logs WHERE status = 'unknown'")

    # AMD-03: idempotency_keys.status + verdict_json NULLABLE for the
    # in-flight reservation pattern. Status defaults to 'success' so
    # existing rows (all successful by definition since they have a
    # populated verdict_json from before this migration) keep passing
    # the new check constraint.
    op.add_column(
        "idempotency_keys",
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'success'"),
        ),
    )
    op.create_check_constraint(
        "ck_idempotency_keys_status",
        "idempotency_keys",
        "status IN ('success','failed','in_flight')",
    )
    # AMD-03 (PROBE-VAL-09 schema delta): verdict_json relaxes to NULLABLE
    # so a placeholder row can be inserted BEFORE the upstream call lands.
    op.alter_column(
        "idempotency_keys",
        "verdict_json",
        existing_type=postgresql.JSONB(),
        nullable=True,
    )


def downgrade() -> None:
    """Reverse upgrade(). The DELETE in upgrade() is non-reversible."""
    # Restore verdict_json to NOT NULL. This is safe because between
    # upgrade and downgrade, every reserved-but-unsettled row will have
    # been resolved by the watchdog sweeper (status='in_flight' rows are
    # the only ones with NULL verdict_json by construction; in-flight
    # rows expire after 5min and are deleted by the watchdog). The op
    # below assumes that downgrade is run from a stable state — if
    # NULLs remain, the statement will fail with NotNullViolation and
    # the operator must run the watchdog cleanup first.
    op.alter_column(
        "idempotency_keys",
        "verdict_json",
        existing_type=postgresql.JSONB(),
        nullable=False,
    )
    op.drop_constraint(
        "ck_idempotency_keys_status",
        "idempotency_keys",
        type_="check",
    )
    op.drop_column("idempotency_keys", "status")

    op.drop_constraint("ck_usage_logs_status", "usage_logs", type_="check")
    op.create_check_constraint(
        "ck_usage_logs_status",
        "usage_logs",
        "status IN ('success','error','unknown')",
    )
    op.drop_column("usage_logs", "upstream_latency_ms")
    op.drop_column("usage_logs", "proxy_latency_ms")
    op.drop_column("agent_containers", "provider_key_enc")
    op.drop_column("agent_containers", "upstream_provider")
    op.drop_index(
        "ix_agent_containers_bridge_ip_running",
        table_name="agent_containers",
    )
    op.drop_column("agent_containers", "bridge_ip")
