"""Allow multiple running containers per agent_instance, one per channel.

2026-05-17 — Bug #2 Part 2. Loosens the partial-unique index from
``UNIQUE (agent_instance_id) WHERE container_status='running'`` to
``UNIQUE (agent_instance_id, channel_type) WHERE container_status='running'``.

Why: hermes (and any other recipe with multi-channel gateway-daemon
mode — see ``recipes/hermes.yaml:222-282``) legitimately spawns a
SEPARATE ``agent_containers`` row per active channel. The mobile
orchestrator's deploy flow is `/v1/runs` → `/start channel=inapp` →
optional `/start channel=telegram` — both on the SAME agent_instance.
Pre-018, the second `/start` raised UniqueViolationError at the
write-to-running step (mapped to 409 AGENT_ALREADY_RUNNING). Post-018,
inapp + telegram can run simultaneously on the same logical agent.

Pairs with:
  - migration 014 D-05 tier cap (already uses COUNT DISTINCT
    agent_instance_id post the 2026-05-17 tier_enforcement.py fix), so
    a multi-channel agent still counts as ONE slot in the cap.
  - run_store.py::fetch_running_container_for_agent now accepts a
    channel_type filter (caller chooses which channel's container).
  - routes/agent_messages.py POST + SSE both filter
    channel_type='inapp' (chat surface is inapp-only).
  - inapp_reaper.py attributes stuck-message events to the inapp
    container only.

Revision ID: 018_multi_channel_partial_unique
Revises: 017... (no 017 yet; chained on 015)
Create Date: 2026-05-17
"""
import sqlalchemy as sa
from alembic import op


revision = "018_multi_channel_partial_unique"
down_revision = "015_email_otp_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old index (agent_instance_id) WHERE status='running'.
    op.drop_index(
        "ix_agent_containers_agent_instance_running",
        table_name="agent_containers",
    )
    # Recreate as a partial unique on (agent_instance_id, channel_type).
    # NULL channel_type is treated as a distinct value by Postgres in
    # uniqueness — which is fine, because every agent_containers row
    # that has been created since channel_type was added (migration 003)
    # has a non-NULL channel_type for the persistent-mode path. Legacy
    # one-shot rows (which never reach `running` status anyway) are not
    # affected.
    op.create_index(
        "ix_agent_containers_agent_instance_channel_running",
        "agent_containers",
        ["agent_instance_id", "channel_type"],
        unique=True,
        postgresql_where=sa.text("container_status = 'running'"),
    )


def downgrade() -> None:
    # Reverse: drop the per-channel index, restore the old per-agent
    # partial unique. If any agent has multiple running containers across
    # channels at downgrade time, the restore would fail; the operator
    # must first stop all-but-one container per agent. This is intentional
    # — downgrading from multi-channel is destructive by nature.
    op.drop_index(
        "ix_agent_containers_agent_instance_channel_running",
        table_name="agent_containers",
    )
    op.create_index(
        "ix_agent_containers_agent_instance_running",
        "agent_containers",
        ["agent_instance_id"],
        unique=True,
        postgresql_where=sa.text("container_status = 'running'"),
    )
