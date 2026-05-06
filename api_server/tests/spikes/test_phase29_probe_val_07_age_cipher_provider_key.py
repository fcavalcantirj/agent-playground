"""PROBE-VAL-07 — age-cipher round-trip + per-user KEK isolation.

Validates that `crypto/age_cipher.py` (existing primitive) suffices
for Phase 29's `agent_containers.provider_key_enc` storage:
  - encrypt + decrypt round-trip preserves the dict
  - cross-user decrypt RAISES (per-user KEK isolation)
  - dev fallback (no AP_CHANNEL_MASTER_KEY env) works
  - ciphertext byte length + entropy recorded

Cost: zero (no network).
"""
from __future__ import annotations

import os
from collections import Counter
from math import log2
from pathlib import Path
from uuid import UUID, uuid4

import pyrage
import pytest

pytestmark = [pytest.mark.spike, pytest.mark.api_integration]

WORKTREE_ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = (
    WORKTREE_ROOT / ".planning" / "phases" / "29-llm-egress-proxy" / "spikes"
)
ARTIFACT_PATH = ARTIFACT_DIR / "PROBE-VAL-07.md"


def _write_artifact(path: Path, body: str, verdict: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {path.stem}\n\n{body}\n\nVERDICT: {verdict}\n")


def _shannon_entropy(b: bytes) -> float:
    counts = Counter(b)
    total = len(b)
    if total == 0:
        return 0.0
    return -sum(
        (c / total) * log2(c / total) for c in counts.values() if c > 0
    )


def test_age_cipher_round_trip_and_isolation() -> None:
    # Force the dev fallback path (no master key env). The cipher's
    # _master_key() returns 32 zero bytes which still produces a valid
    # KEK via HKDF.
    os.environ.pop("AP_CHANNEL_MASTER_KEY", None)
    os.environ["AP_ENV"] = "dev"

    from api_server.crypto.age_cipher import (  # type: ignore
        decrypt_channel_config,
        encrypt_channel_config,
    )

    artifact_lines: list[str] = [
        "## PROBE-VAL-07: age-cipher round-trip + cross-user-isolation",
        "",
    ]

    user_a = uuid4()
    user_b = uuid4()
    plaintext_dict = {
        "key": "or-test-deadbeef" * 4,  # mock 64-char OR-style key
        "provider": "openrouter",
        "rotated_at": "2026-05-06T00:00:00Z",
    }

    # Round-trip
    ciphertext = encrypt_channel_config(user_a, plaintext_dict)
    decrypted = decrypt_channel_config(user_a, ciphertext)
    round_trip_ok = decrypted == plaintext_dict

    artifact_lines.append("### Round-trip (user A encrypts → user A decrypts)")
    artifact_lines.append(f"- ciphertext bytes length: {len(ciphertext)}")
    # Don't print the raw ciphertext; just shape + entropy
    entropy = _shannon_entropy(ciphertext)
    artifact_lines.append(f"- shannon entropy (bits/byte): {entropy:.3f} (expected ~7.5+ for ciphertext)")
    artifact_lines.append(f"- ciphertext begins with: `{ciphertext[:16]!r}` (age framing)")
    artifact_lines.append(f"- round-trip preserved dict: **{round_trip_ok}**")
    artifact_lines.append("")

    # Cross-user isolation
    cross_user_raised = False
    cross_user_exc_type = ""
    try:
        decrypt_channel_config(user_b, ciphertext)
    except pyrage.DecryptError as exc:
        cross_user_raised = True
        cross_user_exc_type = type(exc).__name__
    except Exception as exc:  # noqa: BLE001 — capture any exception
        cross_user_raised = True
        cross_user_exc_type = type(exc).__name__

    artifact_lines.append("### Cross-user-isolation (user A's ciphertext, user B's KEK)")
    artifact_lines.append(f"- user A: {user_a}")
    artifact_lines.append(f"- user B: {user_b}")
    artifact_lines.append(f"- decrypt raised: **{cross_user_raised}** (`{cross_user_exc_type}`)")
    artifact_lines.append("")

    # Dev fallback path verified by completing the round-trip with no
    # AP_CHANNEL_MASTER_KEY in env (we popped it above). The fact that
    # round_trip_ok is True with no master key is the proof.
    artifact_lines.append("### Dev fallback (no AP_CHANNEL_MASTER_KEY env)")
    artifact_lines.append(f"- AP_CHANNEL_MASTER_KEY in env: **{'AP_CHANNEL_MASTER_KEY' in os.environ}**")
    artifact_lines.append(f"- Round-trip nevertheless succeeded: **{round_trip_ok}** (32-zero-byte fallback works)")
    artifact_lines.append("")

    artifact_lines.append("### Verdict reasoning")
    artifact_lines.append(f"- round-trip ok: **{round_trip_ok}**")
    artifact_lines.append(f"- cross-user-isolation enforced: **{cross_user_raised}**")
    artifact_lines.append(f"- dev fallback works without AP_CHANNEL_MASTER_KEY: **{round_trip_ok}**")
    artifact_lines.append("")
    artifact_lines.append(
        "### Implication for Plan 29-04 (provider_key_enc storage)"
    )
    artifact_lines.append(
        "- The existing `crypto.age_cipher.{encrypt,decrypt}_channel_config(user_id, dict)` "
        "primitive can be reused verbatim for Phase 29's `agent_containers.provider_key_enc` "
        "BYTEA column. Per-user KEK isolation is enforced by HKDF-SHA256(master_key, info=ap-ch-||user_id_bytes) "
        "→ each user's encrypted blob is undecryptable by any other user. This satisfies T-29-02 "
        "(cross-tenant key disclosure) without writing new crypto."
    )

    verdict = "PASS" if (round_trip_ok and cross_user_raised) else "FAIL"
    _write_artifact(ARTIFACT_PATH, "\n".join(artifact_lines), verdict)
    assert verdict == "PASS", (
        f"round_trip={round_trip_ok} cross_user_raised={cross_user_raised}"
    )
