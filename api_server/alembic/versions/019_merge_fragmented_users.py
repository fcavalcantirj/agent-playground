"""Merge fragmented users into one row per canonical_email.

2026-05-18 — Bug #1 Part 2 (destructive). Migration 016 added
canonical_email + user_identities (additive); this migration COMPLETES
the dedup by:

  1. For each canonical_email group with COUNT(*) > 1: pick the OLDEST
     users.id as the winner. Reassign every FK pointing at the losers
     to the winner. Sum credit_balances onto the winner. DELETE losing
     users rows.
  2. CREATE UNIQUE INDEX uq_users_canonical_email so the next merge
     can't happen.

DOES NOT drop ``users.provider`` / ``users.sub`` / ``uq_users_provider_sub``
yet — the current ``upsert_user`` step-3 INSERT still writes those columns
(see auth/oauth.py:270-277). Removing them requires a paired code change
that lands in a separate PR.

10 tables with FK → users.id (verified 2026-05-18 via prod
information_schema): sessions (CASCADE), agent_instances (NO ACTION),
agent_containers (NO ACTION), idempotency_keys (NO ACTION), inapp_messages
(CASCADE), usage_logs (CASCADE), credit_balances (CASCADE), credit_transactions
(CASCADE), auth_events (SET NULL), user_identities (CASCADE).

For each (loser → winner) we explicitly UPDATE all 10 tables BEFORE
deleting the loser users row — this preserves audit trail even on
SET-NULL (auth_events) and CASCADE (credit_balances would otherwise
silently drop the row + lose the balance).

Revision ID: 019_merge_fragmented_users
Revises: 016_user_identities
Create Date: 2026-05-18
"""
from alembic import op


