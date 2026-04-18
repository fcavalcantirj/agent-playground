"""age-based symmetric encryption for channel credentials at rest.

BYOK invariant: bot tokens, Telegram allowed-user IDs, and any future
channel-secret field arrive in a POST body, are held in memory for the
duration of the request, and are then either:
  (a) streamed into the container via --env-file (runner path — plaintext
      in RAM, 600-perm file, unlinked post-read), OR
  (b) persisted to ``agent_containers.channel_config_enc`` as an age-
      encrypted blob keyed by a per-user KEK derived from the server
      master key + user_id (this module).

Master key lives in env ``AP_CHANNEL_MASTER_KEY`` (32 bytes, base64).
It MUST be rotated via a dedicated re-encrypt migration; it MUST NOT
be logged. On boot the server fails loud if the env is missing AND
``AP_ENV=prod`` (matches the existing env convention in
``api_server/src/api_server/config.py``).

Per-user KEK derivation: HKDF-SHA256 over master_key with
``info=b'ap-ch-' + user_id.bytes`` — deterministic so the same user
can decrypt what they encrypted, but every user gets a distinct KEK.
The age cipher then uses the KEK (base64) as a passphrase. pyrage's
``pyrage.passphrase.{encrypt, decrypt}`` is the documented age CLI
equivalent; x25519 identities are overkill for the threat model here
(DB exfil, not key custody).

SPIKE EVIDENCE:
- ``22-SPIKES/spike-01-pyrage-install.md`` — pyrage wheel installs
  cleanly on python:3.11-slim inside the api_server image.
- ``22-SPIKES/spike-02-age-hkdf.md`` — per-user KEK isolation proven:
  user A encrypts, user B's KEK raises ``pyrage.DecryptError``.

Gotcha absorbed from spike-02: there is NO ``Recipient.from_str`` or
``Identity.from_str`` on ``pyrage.passphrase``. The surface is just
``encrypt(data: bytes, passphrase: str) -> bytes`` and
``decrypt(data: bytes, passphrase: str) -> bytes``.
"""
from __future__ import annotations

import base64
import json
import os
from uuid import UUID

import pyrage
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def _master_key() -> bytes:
    """Load AP_CHANNEL_MASTER_KEY from env; enforce 32-byte base64.

    Production (``AP_ENV=prod``) fails loud if the env is missing; dev
    falls back to a deterministic 32-zero-byte key so local tests round-
    trip without ops setup. The fallback is NEVER to ship to prod.
    """
    raw = os.environ.get("AP_CHANNEL_MASTER_KEY")
    env = os.environ.get("AP_ENV", "dev")
    if not raw:
        if env == "prod":
            raise RuntimeError(
                "AP_CHANNEL_MASTER_KEY required when AP_ENV=prod"
            )
        # Deterministic dev fallback — 32 zero bytes. NEVER ship this in prod.
        return b"\x00" * 32
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:  # invalid b64
        raise RuntimeError(
            "AP_CHANNEL_MASTER_KEY must be valid base64"
        ) from exc
    if len(key) != 32:
        raise RuntimeError(
            "AP_CHANNEL_MASTER_KEY must be 32 bytes (base64-encoded)"
        )
    return key


def _derive_kek(user_id: UUID) -> bytes:
    """HKDF-SHA256 derive a 32-byte per-user KEK.

    ``info`` binds the KEK to both the purpose (``ap-ch-``) and the
    user's UUID bytes so the same master key can serve multiple
    subsystems + multiple users without collision.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"ap-ch-" + user_id.bytes,
    )
    return hkdf.derive(_master_key())


def encrypt_channel_config(user_id: UUID, config: dict) -> bytes:
    """Encrypt a channel config dict (tokens + metadata) for at-rest storage.

    The returned blob is suitable for writing straight into
    ``agent_containers.channel_config_enc`` (BYTEA column). Ciphertext
    is non-deterministic (random nonce inside pyrage); round-trip tests
    must compare via decrypt, not byte equality.
    """
    kek = _derive_kek(user_id)
    passphrase = base64.b64encode(kek).decode("ascii")
    plaintext = json.dumps(config, separators=(",", ":")).encode("utf-8")
    return pyrage.passphrase.encrypt(plaintext, passphrase)


def decrypt_channel_config(user_id: UUID, ciphertext: bytes) -> dict:
    """Decrypt a stored channel config blob. Raises on MAC / KEK mismatch.

    Cross-user decrypt attempts raise ``pyrage.DecryptError`` because
    ``_derive_kek`` produces a distinct passphrase for every UUID.
    """
    kek = _derive_kek(user_id)
    passphrase = base64.b64encode(kek).decode("ascii")
    plaintext = pyrage.passphrase.decrypt(ciphertext, passphrase)
    return json.loads(plaintext.decode("utf-8"))
