---
phase: 29-llm-egress-proxy
status: discussed
created: 2026-05-05
updated: 2026-05-05
---

# Phase 29 — LLM egress proxy + provider-agnostic cost capture

## Goal

Build a single egress proxy inside `api_server` that sits between agent containers and upstream LLM APIs (OpenRouter, OpenAI, Anthropic). Bots route their `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` to the proxy. The proxy:

1. Identifies the user by the source IP of the request (resolved via `agent_containers.bridge_ip` → `user_id`)
2. Injects the OpenRouter `user` parameter for sticky routing + per-user attribution
3. Looks up the user's BYOK key (encrypted at rest, decrypted on lookup), swaps the `Authorization` header, forwards upstream
4. Captures the response `usage` block + `X-Generation-Id` header
5. Normalizes into the existing `usage_logs` schema, async-writes a row per call
6. For OpenRouter: post-hoc fetches `/api/v1/generation?id=…` for $-accurate cost

This replaces the broken Phase 27 path where `_parse_stripped` returns `0/unknown` for every contract that isn't `openai_compat`.

## Why this phase exists

Phase 27 attempted cost capture **downstream of the bot** — parsing the bot's reply for a `usage` block. That works only when the bot cooperates (`openai_compat`). Bots using `zeroclaw_native`, `a2a_jsonrpc`, or any future custom contract strip both the `usage` block AND the OpenRouter generation id before replying. The deferred Phase 27 plan ("a future post-hoc OpenRouter fetch will backfill") is **infeasible** — confirmed via 4-agent investigation 2026-05-05 — because there is no key (generation id) to look up.

Cost capture must move **upstream of the bot's reply**. That's what an egress proxy is. PROJECT.md cited it as the platform-billed-mode architecture but it was never built.

This phase also unblocks:
- **Phase B (Stripe paywall)** — needs reliable per-call cost numbers across all contracts
- **Provider expansion** — OpenAI direct + Anthropic direct work day 1, no per-recipe coordination
- **Per-user OpenRouter analytics** — `user` parameter enables OpenRouter's enterprise activity attribution

## Locked decisions

### D-01 Topology — proxy lives inside `api_server`

New FastAPI route family at `/v1/llm/{provider}/...` (or similar; researcher decides path naming). Mounted on the same uvicorn process. No new daemon, no sidecar.

**Why:** zero new ops surface. Phase 22c.3 already proved bot→api_server routing works on macOS Docker Desktop and Linux. api_server is the natural home for both control plane (Temporal client, REST API) and the LLM data plane.

**Trade-off accepted:** api_server now serves both control and data plane. For v1 (sub-100 users) that's fine. Phase 999.2 (Go API rewrite) can split them if needed.

### D-02 BYOK key custody — proxy holds keys; per-deploy, persisted encrypted in `agent_containers`

**Storage location.** Add a new column `agent_containers.provider_key_enc bytea` (Phase 29 migration `013`). Encrypted via the SAME age-cipher infrastructure used for `channel_config_enc` (Phase 23 trust model — already audited). The deploy flow contract stays unchanged: `Authorization: Bearer <key>` header is REQUIRED on every `POST /v1/runs` / `POST /v1/agents/.../deploy`. The change is what api_server does with it: instead of "memory only, inject into bot env", it's now "encrypt + persist + populate proxy cache + still inject into bot env until D-04 migrates that recipe".

**Why per-deploy (not user-scoped):** simplicity wins for v1. User-scoped (MSV's `users.anthropic_oauth` pattern with Settings UI + `/v1/byok/*` endpoints + key validation flow) is the better long-term UX but adds ~3-4× the surface area to Phase 29. Per-deploy keeps the existing client contract intact (mobile + web don't change), survives both api_server and bot container restarts, and matches the existing `channel_config_enc` mental model. Phase 30+ can promote to user-scoped without breaking anything.

**Restart resilience (the load-bearing requirement):**
- **api_server restart:** lifespan startup queries `agent_containers WHERE container_status='running'`, decrypts each `provider_key_enc`, populates the proxy's in-memory cache `{(user_id, agent_instance_id) → decrypted_key}`. Live chats resume in seconds.
- **Bot container restart:** no impact. Bot's `OPENAI_BASE_URL` still points at api_server's proxy route; proxy still has the key cached.
- **api_server + bot both restart:** same as above — proxy rehydrates from DB, bot reconnects to proxy. No re-paste.

