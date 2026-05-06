---
phase: 29
plan: 05
subsystem: llm-egress-proxy
tags: [byok, custody, proxy, lifecycle, age-cipher, restart-resilience]
dependency_graph:
  requires:
    - "Plan 29-01: PROBE-VAL-07 (age-cipher round-trip + cross-user isolation)"
    - "Plan 29-01: PROBE-VAL-04 (auth-swap shapes for OpenRouter / Anthropic / OpenAI)"
    - "Plan 29-01: PROBE-VAL-11 (OpenRouter /v1/key endpoint reliability)"
    - "Plan 29-02: migration 013 (provider_key_enc BYTEA + upstream_provider TEXT columns)"
    - "Plan 29-03: services/proxy_dispatcher.py (PROVIDERS, derive_provider, ENV_TO_PROVIDER)"
    - "Plan 29-04: services/proxy_ip_map.py + main.py lifespan (proxy_upstream_client, ProxyIPMap)"
    - "Plan 29-04: routes/llm_proxy.py (consumes proxy_byok_cache.get hot path)"
  provides:
    - "ProxyBYOKCache: in-process {(user_id, agent_instance_id) -> (provider, decrypted_key)} cache"
    - "byok_validator.PROVIDER_VALIDATORS: 3 async probes for deploy-time D-02b validation"
    - "agent_lifecycle.start_agent gated BYOK custody (via_proxy=true only)"
    - "Lifespan rehydrate_from_db: restart-resilient cache repopulation"
    - "GATE-7 mechanical guarantee: legacy recipes deploy with provider_key_enc IS NULL"
  affects:
    - "Plan 29-08 (nanobot recipe flip): when runtime.via_proxy=true is set, this plan's gate fires for nanobot deploys"
    - "Plan 29-09 (acceptance): Gate 6 BYOK-no-leak + Gate 7 legacy-bypass both reachable"
    - "Phase 30+: each subsequent recipe migration is a 1-line YAML flip — no code change in this layer"
tech_stack:
  added:
    - "asyncio.Lock-guarded in-process custody cache pattern (mirrors ProxyIPMap)"
    - "respx with httpx.ConnectError side_effect for network-failure tests"
    - "Plan-level recipe-config gate (recipe.runtime.via_proxy boolean) at deploy time"
  patterns:
    - "Restart resilience via lifespan rehydrate_from_db (load-bearing for D-02)"
    - "Encrypted-at-rest BYOK with per-user KEK (re-uses Phase 22+ age-cipher)"
    - "Pre-flight upstream probe at deploy time (D-02b) — catches typos/expired keys before chat"
    - "via_proxy gate as the migration cadence knob (Plan 09 Gate 7 by construction)"
key_files:
  created:
    - "api_server/src/api_server/services/proxy_byok_cache.py"
    - "api_server/src/api_server/services/byok_validator.py"
    - "api_server/tests/services/test_proxy_byok_cache.py"
    - "api_server/tests/services/test_byok_validator.py"
    - "api_server/tests/routes/test_agent_lifecycle_byok_validation.py"
  modified:
    - "api_server/src/api_server/main.py"
    - "api_server/src/api_server/routes/agent_lifecycle.py"
    - "api_server/src/api_server/services/run_store.py"
decisions:
  - "Cache key is the FULL (user_id, agent_instance_id) tuple — cross-user isolation by construction (Test 7)"
  - "Decrypt failures during rehydrate are LOGGED + SKIPPED (never crash the loop); log carries only agent_instance_id, never the bytes or the decrypted key"
  - "Validator probes use the SHARED app.state.proxy_upstream_client (AMD-05) — 600s timeout is overridden per-call to 10s/15s"
  - "Network failures from validators PROPAGATE (deploy handler converts to 503); only 401 maps to UNAUTHORIZED envelope"
  - "via_proxy gate uses recipe.get('runtime', {}).get('via_proxy', False) — recipes are dicts (ruamel YAML output) — NOT pydantic models with attribute access"
  - "agent_containers.upstream_provider + provider_key_enc are always written together; legacy recipes leave both NULL"
  - "proxy_byok_cache.set is called AFTER write_agent_container_running succeeds (DB is authoritative; cache mirrors)"
metrics:
  duration_minutes: 50
  completed_date: "2026-05-06"
  tasks_completed: 3
  test_count: 26
  test_passed: 26
  files_created: 5
  files_modified: 3
  commits: 3
---

# Phase 29 Plan 05: BYOK Custody (cache + validator + lifecycle integration) Summary

