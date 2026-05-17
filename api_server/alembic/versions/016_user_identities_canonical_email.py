"""User identities join table + canonical_email column.

2026-05-17 — Bug #1 Part 1 (additive). Lays the substrate for cross-
provider account linking. NO destructive changes yet:

  * Creates ``user_identities`` table (one row per (provider, sub) pair),
    backfilled from existing ``users.{provider, sub, email}``.
  * Adds ``users.canonical_email`` column (nullable for now).
  * Backfills ``canonical_email`` from ``users.email`` using Gmail dot-
    collapse + privacy-relay nullification (mirrors the Python helper at
    ``auth/canonical.py``).
  * Does NOT add UNIQUE on canonical_email, does NOT merge duplicate
    rows, does NOT drop users.provider/sub. Those land in migration 017
    after the operator runs the audit script.

The api_server keeps using ``upsert_user`` on the old (provider, sub)
key throughout migration 016's lifetime — but after this migration,
the new upsert_via_identity path can also run (Bug #1 Part 2). Both
write to the same row via ``users.id``; user_identities is the index
of (provider, sub) tuples per user.

Revision ID: 016_user_identities_canonical_email
Revises: 018_multi_channel_partial_unique
Create Date: 2026-05-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic. Length constraint: the
# alembic_version.version_num column is varchar(32), so revision IDs
# must fit cleanly. Earlier longer name `016_user_identities_canonical_email`
# (36 chars) hit StringDataRightTruncationError on alembic upgrade.
# Shortened to fit (the migration's full intent is still in the docstring).
revision = "016_user_identities"
down_revision = "018_multi_channel_partial_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 1. user_identities table -------------------------------------
    op.create_table(
        "user_identities",
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
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "provider", "sub", name="uq_user_identities_provider_sub",
        ),
    )
    op.create_index(
        "ix_user_identities_user_id", "user_identities", ["user_id"],
    )

    # ---- 2. Backfill identities from existing users rows --------------
    # Every existing users row with a non-null sub becomes a
    # user_identities row pointing at the same user_id.
    op.execute("""
        INSERT INTO user_identities (
            user_id, provider, sub, email, created_at, last_login_at
        )
        SELECT id, provider, sub, email,
               created_at,
               COALESCE(last_login_at, created_at)
          FROM users
         WHERE sub IS NOT NULL
           AND provider IS NOT NULL
    """)

    # ---- 3. canonical_email column ------------------------------------
    op.add_column(
        "users", sa.Column("canonical_email", sa.Text(), nullable=True),
    )

    # ---- 4. Backfill canonical_email from users.email -----------------
    # SQL mirror of api_server.auth.canonical::canonical_email:
    #   - Lowercase + trim.
    #   - Privacy-relay → NULL.
    #   - Gmail + Googlemail: strip dots + '+suffix' from local part.
    #   - googlemail.com → gmail.com.
    #   - Everything else: lowercased verbatim.
    op.execute(r"""
        UPDATE users
        SET canonical_email = CASE
          -- Apple privacy relay: never a stable per-human identifier.
          WHEN LOWER(TRIM(email)) LIKE '%@privaterelay.appleid.com' THEN NULL
          -- Gmail + Googlemail: dot-collapse + plus-strip on local part.
          WHEN LOWER(TRIM(email)) LIKE '%@gmail.com'
            OR LOWER(TRIM(email)) LIKE '%@googlemail.com'
          THEN
            REPLACE(
              SPLIT_PART(SPLIT_PART(LOWER(TRIM(email)), '@', 1), '+', 1),
              '.', ''
            )
            || '@gmail.com'
          -- Other providers: dots are significant; preserve verbatim.
          WHEN email IS NOT NULL AND TRIM(email) <> ''
            THEN LOWER(TRIM(email))
          ELSE NULL
        END
        WHERE email IS NOT NULL;
    """)

    # NOTE intentionally omitted: NO `UNIQUE INDEX ON canonical_email` yet.
    # The audit script must surface duplicate groups first; migration 017
    # (post-merge) is when the UNIQUE lands.


def downgrade() -> None:
    # Drop the canonical_email column and the user_identities table.
    # Existing users.{provider, sub, email} survive — they were never
    # touched by 016. Identities table is rebuildable from users on
    # the next re-upgrade.
    op.drop_column("users", "canonical_email")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