**Bot side: still inject the key into the bot container until D-04 flips that recipe.** Phase 29 ships the proxy AND flips one recipe (nano-kaiku, per D-04). For nano-kaiku ONLY, the bot's env loses `OPENROUTER_API_KEY` and gains `OPENAI_BASE_URL=http://api_server:8000/v1/llm/forward` + `OPENAI_API_KEY=ap-proxy-<inapp_auth_token>`. Other recipes keep their current "key in env" path until they migrate.

**Header injection by proxy → upstream:**
- OpenRouter / OpenAI: `Authorization: Bearer <key>`
- Anthropic native: `x-api-key: <key>` + `anthropic-version: 2023-06-01`

Proxy dispatches per the resolved upstream provider (D-09).

**MSV reference:** `api/pkg/anthropicproxy/proxy.go` lines 116-117 (`tidToKey map[string]string`), 296-298 (atomic cache swap), 332-342 (`resolveKey`), 354-360 (`SetDefaultKey` hot-rotation), 526-541 (header injection on outbound). AP equivalent: same shape but cache key is `(user_id, agent_instance_id)` instead of `telegramID`, and the cache source is `agent_containers.provider_key_enc` instead of `users.anthropic_oauth`.

**Deferred to Phase 30+ (explicitly out of scope):** `users.byok_keys_enc` user-scoped table, Settings UI for key management, `POST /v1/byok/{provider}` REST endpoints, key reuse across deploys.

### D-02b Validate the BYOK key on deploy — cheapest probe per provider

Before persisting the key + creating the agent_container, validate it against the upstream provider with the cheapest possible call. Failure → 401 returned to client, no agent created, no encrypted blob written.

| Provider | Validation call | Cost | Why |
|---|---|---|---|
| OpenRouter | `GET https://openrouter.ai/api/v1/key` with `Authorization: Bearer <key>` | $0 (no inference) | Returns key metadata + balance. 401 on invalid. |
| Anthropic | `POST https://api.anthropic.com/v1/messages` body `{"model":"claude-haiku-4-5","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}` | ~$0.00001 | MSV's exact pattern (`api/internal/service/byok_service.go` line 28). 401 on invalid. |
| OpenAI | `GET https://api.openai.com/v1/models` with `Authorization: Bearer <key>` | $0 | Returns 200 + model list. 401 on invalid. |

**Implementation note:** validation runs synchronously in the deploy handler BEFORE any DB write. Adds 50-300ms to deploy latency — acceptable trade-off for catching typos/expired keys at the right moment instead of mid-chat.

**MSV reference:** `api/internal/service/byok_service.go` lines 27-30 (anthropicValidateURL + validateRequestBody constants).

### D-03 Streaming usage capture — inline final chunk + post-hoc verify

Proxy injects `stream_options: { include_usage: true }` into outbound OpenAI/OpenRouter chat-completion requests. Captures the final SSE chunk's `usage` block for instant ticker update.

For OpenRouter: also calls `GET /api/v1/generation?id=<X-Generation-Id>` post-hoc (in a Temporal activity, ~1-3s after stream closes) for $-accurate cost. Updates the `usage_logs` row's `cost_usd` column with the truth.

**Anthropic streaming** uses a different shape (event stream with `message_delta` events carrying `usage`). Proxy parses the final `message_delta`'s `usage`. No post-hoc fetch — Anthropic doesn't expose one.

### D-04 Recipe migration cadence — one at a time, nano-kaiku first

Phase 29 ships:
- the proxy
- One recipe flipped to use it: **nano-kaiku** (already `openai_compat`, lowest risk, simplest E2E proof)

Subsequent recipes flip in 1-line PRs (Phase 29.x or Phase 30): zeroclaw, nullclaw, nanobot, hermes, openclaw.

**Why:** isolates "proxy works correctly" risk from "this specific recipe's bot survives the route change" risk. Each migration is one PR, one human smoke test.