BYOK custody layer with restart-resilient lifespan rehydrate, per-provider deploy-time validation, and via_proxy-gated integration into the start_agent route — delivers Acceptance Gate 6 (BYOK-no-leak) and provides the mechanical foundation for Plan 09 Gate 7 (legacy recipes with provider_key_enc IS NULL).

## What Shipped

### Task 1 — `services/proxy_byok_cache.py` (commit `8788b70`)

`ProxyBYOKCache` class with `__init__(db_pool)`, `rehydrate_from_db()`, `get(user_id, agent_instance_id)`, `set(...)`, `invalidate(...)`. Internal `dict[tuple[UUID, UUID], tuple[str, str]]` guarded by `asyncio.Lock`. Mirrors `ProxyIPMap` shape (Plan 29-04) — same atomic-update + concurrent-snapshot semantics.

`rehydrate_from_db` queries `agent_containers WHERE container_status='running' AND provider_key_enc IS NOT NULL`, decrypts each via `crypto.age_cipher.decrypt_channel_config`, populates the cache. Decrypt failures (corrupt blob, KEK mismatch, missing 'key' field) are logged with ONLY `agent_instance_id` in extras and SKIPPED — single bad row never crashes the loop. Returns count of successful decrypts.

8 integration tests (real PG17 + real `encrypt_channel_config` for seeding):

1. `test_rehydrate_populates_running_rows` — happy path 2 rows
2. `test_rehydrate_skips_stopped_containers` — status filter
3. `test_rehydrate_skips_null_provider_key_enc` — legacy-recipe rows excluded by WHERE clause
4. `test_rehydrate_decrypt_failure_does_not_crash` — corrupt blob is logged + skipped
5. `test_set_adds_entry`
6. `test_invalidate_removes_entry` (idempotent)
7. `test_cross_user_isolation` — same agent_id, different user_id → miss
8. `test_byok_key_never_in_caplog_on_rehydrate_failure` — Acceptance Gate 6 invariant via `caplog` grep on `sk-or` marker + ciphertext hex prefix

### Task 2 — `services/byok_validator.py` (commit `6f4ec31`)

Three async probes + dispatcher dict:

| Validator | URL | Auth | Timeout | Pass criteria |
|---|---|---|---|---|
| `validate_openrouter` | `GET https://openrouter.ai/api/v1/key` | `Authorization: Bearer <key>` | 10s | `status == 200` |
| `validate_anthropic` | `POST https://api.anthropic.com/v1/messages` (`max_tokens=1`, `claude-haiku-4-5`) | `x-api-key: <key>` + `anthropic-version: 2023-06-01` | 15s | `status in (200, 400)` (400 = truncation; auth was OK) |
| `validate_openai` | `GET https://api.openai.com/v1/models` | `Authorization: Bearer <key>` | 10s | `status == 200` |

Each takes an injected `httpx.AsyncClient` (the deploy handler passes `app.state.proxy_upstream_client`). Network failures (`ConnectError`, `TimeoutException`, etc.) propagate up — the validator does NOT swallow. The deploy handler converts propagated errors to 503 envelopes; only explicit `False` returns map to 401.

10 unit tests via `respx` covering: 200 success, 401 failure, header shape, body shape (Anthropic), `PROVIDER_VALIDATORS` keys + async-callable invariant, network-failure propagation.

### Task 3 — `routes/agent_lifecycle.py::start_agent` integration + `main.py` lifespan (commit `b2c4cda`)

**Lifespan addition** (after `proxy_ip_map`, before `inapp_tasks`):

```python
from .services.proxy_byok_cache import ProxyBYOKCache
app.state.proxy_byok_cache = ProxyBYOKCache(db_pool=app.state.db)
_byok_loaded = await app.state.proxy_byok_cache.rehydrate_from_db()
_log.info("phase29.lifespan.proxy_byok_cache_rehydrated",
          extra={"count": _byok_loaded})
```

**Route gate** (inserted between recipe lookup and `insert_pending_agent_container`):

```python
runtime_block = recipe.get("runtime") or {}
via_proxy_flag = bool(runtime_block.get("via_proxy", False))
if via_proxy_flag:
    # derive_provider → validator probe → encrypt → persist via insert kwargs
    # On 401: return UNAUTHORIZED envelope ("BYOK key rejected by upstream")
    # On HTTPError: return INFRA_UNAVAILABLE 503 envelope
    # On unknown env var: return INVALID_REQUEST 400 envelope
    # Success: provider_key_enc + upstream_provider passed to insert_pending_agent_container
# else: legacy path — both columns stay NULL, no validator probe, no cache update
```

