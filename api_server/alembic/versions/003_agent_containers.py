"""Phase 22-02 — persistent-container audit table (agent_containers).

Adds a new `agent_containers` table keyed by `agent_instance_id` so the
Phase 22-05 `/start` / `/stop` / `/status` endpoints can reliably find a
user's running container, and so channel credentials (bot tokens, allowed
user IDs) can live at rest encrypted with age + a per-user KEK.

Design — separate table, NOT additive columns on agent_instances
(PATTERNS.md §Artifact 6 rationale): one agent_instance can have a
history of containers across start/stop cycles. Useful for Phase 23
persistent volumes; cheap here, expensive to retrofit later.

Columns:
  - id UUID PK (gen_random_uuid default)
  - agent_instance_id UUID FK(agent_instances.id) ON DELETE CASCADE
  - user_id UUID FK(users.id)
  - recipe_name TEXT
  - deploy_mode TEXT DEFAULT 'persistent'
      enum via CHECK: ('one_shot', 'persistent')
      future-proofs for Plan 23 (persistent workspaces)
  - container_id TEXT NULL — filled after docker-run returns cidfile
  - container_status TEXT DEFAULT 'starting'
      enum via CHECK: ('starting', 'running', 'stopping', 'stopped',
                       'start_failed', 'crashed')
  - channel_type TEXT NULL — 'telegram' for Phase 22a
  - channel_config_enc BYTEA NULL — age-encrypted blob containing
      JSON {env: {TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER}, channel}.
      BYTEA is the ONLY persistence path for channel creds — no
      plaintext column exists (SC-05 BYOK discipline).
  - boot_wall_s NUMERIC NULL — wall clock from docker-run to ready_at
  - ready_at TIMESTAMPTZ NULL — moment the ready_log_regex matched
  - created_at TIMESTAMPTZ DEFAULT NOW()
  - stopped_at TIMESTAMPTZ NULL
  - last_error TEXT NULL — redacted exception text from failure paths

Indexes:
  - ix_agent_containers_agent_instance_running PARTIAL UNIQUE on
      (agent_instance_id) WHERE container_status='running'
      Enforces "one running container per agent" (CLAUDE.md "one
      active session per user" MVP seam). Partial-only so stopped
      history doesn't block new starts.
  - ix_agent_containers_user_status on (user_id, container_status)
      For /status listings + GC sweeps.

Revision ID: 003_agent_containers
Revises: 002_agent_name_personality
Create Date: 2026-04-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003_agent_containers"
down_revision = "002_agent_name_personality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_containers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "agent_instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("recipe_name", sa.Text, nullable=False),
        sa.Column(
            "deploy_mode",
            sa.Text,
            nullable=False,
            server_default=sa.text("'persistent'"),
        ),
        sa.Column("container_id", sa.Text, nullable=True),
        sa.Column(
            "container_status",
            sa.Text,
            nullable=False,
            server_default=sa.text("'starting'"),
        ),
        sa.Column("channel_type", sa.Text, nullable=True),
        sa.Column("channel_config_enc", sa.LargeBinary, nullable=True),
        sa.Column("boot_wall_s", sa.Numeric, nullable=True),
        sa.Column(
            "ready_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "stopped_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("last_error", sa.Text, nullable=True),
    )
    op.create_check_constraint(
        "ck_agent_containers_deploy_mode",
        "agent_containers",
        "deploy_mode IN ('one_shot', 'persistent')",
    )
    op.create_check_constraint(
        "ck_agent_containers_status",
        "agent_containers",
        "container_status IN ('starting', 'running', 'stopping', "
        "'stopped', 'start_failed', 'crashed')",
    )
    # Partial unique index: at most one RUNNING container per agent.
    # Stopped / failed history rows do not block new starts.
    op.create_index(
        "ix_agent_containers_agent_instance_running",
        "agent_containers",
        ["agent_instance_id"],
        unique=True,
        postgresql_where=sa.text("container_status = 'running'"),
    )
    op.create_index(
        "ix_agent_containers_user_status",
        "agent_containers",
        ["user_id", "container_status"],
    )


def downgrade() -> None:
    # Drop indexes + constraints before the table.
    op.drop_index(
        "ix_agent_containers_user_status", table_name="agent_containers"
    )
    op.drop_index(
        "ix_agent_containers_agent_instance_running",
        table_name="agent_containers",
    )
    op.drop_constraint(
        "ck_agent_containers_status",
        "agent_containers",
        type_="check",
    )
    op.drop_constraint(
        "ck_agent_containers_deploy_mode",
        "agent_containers",
        type_="check",
    )
    op.drop_table("agent_containers")