### D-05 Failure mode — fail-closed

If the proxy errors (api_server route returns 5xx, upstream times out beyond retry budget, BYOK key decrypt fails), the bot's request fails. Temporal's `forward_to_agent` activity already retries `[1s, 2s, 4s]` — transient blips heal. Persistent failure surfaces as `bot_timeout` / `bot_5xx` / `container_not_ready` and the user sees it.

**Why:** consistent with Temporal retry semantics. No silent metering gap. No "request succeeded but we don't know what it cost" rows polluting `usage_logs`.

### D-06 Old `unknown` rows — wipe at cutover

`DELETE FROM usage_logs WHERE status='unknown'` runs as part of Phase 29 migration. Loses the message-count history (which is also queryable from `inapp_messages` anyway). Ensures the Usage screen's `last`/totals reflect only post-proxy data.

**Why:** the 11 existing `unknown` rows can't be backfilled (no generation id stored). Wipe is cleaner than carrying confusing "this one shows 0 forever" rows.

### D-07 User identification — source IP via `agent_containers` lookup

Proxy extracts `request.client.host` (FastAPI), looks up `agent_containers WHERE bridge_ip = <ip> AND container_status = 'running'` to resolve `(user_id, agent_instance_id)`. Cache the map in-process, refresh on Docker network events or every 60s, whichever is sooner.

Defense-in-depth: also validate the `Authorization` header against `agent_containers.inapp_auth_token` (already exists from Phase 22c.3) — proxy accepts the call only when both IP map AND token check agree.

**MSV reference:** `api/pkg/anthropicproxy/proxy.go` lines 240-255 (`startIPRefresh`), 446-457 (`ipToTID` lookup at request time), 273-298 (`refreshIPMap` calls `dockerRunner.ListPodIPs(ctx)`).

**AP equivalent:** `inapp_recipe_index.get_container_ip(container_id)` already resolves Docker bridge IPs. We add the inverse lookup (IP → container_id → user_id).

### D-08 OpenRouter `user` parameter format

Proxy injects `user: "ap_<user_id>_<agent_instance_id>"` into outbound OpenRouter chat-completion requests. Format chosen so OpenRouter's activity dashboard groups per-user AND lets us drill down per-agent.

**Why include agent_instance_id:** different agents on the same user account should be distinguishable in OpenRouter's analytics for ops debugging.

### D-09 Provider routing — by upstream URL, not request path

Recipe declares the upstream provider in its config. Proxy reads from a config table or `agent_containers.upstream_provider` (NEW column, Phase 29 migration). Path on api_server is `/v1/llm/forward` (one route); the upstream URL comes from the resolved agent context.

**Why not path-based:** path-based dispatch (MSV does `/v1/chat/completions` → OR, others → Anthropic) couples the URL to the provider. AP supports BYOK across all 3 providers per recipe — the user picks at deploy time. Path-based dispatch would force users to know their provider when they only know their agent.

### D-10 Recording path — async, hooked into existing `usage_recorder`

Proxy calls `services.usage_recorder.record_usage(...)` directly (not via Temporal activity) because it has all the data in-process: tokens, cost, model, user_id. The existing function already inserts into `usage_logs` async.

For OpenRouter post-hoc backfill: that DOES go through a new Temporal activity (`backfill_openrouter_cost`) because it needs retries + persistence and runs ~1-3s after the proxy returned.

### D-11 Schema additions — minimal

`usage_logs` columns are already provider-agnostic. New additions:

- `agent_containers.upstream_provider TEXT NULL` — one of `openrouter` | `openai` | `anthropic`. Set at deploy time from recipe config.
- `usage_logs.proxy_latency_ms INTEGER NULL` — time in proxy (excluding upstream call). Ops debugging.
- `usage_logs.upstream_latency_ms INTEGER NULL` — time waiting for upstream.

