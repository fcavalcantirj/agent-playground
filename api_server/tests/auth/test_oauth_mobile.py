"""Phase 23-06: mobile-OAuth credential-exchange endpoints + helpers.

This file covers the D-30 9-cell coverage matrix for
``POST /v1/auth/google/mobile`` and ``POST /v1/auth/github/mobile``:

  Google (5 cells):
    * happy-path             — valid JWT → 200 + session
    * invalid-signature      — wrong key → 401
    * expired                — exp in past → 401
    * audience-mismatch      — aud not in mobile_client_ids → 401
    * missing-claims         — no email or no sub → 401

  GitHub (3 cells):
    * public-email           — /user returns email → 200 + session
    * private-email          — /user email null → /user/emails fallback → 200
    * invalid-token          — /user 401 → 401 envelope

  Cookie-continuity (1 cell):
    * mobile sign-in → ``Cookie: ap_session=<uuid>`` →
      GET /v1/users/me returns the same user (D-17 verification)

JWKS-mocking strategy (per Plan 23-01 Task 3 OUTCOME):
  Spike A2 empirically proved respx does NOT intercept google-auth's
  requests-based transport. We monkeypatch
  ``google.oauth2.id_token._fetch_certs`` directly (the same seam used in
  the A1 Wave-0 spike). This lets us exercise the production
  ``verify_google_id_token`` helper end-to-end against real JWT
  cryptography without going through googleapis.com.

GitHub HTTP mocking uses respx (httpx-based, intercepts cleanly per
spike A2's control test).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging

import httpx
import pytest
import respx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt as _gauth_crypt
from google.auth import jwt as _gauth_jwt
from google.oauth2 import id_token as _google_id_token

pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# JWT/JWKS helpers — copied from tests/spikes/test_google_auth_multi_audience.py
# (TODO: extract to tests/auth/_jwt_helpers.py once the third caller appears.)
# ---------------------------------------------------------------------------


def _generate_keypair_and_cert() -> tuple[rsa.RSAPrivateKey, bytes]:
    """Mint a fresh RSA-2048 keypair + self-signed PEM x509 cert.

    google.auth.jwt.decode (the verify path google-auth uses with the v1
    PEM certs URL) accepts a Mapping[kid -> pem_bytes] for cert lookup.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "phase23-06.example")]
    )
    now = _dt.datetime.now(tz=_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=1))
        .not_valid_after(now + _dt.timedelta(hours=1))
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return private_key, cert_pem


def _mint_id_token(
    private_key: rsa.RSAPrivateKey,
    *,
    aud: str,
    kid: str,
    sub: str | None = "mobile-sub-1",
    email: str | None = "mobile@test.example",
    name: str | None = "Mobile User",
    picture: str | None = None,
    exp_offset_seconds: int = 3600,
    iss: str = "https://accounts.google.com",
) -> bytes:
    """Mint an RS256-signed ID token with the requested claims.

    ``sub`` / ``email`` may be set to ``None`` to omit the claim entirely
    — the missing-claims test cell uses this to drive the route's
    "missing required claims" 401 path.
    """
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    signer = _gauth_crypt.RSASigner.from_string(private_key_pem, key_id=kid)
    now = int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp())
    payload: dict = {
        "iss": iss,
        "aud": aud,
        "iat": now,
        "exp": now + exp_offset_seconds,
    }
    if sub is not None:
        payload["sub"] = sub
    if email is not None:
        payload["email"] = email
        payload["email_verified"] = True
    if name is not None:
        payload["name"] = name
    if picture is not None:
        payload["picture"] = picture
    return _gauth_jwt.encode(signer, payload)


def _install_jwks_monkeypatch(monkeypatch, certs_mapping: dict) -> None:
    """Redirect google-auth's ``_fetch_certs`` to return our in-memory PEM
    cert mapping. Plan 23-01 Task 3 (spike A2) confirmed respx does NOT
    intercept google-auth's transport — this is the production seam.
    """
    monkeypatch.setattr(
        _google_id_token,
        "_fetch_certs",
        lambda request, certs_url: certs_mapping,
    )


# ---------------------------------------------------------------------------
# Task 1 RED: helper imports — these MUST exist on auth/oauth.py
# ---------------------------------------------------------------------------


