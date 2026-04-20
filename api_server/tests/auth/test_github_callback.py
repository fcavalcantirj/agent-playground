"""R2 + D-22c-OAUTH-03: GitHub callback — state mismatch, email-fallback matrix.

GitHub is NOT OIDC, so the happy path fetches ``/user`` and (when
primary email is private) ``/user/emails``. This test file covers all
four branches:

  1. state mismatch (``mismatching_state``) → ``/login?error=state_mismatch``
  2. non-state OAuthError → ``/login?error=oauth_failed`` (WARNING-3 fix)
  3. happy path with a public profile email → ``/dashboard`` + user row
  4. happy path with private email → fallback to ``/user/emails`` →
     first primary+verified entry lands in users.email
  5. fallback yields no primary+verified entry → ``/login?error=oauth_failed``

The token-exchange path is monkey-patched; the ``/user`` and
``/user/emails`` endpoints are stubbed via respx (via the
``respx_oauth_providers`` fixture).
"""
from __future__ import annotations

import httpx
import pytest
from authlib.integrations.starlette_client import OAuthError

from api_server.auth.oauth import get_oauth
from api_server.config import Settings


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_state_mismatch_redirects_to_login_error(async_client, monkeypatch):
    """OAuthError(error='mismatching_state') → 302 /login?error=state_mismatch."""
    oauth = get_oauth(Settings())

    async def _raise_mismatch(_request):
        raise OAuthError(error="mismatching_state", description="x")

    monkeypatch.setattr(oauth.github, "authorize_access_token", _raise_mismatch)
    r = await async_client.get(
        "/v1/auth/github/callback?state=bad&code=x",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    assert "/login?error=state_mismatch" in r.headers["location"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_oauth_failed_on_non_state_error(async_client, monkeypatch):
    """WARNING-3 fix: non-``mismatching_state`` OAuthError → oauth_failed."""
    oauth = get_oauth(Settings())

    async def _raise_invalid_client(_request):
        raise OAuthError(error="invalid_client", description="bad creds")

    monkeypatch.setattr(
        oauth.github, "authorize_access_token", _raise_invalid_client
    )
    r = await async_client.get(
        "/v1/auth/github/callback?state=x&code=y",
        follow_redirects=False,
    )
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert "/login?error=oauth_failed" in loc
    assert "state_mismatch" not in loc, (
        f"invalid_client must not be misclassified as state_mismatch; got: {loc!r}"
    )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_happy_path_with_public_email(
    async_client, monkeypatch, respx_oauth_providers, db_pool,
):
    """GitHub returns public email → single /user fetch, no /emails call."""
    oauth = get_oauth(Settings())

    async def _fake_authorize(_request):
        return {"access_token": "gho_fake", "token_type": "bearer", "scope": "user:email"}

    monkeypatch.setattr(oauth.github, "authorize_access_token", _fake_authorize)

    with respx_oauth_providers() as stubs:
        stubs["github_user"].mock(return_value=httpx.Response(200, json={
            "id": 4242,
            "login": "octocat",
            "name": "The Octocat",
            "email": "octo@github.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/4242",
        }))
        r = await async_client.get(
            "/v1/auth/github/callback?state=x&code=y",
            follow_redirects=False,
        )

    assert r.status_code == 302, r.text
    assert r.headers["location"] == "/dashboard"
    assert "ap_session=" in r.headers.get("set-cookie", "")

    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT email, display_name, provider FROM users WHERE sub = '4242'"
        )
        assert user_row is not None, "GitHub user was not upserted"
        assert user_row["provider"] == "github"
        assert user_row["email"] == "octo@github.com"
        assert user_row["display_name"] == "The Octocat"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_happy_path_falls_back_to_user_emails_when_primary_private(
    async_client, monkeypatch, respx_oauth_providers, db_pool,
):
    """Primary email null → /user/emails fallback picks primary+verified entry.

    This is the contract GitHub users who set their primary email to
    private rely on (D-22c-OAUTH-03).
    """
    oauth = get_oauth(Settings())

    async def _fake_authorize(_request):
        return {"access_token": "gho_fake", "token_type": "bearer"}

    monkeypatch.setattr(oauth.github, "authorize_access_token", _fake_authorize)

    with respx_oauth_providers() as stubs:
        stubs["github_user"].mock(return_value=httpx.Response(200, json={
            "id": 5555,
            "login": "privatecat",
            "name": "Private Cat",
            "email": None,  # primary email private on GitHub
            "avatar_url": "https://avatars.githubusercontent.com/u/5555",
        }))
        stubs["github_user_emails"].mock(return_value=httpx.Response(200, json=[
            {
                "email": "5555+privatecat@users.noreply.github.com",
                "primary": True,
                "verified": True,
            },
            {
                "email": "other-not-primary@example.com",
                "primary": False,
                "verified": True,
            },
        ]))
        r = await async_client.get(
            "/v1/auth/github/callback?state=x&code=y",
            follow_redirects=False,
        )

    assert r.status_code == 302, r.text
    assert r.headers["location"] == "/dashboard"

    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT email FROM users WHERE sub = '5555'"
        )
        assert user_row is not None, "fallback user was not upserted"
        assert (
            user_row["email"]
            == "5555+privatecat@users.noreply.github.com"
        ), (
            f"expected primary+verified from /user/emails; got {user_row['email']!r}"
        )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_no_verified_email_redirects_to_oauth_failed(
    async_client, monkeypatch, respx_oauth_providers,
):
    """Primary email null + /user/emails yields no primary+verified → oauth_failed.

    We refuse to create an account without a verified email address on
    file (D-22c-OAUTH-03 second half).
    """
    oauth = get_oauth(Settings())

    async def _fake_authorize(_request):
        return {"access_token": "gho_fake", "token_type": "bearer"}

    monkeypatch.setattr(oauth.github, "authorize_access_token", _fake_authorize)

    with respx_oauth_providers() as stubs:
        stubs["github_user"].mock(return_value=httpx.Response(200, json={
            "id": 6666,
            "login": "noemail",
            "name": "No Email",
            "email": None,
        }))
        stubs["github_user_emails"].mock(return_value=httpx.Response(200, json=[
            {"email": "unverified@example.com", "primary": True, "verified": False},
            {"email": "verified-not-primary@example.com", "primary": False, "verified": True},
        ]))
        r = await async_client.get(
            "/v1/auth/github/callback?state=x&code=y",
            follow_redirects=False,
        )

    assert r.status_code == 302, r.text
    assert "/login?error=oauth_failed" in r.headers["location"]
