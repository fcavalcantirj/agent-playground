"""R2 + D-22c-FE-03: Google callback — all error-redirect flavors + happy path.

Tests monkeypatch ``oauth.google.authorize_access_token`` rather than
driving authlib's full state-verification machinery. Rationale:

* For error cases (mismatching_state, invalid_grant, missing sub), the
  point of the test is "given authlib raised this exact OAuthError, does
  our route emit the correct ``/login?error=<code>`` redirect?". The
  monkey-patch lets us force the exact OAuthError value without having
  to manufacture a valid-then-invalid state cookie.

* For the happy path, we monkey-patch to return a canned token dict with
  a ``userinfo`` sub-dict, then assert the users + sessions rows land in
  PG and the ``ap_session`` cookie is set on the 302 response.

The ``access_denied`` case hits the route BEFORE authlib is invoked
(the route short-circuits on ``request.query_params.get("error")``), so
no patching is required.

WARNING-3 fix verification: ``test_oauth_failed_on_non_state_error``
confirms that an OAuthError whose ``.error`` is NOT the literal string
``"mismatching_state"`` routes to ``oauth_failed``, not ``state_mismatch``.
"""
from __future__ import annotations

import pytest
from authlib.integrations.starlette_client import OAuthError

from api_server.auth.oauth import get_oauth
from api_server.config import Settings


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_state_mismatch_redirects_to_login_error(async_client, monkeypatch):
    """OAuthError(error='mismatching_state') → 302 /login?error=state_mismatch.

    EXACT-match check: the route compares ``e.error == "mismatching_state"``.
    """
    oauth = get_oauth(Settings())

    async def _raise_mismatch(_request):
        raise OAuthError(error="mismatching_state", description="State mismatch")

    monkeypatch.setattr(oauth.google, "authorize_access_token", _raise_mismatch)
    r = await async_client.get(
        "/v1/auth/google/callback?state=bad&code=x",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    assert "/login?error=state_mismatch" in r.headers["location"], r.headers


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_access_denied_redirects_to_login_error(async_client):
    """?error=access_denied → 302 /login?error=access_denied (no authlib touch)."""
    r = await async_client.get(
        "/v1/auth/google/callback?error=access_denied",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    assert "/login?error=access_denied" in r.headers["location"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_oauth_failed_on_non_state_error(async_client, monkeypatch):
    """WARNING-3 fix: non-``mismatching_state`` OAuthError → oauth_failed.

    Regression trap against a future refactor that substring-matches on
    ``"state"``. ``invalid_grant`` is the canonical "authorization code
    expired / already used" error returned by Google's token endpoint.
    """
    oauth = get_oauth(Settings())

    async def _raise_invalid_grant(_request):
        raise OAuthError(error="invalid_grant", description="Code expired")

    monkeypatch.setattr(
        oauth.google, "authorize_access_token", _raise_invalid_grant
    )
    r = await async_client.get(
        "/v1/auth/google/callback?state=x&code=y",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert "/login?error=oauth_failed" in loc, loc
    assert "state_mismatch" not in loc, (
        "invalid_grant must NOT be misclassified as state_mismatch; "
        f"got: {loc!r}"
    )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_happy_path_upserts_user_mints_session_sets_cookie(
    async_client, monkeypatch, db_pool,
):
    """Full happy path: userinfo in token → user + session rows + ap_session cookie.

    We avoid the discovery + JWKS dance by monkey-patching
    ``authorize_access_token`` to directly return a token dict with an
    embedded ``userinfo``. This exercises every line of the happy path
    in ``google_callback`` including the upsert + mint_session branch.
    """
    oauth = get_oauth(Settings())

    async def _fake_authorize(_request):
        return {
            "access_token": "ya29.fake",
            "token_type": "Bearer",
            "expires_in": 3600,
            "userinfo": {
                "sub": "google-test-sub-happy-path",
                "email": "happy@example.com",
                "name": "Happy User",
                "picture": "https://example.com/happy.png",
            },
        }

    monkeypatch.setattr(oauth.google, "authorize_access_token", _fake_authorize)

    r = await async_client.get(
        "/v1/auth/google/callback?state=x&code=y",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    assert r.headers["location"] == "/dashboard", r.headers
    set_cookie = r.headers.get("set-cookie", "")
    assert "ap_session=" in set_cookie, (
        f"expected ap_session cookie; got: {set_cookie!r}"
    )

    # users row landed via upsert_user
    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT id, provider, sub, email, display_name, avatar_url "
            "FROM users WHERE sub = $1",
            "google-test-sub-happy-path",
        )
        assert user_row is not None, "user row was not upserted"
        assert user_row["provider"] == "google"
        assert user_row["email"] == "happy@example.com"
        assert user_row["display_name"] == "Happy User"
        assert user_row["avatar_url"] == "https://example.com/happy.png"

        # sessions row landed via mint_session and points at this user
        session_count = await conn.fetchval(
            "SELECT COUNT(*) FROM sessions WHERE user_id = $1",
            user_row["id"],
        )
        assert session_count == 1, (
            f"expected exactly 1 session for new user; got {session_count}"
        )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_missing_sub_redirects_to_oauth_failed(async_client, monkeypatch):
    """userinfo without ``sub`` → 302 /login?error=oauth_failed.

    authlib's token dict should always carry a ``sub`` for a valid OIDC
    round-trip; if it doesn't (provider bug / malformed id_token), we
    refuse to mint a session rather than write a user row keyed on None.
    """
    oauth = get_oauth(Settings())

    async def _fake_no_sub(_request):
        return {
            "access_token": "ya29.fake",
            "token_type": "Bearer",
            "userinfo": {
                # No "sub" key
                "email": "ghost@example.com",
                "name": "Ghost",
            },
        }

    monkeypatch.setattr(oauth.google, "authorize_access_token", _fake_no_sub)
    r = await async_client.get(
        "/v1/auth/google/callback?state=x&code=y",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    assert "/login?error=oauth_failed" in r.headers["location"]
