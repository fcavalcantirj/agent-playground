"""R1: GET /v1/auth/github returns 302 to the GitHub authorize endpoint.

GitHub is NOT OIDC — authlib was registered with hand-specified endpoints
(see ``auth/oauth.py``), so the 302 target is
``github.com/login/oauth/authorize`` rather than a discovered URL.
"""
from __future__ import annotations

import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_github_authorize_returns_302_with_state_cookie(async_client):
    """Authorize endpoint emits a proper 302 + all required query params.

    See ``test_google_authorize`` for the rationale behind mutating
    ``app.state.settings`` in-place (async_client fixture leaves OAuth
    envvars unset; the redirect URI is needed for the ``redirect_uri=``
    assertion below).
    """
    async_client._transport.app.state.settings.oauth_github_redirect_uri = (
        "http://localhost:8000/v1/auth/github/callback"
    )
    r = await async_client.get("/v1/auth/github", follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert loc.startswith("https://github.com/login/oauth/authorize"), (
        f"Location must be the GitHub authorize URL; got: {loc!r}"
    )
    assert "client_id=" in loc
    assert "state=" in loc
    assert "redirect_uri=" in loc, (
        f"expected redirect_uri in Location; got: {loc!r}"
    )
    set_cookie = r.headers.get("set-cookie", "")
    assert "ap_oauth_state=" in set_cookie, (
        f"expected ap_oauth_state cookie; got Set-Cookie: {set_cookie!r}"
    )
