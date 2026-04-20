"""R5: POST /v1/auth/logout — invalidate session + clear cookie.

Flow asserted end-to-end:
  1. Authenticated GET /v1/users/me → 200 (sanity check the cookie works)
  2. POST /v1/auth/logout with same cookie → 204 + Set-Cookie clears ap_session
  3. Same cookie against /v1/users/me → 401 (session row deleted)

And the negative path:
  * POST /v1/auth/logout without a cookie → 401 Stripe-shape envelope
"""
from __future__ import annotations

import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_logout_204_invalidates_session(async_client, authenticated_cookie, db_pool):
    """Full round-trip: authenticated → logout 204 → same cookie now rejected."""
    cookie = {"Cookie": authenticated_cookie["Cookie"]}

    # Sanity: cookie works before logout.
    r_before = await async_client.get("/v1/users/me", headers=cookie)
    assert r_before.status_code == 200, r_before.text

    # Logout.
    r_logout = await async_client.post("/v1/auth/logout", headers=cookie)
    assert r_logout.status_code == 204, r_logout.text
    # 204 has no body — assert empty content.
    assert r_logout.content == b"", (
        f"204 must have no body; got: {r_logout.content!r}"
    )
    set_cookie = r_logout.headers.get("set-cookie", "")
    assert "ap_session=" in set_cookie, (
        f"expected ap_session clearing cookie; got: {set_cookie!r}"
    )
    assert "max-age=0" in set_cookie.lower(), (
        f"expected Max-Age=0 to clear the cookie; got: {set_cookie!r}"
    )

    # sessions row actually deleted from PG.
    async with db_pool.acquire() as conn:
        row_count = await conn.fetchval(
            "SELECT COUNT(*) FROM sessions WHERE id::text = $1",
            authenticated_cookie["_session_id"],
        )
        assert row_count == 0, (
            f"expected session row to be DELETEd; still present ({row_count} rows)"
        )

    # Cookie is now invalid — /v1/users/me returns 401.
    r_after = await async_client.get("/v1/users/me", headers=cookie)
    assert r_after.status_code == 401, r_after.text


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_logout_without_cookie_returns_401(async_client):
    """POST /v1/auth/logout without an ``ap_session`` cookie → 401 Stripe envelope."""
    r = await async_client.post("/v1/auth/logout")
    assert r.status_code == 401, r.text
    body = r.json()
    assert "error" in body, body
    assert body["error"]["code"] == "UNAUTHORIZED", body
    assert body["error"]["param"] == "ap_session", body