**Cache population** (after `write_agent_container_running` succeeds, before response):

```python
if proxy_validated_key is not None and proxy_validated_provider is not None:
    await request.app.state.proxy_byok_cache.set(
        user_id, agent_id, proxy_validated_provider, proxy_validated_key,
    )
```

**run_store extension:** `insert_pending_agent_container` gained `*, upstream_provider=None, provider_key_enc=None` keyword args. Legacy callers (any caller that doesn't pass them) leave both columns NULL — Plan 09 Gate 7's mechanical guarantee.

8 integration tests (commit `b2c4cda`):

1. `test_via_proxy_happy_path_persists_and_caches` — Validator 200 → row + cache populated, Authorization header sent correctly
2. `test_via_proxy_validator_401_blocks_deploy` — 401 envelope + zero rows in agent_containers
3. `test_via_proxy_validator_network_failure_returns_503` — `httpx.ConnectError` → 503 INFRA_UNAVAILABLE
4. `test_via_proxy_unknown_api_key_env_var_returns_400` — recipe with `BOGUS_KEY` → 400 INVALID_REQUEST
5. `test_via_proxy_encrypted_blob_round_trips` — `decrypt_channel_config(user_id, blob)` yields `{"key": <original BYOK>}`
6. `test_byok_key_never_in_caplog_on_401` — Acceptance Gate 6 via `caplog` grep on a recognizable LEAKMARKER substring
7. **GATE-7 INVARIANT** `test_legacy_recipe_skips_validator_entirely` — `respx.call_count == 0`, `upstream_provider IS NULL`, `provider_key_enc IS NULL`, cache miss
8. **GATE-7 INVARIANT** `test_legacy_recipe_with_bogus_key_still_succeeds` — counter-example: bogus key + via_proxy=False → 200 (no probe means no rejection)

## Cache Shape Reference

```
key:   (user_id: UUID, agent_instance_id: UUID)
value: (provider: str, decrypted_key: str)

Source of truth: agent_containers
  WHERE container_status='running' AND provider_key_enc IS NOT NULL
Crypto primitive: crypto.age_cipher.{encrypt,decrypt}_channel_config(user_id, dict)
  master key: AP_CHANNEL_MASTER_KEY env (32 bytes base64); dev fallback = 32 zero bytes
  per-user KEK: HKDF-SHA256(master, info=b'ap-ch-' || user_id.bytes)
Plaintext blob shape: {"key": "<provider key string>"}
```

## Validation Flow Reference

```
client POST /v1/agents/:id/start
   |
   |-- require_user (session cookie) -> user_id
   |-- Authorization: Bearer <byok_key>
   |-- recipe = app.state.recipes[agent.recipe_name]
   |-- via_proxy_flag = recipe['runtime']['via_proxy']  # default False
   |
   if via_proxy_flag:
   |       provider = derive_provider(recipe['runtime']['process_env']['api_key'])
   |       try:
   |           ok = await PROVIDER_VALIDATORS[provider](
   |                   app.state.proxy_upstream_client, byok_key)
   |       except httpx.HTTPError:
   |           -> 503 INFRA_UNAVAILABLE (no agent created)
   |       if not ok:
   |           -> 401 UNAUTHORIZED ("BYOK key rejected by upstream")
   |       provider_key_enc = encrypt_channel_config(user_id, {"key": byok_key})
   |       upstream_provider = provider
   |
   |-- insert_pending_agent_container(..., upstream_provider, provider_key_enc)
   |-- execute_persistent_start(...)  # docker boot
   |-- write_agent_container_running(...)  # 'starting' -> 'running'
   |
   if via_proxy_flag:
   |       await proxy_byok_cache.set(user_id, agent_id, provider, byok_key)
   |
   -> 200 AgentStartResponse
```

## Self-Check: PASSED

| Item | Check | Result |
|---|---|---|
| `proxy_byok_cache.py` exists | `[ -f api_server/src/api_server/services/proxy_byok_cache.py ]` | FOUND |
| `byok_validator.py` exists | `[ -f api_server/src/api_server/services/byok_validator.py ]` | FOUND |
| `test_proxy_byok_cache.py` exists | `[ -f api_server/tests/services/test_proxy_byok_cache.py ]` | FOUND |
| `test_byok_validator.py` exists | `[ -f api_server/tests/services/test_byok_validator.py ]` | FOUND |
| `test_agent_lifecycle_byok_validation.py` exists | `[ -f api_server/tests/routes/test_agent_lifecycle_byok_validation.py ]` | FOUND |
| Task 1 commit | `git log | grep 8788b70` | FOUND `feat(29-05): add ProxyBYOKCache...` |
| Task 2 commit | `git log | grep 6f4ec31` | FOUND `feat(29-05): add byok_validator...` |
| Task 3 commit | `git log | grep b2c4cda` | FOUND `feat(29-05): integrate BYOK validation...` |
| All 26 plan tests | `pytest tests/services/test_proxy_byok_cache.py tests/services/test_byok_validator.py tests/routes/test_agent_lifecycle_byok_validation.py` | 26/26 PASSED |
| Regression (proxy_ip_map + idempotency_reserved_row) | `pytest tests/services/test_proxy_ip_map.py tests/services/test_idempotency_reserved_row.py -m api_integration` | 15/15 PASSED |
| Regression (proxy_dispatcher + stream_parser + usage_recorder) | `pytest tests/services/test_proxy_dispatcher.py tests/services/test_stream_parser.py tests/services/test_usage_recorder.py` | 43/43 PASSED |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] LogRecord reserved-name collision in `byok_validator.network_failure` log call**

