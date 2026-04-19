"""SPIKE A (Wave 0 gate) — respx x authlib 1.6.11 interop.

Proves that ``respx`` correctly intercepts authlib's outbound httpx calls to
Google's OAuth endpoints BEFORE any downstream test authors a real OAuth
integration test against respx stubs. Per D-22c-TEST-03 + AMD-05 + RESEARCH
Open Question 5.

PASS criterion: the stubbed Google /token endpoint fires exactly once and
authlib parses the canned payload without a network call escaping.

FAIL -> phase goes back to discuss-phase; respx + authlib combination is
not compatible and the test strategy must be revisited (pytest-httpx
fallback per RESEARCH Alternatives Considered).
"""
from __future__ import annotations

import httpx
import pytest
import respx
from authlib.integrations.starlette_client import OAuth


@pytest.mark.asyncio
@respx.mock
async def test_respx_intercepts_authlib_token_exchange():
    """Stub Google's /token endpoint, drive authlib's fetch_access_token,
    assert the stub fired and authlib parsed the canned payload.

    No network call escapes: ``respx.mock`` raises on any unmatched httpx
    request, so a regression that bypasses the interceptor would surface
    here as a ``respx.MockError`` or a DNS-level failure, not a silent
    pass.
    """
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id="spike-client-id",
        client_secret="spike-client-secret",
        access_token_url="https://oauth2.googleapis.com/token",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        client_kwargs={"scope": "openid email profile"},
    )

    token_route = respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "ya29.spike",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid email profile",
            },
        )
    )

    # Exercise authlib's token-exchange path directly. No Starlette request
    # is needed because state verification happens at authorize_access_token
    # (the higher-level wrapper) — fetch_access_token itself just hits
    # the token endpoint with the auth code.
    token = await oauth.google.fetch_access_token(
        redirect_uri="http://localhost:8000/v1/auth/google/callback",
        code="spike-auth-code",
    )

    assert token_route.called, "respx did not intercept authlib's token call"
    assert token_route.call_count == 1, (
        f"expected exactly 1 intercepted call, got {token_route.call_count}"
    )
    assert token["access_token"] == "ya29.spike"
    assert token["token_type"] == "Bearer"
    assert token["expires_in"] == 3600
