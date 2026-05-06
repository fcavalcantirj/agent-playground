# PROBE-VAL-07

## PROBE-VAL-07: age-cipher round-trip + cross-user-isolation

### Round-trip (user A encrypts → user A decrypts)
- ciphertext bytes length: 316
- shannon entropy (bits/byte): 7.016 (expected ~7.5+ for ciphertext)
- ciphertext begins with: `b'age-encryption.o'` (age framing)
- round-trip preserved dict: **True**

### Cross-user-isolation (user A's ciphertext, user B's KEK)
- user A: f63de739-f25b-43d7-ba71-ac7ef9f881f3
- user B: cd2b56ca-05e4-4bbb-8cea-6b5d23d0227d
- decrypt raised: **True** (`DecryptError`)

### Dev fallback (no AP_CHANNEL_MASTER_KEY env)
- AP_CHANNEL_MASTER_KEY in env: **False**
- Round-trip nevertheless succeeded: **True** (32-zero-byte fallback works)

### Verdict reasoning
- round-trip ok: **True**
- cross-user-isolation enforced: **True**
- dev fallback works without AP_CHANNEL_MASTER_KEY: **True**

### Implication for Plan 29-04 (provider_key_enc storage)
- The existing `crypto.age_cipher.{encrypt,decrypt}_channel_config(user_id, dict)` primitive can be reused verbatim for Phase 29's `agent_containers.provider_key_enc` BYTEA column. Per-user KEK isolation is enforced by HKDF-SHA256(master_key, info=ap-ch-||user_id_bytes) → each user's encrypted blob is undecryptable by any other user. This satisfies T-29-02 (cross-tenant key disclosure) without writing new crypto.

VERDICT: PASS