Migration `013` adds these. Existing columns (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_creation_tokens`, `cost_usd`, `provider`, `model`, `upstream_request_id`, `latency_ms`) stay.

### D-12 Anthropic-native parser — new function in `usage_recorder`

Add `_parse_anthropic_native(response: dict) -> ParsedUsage`. Same shape as `_parse_openai_compat` but reads `usage.input_tokens` / `output_tokens` / `cache_read_input_tokens` / `cache_creation_input_tokens`.

`_parse_stripped` stays for now (called by the legacy non-proxy path until all recipes migrate). After D-04 completes (all recipes flipped), `_parse_stripped` is deleted in Phase 30 cleanup.

### D-13 Rate limiting — none in v1

Proxy does NOT enforce per-user rate limits in Phase 29. The user is paying their own provider (BYOK), provider already enforces rate limits, and AP isn't yet at scale where we need a defense.

**Defer to Phase B** when platform-billed mode adds the 402-balance gate (also a natural rate-limit hook).

**MSV has tier-based RPM** (`RateLimits.FreeRPM` / `StarterRPM` etc) — that pattern is the future migration path; we don't pre-build it.

### D-14 Outbound request body mutation — minimal-mutation, recompute Content-Length

Proxy must inject two fields into outbound chat-completion request bodies:

- `user: "ap_<user_id>_<agent_instance_id>"` (D-08)
- `stream_options: { include_usage: true }` when `stream: true` (D-03)

**Mechanism:** read JSON body → mutate dict → re-serialize → set `Content-Length` to the new length. Bot's original body is ALSO logged at debug level (with the BYOK key field redacted if any leaks through) for diff debugging.

**Anthropic's `/v1/messages` body** has no equivalent `user` field — Anthropic surfaces user attribution via OpenTelemetry headers, not body. Proxy adds `OpenTelemetry: ap_user=<user_id>` header instead of body mutation for that provider.

**Streaming responses** flow back to the bot as SSE without buffering. Proxy splits the stream: forward each chunk to bot in real-time AND tee a copy to a parser goroutine that watches for the final `usage` chunk. FastAPI's `StreamingResponse` + `aiohttp` async client handles this idiom natively.

### D-15 Error response handling — record `usage_logs` row with `status='failed'`

When upstream returns 4xx/5xx, proxy:

1. Forwards the response body verbatim to the bot (bot's error UX is its own concern)
2. Writes a `usage_logs` row with `status='failed'`, `status_code=<upstream_status>`, `cost_usd=0`, tokens=0
3. Logs a structured event for ops

Reasoning: the message attempt happened (Temporal will retry per `forward_to_agent`'s budget), and we want it visible in usage analytics so cost-attribution audits show the gap clearly.

`status` enum becomes `success | failed | unknown` (with `unknown` only on legacy non-proxy rows pre-Phase-30 cleanup).

### D-16 Idempotency — proxy honors `Idempotency-Key` header from Temporal retries

When `forward_to_agent` activity retries (per `[1s, 2s, 4s]` budget), it must NOT cause double charges. The Temporal-driven retry already has `attempt` exposed; bot's outbound LLM call should carry `Idempotency-Key: msg-<message_id>-<workflow_run_id>` in the request to api_server's proxy route.

**Proxy behavior on duplicate Idempotency-Key:** look up the existing `usage_logs` row by `(idempotency_key, status='success')`. If found, replay that row's response — do NOT re-call upstream. If not found (still in-flight or last attempt failed), forward to upstream normally.

This is closely modeled after the existing `IdempotencyMiddleware` (services/idempotency.py) which already handles `POST /messages` idempotency. Proxy reuses the same Redis-backed cache with a different namespace (`ap:proxy:idem:`).

### D-17 Provider derivation — from recipe's `runtime.process_env.api_key`

The recipe's existing `runtime.process_env.api_key` field already declares which env var name carries the BYOK key (`OPENROUTER_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`). That same signal tells the proxy which upstream URL to forward to:

| Recipe declares | Proxy forwards to | Auth header |
|---|---|---|
| `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | `Authorization: Bearer <key>` |
| `ANTHROPIC_API_KEY` | `https://api.anthropic.com` | `x-api-key: <key>` + `anthropic-version: 2023-06-01` |
| `OPENAI_API_KEY` | `https://api.openai.com/v1` | `Authorization: Bearer <key>` |

`agent_containers.upstream_provider` (D-11 schema add) is materialized at deploy time from this signal — the proxy reads it on every request, no recipe lookup at hot path.

**Why not recipe-config-driven explicitly:** the existing `_ENV_TO_PROVIDER` map in `services/recipes_loader.py:58` already does this derivation for the BYOK label-swap UX. Proxy reuses the same source of truth — one place to change if a fourth provider is added.

### D-18 Recipe field that turns on the proxy — `runtime.via_proxy: true`

New optional recipe YAML field: `runtime.via_proxy: true`. When set, the runner:

- Strips `OPENROUTER_API_KEY`/`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` from the bot container's env
- Injects `OPENAI_BASE_URL=http://api_server:8000/v1/llm/forward` (or the equivalent for Anthropic-direct: `ANTHROPIC_BASE_URL=...`)
- Injects `OPENAI_API_KEY=ap-proxy-<inapp_auth_token>` as a placeholder so OpenAI SDK clients don't barf on missing-key validation
- The bot's outbound LLM call lands on api_server's proxy route, which holds the real key

When unset (or `false`), the runner uses the legacy path: bot gets the real key in env, calls upstream directly, no proxy involvement.

**Phase 29 sets `via_proxy: true` only on `recipes/nano-kaiku.yaml`.** Other recipes flip in subsequent PRs (D-04).

### D-19 Live container migration at cutover — wipe nano-kaiku containers

When the nano-kaiku recipe's `via_proxy: true` flag goes live, existing nano-kaiku containers (running with keys baked in env) become incompatible — they have a real `OPENROUTER_API_KEY` set, so the bot will keep calling OpenRouter directly, bypassing the proxy. Cutover script:

```python
# tools/migrate_phase29_nano_kaiku_cutover.py
# 1. Find live nano-kaiku containers
rows = await fetch("""
    SELECT id, container_id FROM agent_containers
    WHERE recipe_name='nano-kaiku' AND container_status IN ('running','starting')
""")
# 2. Stop the Docker containers (idempotent)
for row in rows:
    docker_client.containers.get(row.container_id).stop(timeout=10)
# 3. Mark rows stopped (the reaper will GC them)
await execute("""
    UPDATE agent_containers SET container_status='stopped', stopped_at=NOW()
    WHERE id = ANY($1)
""", [r.id for r in rows])
```

Dev-OK per user decision: "wipe — it's dev, just kill them." User must redeploy nano-kaiku agents post-cutover. Mobile app's "deploy" UX is unchanged so re-deploy is one tap.

**This script runs as part of Phase 29 Plan 09 (cutover). Plus a final invocation after `via_proxy: true` is committed but BEFORE merge to ensure no race with new deploys.**

## Out of scope (deferred / Phase 30+)

- Migrating zeroclaw, nullclaw, nanobot, hermes, openclaw to use the proxy (one PR each, Phase 29.x)
- Removing `_parse_stripped` and the legacy non-proxy path
- Phase B Stripe paywall (this phase merely unblocks it)
- Live OpenRouter price sync into `cost_weights` (currently manual via Alembic seeds; out of v1 scope, see migration 010 + 012 for the pattern)
- Multi-host proxy / Phase 999.2 Go rewrite — current architecture is single-host

## Reusable assets (existing in codebase)

| Asset | Path | Use |
|---|---|---|
| `usage_logs` schema | migration 010 | Already provider-agnostic; add 2 columns in migration 013 |
| `cost_weights` schema | migration 010 + 012 | Already provider-agnostic; OpenAI/Anthropic direct prices stay seeded; OpenRouter rows can be ignored once post-hoc fetch is the truth |
| `usage_recorder.record_usage` | services/usage_recorder.py | Async writer; called by proxy directly |
| `_parse_openai_compat` | services/usage_recorder.py:108 | Already correct; reused by proxy for OpenAI/OpenRouter responses |
| `agent_containers.channel_config_enc` | migration 002+ | Encrypted BYOK key storage; decrypt path exists |
| `agent_containers.inapp_auth_token` | Phase 22c.3 | Defense-in-depth secondary auth for D-07 |
| `inapp_recipe_index.get_container_ip` | services/inapp_recipe_index.py:346 | Container ID → bridge IP. Inverse map (IP → container_id → user_id) is new |
| Temporal `forward_to_agent` activity retry | activities/forward_to_agent.py | Existing `[1s, 2s, 4s]` retry covers transient proxy errors per D-05 |

## MSV references (steal these patterns)

| Pattern | MSV file:line | What to mirror |
|---|---|---|
| Proxy Config + Start lifecycle | `api/pkg/anthropicproxy/proxy.go` lines 65-180, 217-238 | FastAPI lifespan equivalent; mount proxy router on app startup |
| IP-based user identification | `api/pkg/anthropicproxy/proxy.go` lines 446-457 (`ipToTID` lookup), 240-298 (refresh goroutine) | `agent_containers` query equivalent |
| BYOK key cache + hot refresh | `api/pkg/anthropicproxy/proxy.go` lines 116-117, 330-360 (`resolveKey`, `SetDefaultKey`, `SetOpenRouterKey`) | Background task that re-reads encrypted keys every 2 min |
| Path-dispatch for multiple upstreams | `api/pkg/anthropicproxy/proxy.go` lines 508-521 (OpenRouter sub-proxy) | We do D-09 instead (recipe config drives provider), but the multi-upstream-in-one-router pattern transfers |
| `APICallRecorder` async write | `api/pkg/anthropicproxy/recorder.go` lines 21-60 | Direct call to `usage_recorder.record_usage` (Python equivalent) |
| Pre-flight 402 gate (for Phase B later) | `api/pkg/anthropicproxy/proxy.go` `BalanceCheckFunc` | Phase B work; out of scope for 29 |

## Risks / open questions for the researcher

1. **Streaming `stream_options.include_usage`** — confirmed supported by OpenAI + OpenRouter. Anthropic uses a different mechanism (`message_delta` events). Researcher: verify the exact key paths in current API versions and any quirks (e.g. does `include_usage` work with `stream=false` too?).

2. **`X-Generation-Id` header preservation** — confirmed in OPTIONS preflight. Researcher: verify the header is on EVERY OpenRouter response (success + error) and document the exact header name used in the streaming case (some implementations use a body field instead).

3. **OpenRouter `/api/v1/generation` lookup latency** — Agent 2 noted "data may take a few seconds to populate." Researcher: empirically measure across 5+ requests; pick a sensible delay before the post-hoc activity fires (target ≤2s).

4. **Auth swap for non-OpenAI-compat headers** — Anthropic uses `x-api-key` not `Authorization: Bearer`. OpenAI uses `Authorization: Bearer`. OpenRouter accepts both. Proxy must dispatch the auth-injection mechanism per provider.

5. **Bot-side trust** — when the bot makes its outbound LLM call, does it currently set `OPENAI_BASE_URL` from env or hardcode? Researcher: inspect the 5 recipes' bot code to confirm `--dart-define`-style env injection works for all of them.

6. **Idempotency on retry** — if Temporal retries `forward_to_agent`, the bot retries its upstream LLM call, the proxy sees the second call. Without dedup, we double-write `usage_logs`. Researcher: propose an idempotency key (e.g. `Idempotency-Key: msg-<message_id>-<attempt>`) the proxy honors.

## Acceptance gates (forward-looking — drives Plan 09)

1. nano-kaiku end-to-end smoke: chat round-trip records a `usage_logs` row with non-zero `input_tokens`, `output_tokens`, `cost_usd`, and a populated `upstream_request_id`.
2. OpenRouter `/api/v1/generation` post-hoc backfill updates the row's `cost_usd` to within ±$0.001 of the response's reported total.
3. Mobile Usage screen shows non-zero `$` for the test message within 5s of send-complete.
4. Pre-existing `usage_logs` rows with `status='unknown'` are deleted by the migration.
5. Failure-injection: kill api_server during a chat send → bot's call fails → user sees `bot_timeout` (D-05 fail-closed).
6. BYOK key never appears in any log line (proxy injects upstream-only).
7. The other 4 recipes (zeroclaw, nullclaw, nanobot, hermes) continue to work via the **legacy non-proxy path** (proven by re-running existing 5×5 e2e matrix). They migrate in subsequent phases.
