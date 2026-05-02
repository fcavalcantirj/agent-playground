"""SPIKE A2 (Wave 0) — respx interception of google-auth JWKS fetch.

Confirm whether ``respx`` (an httpx-only HTTP mock) intercepts the JWKS
HTTP fetch performed by google-auth's transport when
``google.oauth2.id_token.verify_oauth2_token`` is called.

Why this matters: Plan 23-06 (mobile-OAuth tests) wants the cleanest test
scaffold. Two candidate patterns:

  (A) ``respx.mock`` stubs the JWKS endpoint → google-auth's verify call
      uses our mocked JWKS payload, signature verification proceeds
      normally, audience check determines pass/fail.

  (B) ``respx`` does NOT intercept (because google-auth's transport uses
      the ``requests`` library, not ``httpx``) → mobile-OAuth tests
      fall back to monkeypatching ``_fetch_certs`` (or
      ``verify_oauth2_token`` itself) to bypass the JWKS fetch entirely.

Spike A1 (``test_google_auth_multi_audience.py``) already validates the
fallback path (B) works cleanly. This spike empirically picks (A) vs (B)
so Plan 23-06's executor doesn't have to re-derive it.

OUTCOME (filled in by executor after running):
  respx intercepts google-auth JWKS fetch: NO
  Mobile-OAuth test scaffold should use: monkeypatch _fetch_certs (the
    fallback path validated in spike A1)

Empirical reasoning: ``google.auth.transport.requests.Request`` calls the
``requests`` library under the hood (via ``requests.Session.send``).
``respx`` mocks ``httpx.HTTPTransport`` — a different HTTP stack. There
is no shared seam between them. This spike asserts the fact directly so
a future google-auth version that switches to httpx (unlikely but
possible) would flip the spike to PASS the (A) branch and prompt a
test-scaffold revisit.
"""
from __future__ import annotations

import httpx
import pytest
import respx
from google.auth.transport import requests as _gauth_ga_requests
from google.oauth2 import id_token as _google_id_token


_GOOGLE_V1_CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
_GOOGLE_V3_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"


@pytest.mark.asyncio
@respx.mock(assert_all_called=False)
async def test_respx_does_not_intercept_google_auth_requests_transport():
    """Drive ``id_token._fetch_certs`` directly with the production
    transport (``google.auth.transport.requests.Request``) and assert:

      1. The respx route stub is NOT marked as called (proving respx
         did not see the request).
      2. The actual call either reaches the network and returns a real
         response, OR raises a network/transport error — but in NEITHER
         case is our mocked payload returned.

    This drives the "outcome=B / monkeypatch fallback" decision for
    Plan 23-06's mobile-OAuth tests.
    """
    sentinel_jwks = {"keys": [{"kid": "spike-a2-sentinel", "kty": "RSA"}]}
    v1_route = respx.get(_GOOGLE_V1_CERTS_URL).mock(
        return_value=httpx.Response(200, json=sentinel_jwks)
    )
    v3_route = respx.get(_GOOGLE_V3_CERTS_URL).mock(
        return_value=httpx.Response(200, json=sentinel_jwks)
    )

    request = _gauth_ga_requests.Request()

    actual_payload: dict | None = None
    transport_error: Exception | None = None
    try:
        # _fetch_certs is the single network seam in verify_token's path.
        # Calling it directly bypasses the rest of verify_token (which
        # would also need a valid signed token + matching keys) and
        # isolates the question to: did respx see this HTTP call?
        actual_payload = _google_id_token._fetch_certs(
            request, _GOOGLE_V1_CERTS_URL
        )
    except Exception as exc:  # network errors are acceptable — see below
        transport_error = exc

    assert not v1_route.called, (
        "UNEXPECTED: respx intercepted google-auth's v1 PEM-certs "
        "fetch. This means google-auth has switched its transport to "
        "httpx (or respx has gained requests-lib coverage). Plan 23-06 "
        "test scaffold should be re-evaluated — switch to respx.mock "
        "JWKS stub pattern."
    )
    assert not v3_route.called, (
        "UNEXPECTED: respx intercepted google-auth's v3 JWK-certs fetch."
    )

    # The fetch either succeeded against the real Google endpoint OR
    # failed with a network error. EITHER outcome confirms respx did
    # NOT short-circuit the call. What we want to rule out is "respx
    # returned our sentinel payload" — that would mean respx DID
    # intercept and the (A) branch is live.
    if actual_payload is not None:
        assert actual_payload != sentinel_jwks, (
            "respx-stub payload was returned despite v1_route.called "
            "being False — this should be impossible. Investigate."
        )

    # If we got here without surfacing the sentinel, outcome=B is
    # confirmed: respx does not intercept google-auth's HTTP boundary,
    # and Plan 23-06 should use monkeypatching of _fetch_certs (per
    # spike A1's pattern) for its mobile-OAuth tests.
    # Either succeeded (real Google response — fine) or raised
    # (offline / DNS / TLS failure — also fine for the spike's claim).
    _ = transport_error  # used only for human-readable trace if needed


@pytest.mark.asyncio
@respx.mock
async def test_respx_does_intercept_httpx_calls_for_control():
    """Control test: confirm respx IS active and DOES intercept httpx
    calls in this same test process. Without this control, the previous
    test's "not v1_route.called" could be a respx wiring failure rather
    than a stack-layer mismatch.
    """
    expected = {"keys": [{"kid": "control-test"}]}
    route = respx.get(_GOOGLE_V3_CERTS_URL).mock(
        return_value=httpx.Response(200, json=expected)
    )

    async with httpx.AsyncClient() as client:
        response = await client.get(_GOOGLE_V3_CERTS_URL)

    assert route.called, (
        "respx did NOT intercept a direct httpx.AsyncClient call — "
        "respx wiring is broken in this environment, NOT a stack-layer "
        "mismatch. Investigate before drawing A2 conclusions."
    )
    assert response.status_code == 200
    assert response.json() == expected


# OUTCOME (filled in by executor after running):
#   respx intercepts google-auth's transport.requests.Request fetch: NO
#   Reason: google.auth.transport.requests.Request uses the `requests`
#     library under the hood; respx is httpx-only — different HTTP
#     stacks, no shared seam. The control test confirms respx wiring
#     is functional in this environment, isolating the result to a
#     genuine stack-layer mismatch (not a config error).
#   Mobile-OAuth test scaffold for Plan 23-06: use the monkeypatch
#     _fetch_certs pattern from spike A1 (test_google_auth_multi_audience.py).
#     Skip respx for the JWKS-fetch boundary; reserve respx for the
#     GitHub /user + /user/emails endpoints (which the existing
#     respx_oauth_providers fixture already mocks via httpx-based
#     authlib calls — that path stays compatible).
