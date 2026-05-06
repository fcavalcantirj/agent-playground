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

### D-02 BYOK key custody — proxy holds keys

Proxy decrypts the user's encrypted OpenRouter / Anthropic / OpenAI key at request time, swaps the `Authorization` header on the outbound request, forwards upstream. Bot never sees the key.

**Reuse:** `agent_containers.channel_config_enc` already encrypts BYOK key material per Phase 23. Decrypt path exists.

**MSV reference:** `api/pkg/anthropicproxy/proxy.go` lines 116-117 (`tidToKey map[string]string`), 332-342 (`resolveKey`), 526-541 (header injection). Cache refreshed every 2 min via `KeyFunc` callback.

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
