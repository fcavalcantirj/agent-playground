"""SPIKE A1 (Wave 0) — google-auth verify_oauth2_token multi-audience.

Confirm ``google.oauth2.id_token.verify_oauth2_token(audience=[client_a,
client_b])`` accepts a JWT whose ``aud`` claim matches EITHER entry.

Why this spike: RESEARCH §A1 cites that ``verify_token``'s signature is
``audience: Union[str, list[str], None]`` and that ``verify_oauth2_token``
forwards verbatim — but the latter's docstring claims str-only. This spike
proves the runtime behavior and pins the contract Plan 23-06's mobile
endpoint depends on.

PASS criterion: ``verify_oauth2_token(token, request, audience=[A, B])``
returns the decoded claims when token's ``aud`` is B (the second list
entry); raises when token's ``aud`` is C (not in list).

Implementation strategy:
* Generate an RSA-2048 keypair in-memory + a self-signed PEM x.509 cert.
  ``google.auth.jwt.decode`` (the path google-auth uses by default with
  the v1 PEM certs URL) accepts a ``Mapping[kid, cert_pem]``.
* Mint a JWT signed with the private key using ``google.auth.crypt`` +
  ``google.auth.jwt.encode``. This avoids needing pyjwt, since
  ``id_token._GOOGLE_OAUTH2_CERTS_URL`` defaults to the v1 PEM endpoint
  (NOT the v3 JWK endpoint), so the verify path stays in
  ``google.auth.jwt.decode``.
* Monkeypatch ``google.oauth2.id_token._fetch_certs`` so it returns our
  in-memory PEM cert mapping instead of fetching from googleapis.com.
  This intercepts the HTTP boundary at the call site, which is the
  cleanest seam for this library (``_fetch_certs`` is called once
  immediately at the top of ``verify_token``).

The helper for JWT minting lives INLINE in the test file. Plan 23-06 will
build a similar (but production-shaped) helper in ``tests/auth/`` that
this spike's pattern informs.
"""
from __future__ import annotations

import datetime as _dt
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt as _gauth_crypt
from google.auth import jwt as _gauth_jwt
from google.auth.transport import requests as _gauth_ga_requests
from google.oauth2 import id_token as _google_id_token


# Test client IDs — the SECOND one is the audience the spike's "happy"
# JWT will claim, proving the multi-audience match works for non-first
# entries (the most likely silent-failure mode if verify_oauth2_token
# only honored the first list element).
_CLIENT_A = "client-a.apps.googleusercontent.com"
_CLIENT_B = "client-b.apps.googleusercontent.com"
_CLIENT_C = "client-c.apps.googleusercontent.com"
_KID = "spike-a1"


