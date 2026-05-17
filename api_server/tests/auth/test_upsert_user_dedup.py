"""2026-05-17 — Bug #1 upsert_user dedup tests.

Real Postgres testcontainer. Verifies that:

  * Same (provider, sub) signing in twice → one users row + one identity.
  * Different (provider, sub) but same canonical_email → one users row +
    multiple identity rows.
  * Apple privacy-relay never links to other identities (canonical=NULL).
  * Gmail dot variants collapse to one users row.
  * Cross-tenant isolation preserved.
"""
from __future__ import annotations

import asyncio

import pytest


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


async def test_same_provider_sub_twice_one_user_row(db_pool):
    """Sign in via google twice with the same sub → one users.id, one
    user_identities row, last_login_at updated."""
    from api_server.auth.oauth import upsert_user

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            uid_1 = await upsert_user(
                conn,
                provider="google", sub="g-1",
                email="abc@gmail.com",
                display_name="Abc", avatar_url=None,
            )
        async with conn.transaction():
            uid_2 = await upsert_user(
                conn,
                provider="google", sub="g-1",
                email="abc@gmail.com",
                display_name="Abc Updated", avatar_url="https://pic",
            )
    assert uid_1 == uid_2, "second signin must return the same user_id"

    async with db_pool.acquire() as conn:
        user_rows = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE canonical_email='abc@gmail.com'"
        )
        identity_rows = await conn.fetchval(
            "SELECT COUNT(*) FROM user_identities WHERE user_id=$1", uid_1,
        )
        # display_name updated to the second login's value
        display = await conn.fetchval(
            "SELECT display_name FROM users WHERE id=$1", uid_1,
        )
    assert user_rows == 1
    assert identity_rows == 1
    assert display == "Abc Updated"


async def test_gmail_dots_variants_link_to_one_user(db_pool):
    """The actual bug-driving prod case: Google returns
    `felipe.cavalcanti.rj@gmail.com` (with dots); GitHub returns
    `felipecavalcantirj@gmail.com` (without dots); magic-link uses the
    dotted form. All three → ONE users row, THREE identities."""
    from api_server.auth.oauth import upsert_user

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            uid_google = await upsert_user(
                conn,
                provider="google", sub="g-felipe",
                email="felipe.cavalcanti.rj@gmail.com",
                display_name="Felipe (Google)", avatar_url=None,
            )
        async with conn.transaction():
            uid_github = await upsert_user(
                conn,
                provider="github", sub="gh-felipe",
                email="felipecavalcantirj@gmail.com",  # GitHub strips dots
                display_name="Felipe (GitHub)", avatar_url=None,
            )
        async with conn.transaction():
            uid_email = await upsert_user(
                conn,
                provider="email", sub="felipe.cavalcanti.rj@gmail.com",
                email="felipe.cavalcanti.rj@gmail.com",
                display_name="Felipe (Magic-Link)", avatar_url=None,
            )

    assert uid_google == uid_github == uid_email, (
        f"all 3 providers must resolve to ONE user; got "
        f"google={uid_google}, github={uid_github}, email={uid_email}"
    )

    async with db_pool.acquire() as conn:
        user_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE canonical_email IS NOT NULL "
            "AND canonical_email = 'felipecavalcantirj@gmail.com'"
        )
        identity_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_identities WHERE user_id=$1",
            uid_google,
        )
        providers = await conn.fetch(
            "SELECT provider FROM user_identities WHERE user_id=$1 "
            "ORDER BY provider", uid_google,
        )
    assert user_count == 1
    assert identity_count == 3
    assert [r["provider"] for r in providers] == ["email", "github", "google"]


async def test_apple_privacy_relay_does_not_link(db_pool):
    """Apple privacy-relay emails canonicalize to NULL → cannot link
    cross-provider. Two Apple sign-ins WITH DIFFERENT subs produce TWO
    users rows. (That's a separate bug class — Apple privacy-relay
    rotates — but our system MUST NOT spuriously link unrelated users
    via the relay-shaped email string.)"""
    from api_server.auth.oauth import upsert_user

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            uid_a = await upsert_user(
                conn,
                provider="apple", sub="apple-sub-A",
                email="randomA@privaterelay.appleid.com",
                display_name="A", avatar_url=None,
            )
        async with conn.transaction():
            uid_b = await upsert_user(
                conn,
                provider="apple", sub="apple-sub-B",
                email="randomB@privaterelay.appleid.com",
                display_name="B", avatar_url=None,
            )
    assert uid_a != uid_b, (
        "two distinct Apple subs with relay emails must NOT collapse "
        "into one user; relay addresses are never canonical identifiers"
    )
    async with db_pool.acquire() as conn:
        canonical_a = await conn.fetchval(
            "SELECT canonical_email FROM users WHERE id=$1", uid_a,
        )
        canonical_b = await conn.fetchval(
            "SELECT canonical_email FROM users WHERE id=$1", uid_b,
        )
    assert canonical_a is None
    assert canonical_b is None


async def test_apple_real_email_links_with_google(db_pool):
    """If Apple returns a REAL email (user shared their email rather than
    using privacy-relay), AND the Google account uses the same email,
    the two providers should link to ONE user."""
    from api_server.auth.oauth import upsert_user

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            uid_google = await upsert_user(
                conn,
                provider="google", sub="g-jane",
                email="jane@example.com",
                display_name="Jane (Google)", avatar_url=None,
            )
        async with conn.transaction():
            uid_apple = await upsert_user(
                conn,
                provider="apple", sub="apple-sub-jane",
                email="jane@example.com",  # real email, not relay
                display_name="Jane (Apple)", avatar_url=None,
            )
    assert uid_google == uid_apple