revision = "019_merge_fragmented_users"
down_revision = "016_user_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 1. Reassign every FK from loser → winner, table by table ----
    # The CTE `pairs` materializes (loser_id, winner_id) for every
    # canonical_email group with > 1 row. winner = oldest by created_at.
    # We then run 10 explicit UPDATEs that reference `pairs` via a sub-
    # select. After all UPDATEs land, DELETE the losing users rows.
    #
    # Done inside a single transaction (alembic default) so the whole
    # merge is atomic: any FK conflict or constraint violation rolls
    # back the entire migration.
    op.execute(r"""
        -- Build a temp table holding (loser_id, winner_id) for the merge.
        -- DISTINCT ON (canonical_email, …) picks the oldest as winner;
        -- losers are everything else in the group.
        CREATE TEMP TABLE _merge_pairs ON COMMIT DROP AS
        WITH grouped AS (
          SELECT
            id,
            canonical_email,
            created_at,
            FIRST_VALUE(id) OVER (
              PARTITION BY canonical_email
              ORDER BY created_at, id
            ) AS winner_id
          FROM users
          WHERE canonical_email IS NOT NULL
        )
        SELECT id AS loser_id, winner_id
        FROM grouped
        WHERE id <> winner_id;
    """)

    # 1a. sessions — CASCADE on delete, but we want to PRESERVE active
    # sessions so the user stays signed in. Explicit UPDATE.
    op.execute("""
        UPDATE sessions
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE sessions.user_id = p.loser_id;
    """)

    # 1b. agent_instances — NO ACTION on delete (would block the delete
    # entirely). Explicit UPDATE moves agents to the winner.
    op.execute("""
        UPDATE agent_instances
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE agent_instances.user_id = p.loser_id;
    """)

    # 1c. agent_containers — NO ACTION on delete; explicit UPDATE.
    op.execute("""
        UPDATE agent_containers
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE agent_containers.user_id = p.loser_id;
    """)

    # 1d. idempotency_keys — NO ACTION on delete; explicit UPDATE.
    # NOTE: idempotency_keys has UNIQUE (user_id, key). If the winner
    # AND loser both have rows with the SAME key, the UPDATE will
    # collide. Defensive: if a winner already has the key, DROP the
    # loser's row instead of moving it. asyncpg rejects multi-statement
    # op.execute() ("cannot insert multiple commands into a prepared
    # statement"), so DELETE + UPDATE go in separate op.execute() calls.
    op.execute("""
        DELETE FROM idempotency_keys ik
        USING _merge_pairs p
        WHERE ik.user_id = p.loser_id
          AND EXISTS (
            SELECT 1 FROM idempotency_keys w
            WHERE w.user_id = p.winner_id AND w.key = ik.key
          )
    """)
    op.execute("""
        UPDATE idempotency_keys
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE idempotency_keys.user_id = p.loser_id
    """)

    # 1e. inapp_messages — CASCADE on delete; reassign first so we keep
    # the conversation history. UNIQUE(user_id, idempotency_key) WHERE
    # idempotency_key IS NOT NULL exists; same defensive DROP-on-collide
    # pattern as idempotency_keys, split same way.
    op.execute("""
        DELETE FROM inapp_messages im
        USING _merge_pairs p
        WHERE im.user_id = p.loser_id
          AND im.idempotency_key IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM inapp_messages w
            WHERE w.user_id = p.winner_id
              AND w.idempotency_key = im.idempotency_key
          )
    """)
    op.execute("""
        UPDATE inapp_messages
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE inapp_messages.user_id = p.loser_id
    """)

    # 1f. usage_logs — CASCADE; reassign so the per-user usage trail
    # under the winner shows the full history.
    op.execute("""
        UPDATE usage_logs
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE usage_logs.user_id = p.loser_id;
    """)

    # 1g. credit_balances — CASCADE on delete + PK(user_id) (one row
    # per user). Both loser AND winner can have a row → SUM into
    # winner, DROP loser. Mirror Stripe-side `total_credits` accounting:
    # the platform owes the human the SUM of all their balances.
    # Aggregate loser balances per winner FIRST. If Felipe has 2 losing
    # rows both pointing at the same winner, the naive INSERT ... ON
    # CONFLICT DO UPDATE would try to UPDATE the same target row twice
    # in one statement → Postgres error "ON CONFLICT DO UPDATE command
    # cannot affect row a second time" (verified via dry-run on
    # 2026-05-18). GROUP BY winner_id collapses N losers into 1 sum
    # per winner. Split into two op.execute() calls (asyncpg
    # rejects multi-statement prepared statements).
    op.execute("""
        INSERT INTO credit_balances (user_id, balance_cents, updated_at)
        SELECT p.winner_id, SUM(cb.balance_cents), NOW()
        FROM _merge_pairs p
        JOIN credit_balances cb ON cb.user_id = p.loser_id
        GROUP BY p.winner_id
        ON CONFLICT (user_id)
        DO UPDATE SET
          balance_cents = credit_balances.balance_cents + EXCLUDED.balance_cents,
          updated_at = NOW()
    """)
    op.execute("""
        DELETE FROM credit_balances cb
        USING _merge_pairs p
        WHERE cb.user_id = p.loser_id
    """)

    # 1h. credit_transactions — CASCADE; reassign so the ledger under
    # the winner shows the full transaction history (no SUM needed —
    # transactions are append-only per-row).
    op.execute("""
        UPDATE credit_transactions
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE credit_transactions.user_id = p.loser_id;
    """)

    # 1i. auth_events — SET NULL on delete; explicit UPDATE preserves
    # the audit trail under the winner instead of NULL-ing.
    op.execute("""
        UPDATE auth_events
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE auth_events.user_id = p.loser_id;
    """)

    # 1j. user_identities — CASCADE; reassign so all (provider, sub)
    # rows for the human point at the winner.
    op.execute("""
        UPDATE user_identities
        SET user_id = p.winner_id
        FROM _merge_pairs p
        WHERE user_identities.user_id = p.loser_id;
    """)

    # ---- 2. DELETE losing users rows ---------------------------------
    # All FKs have been reassigned (or, for CASCADE tables we explicitly
    # moved the rows). This DELETE is now safe.
    op.execute("""
        DELETE FROM users u
        USING _merge_pairs p
        WHERE u.id = p.loser_id;
    """)

    # ---- 3. UNIQUE on canonical_email --------------------------------
    # Partial unique — NULL canonical_email (Apple privacy-relay rows)
    # are exempt. After this index lands, future ``upsert_user`` calls
    # for a duplicate canonical_email must go through the link path
    # in auth/oauth.py:243-263 (which always returns the existing
    # winner's user_id), not the new-user path.
    op.execute("""
        CREATE UNIQUE INDEX uq_users_canonical_email
        ON users (canonical_email)
        WHERE canonical_email IS NOT NULL;
    """)


def downgrade() -> None:
    # The merge is destructive — losers are gone. A downgrade can drop
    # the UNIQUE index but cannot resurrect the merged rows. Document
    # the asymmetry; never call downgrade in prod past this revision.
    op.execute("DROP INDEX IF EXISTS uq_users_canonical_email;")