def _generate_keypair_and_cert() -> tuple[rsa.RSAPrivateKey, bytes]:
    """Return ``(private_key, cert_pem_bytes)`` where ``cert_pem_bytes``
    is the PEM-encoded self-signed x.509 cert wrapping the public half.
    google.auth.jwt.decode accepts PEM-format certs in this shape via
    its ``certs={kid: pem_bytes}`` mapping argument."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "spike-a1.example")]
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
    iss: str = "https://accounts.google.com",
    sub: str = "1234567890",
    email: str = "test@example.com",
) -> bytes:
    """Mint an RS256-signed ID token with the given audience claim.

    Uses ``google.auth.crypt.RSASigner`` + ``google.auth.jwt.encode`` so
    we don't need pyjwt; this matches the verifier's exact algorithm
    family and header kid expectation.
    """
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    signer = _gauth_crypt.RSASigner.from_string(private_key_pem, key_id=_KID)
    now = int(_dt.datetime.now(tz=_dt.timezone.utc).timestamp())
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "email": email,
        "email_verified": True,
        "iat": now,
        "exp": now + 3600,
    }
    token = _gauth_jwt.encode(signer, payload)
    # google.auth.jwt.encode returns bytes; verify_oauth2_token accepts
    # either str or bytes per its signature.
    return token


def test_verify_oauth2_token_accepts_list_audience_match_on_second_entry(
    monkeypatch,
):
    """Happy path: JWT's aud == second entry of the audience list passed
    to verify_oauth2_token. The call must succeed and return the decoded
    claims with aud == _CLIENT_B (proving the list iteration covers
    non-first entries, not just element 0)."""
    private_key, cert_pem = _generate_keypair_and_cert()
    certs_mapping = {_KID: cert_pem}

    # Intercept google-auth's HTTP fetch by monkeypatching _fetch_certs
    # directly. This is the cleanest seam: _fetch_certs is the only
    # place id_token.verify_token reaches the network in the PEM-format
    # path, and patching here means we don't need to mock urllib /
    # requests / httpx layers underneath. This is the SAME pattern
    # Plan 23-06's tests can fall back to if A2 (respx-PyJWK) shows
    # respx does NOT intercept google-auth's transport.
    monkeypatch.setattr(
        _google_id_token,
        "_fetch_certs",
        lambda request, certs_url: certs_mapping,
    )

    token = _mint_id_token(private_key, aud=_CLIENT_B)

    claims = _google_id_token.verify_oauth2_token(
        token,
        _gauth_ga_requests.Request(),
        audience=[_CLIENT_A, _CLIENT_B],
    )

    assert claims["aud"] == _CLIENT_B, claims
    assert claims["iss"] == "https://accounts.google.com"
    assert claims["sub"] == "1234567890"
    assert claims["email"] == "test@example.com"


def test_verify_oauth2_token_rejects_audience_not_in_list(monkeypatch):
    """Negative path: JWT's aud is _CLIENT_C, not in the audience list.
    verify_oauth2_token must raise (ValueError or GoogleAuthError —
    google-auth raises ValueError for aud mismatch in the PEM path).
    Proves audience verification is actually happening, not silently
    passing through."""
    private_key, cert_pem = _generate_keypair_and_cert()
    certs_mapping = {_KID: cert_pem}

    monkeypatch.setattr(
        _google_id_token,
        "_fetch_certs",
        lambda request, certs_url: certs_mapping,
    )

    token = _mint_id_token(private_key, aud=_CLIENT_C)

    with pytest.raises(Exception) as excinfo:
        _google_id_token.verify_oauth2_token(
            token,
            _gauth_ga_requests.Request(),
            audience=[_CLIENT_A, _CLIENT_B],
        )

    # Don't pin the exception class — google-auth's PEM path raises
    # ValueError, but the JWK-path branch may raise jwt.InvalidAudienceError.
    # What matters: the error message references the audience mismatch.
    msg = str(excinfo.value).lower()
    assert "audience" in msg or "aud" in msg, (
        f"expected audience-mismatch in error, got: {excinfo.value!r}"
    )


def test_helper_payload_round_trips(monkeypatch):
    """Sanity: the JWT minted by _mint_id_token decodes to the expected
    claims when run through google.auth.jwt.decode directly (no
    audience filter). Catches harness regressions where the keypair /
    cert / signer combination silently breaks before we even reach
    verify_oauth2_token."""
    private_key, cert_pem = _generate_keypair_and_cert()
    certs_mapping = {_KID: cert_pem}

    token = _mint_id_token(private_key, aud=_CLIENT_B)
    decoded = _gauth_jwt.decode(token, certs=certs_mapping, audience=None)

    assert decoded["aud"] == _CLIENT_B
    assert decoded["iss"] == "https://accounts.google.com"
    assert decoded["email"] == "test@example.com"

    # Also confirm the encoded token has the expected kid header — this
    # is what _fetch_certs / verify_token use to look up the cert.
    header_b64 = token.split(b".", 1)[0]
    # google.auth.jwt encodes URL-safe base64 without padding; pad for json
    pad = b"=" * (-len(header_b64) % 4)
    import base64

    header = json.loads(base64.urlsafe_b64decode(header_b64 + pad))
    assert header["kid"] == _KID
    assert header["alg"] == "RS256"
