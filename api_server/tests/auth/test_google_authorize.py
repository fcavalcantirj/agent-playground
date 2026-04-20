"""R1: GET /v1/auth/google returns 302 to the Google authorize endpoint.

The handler delegates to ``oauth.google.authorize_redirect``. Per D-22c-OAUTH-02
this emits a ``Location`` header pointing at ``accounts.google.com/...`` with
``client_id``, ``state``, and (when a redirect_uri is configured)
``redirect_uri`` query-string params, and sets the ``ap_oauth_state``
cookie (Starlette's built-in SessionMiddleware stores authlib's CSRF
nonce there — AMD-07 signed with AP_OAUTH_STATE_SECRET).

No respx stubs needed — authlib's authorize-redirect path is pure URL
construction + cookie write; no outbound HTTP is issued.

The test sets ``AP_OAUTH_GOOGLE_REDIRECT_URI`` directly on the Settings
instance after the app boots: the ``async_client`` fixture monkeypatches
``AP_ENV=dev`` but leaves the OAuth env vars unset (so the registry
registers with dev placeholders). To exercise the ``redirect_uri=``
assertion below we override the setting in-place on ``app.state.settings``
— the route reads via ``request.app.state.settings`` so this takes
effect without rebuilding the app.
"""
from __future__ import annotations

import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_google_authorize_returns_302_with_state_cookie(async_client):
    """Authorize endpoint emits a proper 302 + all required query params."""
    # Inject a redirect URI on the live Settings object; route will pass it
    # through to ``oauth.google.authorize_redirect`` → landed in Location.
    async_client._transport.app.state.settings.oauth_google_redirect_uri = (
        "http://localhost:8000/v1/auth/google/callback"
    )
    r = await async_client.get("/v1/auth/google", follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/"), (
        f"Location must be a Google authorize URL; got: {loc!r}"
    )
    assert "client_id=" in loc
    assert "state=" in loc
    assert "redirect_uri=" in loc, (
        f"expected redirect_uri in Location; got: {loc!r}"
    )
    # Starlette's SessionMiddleware emits the state cookie on the first
    # session write (authlib stashes the nonce in request.session).
    set_cookie = r.headers.get("set-cookie", "")
    assert "ap_oauth_state=" in set_cookie, (
        f"expected ap_oauth_state cookie; got Set-Cookie: {set_cookie!r}"
    )
