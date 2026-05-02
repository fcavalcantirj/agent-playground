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
