# Spike 02 — age passphrase + HKDF per-user KEK

**Date:** 2026-04-18
**Plan affected:** 22-02 (postgres migration + age crypto)
**Verdict:** PASS with minor plan delta

## Probe

Inside `deploy-api_server-1` container (Python 3.11):

```python
import pyrage
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

MASTER = b'test-master-key-32-bytes-exactly!'
def user_kek_hex(uid):
    kdf = HKDF(algorithm=hashes.SHA256(), length=32,
               salt=uid.encode(), info=b'channel-cred')
    return kdf.derive(MASTER).hex()

ka = user_kek_hex('user-a')
ct = pyrage.passphrase.encrypt(b'bot_token_abc', ka)
pt = pyrage.passphrase.decrypt(ct, ka)     # OK
kb = user_kek_hex('user-b')
pyrage.passphrase.decrypt(ct, kb)           # must raise
```

## Actual output

```
ciphertext len: 195
A->A decrypt OK
A->B denied OK: DecryptError Decryption failed
```

## Verdict: PASS

- pyrage works in the api_server image (Python 3.11-slim base)
- HKDF per-user KEK via `cryptography` library gives deterministic isolation
- Cross-user decrypt raises `pyrage.DecryptError` (catchable)

## Plan delta (minor)

Plan 22-02's API call examples reference `pyrage.passphrase.Recipient.from_str(...)` and `pyrage.passphrase.Identity.from_str(...)` — **those don't exist**.

Actual `pyrage.passphrase` surface: just `encrypt(data, passphrase_str)` and `decrypt(data, passphrase_str)`. Correct idiom for the plan:

```python
# encrypt
ct = pyrage.passphrase.encrypt(plaintext, user_kek_hex)
# decrypt
pt = pyrage.passphrase.decrypt(ciphertext, user_kek_hex)
```

Plan 22-02's Task 2 needs this one-line correction. No structural change.

## Dependencies surfaced

- `cryptography` library required (used for HKDF). Not in current image; plan must add it to `requirements.txt` or `pyproject.toml`.
- `pyrage` also must land in deps (probe `pip installed` it inline; prod build needs it baked).
- Dockerfile rebuild required for both new deps.