- **Found during:** Task 3 — running `test_via_proxy_validator_network_failure_returns_503`
- **Issue:** First version used `extra={"msg": ...}` which collides with LogRecord's reserved `msg` attribute → `KeyError: "Attempt to overwrite 'msg' in LogRecord"`. Switched to `extra={"exc_text": ...}` which ALSO collides (LogRecord caches an `exc_text` attribute when exc_info is set).
- **Fix:** Renamed the field to `error_text` — neither reserved nor cached. The redaction substitution `str(exc).replace(provider_key, "<REDACTED>")` is preserved.
- **Files modified:** `api_server/src/api_server/routes/agent_lifecycle.py` (one line)
- **Commit:** `b2c4cda`

### CLAUDE.md Compliance Notes

- **Golden Rule #1 (no mocks for core substrate):** All Postgres operations hit a real PG17 testcontainer. The `crypto.age_cipher.encrypt_channel_config` primitive is the REAL one for seeding test rows (PROBE-VAL-07 verified). The only mocks are `respx` for upstream HTTP (stays in the test-double layer per byok_validator's contract) and a fake `execute_persistent_start` (Docker boot is out of scope for route-handler tests — same pattern as `test_agent_lifecycle_inapp.py`).
- **Golden Rule #2 (dumb client):** No client-side change in this plan. The proxy custody layer lives entirely server-side; clients still POST `/v1/agents/:id/start` with `Authorization: Bearer <byok_key>` exactly as before.
- **Golden Rule #3 (ship locally first):** Validation is purely server-side; no deploy implications. Phase 29 ships the proxy + nanobot in Plans 08-09; this plan is the custody substrate underneath.

### Auth Gates

None — this plan does not interact with OAuth or session minting. `OPENROUTER_API_KEY` env is not required for the test suite (the integration tests use a hardcoded `_TEST_BYOK_KEY` constant; the validator upstreams are mocked via respx).

## Threat Flags

| Flag | File | Description |
|---|---|---|
| (none) | — | No new security-relevant surface introduced beyond what the plan's `<threat_model>` already documented (T-29-01, T-29-04, T-29-11). All three are mitigated as planned. |

## Known Stubs

None. The cache, validators, route gate, and lifespan rehydrate are all fully implemented. Test 8 (legacy + bogus key) intentionally exercises the "no validation" property of the legacy path — that is correct behavior, not a stub.

## What This Plan Unblocks

- **Plan 29-08 (nanobot recipe flip):** the recipe YAML edit `runtime.via_proxy: true` will trigger this plan's gate; the existing infrastructure persists provider_key_enc + populates the cache without any further code change.
- **Plan 29-09 (Acceptance Gate 6 + Gate 7):** Gate 6 (BYOK-no-leak) is verified empirically by Test 6 + Test 8 of proxy_byok_cache + Test 6 of integration; Gate 7 (legacy recipes deploy with provider_key_enc IS NULL) is mechanically guaranteed by the via_proxy gate's short-circuit semantics.
- **Phase 30+:** every subsequent recipe migration is a 1-line YAML flip (`via_proxy: true`) — no code change required in this layer.