def test_helpers_exist_on_auth_oauth_module():
    """RED gate for Task 1 helpers. Imports must succeed and both helpers
    must be coroutine functions."""
    import inspect

    from api_server.auth.oauth import (
        verify_github_access_token,
        verify_google_id_token,
    )

    assert inspect.iscoroutinefunction(verify_google_id_token)
    assert inspect.iscoroutinefunction(verify_github_access_token)


# ---------------------------------------------------------------------------
# Task 2 RED: route handlers exist + return 401 with Stripe envelope on
# the easiest negative path (empty/missing token surface). Full 9-cell
# matrix in the rest of this file (Task 4).
# ---------------------------------------------------------------------------


def test_google_mobile_and_github_mobile_route_handlers_importable():
    """RED gate for Task 2 — both handlers must be coroutine functions
    exported from api_server.routes.auth."""
    import inspect

    from api_server.routes.auth import github_mobile, google_mobile

    assert inspect.iscoroutinefunction(google_mobile)
    assert inspect.iscoroutinefunction(github_mobile)


async def test_google_mobile_rejects_empty_id_token_with_422(async_client):
    """Pydantic Field(min_length=1) on id_token rejects empty string at
    the boundary (T-23-V5-EMPTY-TOKEN mitigation). FastAPI returns 422
    for body validation failures — this is BEFORE our 401 handler."""
    r = await async_client.post(
        "/v1/auth/google/mobile",
        json={"id_token": ""},
    )
    assert r.status_code == 422, r.text