async def test_cross_user_isolation(db_pool):
    """Two different humans with different emails get different user_ids
    regardless of provider mix. Defense against canonical_email collision."""
    from api_server.auth.oauth import upsert_user

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            uid_a = await upsert_user(
                conn,
                provider="google", sub="g-alice",
                email="alice@example.com",
                display_name="Alice", avatar_url=None,
            )
        async with conn.transaction():
            uid_b = await upsert_user(
                conn,
                provider="google", sub="g-bob",
                email="bob@example.com",
                display_name="Bob", avatar_url=None,
            )
    assert uid_a != uid_b


async def test_first_sign_in_creates_user_and_identity_rows(db_pool):
    """A brand-new signup creates 1 users row + 1 user_identities row.
    Both have last_login_at set. canonical_email is computed from email."""
    from api_server.auth.oauth import upsert_user

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            uid = await upsert_user(
                conn,
                provider="google", sub="g-new",
                email="New.User@Gmail.com",
                display_name="New User", avatar_url="https://pic",
            )
        user = await conn.fetchrow(
            "SELECT canonical_email, email, display_name, avatar_url, "
            "last_login_at FROM users WHERE id=$1", uid,
        )
        identity = await conn.fetchrow(
            "SELECT provider, sub, email, last_login_at "
            "FROM user_identities WHERE user_id=$1", uid,
        )
    assert user["canonical_email"] == "newuser@gmail.com"
    assert user["email"] == "New.User@Gmail.com"  # original preserved
    assert user["display_name"] == "New User"
    assert user["avatar_url"] == "https://pic"
    assert user["last_login_at"] is not None
    assert identity["provider"] == "google"
    assert identity["sub"] == "g-new"
    assert identity["email"] == "New.User@Gmail.com"
    assert identity["last_login_at"] is not None


# --- Concurrent-race regression tests (Reviewer #3 BLOCK fixes) ----------


async def test_concurrent_cross_provider_link_no_duplicate_users(db_pool):
    """Two simultaneous first-time sign-ins from DIFFERENT providers but
    the SAME canonical_email MUST collapse to ONE users row.

    Pre-fix: both transactions would miss steps 1 + 2 and both fall to
    step 3, creating two users rows -- the exact bug 016 is fixing --
    because migration 016 deliberately has no UNIQUE on canonical_email
    yet (it waits for the 017 audit step).

    Post-fix: ``pg_advisory_xact_lock(canonical_email)`` serializes the
    two transactions on the canonical_email hash so the second one sees
    the first one's users row via step 2 and links instead of inserting.
    """
    from api_server.auth.oauth import upsert_user

    async def signin(provider, sub, email):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                return await upsert_user(
                    conn,
                    provider=provider, sub=sub,
                    email=email,
                    display_name=f"{provider}-name", avatar_url=None,
                )

    # Same Gmail inbox via two different providers, racing.
    uid_a, uid_b = await asyncio.gather(
        signin("google", "g-race-1", "race.user@gmail.com"),
        signin("github", "gh-race-1", "raceuser@gmail.com"),
    )
    assert uid_a == uid_b, (
        f"concurrent cross-provider sign-ins must collapse to one user; "
        f"got google={uid_a}, github={uid_b}"
    )
    async with db_pool.acquire() as conn:
        users_for_canonical = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE canonical_email = 'raceuser@gmail.com'"
        )
        identities = await conn.fetchval(
            "SELECT COUNT(*) FROM user_identities WHERE user_id = $1", uid_a,
        )
    assert users_for_canonical == 1
    assert identities == 2


async def test_concurrent_same_provider_sub_no_orphan(db_pool):
    """Two simultaneous first-time sign-ins with the SAME (provider, sub)
    MUST resolve to one users row + one identity, no orphan.

    Pre-fix: UNIQUE (provider, sub) on user_identities would raise
    UniqueViolationError on the loser, and the loser's just-INSERTed
    users row would survive the rollback only if the caller's transaction
    succeeded.

    Post-fix: ON CONFLICT (provider, sub) DO UPDATE RETURNING user_id
    returns the winner's user_id; the loser deletes its orphan users row
    before returning the winner.
    """
    from api_server.auth.oauth import upsert_user

    async def signin():
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                return await upsert_user(
                    conn,
                    provider="google", sub="g-concurrent-same",
                    email="concurrent@example.com",
                    display_name="Concurrent", avatar_url=None,
                )

    uid_a, uid_b = await asyncio.gather(signin(), signin())
    assert uid_a == uid_b, (
        f"concurrent same-(provider, sub) sign-ins must return same user_id; "
        f"got {uid_a} vs {uid_b}"
    )
    async with db_pool.acquire() as conn:
        users_count = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE email = 'concurrent@example.com'"
        )
        identities_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_identities WHERE provider = 'google' "
            "AND sub = 'g-concurrent-same'"
        )
    assert users_count == 1, "no orphan users row from the losing race"
    assert identities_count == 1


async def test_concurrent_apple_relay_does_not_collapse(db_pool):
    """Two simultaneous Apple sign-ins with DIFFERENT subs but both
    privacy-relay emails MUST NOT collapse. canonical_email=NULL means
    the advisory lock is skipped, so this test proves the (provider, sub)
    ON CONFLICT path correctly differentiates."""
    from api_server.auth.oauth import upsert_user

    async def signin(sub, relay_email):
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                return await upsert_user(
                    conn,
                    provider="apple", sub=sub,
                    email=relay_email,
                    display_name="Apple User", avatar_url=None,
                )

    uid_a, uid_b = await asyncio.gather(
        signin("apple-sub-RACE-A", "a@privaterelay.appleid.com"),
        signin("apple-sub-RACE-B", "b@privaterelay.appleid.com"),
    )
    assert uid_a != uid_b, "different Apple subs must NOT collapse"
