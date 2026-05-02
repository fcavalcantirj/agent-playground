"""Auth-test-local fixtures (Phase 23-06).

Adds ``authenticated_mobile_session`` — the mobile-flavored analog of
``authenticated_cookie`` from ``tests/conftest.py``. Where the latter
seeds rows directly via asyncpg, this fixture exercises the production
path end-to-end: it mints a real RS256-signed JWT, monkeypatches
``_fetch_certs`` (per A2 spike outcome — respx does NOT intercept
google-auth's transport), and POSTs to ``/v1/auth/google/mobile``,
yielding the resulting session_id wrapped as a ``Cookie:`` header for
subsequent requests.

JWT/JWKS minting helpers are duplicated from
``tests/spikes/test_google_auth_multi_audience.py`` (and from the
sibling ``test_oauth_mobile.py`` test module). When a third caller
appears, extract them to ``tests/auth/_jwt_helpers.py``. For now the
duplication is intentional MVP scope — the helpers are short and the
spike file's stability depends on its own self-contained shape.
"""
from __future__ import annotations

import datetime as _dt

import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt as _gauth_crypt
from google.auth import jwt as _gauth_jwt
from google.oauth2 import id_token as _google_id_token

_FIXTURE_AUD = "phase23-06-fixture.apps.googleusercontent.com"
_FIXTURE_KID = "phase23-06-fixture-kid"


def _generate_keypair_and_cert() -> tuple[rsa.RSAPrivateKey, bytes]:
    """Mint a fresh RSA-2048 keypair + self-signed PEM x509 cert (PEM mode)."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "phase23-06-fixture.example")]
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
    aud: str = _FIXTURE_AUD,
    kid: str = _FIXTURE_KID,
    sub: str = "fixture-mobile-sub",
    email: str = "fixture-mobile@test.example",
    name: str = "Fixture Mobile User",
) -> bytes:
    """Mint an RS256-signed Google-shaped ID token for the fixture path."""
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    signer = _gauth_crypt.RSASigner.from_string(private_key_pem, key_id=kid)
    now = int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp())
    payload = {
        "iss": "https://accounts.google.com",
        "aud": aud,
        "sub": sub,
        "email": email,
        "email_verified": True,
        "name": name,
        "iat": now,
        "exp": now + 3600,
    }
    return _gauth_jwt.encode(signer, payload)


@pytest_asyncio.fixture
async def authenticated_mobile_session(async_client, monkeypatch):
    """Mobile-flavored sign-in fixture — analog of ``authenticated_cookie``.

    Drives the full production code path:

      1. Mint a fresh RSA-2048 keypair + self-signed PEM cert.
      2. Mint an RS256-signed JWT with ``aud =``
         ``phase23-06-fixture.apps.googleusercontent.com``.
      3. Monkeypatch
         ``app.state.settings.oauth_google_mobile_client_ids`` to include
         the fixture audience (so verify_oauth2_token accepts it).
      4. Monkeypatch ``google.oauth2.id_token._fetch_certs`` to return
         our in-memory PEM cert mapping (per Plan 23-01 Task 3 OUTCOME —
         respx does NOT intercept google-auth's requests-based transport).
      5. POST to ``/v1/auth/google/mobile``; assert 200.
      6. Yield ``{Cookie, _user_id, _session_id}`` — same shape as
         ``authenticated_cookie`` so callers can pass
         ``headers={"Cookie": fixture["Cookie"]}`` to httpx and let
         ``ApSessionMiddleware`` resolve the user transparently (D-17
         end-to-end verification).
    """
    private_key, cert_pem = _generate_keypair_and_cert()
    certs_mapping = {_FIXTURE_KID: cert_pem}

    # 3. patch settings on the running app — read it from
    # async_client._transport.app. The shared async_client fixture in
    # tests/conftest.py does NOT export ._app (started_api_server does);
    # we get the same FastAPI instance via the transport's .app attribute.
    app = async_client._transport.app  # type: ignore[attr-defined]
    monkeypatch.setattr(
        app.state.settings,
        "oauth_google_mobile_client_ids",
        [_FIXTURE_AUD],
    )

    # 4. patch JWKS fetch
    monkeypatch.setattr(
        _google_id_token,
        "_fetch_certs",
        lambda request, certs_url: certs_mapping,
    )

    # 5. mint + POST
    token = _mint_id_token(private_key)
    r = await async_client.post(
        "/v1/auth/google/mobile",
        json={"id_token": token.decode("ascii")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    session_id = body["session_id"]
    user_id = body["user"]["id"]

    yield {
        "Cookie": f"ap_session={session_id}",
        "_user_id": user_id,
        "_session_id": session_id,
    }
