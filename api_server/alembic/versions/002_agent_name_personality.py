"""Add `name` + `personality` to agent_instances; replace unique constraint
to support multiple agents per (recipe, model) with different personas.

A user should be able to deploy many agents that share the same recipe and
model but have distinct names and personalities (e.g. "polite-helper" vs
"harsh-critic", both `picoclaw` + `openai/gpt-4o-mini`). The Phase 19
baseline constraint `(user_id, recipe_name, model)` blocks that — drop it
and add `(user_id, name)` instead so the natural user-facing key (the
agent's name) is what enforces uniqueness.

Existing rows (if any) are seeded with a synthetic name derived from
`recipe_name + model` so the upgrade is non-destructive. New deploys
through the API supply a real name.

Revision ID: 002_agent_name_personality
Revises: 001_baseline
Create Date: 2026-04-17
"""
import sqlalchemy as sa
from alembic import op

revision = "002_agent_name_personality"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the new columns NULLABLE first so the backfill doesn't choke.
    op.add_column("agent_instances", sa.Column("name", sa.Text, nullable=True))
    op.add_column("agent_instances", sa.Column("personality", sa.Text, nullable=True))

    # 2. Backfill name for any pre-existing rows (Phase 19 dev data).
    op.execute(
        """
        UPDATE agent_instances
        SET name = recipe_name || '-' || regexp_replace(model, '[^a-zA-Z0-9]+', '-', 'g')
        WHERE name IS NULL
        """
    )

    # 3. Make name NOT NULL now that every row has one.
    op.alter_column("agent_instances", "name", nullable=False)

    # 4. Drop the old unique constraint and add the new one keyed on (user_id, name).
    op.drop_constraint(
        "uq_agent_instances_user_recipe_model",
        "agent_instances",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_agent_instances_user_name",
        "agent_instances",
        ["user_id", "name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_agent_instances_user_name", "agent_instances", type_="unique"
    )
    op.create_unique_constraint(
        "uq_agent_instances_user_recipe_model",
        "agent_instances",
        ["user_id", "recipe_name", "model"],
    )
    op.drop_column("agent_instances", "personality")
    op.drop_column("agent_instances", "name")