async def test_github_mobile_rejects_empty_access_token_with_422(async_client):
    """Same boundary check for GitHub mobile."""
    r = await async_client.post(
        "/v1/auth/github/mobile",
        json={"access_token": ""},
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Task 4: D-30 9-cell coverage matrix
# ---------------------------------------------------------------------------
#
# Test naming convention satisfies the plan's acceptance grep:
#   * test_google_happy_*           (1 cell)
#   * test_google_invalid_*         (1 cell — invalid signature)
#   * test_google_expired_*         (1 cell)
#   * test_google_audience_*        (1 cell — audience-mismatch)
#   * test_google_missing_*         (1 cell — missing-claims)
#   * test_github_public_*          (1 cell — email present on /user)
#   * test_github_private_*         (1 cell — falls back to /user/emails)
#   * test_github_invalid_*         (1 cell — /user returns 401)
#   * test_mobile_cookie_*          (1 cell — D-17 end-to-end via fixture)


# Test audiences — Android + iOS pair to match D-23's expected production
# shape (settings.oauth_google_mobile_client_ids = list[str]).
_TEST_AUD_ANDROID = "phase23-test-android.apps.googleusercontent.com"
_TEST_AUD_IOS = "phase23-test-ios.apps.googleusercontent.com"
_TEST_KID = "phase23-test-kid"


def _patch_settings_audiences(async_client, monkeypatch, audiences):
    """Helper — patch app.state.settings.oauth_google_mobile_client_ids
    on the running FastAPI app under test."""
    app = async_client._transport.app  # type: ignore[attr-defined]
    monkeypatch.setattr(
        app.state.settings,
        "oauth_google_mobile_client_ids",
        list(audiences),
    )


# --- Google: 5 cells -------------------------------------------------------


async def test_google_happy_path_returns_session_and_user(
    async_client, db_pool, monkeypatch,
):
    """Cell 1/5: valid JWT (correct aud, valid signature, future exp,
    sub + email present) → 200 + {session_id, expires_at, user};
    sessions row + users row both land in Postgres.
    """
    private_key, cert_pem = _generate_keypair_and_cert()
    _patch_settings_audiences(
        async_client, monkeypatch, [_TEST_AUD_ANDROID, _TEST_AUD_IOS],
    )
    _install_jwks_monkeypatch(monkeypatch, {_TEST_KID: cert_pem})

    # Mint with the SECOND audience (iOS) — exercises Wave-0 spike A1's
    # multi-aud guarantee that match works on non-first list entries.
    token = _mint_id_token(
        private_key,
        aud=_TEST_AUD_IOS,
        kid=_TEST_KID,
        sub="g-happy-sub",
        email="alice-mobile@test.example",
        name="Alice Mobile",
        picture="https://example.com/alice.png",
    )
    r = await async_client.post(
        "/v1/auth/google/mobile",
        json={"id_token": token.decode("ascii")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "session_id" in body, body
    assert "expires_at" in body, body
    assert body["user"]["email"] == "alice-mobile@test.example"
    assert body["user"]["display_name"] == "Alice Mobile"
    assert body["user"]["provider"] == "google"
    assert body["user"]["avatar_url"] == "https://example.com/alice.png"
    # No Set-Cookie header — mobile responses do NOT call _set_session_cookie.
    assert "set-cookie" not in {k.lower() for k in r.headers.keys()}, r.headers

    # DB-level assertions: users row + sessions row landed.
    from uuid import UUID
    async with db_pool.acquire() as conn:
        sess_row = await conn.fetchrow(
            "SELECT id, user_id, expires_at FROM sessions WHERE id = $1",
            UUID(body["session_id"]),
        )
        assert sess_row is not None
        user_row = await conn.fetchrow(
            "SELECT id, email, display_name, provider FROM users "
            "WHERE provider = 'google' AND sub = 'g-happy-sub'"
        )
        assert user_row is not None
        assert str(user_row["id"]) == body["user"]["id"]
        assert user_row["email"] == "alice-mobile@test.example"


async def test_google_invalid_signature_returns_401(async_client, monkeypatch):
    """Cell 2/5: JWT signed with a key whose public half is NOT in our
    JWKS mapping → 401 envelope param='id_token'.
    """
    pk_attacker, _ = _generate_keypair_and_cert()
    pk_real, cert_pem_real = _generate_keypair_and_cert()  # different key
    _patch_settings_audiences(
        async_client, monkeypatch, [_TEST_AUD_ANDROID],
    )
    # Install JWKS for the REAL key only — the attacker's key won't match.
    _install_jwks_monkeypatch(monkeypatch, {_TEST_KID: cert_pem_real})

    token = _mint_id_token(
        pk_attacker,
        aud=_TEST_AUD_ANDROID,
        kid=_TEST_KID,  # same kid → google-auth looks up real cert; signature mismatch
        sub="g-attacker-sub",
        email="attacker@example.com",
    )
    r = await async_client.post(
        "/v1/auth/google/mobile",
        json={"id_token": token.decode("ascii")},
    )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["param"] == "id_token", body


async def test_google_expired_returns_401(async_client, monkeypatch):
    """Cell 3/5: JWT with exp ~1h in the past → 401 envelope.
    """
    private_key, cert_pem = _generate_keypair_and_cert()
    _patch_settings_audiences(
        async_client, monkeypatch, [_TEST_AUD_ANDROID],
    )
    _install_jwks_monkeypatch(monkeypatch, {_TEST_KID: cert_pem})

    # exp_offset_seconds=-3600 → exp is 1 hour in the past
    token = _mint_id_token(
        private_key,
        aud=_TEST_AUD_ANDROID,
        kid=_TEST_KID,
        sub="g-expired-sub",
        email="expired@test.example",
        exp_offset_seconds=-3600,
    )
    r = await async_client.post(
        "/v1/auth/google/mobile",
        json={"id_token": token.decode("ascii")},
    )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["param"] == "id_token", body


async def test_google_audience_mismatch_returns_401(async_client, monkeypatch):
    """Cell 4/5: JWT with aud not in mobile_client_ids → 401 envelope.

    Critical mitigation for T-23-AUD-CONFUSION (id_token issued for some
    other app re-used against our app).
    """
    private_key, cert_pem = _generate_keypair_and_cert()
    # Settings only allow Android + iOS — mint with a third client.
    _patch_settings_audiences(
        async_client, monkeypatch, [_TEST_AUD_ANDROID, _TEST_AUD_IOS],
    )
    _install_jwks_monkeypatch(monkeypatch, {_TEST_KID: cert_pem})

    token = _mint_id_token(
        private_key,
        aud="other-app.apps.googleusercontent.com",  # not in settings list
        kid=_TEST_KID,
        sub="g-aud-mismatch-sub",
        email="other@example.com",
    )
    r = await async_client.post(
        "/v1/auth/google/mobile",
        json={"id_token": token.decode("ascii")},
    )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["param"] == "id_token", body


async def test_google_missing_claims_returns_401(async_client, monkeypatch):
    """Cell 5/5: JWT signed correctly but with no ``email`` claim → 401
    via the route-level "missing required claims" gate.

    The route checks ``claims.get("sub")`` and ``claims.get("email")``
    AFTER verify_oauth2_token returns; so a valid-but-incomplete JWT
    should still be rejected.
    """
    private_key, cert_pem = _generate_keypair_and_cert()
    _patch_settings_audiences(
        async_client, monkeypatch, [_TEST_AUD_ANDROID],
    )
    _install_jwks_monkeypatch(monkeypatch, {_TEST_KID: cert_pem})

    token = _mint_id_token(
        private_key,
        aud=_TEST_AUD_ANDROID,
        kid=_TEST_KID,
        sub="g-no-email-sub",
        email=None,  # omit email entirely
    )
    r = await async_client.post(
        "/v1/auth/google/mobile",
        json={"id_token": token.decode("ascii")},
    )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["param"] == "id_token", body
    # The route's gate emits a specific message for this case.
    assert "missing required claims" in body["error"]["message"].lower(), body


# --- GitHub: 3 cells -------------------------------------------------------


async def test_github_public_email_returns_session(async_client, db_pool):
    """Cell 6/9: /user returns a public email → single fetch, 200 + session.
    """
    with respx.mock(assert_all_called=False) as m:
        m.get("https://api.github.com/user").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 4242,
                    "login": "ghuser-mobile",
                    "name": "GH Mobile User",
                    "email": "pub-mobile@example.com",
                    "avatar_url": "https://avatars.example.com/4242",
                },
            )
        )
        r = await async_client.post(
            "/v1/auth/github/mobile",
            json={"access_token": "valid-public-token"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "pub-mobile@example.com"
    assert body["user"]["display_name"] == "GH Mobile User"
    assert body["user"]["provider"] == "github"
    assert "session_id" in body
    # No Set-Cookie on mobile responses.
    assert "set-cookie" not in {k.lower() for k in r.headers.keys()}, r.headers

    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT id, email, provider FROM users "
            "WHERE provider = 'github' AND sub = '4242'"
        )
        assert user_row is not None
        assert user_row["email"] == "pub-mobile@example.com"


async def test_github_private_email_falls_back_to_emails_endpoint(
    async_client, db_pool,
):
    """Cell 7/9: /user email is null (user set primary email private) →
    /user/emails fallback picks first primary+verified entry.
    """
    with respx.mock(assert_all_called=False) as m:
        m.get("https://api.github.com/user").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 7777,
                    "login": "private-mobile",
                    "name": "Private Mobile",
                    "email": None,
                    "avatar_url": None,
                },
            )
        )
        m.get("https://api.github.com/user/emails").mock(
            return_value=httpx.Response(
                200,
                json=[
                    # NOTE: order matters — the helper picks the FIRST
                    # primary+verified entry. We put a non-primary verified
                    # entry first to confirm the filter is correct.
                    {
                        "email": "non-primary-verified@example.com",
                        "primary": False,
                        "verified": True,
                    },
                    {
                        "email": "priv-mobile@example.com",
                        "primary": True,
                        "verified": True,
                    },
                ],
            )
        )
        r = await async_client.post(
            "/v1/auth/github/mobile",
            json={"access_token": "valid-private-token"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "priv-mobile@example.com", body

    async with db_pool.acquire() as conn:
        user_row = await conn.fetchrow(
            "SELECT email FROM users WHERE provider = 'github' AND sub = '7777'"
        )
        assert user_row is not None
        assert user_row["email"] == "priv-mobile@example.com"


async def test_github_invalid_token_returns_401(async_client):
    """Cell 8/9: /user returns 401 → endpoint returns 401 envelope
    param='access_token'.
    """
    with respx.mock(assert_all_called=False) as m:
        m.get("https://api.github.com/user").mock(
            return_value=httpx.Response(401, json={"message": "Bad credentials"})
        )
        r = await async_client.post(
            "/v1/auth/github/mobile",
            json={"access_token": "bad-token"},
        )
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["param"] == "access_token", body


# --- Cookie continuity: 1 cell --------------------------------------------


async def test_mobile_cookie_header_grants_authenticated_session(
    async_client, authenticated_mobile_session,
):
    """Cell 9/9 — D-17 end-to-end verification.

    Sign in via POST /v1/auth/google/mobile (the fixture does this);
    capture the returned session_id; then send it back as
    ``Cookie: ap_session=<uuid>`` on a subsequent request to
    /v1/users/me. ApSessionMiddleware must resolve the user
    transparently — proving the cookie-continuity contract that lets
    the Flutter app store the session_id and keep using it.
    """
    r = await async_client.get(
        "/v1/users/me",
        headers={"Cookie": authenticated_mobile_session["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == authenticated_mobile_session["_user_id"], body
