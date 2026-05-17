"""2026-05-17 — Migration 016 schema + backfill tests.

Real Postgres testcontainer. Verifies:

  * user_identities table exists with the right shape.
  * canonical_email column added; backfilled correctly for every email
    shape (Gmail-with-dots, Gmail-with-plus, Googlemail, Outlook,
    Apple-relay, NULL-email).
  * UNIQUE (provider, sub) on user_identities still enforces dedup per
    provider (no two users share the same (provider, sub)).
"""
from __future__ import annotations

from uuid import uuid4

import asyncpg
import pytest


pytestmark = pytest.mark.api_integration


async def test_user_identities_table_exists(db_pool):
    """Table shape matches migration 016."""
    async with db_pool.acquire() as conn:
        cols = await conn.fetch(
            "SELECT column_name, is_nullable, data_type "
            "FROM information_schema.columns "
            "WHERE table_name = 'user_identities' "
            "ORDER BY ordinal_position"
        )
    col_names = [c["column_name"] for c in cols]
    assert "id" in col_names
    assert "user_id" in col_names
    assert "provider" in col_names
    assert "sub" in col_names
    assert "email" in col_names
    assert "created_at" in col_names
    assert "last_login_at" in col_names


async def test_user_identities_unique_provider_sub(db_pool):
    """Two rows with the same (provider, sub) must violate UNIQUE."""
    user_a = uuid4()
    user_b = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name, tier) "
            "VALUES ($1, 'google', 'collide-sub', 'a@x.com', 'A', 'free'), "
            "($2, 'google', 'other-sub', 'b@x.com', 'B', 'free')",
            user_a, user_b,
        )
        await conn.execute(
            "INSERT INTO user_identities (user_id, provider, sub, email) "
            "VALUES ($1, 'google', 'collide-sub', 'a@x.com')",
            user_a,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO user_identities (user_id, provider, sub, email) "
                "VALUES ($1, 'google', 'collide-sub', 'b@x.com')",
                user_b,
            )


async def test_canonical_email_column_exists(db_pool):
    async with db_pool.acquire() as conn:
        col = await conn.fetchrow(
            "SELECT column_name, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'canonical_email'"
        )
    assert col is not None
    assert col["is_nullable"] == "YES"


async def test_backfill_gmail_dot_collapse(db_pool):
    """Inserting a Gmail-with-dots email backfills as the dot-stripped form
    when the migration re-runs OR via the post-016 SQL helper. For a fresh
    INSERT today the column is left NULL — the api_server upsert path is
    what writes it for new users (Part 2). This test verifies the COLUMN
    DEFAULT is NULL and the schema is ready."""
    user_id = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name, tier) "
            "VALUES ($1, 'google', $2, 'a.b@gmail.com', 'A', 'free')",
            user_id, f"sub-{user_id.hex[:8]}",
        )
        # Fresh insert leaves canonical_email NULL (Part 2 writes it).
        ce = await conn.fetchval(
            "SELECT canonical_email FROM users WHERE id = $1", user_id,
        )
    assert ce is None


async def test_backfill_sql_dot_collapse_executed_against_seed(db_pool):
    """Run the migration's backfill SQL again against a fresh seed and
    verify the canonicalization rules. Mirrors the Python helper but
    proves the SQL behavior."""
    user_ids = {
        "gmail_dots": uuid4(),
        "gmail_no_dots": uuid4(),
        "gmail_plus": uuid4(),
        "googlemail": uuid4(),
        "outlook": uuid4(),
        "relay": uuid4(),
        "null_email": uuid4(),
    }
    async with db_pool.acquire() as conn:
        for label, uid in user_ids.items():
            emails = {
                "gmail_dots":     "a.b.c@gmail.com",
                "gmail_no_dots":  "abc@gmail.com",
                "gmail_plus":     "a.b+tag@gmail.com",
                "googlemail":     "a.b@googlemail.com",
                "outlook":        "a.b@outlook.com",
                "relay":          "xyz123@privaterelay.appleid.com",
                "null_email":     None,
            }
            email_val = emails[label]
            await conn.execute(
                "INSERT INTO users (id, provider, sub, email, display_name, tier) "
                "VALUES ($1, 'google', $2, $3, $4, 'free')",
                uid, f"sub-{uid.hex[:12]}", email_val, label,
            )
        # Run the same backfill SQL the migration uses, scoped to these rows.
        await conn.execute(r"""
            UPDATE users SET canonical_email = CASE
              WHEN LOWER(TRIM(email)) LIKE '%@privaterelay.appleid.com' THEN NULL
              WHEN LOWER(TRIM(email)) LIKE '%@gmail.com'
                OR LOWER(TRIM(email)) LIKE '%@googlemail.com'
              THEN
                REPLACE(
                  SPLIT_PART(SPLIT_PART(LOWER(TRIM(email)), '@', 1), '+', 1),
                  '.', ''
                )
                || '@gmail.com'
              WHEN email IS NOT NULL AND TRIM(email) <> ''
                THEN LOWER(TRIM(email))
              ELSE NULL
            END
            WHERE id = ANY($1::uuid[]);
        """, list(user_ids.values()))
        rows = await conn.fetch(
            "SELECT display_name AS label, canonical_email FROM users "
            "WHERE id = ANY($1::uuid[])",
            list(user_ids.values()),
        )
    out = {r["label"]: r["canonical_email"] for r in rows}
    assert out["gmail_dots"]    == "abc@gmail.com"
    assert out["gmail_no_dots"] == "abc@gmail.com"
    assert out["gmail_plus"]    == "ab@gmail.com"
    assert out["googlemail"]    == "ab@gmail.com"
    assert out["outlook"]       == "a.b@outlook.com"
    assert out["relay"]         is None
    assert out["null_email"]    is None


async def test_real_user_case_collapses(db_pool):
    """The real prod case: felipe.cavalcanti.rj@gmail.com AND
    felipecavalcantirj@gmail.com canonicalize to the same string."""
    user_dots = uuid4()
    user_no_dots = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name, tier) "
            "VALUES "
            "($1, 'google', $2, 'felipe.cavalcanti.rj@gmail.com', 'A', 'free'),"
            "($3, 'github', $4, 'felipecavalcantirj@gmail.com', 'B', 'free')",
            user_dots, f"sub-{user_dots.hex[:8]}",
            user_no_dots, f"sub-{user_no_dots.hex[:8]}",
        )
        await conn.execute(r"""
            UPDATE users SET canonical_email = CASE
              WHEN LOWER(TRIM(email)) LIKE '%@privaterelay.appleid.com' THEN NULL
              WHEN LOWER(TRIM(email)) LIKE '%@gmail.com'
                OR LOWER(TRIM(email)) LIKE '%@googlemail.com'
              THEN
                REPLACE(
                  SPLIT_PART(SPLIT_PART(LOWER(TRIM(email)), '@', 1), '+', 1),
                  '.', ''
                )
                || '@gmail.com'
              WHEN email IS NOT NULL AND TRIM(email) <> ''
                THEN LOWER(TRIM(email))
              ELSE NULL
            END
            WHERE id IN ($1, $2)
        """, user_dots, user_no_dots)
        rows = await conn.fetch(
            "SELECT canonical_email FROM users WHERE id IN ($1, $2)",
            user_dots, user_no_dots,
        )
    canonicals = [r["canonical_email"] for r in rows]
    assert canonicals[0] == canonicals[1] == "felipecavalcantirj@gmail.com", (
        f"both Gmail dot variants must canonicalize to the same string; "
        f"got {canonicals!r}"
    )
