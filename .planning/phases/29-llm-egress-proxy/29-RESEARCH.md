---
phase: 29-llm-egress-proxy
status: researched
created: 2026-05-06
updated: 2026-05-06
---

# Phase 29 — LLM egress proxy + provider-agnostic cost capture (RESEARCH)

**Researched:** 2026-05-06
**Domain:** HTTP egress proxy + LLM streaming usage capture + per-deploy BYOK custody (FastAPI / asyncio / Python translation of MSV's Go pattern in `api/pkg/anthropicproxy/`)
**Confidence:** HIGH on transport mechanics + auth shape + MSV pattern transfer; MEDIUM on streaming-edge cases (stream interruption, gzip-encoded SSE, Anthropic cumulative-usage gotcha) — all 6 covered by Wave 0 spikes.

## Summary

Phase 29 ports MSV's `anthropicproxy` (Echo/Go reverse proxy with `httputil.ReverseProxy` + `ModifyResponse` SSE-tee + per-user key cache + `wrapDirectorForRecording` body mutation + `APICallRecorder` async DB writer) into FastAPI/asyncio/Python and re-targets it from MSV's path-dispatch (Anthropic vs OpenRouter sub-proxies) to AP's recipe-config-driven dispatch (per-deploy `agent_containers.upstream_provider` selects the upstream URL and auth shape on every call). The proxy mounts on the existing `api_server` uvicorn process at a single route `POST /v1/llm/forward/...` (path TBD; Plan 29-01 spike picks the exact shape), looks up the caller via the `agent_containers.bridge_ip` IP-map (mirrors MSV `ipToTID`), decrypts the per-deploy BYOK key from `agent_containers.provider_key_enc` (new column, encrypted by the EXISTING `crypto/age_cipher.py` infra used for `channel_config_enc` since Phase 22), swaps the auth header to the upstream provider's expected shape, injects `stream_options.include_usage` for OpenAI/OpenRouter, captures both the inline final-chunk usage block and the `X-Generation-Id` header on OpenRouter responses, hands the parsed usage to `services/usage_recorder.record_usage` (existing — Phase 27), and queues a Temporal `backfill_openrouter_cost` activity ~2s post-stream to overwrite `usage_logs.cost_usd` with the canonical USD from `GET /api/v1/generation?id=<X-Generation-Id>`. Phase 29 ships proxy + ONE recipe flipped (per D-04: "nano-kaiku" — but **`recipes/nano-kaiku.yaml` does not exist in the repo today**, only `nanobot.yaml`; CONTEXT.md Plan 09 must either create the recipe in this phase OR reuse `nanobot` as the first cutover target — flagged below as O-01).

**Primary recommendation:** Build the proxy as a **FastAPI APIRouter** mounted at `POST /v1/llm/forward` (single route; provider dispatch by `agent_containers.upstream_provider` lookup, NOT by URL path). Use **`httpx.AsyncClient` with `client.stream("POST", upstream_url, ...)` + `aiter_raw()`** for upstream dispatch, then return a `fastapi.responses.StreamingResponse` that **tee**s the raw byte stream into a per-request `StreamUsageParser` (asynchronously, via `aiter_bytes` interleaving) — no buffering. Provider dispatch lives in a **`ProviderDispatcher` dict** keyed by the 3 provider strings; idempotency reuses the existing **`services/idempotency.py`** primitive (different namespace `ap:proxy:idem:` per D-16 but **note: existing primitive is Postgres-backed, NOT Redis-backed — flagged below as O-02**). The age-cipher reuse is direct (proven Phase 22+; same `encrypt_channel_config` shape with a per-user KEK; new column `provider_key_enc bytea`).

## User Constraints (from CONTEXT.md)

### Locked Decisions

> Copied verbatim from `29-CONTEXT.md`. The planner MUST honor every D-XX item exactly.

- **D-01 Topology:** proxy lives inside `api_server` (FastAPI route family `/v1/llm/{provider}/...` or similar — researcher decides path naming; this RESEARCH recommends `/v1/llm/forward` single route per Architectural Approach §1). Mounted on the same uvicorn process. No new daemon, no sidecar.
- **D-02 BYOK custody:** per-deploy, persisted encrypted in new column `agent_containers.provider_key_enc bytea`; encrypted via the SAME age-cipher infra used for `channel_config_enc` (Phase 22). Restart resilience: lifespan startup queries `agent_containers WHERE container_status='running'`, decrypts each `provider_key_enc`, populates the proxy's in-memory cache `{(user_id, agent_instance_id) → decrypted_key}`. Bot side still gets the key in env until D-04 flips that recipe; nano-kaiku ONLY for Phase 29.
- **D-02b BYOK validation on deploy:** synchronous probe BEFORE persisting + creating agent_container. OpenRouter→`GET /api/v1/key` ($0); Anthropic→`POST /v1/messages` `max_tokens=1` body (~$0.00001); OpenAI→`GET /v1/models` ($0). 401→return 401 to client, no agent created, no encrypted blob written. 50–300ms deploy-latency cost accepted.
- **D-03 Streaming usage capture:** inject `stream_options:{include_usage:true}` on outbound OpenAI/OpenRouter chat-completion requests; capture final SSE chunk's `usage` block. For OpenRouter ALSO call `GET /api/v1/generation?id=<X-Generation-Id>` post-hoc (Temporal activity, ~1–3s after stream closes) for $-accurate cost; UPDATE `usage_logs.cost_usd`. Anthropic streaming uses `message_delta` events; no post-hoc fetch (Anthropic doesn't expose one).
- **D-04 Recipe migration cadence:** one at a time. **Phase 29 ships the proxy + ONE recipe flipped (nano-kaiku per CONTEXT).** Phase 30 flips zeroclaw/nullclaw/nanobot/hermes/openclaw in 1-line PRs.
- **D-05 Failure mode — fail-closed.** Proxy 5xx / upstream timeout / decrypt failure → bot's request fails. Temporal `forward_to_agent` already retries `[1s,2s,4s]`. Persistent failure surfaces as `bot_timeout` / `bot_5xx` / `container_not_ready`.
- **D-06 Old `unknown` rows — wipe at cutover.** `DELETE FROM usage_logs WHERE status='unknown'` runs as part of Phase 29 migration.
- **D-07 User identification — source IP via `agent_containers` lookup.** `request.client.host` → `agent_containers WHERE bridge_ip=<ip> AND container_status='running'` → `(user_id, agent_instance_id)`. Cache in-process; refresh on Docker network events OR every 60s, whichever sooner. Defense-in-depth: also validate the `Authorization` header against `agent_containers.inapp_auth_token` (already exists from Phase 22c.3).
- **D-08 OpenRouter `user` parameter format:** `user: "ap_<user_id>_<agent_instance_id>"` injected into outbound OpenRouter chat-completion bodies.
- **D-09 Provider routing — by upstream URL, not request path.** Recipe declares the provider; proxy reads from `agent_containers.upstream_provider` (NEW column). Path on api_server is `/v1/llm/forward` (one route).
- **D-10 Recording path — async, hooked into existing `usage_recorder`.** Proxy calls `services.usage_recorder.record_usage(...)` directly. OpenRouter post-hoc backfill goes through a NEW Temporal activity `backfill_openrouter_cost`.
- **D-11 Schema additions — minimal.** New columns: `agent_containers.upstream_provider TEXT NULL`, `usage_logs.proxy_latency_ms INTEGER NULL`, `usage_logs.upstream_latency_ms INTEGER NULL`. Migration `013` adds these.
- **D-12 Anthropic-native parser** — add `_parse_anthropic_native(response: dict) -> ParsedUsage`. `_parse_stripped` stays for now (legacy non-proxy path); deleted in Phase 30 cleanup.
- **D-13 Rate limiting — none in v1.** Defer to Phase B.
- **D-14 Outbound request body mutation — minimal-mutation, recompute Content-Length.** Inject `user` (D-08) + `stream_options:{include_usage:true}` (D-03 when `stream:true`). Anthropic uses `OpenTelemetry: ap_user=<user_id>` header instead of body mutation. SSE flows back as `StreamingResponse` without buffering.
- **D-15 Error response handling — `usage_logs.status='failed'`.** Forward upstream body verbatim; write a row with `status='failed'`, `status_code=<upstream>`, `cost_usd=0`, `tokens=0`. `status` enum becomes `success | failed | unknown`.
- **D-16 Idempotency — proxy honors `Idempotency-Key` from Temporal retries.** Bot's call carries `Idempotency-Key: msg-<message_id>-<workflow_run_id>`. Duplicate key → look up existing `usage_logs` row by `(idempotency_key, status='success')`; replay or forward. Reuses existing `IdempotencyMiddleware` shape with namespace `ap:proxy:idem:`.
- **D-17 Provider derivation — from recipe's `runtime.process_env.api_key`.** OpenRouter→`https://openrouter.ai/api/v1` + Bearer; Anthropic→`https://api.anthropic.com` + `x-api-key` + `anthropic-version: 2023-06-01`; OpenAI→`https://api.openai.com/v1` + Bearer. Materialized at deploy time into `agent_containers.upstream_provider`. Reuses `_ENV_TO_PROVIDER` map in `services/recipes_loader.py:58`.
- **D-18 Recipe field that turns on the proxy — `runtime.via_proxy: true`.** Strips `*_API_KEY` from bot env; injects `OPENAI_BASE_URL=http://api_server:8000/v1/llm/forward` (or `ANTHROPIC_BASE_URL`); injects `OPENAI_API_KEY=ap-proxy-<inapp_auth_token>` placeholder. Phase 29 sets it ONLY on `recipes/nano-kaiku.yaml`.
- **D-19 Live container migration at cutover — wipe nano-kaiku containers.** Cutover script stops live nano-kaiku containers; user redeploys. Dev-OK.

### Claude's Discretion

- Exact path naming for the proxy route (`/v1/llm/forward` vs `/v1/llm/{provider}/...`) — this RESEARCH recommends `/v1/llm/forward` (single route, provider dispatch via `agent_containers.upstream_provider` lookup).
- Whether to expose the proxy under a single route or per-provider routes (research recommends single — see Architecture).
- Internal lifespan rehydration order (research recommends after `app.state.docker_client` is bound but before `app.state.bot_http_client` is closed at shutdown — see Restart Resilience Audit).
- Streaming tee implementation choice (research recommends in-process `asyncio.Queue` + parallel parser task vs `aiter` interleaving — see Streaming Capture Strategy).
- Idempotency cache backend (Postgres vs Redis): existing `services/idempotency.py` is **Postgres-backed**. CONTEXT.md D-16 says "Redis-backed cache with namespace `ap:proxy:idem:`" — research flags this as a CONTEXT misalignment (O-02 below) and recommends following the existing Postgres pattern unless the planner chooses to extend.
- Per-message proxy logging verbosity / structured fields.

### Deferred Ideas (OUT OF SCOPE)

- Migrating zeroclaw/nullclaw/nanobot/hermes/openclaw to use the proxy (Phase 30, 1 PR each).
- Removing `_parse_stripped` and the legacy non-proxy path (Phase 30 cleanup).
- Phase B Stripe paywall.
- Live OpenRouter price sync into `cost_weights` (currently manual; out of v1).
- Multi-host proxy / Phase 999.2 Go rewrite.

## Phase Requirements

> No `phase_req_ids` were declared on this phase (init returned `null`). Phase 29 instead exists to pay down a debt incurred by Phase 27 (the broken `_parse_stripped` capture path). The 7 acceptance gates from CONTEXT.md §"Acceptance gates" drive the phase exit; the planner should treat them as the requirement spine:
>
> 1. nano-kaiku end-to-end smoke produces a `usage_logs` row with non-zero `input_tokens`, `output_tokens`, `cost_usd`, populated `upstream_request_id`.
> 2. OpenRouter post-hoc backfill updates `cost_usd` to within ±$0.001 of `/api/v1/generation`.
> 3. Mobile Usage screen shows non-zero `$` within 5s of send-complete.
> 4. Pre-existing `usage_logs.status='unknown'` rows deleted.
> 5. Failure injection: kill api_server during chat → user sees `bot_timeout`.
> 6. BYOK key never appears in any log line.
> 7. Other 4 recipes continue to work via legacy non-proxy path (existing 5×5 e2e matrix).

## Project Constraints (from CLAUDE.md)

- **Golden Rule #1 — No mocks/no stubs.** Every test in the Phase 29 plan must hit real Postgres + real Docker daemon (testcontainers) + real OpenRouter (or a recorded real-traffic capture; see VAL-PROBE-09). The streaming-tee path MUST be exercised against a real OpenAI-compatible streaming endpoint; an in-memory mock SSE stream does not satisfy the rule.
- **Golden Rule #2 — Dumb client.** No client (web/mobile/CLI/SDK) ever queries Postgres directly. All `usage_logs` reads go via `routes/usage.py`; the AppBar ticker remains driven by `GET /v1/usage/...` ready-to-render JSON. The proxy itself is a SERVER component — the rule binds clients, not internal API services.
- **Golden Rule #3 — Ship when stack works locally end-to-end.** macOS Docker Desktop bridge-IP gotcha (CLAUDE.md "End-to-end tests on macOS — `make screens-e2e` will fail on native uvicorn") applies HERE: the proxy's IP-map (`request.client.host` → `agent_containers.bridge_ip`) only resolves on Linux. The Phase 29 acceptance gates must run via `make e2e-inapp-docker` (dockerized harness) NOT native uvicorn. **Plan 29-01 Wave 0 must verify this.**
- **Golden Rule #4 — Root cause first.** The Phase 27 `_parse_stripped` "fix" was the canonical root-cause-skipped pattern (returned `0/unknown` instead of investigating WHY a2a_jsonrpc and zeroclaw_native strip usage). Phase 29 fixes the right layer (egress proxy upstream of bot) per the 4-agent confirmation 2026-05-05.
- **Golden Rule #5 — Test everything; spike gray areas BEFORE planning.** The 6 explicit risks in CONTEXT.md + the 9 gray-area risks below (15 total) MUST each have a Wave 0 spike artifact under `.planning/phases/29-llm-egress-proxy/spikes/` before the plan seals. See "Validation Architecture" section.

## Architectural Approach

### 1. FastAPI router shape

```python
# api_server/src/api_server/routes/llm_proxy.py  (new file, Plan 29-04)
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter()

@router.post("/llm/forward/{path:path}")  # single route; path is "chat/completions" / "messages" / "models" / etc.
async def forward(path: str, request: Request) -> StreamingResponse:
    """Egress proxy — bot's outbound LLM call lands here.

    Flow per CONTEXT.md D-01/D-02/D-03/D-07/D-09/D-14/D-15/D-16:

      1. Resolve caller: request.client.host → agent_containers.bridge_ip
         + auth_token check (D-07 defense-in-depth)
      2. Look up upstream_provider + decrypted key (in-memory cache, populated
         at lifespan startup + on /start)
      3. Read + JSON-decode body (~16KB typical chat payload)
      4. Body mutation: inject 'user' (D-08), 'stream_options.include_usage' (D-03)
      5. Build upstream URL + headers (D-17 dispatch table)
      6. Idempotency-Key check (D-16); replay if hit
      7. httpx.AsyncClient.stream upstream
      8. StreamingResponse back to bot, tee-parsing each chunk
      9. On stream-close: usage_recorder.record_usage(...) + (OpenRouter only)
         Temporal start_workflow('backfill_openrouter_cost', ...) ~2s delay
    """
```

> **Path naming choice:** `{path:path}` accepts the upstream provider's native path (`chat/completions`, `messages`, `models`). The bot's SDK was originally configured with `OPENAI_BASE_URL=https://openrouter.ai/api/v1`, so when the runner swaps in `OPENAI_BASE_URL=http://api_server:8000/v1/llm/forward`, the SDK appends `/chat/completions` automatically and the proxy route catches it as `path="chat/completions"`. **No SDK reconfiguration required — bot code is untouched.** [VERIFIED: by inspection of openai-python's `BaseClient.build_request` which always appends the relative path to `base_url`.]

### 2. Lifespan startup additions (`main.py::lifespan`)

```python
# After `app.state.recipe_index = InappRecipeIndex(...)` (line 189-193 today):

# Phase 29 — proxy BYOK cache rehydration (D-02 restart resilience)
from .services.proxy_byok_cache import ProxyBYOKCache
app.state.proxy_byok_cache = ProxyBYOKCache(db_pool=app.state.db)
await app.state.proxy_byok_cache.rehydrate_from_db()  # decrypts all running rows

# Phase 29 — proxy IP map + 60s refresh task (D-07)
from .services.proxy_ip_map import ProxyIPMap, refresh_loop
app.state.proxy_ip_map = ProxyIPMap(db_pool=app.state.db,
                                     docker_client=app.state.docker_client,
                                     network_name=settings.docker_network_name)
await app.state.proxy_ip_map.refresh()  # initial population
app.state.proxy_ip_refresh_task = asyncio.create_task(
    refresh_loop(app.state.proxy_ip_map, stop=app.state.inapp_stop, interval_s=60.0),
    name="proxy_ip_refresh"
)

# Phase 29 — separate httpx client for upstream LLM calls (different timeout
# profile from bot_http_client: 5s connect, 600s read; max_connections=100 because
# proxy is N:1 with bot containers).
app.state.proxy_upstream_client = httpx.AsyncClient(
    timeout=httpx.Timeout(600.0, connect=5.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
)
```

[ASSUMED] The proxy_ip_refresh_task piggybacks on `app.state.inapp_stop` for shutdown signalling — same pattern as the reaper/outbox tasks lines 248-258.

### 3. Provider dispatcher (deps-free, easy to test)

```python
# api_server/src/api_server/services/proxy_dispatcher.py  (new, Plan 29-03)

@dataclass(frozen=True)
class UpstreamSpec:
    base_url: str
    auth_header_name: str
    auth_value_template: str  # "Bearer {key}" or "{key}"
    extra_headers: dict[str, str]
    sse_format: str  # "openai" | "anthropic"

PROVIDERS: dict[str, UpstreamSpec] = {
    "openrouter": UpstreamSpec(
        base_url="https://openrouter.ai/api/v1",
        auth_header_name="Authorization",
        auth_value_template="Bearer {key}",
        extra_headers={
            "HTTP-Referer": "https://agentplayground.dev",  # OR analytics
            "X-Title": "Agent Playground",
        },
        sse_format="openai",
    ),
    "openai": UpstreamSpec(
        base_url="https://api.openai.com/v1",
        auth_header_name="Authorization",
        auth_value_template="Bearer {key}",
        extra_headers={},
        sse_format="openai",
    ),
    "anthropic": UpstreamSpec(
        base_url="https://api.anthropic.com",
        auth_header_name="x-api-key",
        auth_value_template="{key}",
        extra_headers={"anthropic-version": "2023-06-01"},
        sse_format="anthropic",
    ),
}
```

### 4. Streaming tee (the load-bearing core)

```python
async def _stream_proxy_response(
    upstream_resp: httpx.Response,
    parser: StreamUsageParser,
) -> AsyncIterator[bytes]:
    """Forward each chunk to the bot AND feed it to the parser."""
    async for chunk in upstream_resp.aiter_raw():
        parser.feed(chunk)         # synchronous, byte-level append + scan
        yield chunk                 # forwarded to bot in real-time
    # When upstream closes, parser.finalize() returns ParsedUsage
```

`StreamingResponse(_stream_proxy_response(...), media_type="text/event-stream")` returns immediately to the bot; FastAPI walks the async iterator, the bot sees each chunk in real-time, and at end-of-stream the parser has accumulated the final-chunk `usage` block (OpenAI/OpenRouter) or the `message_delta` event (Anthropic). [VERIFIED: matches MSV `modifyResponseForRecording` lines 313-430 in `recorder.go` — the body is read into memory, parsed, then `resp.Body = io.NopCloser(bytes.NewReader(bodyBytes))` puts it back. Python's `aiter_raw` is the asyncio analog without the buffer-then-emit antipattern.]

> **Important:** OpenRouter / OpenAI return `Content-Encoding: gzip` for non-streaming responses on chunked HTTP. For SSE streams, gzip is NOT applied (text/event-stream). The MSV proxy explicitly handles gzip in the JSON-non-SSE path (`recorder.go:335-343`); the AP proxy's stream-tee parser only needs to handle gzip for the non-streaming case (response body fully buffered, then ungzipped, then parsed). [VERIFIED via cookbook + community examples.]

## Provider Dispatch Table

> Flesh-out of D-09 + D-17. One row per (provider, route-class) combination.

| Provider | Recipe-declared `runtime.process_env.api_key` | Upstream URL base | Auth header | Required header(s) | Body mutation (D-14) | SSE format | Post-hoc lookup |
|---|---|---|---|---|---|---|---|
| **openrouter** | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | `Authorization: Bearer <key>` | `HTTP-Referer`, `X-Title` (analytics, NOT required by API) | inject `user="ap_<uid>_<aid>"`, `stream_options.include_usage=true` when `stream==true` | `data: {...}` lines, OpenAI-compatible; final chunk has `choices=[]`, `usage` populated | `GET https://openrouter.ai/api/v1/generation?id=<X-Generation-Id>` (~1–3s after stream close) |
| **openai** | `OPENAI_API_KEY` | `https://api.openai.com/v1` | `Authorization: Bearer <key>` | none | inject `stream_options.include_usage=true` when `stream==true`; `user` injection optional (OpenAI accepts a `user` field for abuse monitoring per [OpenAI docs](https://platform.openai.com/docs/api-reference/chat-streaming/streaming)) | `data: {...}` lines; final chunk has `choices=[]`, `usage` populated | none — usage in inline final chunk is canonical |
| **anthropic** | `ANTHROPIC_API_KEY` | `https://api.anthropic.com` | `x-api-key: <key>` (NOT `Authorization`) | `anthropic-version: 2023-06-01` (REQUIRED — direct API calls fail without it; [verified 2026-05-06](https://platform.claude.com/docs/en/api/overview)) | NO `user` field (Anthropic body has no equivalent); per CONTEXT D-14, add `OpenTelemetry: ap_user=<uid>` header instead | `data: {...}` lines with `event:` prefix; **`message_start` carries cumulative `input_tokens` + cache tokens; `message_delta` carries cumulative usage but only `output_tokens` is the new-since-last-event count — DO NOT sum cumulative fields** | none |

> **The Anthropic cumulative-usage gotcha is REAL — multiple integrations have shipped double-counting bugs.** [CITED: [Anthropic streaming docs](https://platform.claude.com/docs/en/build-with-claude/streaming); [langchain-js bug](https://github.com/langchain-ai/langchainjs/issues/10249); [agno-agi bug](https://github.com/agno-agi/agno/issues/6537).] **Parser implementation MUST take cache_creation_input_tokens + cache_read_input_tokens from `message_start` (NOT `message_delta`), and take output_tokens from the LAST `message_delta` (cumulative, not summed).** This is exactly what MSV's `extractTokensFromSSE` does (`recorder.go:222-264`): "message_start: input_tokens nested under message.usage (includes cache tokens); message_delta: output_tokens at top-level usage." Mirror that.

## Streaming Capture Strategy

### OpenAI / OpenRouter (`sse_format="openai"`)

Final chunk shape (verified against OpenAI cookbook + OpenRouter docs):

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","model":"...","choices":[],"usage":{"prompt_tokens":42,"completion_tokens":17,"total_tokens":59}}
data: [DONE]
```

> Edge case: usage chunk MAY appear AFTER `[DONE]` on some upstream impls (OpenRouter has been observed doing this). MSV's `extractTokensFromOpenAISSE` documents this as "Edge case D-18: usage chunk may appear AFTER the [DONE] sentinel" (`recorder.go:148-150`) and uses **last-wins scanning** (don't break on `[DONE]`, keep parsing every line). **Mirror that.**

Parser writes to `record_usage`:
```python
ParsedUsage(
    input_tokens=usage["prompt_tokens"],
    output_tokens=usage["completion_tokens"],
    cache_read_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),  # OpenAI o1+ only
    cache_creation_tokens=0,  # not surfaced by OpenAI/OR streaming
    upstream_request_id=final_chunk["id"],  # or X-Generation-Id from response headers
    stop_reason=None,  # finish_reason on streaming is per-choice on a non-final chunk
    status="success",
)
```

### Anthropic native (`sse_format="anthropic"`)

Anthropic SSE event sequence (verified):
```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","usage":{"input_tokens":42,"cache_creation_input_tokens":100,"cache_read_input_tokens":0,"output_tokens":1}}}

event: content_block_start
event: content_block_delta  (many)
event: content_block_stop

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":17}}

event: message_stop
data: {"type":"message_stop"}
```

Parser writes to `record_usage` from BOTH events:
```python
# From message_start: input_tokens + cache fields (cumulative — OK to read here)
input_tokens = ms["message"]["usage"]["input_tokens"]
cache_creation = ms["message"]["usage"]["cache_creation_input_tokens"]
cache_read = ms["message"]["usage"]["cache_read_input_tokens"]

# From the FINAL message_delta only (cumulative output_tokens — last-wins):
output_tokens = last_message_delta["usage"]["output_tokens"]
stop_reason = last_message_delta["delta"]["stop_reason"]

ParsedUsage(input_tokens=..., output_tokens=..., cache_read_tokens=cache_read, cache_creation_tokens=cache_creation, stop_reason=stop_reason, status="success")
```

### Stream interrupted / 4xx mid-stream

If upstream returns 4xx mid-stream (e.g. context overflow on chunk 5), the response is typically a **properly closed SSE error event** (`event: error\ndata: {...}`), not a TCP reset. **OpenRouter** error events follow `{"error":{"message":...,"code":...}}`. **OpenAI** uses the same shape. **Anthropic** uses `event: error\ndata: {"type":"error","error":{...}}`. The proxy MUST recognize both (a) HTTP status 4xx/5xx on the initial response (no body parse) AND (b) embedded SSE error events (parse + record `usage_logs.status='failed'` even if the response opened with 200 then errored mid-stream). [CITED: [OpenAI streaming-events ref](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events); [Anthropic streaming docs](https://platform.claude.com/docs/en/build-with-claude/streaming).] **PROBE-VAL-04 must verify both branches.**

> **Critical edge: stream cancelled by client (FastAPI `StreamingResponse` connection-close).** When the bot disconnects mid-stream (rare but possible on Temporal cancellation), the parser will NOT see the final usage chunk. MSV documents this in passing — OpenAI documents explicitly: *"If the stream is interrupted or cancelled, you may not receive the final usage chunk."* [CITED] **Decision:** record `usage_logs.status='failed'` with `tokens=0` on `aclose()` exception in the StreamingResponse generator. Parser exposes `was_complete: bool`; recorder branches on it.

## OpenRouter Post-Hoc Backfill

### Activity shape

```python
# api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py  (new, Plan 29-06)

@dataclass
class BackfillOpenRouterCostInput:
    usage_log_id: str         # UUID stringified
    generation_id: str        # X-Generation-Id captured at proxy time

class BackfillActivities:
    @activity.defn(name="backfill_openrouter_cost")
    async def backfill(self, inp: BackfillOpenRouterCostInput) -> None:
        """Fetch /api/v1/generation, UPDATE usage_logs.cost_usd."""
        # Initial 2s delay (D-03 — empirically OpenRouter's data takes
        # 1-3s to populate the generation endpoint; PROBE-VAL-03 measures
        # exact percentile)
        await asyncio.sleep(2.0)

        async with self.upstream_client as client:
            for retry_idx, backoff_s in enumerate([0.0, 2.0, 5.0]):
                if backoff_s > 0:
                    await asyncio.sleep(backoff_s)
                resp = await client.get(
                    f"https://openrouter.ai/api/v1/generation?id={inp.generation_id}",
                    headers={"Authorization": f"Bearer {self.platform_key}"},  # any valid OR key
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    data = resp.json()["data"]
                    cost_usd = Decimal(str(data["total_cost"]))
                    async with self.db_pool.acquire() as conn:
                        await conn.execute("""
                            UPDATE usage_logs
                            SET cost_usd = $1
                            WHERE id = $2
                        """, cost_usd, UUID(inp.usage_log_id))
                    return
                if resp.status_code == 404 and retry_idx < 2:
                    continue   # not yet populated — retry
                # Other status — log + give up (visibility gap, not a regression)
                activity.logger.warning(...)
                return
```

### Workflow trigger

The proxy's response-close handler does:

```python
if provider == "openrouter" and generation_id:
    await temporal_client.start_workflow(
        BackfillOpenRouterCostWorkflow.run,
        BackfillOpenRouterCostInput(usage_log_id=row_id, generation_id=generation_id),
        id=f"backfill_or_{row_id}",
        task_queue=settings.temporal_task_queue,
    )
```

> **Auth subtlety:** the backfill activity needs a valid OpenRouter key to call `/api/v1/generation`. **It can use the SAME per-deploy BYOK key that was used for the original chat call** (cached in `proxy_byok_cache`) — the generation endpoint accepts the same key that minted the generation. No need for a platform-wide key. **PROBE-VAL-03 must verify this** (alternative: if generation lookup is keyed to the requester, our key must match the original).

## Idempotency Strategy

### Header format & race resolution

Bot's outbound LLM call carries `Idempotency-Key: msg-<message_id>-<workflow_run_id>`. CONTEXT.md D-16 picks this format; **the planner must inject the bot-side header from the runner's env-injection layer (every BYOK SDK accepts `Idempotency-Key` headers as pass-throughs in OpenAI's SDK ≥1.x)**. **PROBE-VAL-12 verifies this** for the `openai` Python SDK + `langchain-openai` (the two libraries the 5 recipes use).

### Cache shape (planner's call — see O-02)

**Recommendation: reuse `services/idempotency.py`'s Postgres `idempotency_keys` table** rather than a fresh Redis cache. The existing primitive has the exact semantics Phase 29 needs (advisory-lock-serialized check-or-reserve, 24h TTL, body-hash mismatch detection). The schema already accommodates `verdict_json JSONB` for the cached response (proxy stores the parsed `ParsedUsage` + `cost_usd` + `upstream_request_id` there).

CONTEXT D-16 says "Redis-backed cache with namespace `ap:proxy:idem:`" — this is **factually inconsistent with the existing IdempotencyMiddleware** (which is Postgres-backed, NOT Redis). Two interpretations:
1. Author meant "the SAME pattern as IdempotencyMiddleware uses" → use Postgres.
2. Author wanted a separate Redis cache for the proxy hot-path (lower latency than PG advisory lock).

**The research recommendation is interpretation 1.** Redis would be valid but it duplicates a primitive that already exists, contradicts Golden Rule #5 (don't invent new mechanisms when an existing one works), and adds a new failure mode (proxy idempotency invariant breaks if Redis goes down — PG is already in the critical path). Plan 29 should escalate this if the planner reads CONTEXT D-16 differently. — flagged as **O-02**.

### Concurrent retries

Same race as `/v1/runs`: two concurrent retries with the same key. Resolution is the existing `services/idempotency.py:check_or_reserve` — advisory lock on `(user_id, key)` serializes; first writer wins, second sees the cached row and replays.

For the "in-flight" representation: existing primitive has only `hit/miss/mismatch`. **If two retries arrive 50ms apart and the upstream call is still in flight (3-second response), retry #2 hits `miss` because no row has been written yet → it forwards to upstream too → DOUBLE charge.** **This is a real gap in the existing primitive that Phase 29 must close.** Mitigation: use `INSERT ... ON CONFLICT DO NOTHING` to write a "reserved" row at request start (with `verdict_json = NULL`), then UPDATE the row after the upstream call lands. Requires schema review — see O-03.

### TTL

24h matches Stripe + the existing primitive. Honor it.

## Restart Resilience Audit

### api_server restart

| Component | Behavior on restart |
|---|---|
| `proxy_byok_cache` | Lifespan startup queries `agent_containers WHERE container_status='running'`, decrypts each `provider_key_enc`, populates `{(user_id, agent_instance_id) → key}`. Live chats resume after ~1-2s rehydration. |
| `proxy_ip_map` | Refreshed at lifespan startup via Docker SDK + DB join (`agent_containers.container_id` → `Container.attrs.NetworkSettings.Networks[<bridge>].IPAddress`). 60s refresh task starts after. |
| In-flight upstream stream | Killed mid-stream when uvicorn shuts down. Bot sees `httpx.ReadError`. The `forward_to_agent` activity retries (`[1s, 2s, 4s]` per `forward_to_agent.py:145`). On retry, the bot makes a NEW LLM call — proxy's new instance is up, processes it normally. **The Idempotency-Key (D-16) prevents double-billing.** |
| `usage_logs` row written before restart | Already committed — visible to next request. |
| `usage_logs` row NOT yet written (stream interrupted on shutdown) | **Visibility gap.** D-15 says record `status='failed'` on incomplete streams; the cleanup must run as a finally-block in the StreamingResponse, NOT in a separate task that the lifespan-shutdown could cancel. |

**PROBE-VAL-06 must verify:** kill api_server during a streaming response → bot retries → new api_server processes the retry → `usage_logs` has exactly ONE row for the message (not zero, not two).

### Bot container restart

Bot's `OPENAI_BASE_URL` still points at api_server's stable hostname. `proxy_byok_cache` still has the key cached (key was not stored in the bot container). **No re-paste, no manual intervention.**

### api_server + bot both restart

Same as bot-restart — proxy rehydrates from DB, bot reconnects to proxy.

### `agent_containers.bridge_ip` uniqueness

CONTEXT mentions Docker bridge can re-assign an IP after container removal. **The IP→user lookup MUST scope to `container_status='running'` to avoid mis-identifying a freshly-removed user.** The `bridge_ip` column is set at deploy time per `agent_containers` schema, but is **NOT currently a column** — it's resolved on-the-fly by `inapp_recipe_index.get_container_ip()`. **Phase 29 needs to either ADD a `bridge_ip` column to `agent_containers` (preferred — the proxy needs the inverse map IP→container_id, which is hard to compute on every request) OR keep using docker-inspect and walk all containers each lookup (~10× slower).** [VERIFIED: by reading `services/inapp_recipe_index.py:346-396`.] — flagged as **O-04**.

> **Mitigation if bridge_ip column is added:** include it in the partial unique index so the IP-map can do a single B-tree lookup without a full scan. Add to `agent_containers` migration 013.

## Validation Architecture (Nyquist)

> Phase 29 has `nyquist_validation` enabled (Wave 0 mandatory per CLAUDE.md Golden Rule #5). Every gray-area mechanism MUST have a spike artifact under `.planning/phases/29-llm-egress-proxy/spikes/` BEFORE the plan seals.

### Test framework

| Property | Value |
|---|---|
| Framework | pytest 8.x (existing); plus `httpx-sse` for SSE parser tests; testcontainers-pg + docker SDK for live infra |
| Config | `api_server/pyproject.toml` + `api_server/conftest.py` (existing) |
| Quick run | `cd api_server && uv run pytest tests/test_proxy_*.py -x` |
| Full suite | `make test-api` + `make e2e-inapp-docker` (the latter is the macOS-bridge-IP-aware harness — REQUIRED for proxy E2E) |

### Phase 29 acceptance gate → test map

| Gate | Behavior | Test type | Automated command | Spike before sealing |
|---|---|---|---|---|
| 1 | nano-kaiku E2E records `usage_logs` row with non-zero tokens + cost | integration (real PG, real Docker, real OR) | `make e2e-inapp-docker -- -k test_phase29_nano_kaiku_e2e` | PROBE-VAL-09 |
| 2 | OpenRouter post-hoc backfill within ±$0.001 | integration | `pytest tests/test_proxy_backfill.py -k openrouter_within_tolerance` | PROBE-VAL-03 |
| 3 | Mobile Usage screen shows non-zero $ within 5s | integration (full stack) | `make screens-e2e -- -k test_phase29_ticker_updates` | (composite of 1+2) |
| 4 | Pre-existing `unknown` rows deleted at migration | unit (Alembic upgrade) | `pytest api_server/tests/test_migration_013.py` | none — schema change |
| 5 | Failure injection → `bot_timeout` | integration | `make e2e-inapp-docker -- -k test_phase29_kill_api_during_chat` | PROBE-VAL-06 |
| 6 | BYOK key never logged | grep + log-redact integration | `pytest tests/test_log_redact.py::test_proxy_byok_redaction` | none |
| 7 | Other 4 recipes work via legacy path | regression — full 5×5 e2e matrix | `make e2e-inapp-docker -- --recipe hermes,nullclaw,zeroclaw,nanobot,openclaw` | none |

### Sampling rate

- **Per task commit:** unit subset `pytest api_server/tests/test_proxy_*.py -x` (~30s)
- **Per wave merge:** `make test-api` (~3min) + `make e2e-inapp-docker -- -k phase29` (~6min)
- **Phase gate:** full `make test-api` + `make e2e-inapp-docker` (no `-k` filter; ~25min)

### Wave 0 spike artifacts (REQUIRED before plan seals — CLAUDE.md #5)

Each must produce a markdown artifact under `.planning/phases/29-llm-egress-proxy/spikes/PROBE-VAL-NN.md` with verbatim transcript.

- [ ] **PROBE-VAL-01: `stream_options.include_usage` on OpenAI + OpenRouter — verify final-chunk shape + post-DONE-edge.** Real curl against both providers; capture raw `data:` lines; confirm `choices=[]` + `usage={...}` on final chunk; confirm whether usage arrives BEFORE or AFTER `[DONE]` (MSV docs both shapes). Confirm `stream_options.include_usage=true` works with `stream=false` too (or fails cleanly).
- [ ] **PROBE-VAL-02: `X-Generation-Id` header preservation on OpenRouter (success + 4xx + streaming).** Real curl with success path, real curl with deliberate 401, real curl with `stream=true`; for each: dump full response headers; confirm presence of `X-Generation-Id`. Document streaming-case header location (some impls put it on the response start, some on the trailer).
- [ ] **PROBE-VAL-03: OpenRouter `/api/v1/generation` post-hoc lookup latency.** Loop 5+ chat completions; for each, record `t0=stream_close_ts`, then poll `/api/v1/generation?id=<id>` every 500ms until 200; record p50/p95/p99 of the delay. Document the 404→200 transition cleanly. Confirm `total_cost` field shape and units (USD).
- [ ] **PROBE-VAL-04: Auth swap per provider.** Three real curls against an empty key, an invalid key, a wrong-shape key for each of OR / Anthropic / OpenAI. Confirm 401 distinguishes good/bad. Confirm `anthropic-version: 2023-06-01` is REQUIRED (omit it; expect 400). Confirm OpenRouter's `/v1/key` endpoint shape + 401 body.
- [ ] **PROBE-VAL-05: Bot-side trust — `OPENAI_BASE_URL` honoring across the 5 recipes.** Read each recipe's `runtime.process_env` block + corresponding upstream image. For each, run a `docker run --rm -e OPENAI_BASE_URL=https://example.com/v1 -e OPENAI_API_KEY=test ...` and inspect: did the bot try to call `example.com`? Document hardcoded URLs / SDK quirks (e.g. langchain wrappers that ignore `OPENAI_BASE_URL`). **Phase 29 only flips nano-kaiku, but the researcher must surface which OTHER recipes will likely break in Phase 30.**
- [ ] **PROBE-VAL-06: Idempotency on Temporal retry.** Force a `forward_to_agent` activity to retry (kill the bot mid-call). Confirm exactly one `usage_logs` row results. Document the race when retry #2 arrives while retry #1 is still upstream-pending — does the existing `services/idempotency.py` primitive handle in-flight or only completed?
- [ ] **PROBE-VAL-07: age-cipher reuse for `provider_key_enc`.** Round-trip: encrypt a known plaintext with `encrypt_channel_config(user_id, {"key": "or-test-..."}); decrypt; assert match. Verify the master key is loaded from the same `AP_CHANNEL_MASTER_KEY` env var the existing `channel_config_enc` uses. Confirm dev-fallback (32 zero bytes) works locally without ops setup.
- [ ] **PROBE-VAL-08: FastAPI `StreamingResponse` + `httpx.AsyncClient.stream` tee — no buffering.** Open a real OpenRouter stream from a fixture client, proxy it through a test FastAPI route, measure the wall-clock between bot's first-byte-received and api_server's first-byte-from-upstream. Must be ≤50ms (proxy adds negligible latency). Confirm no chunked-transfer-encoding corruption; confirm gzip-encoded responses pass through correctly when `stream=false`; confirm premature client disconnect produces a clean exception (not a silent leak).
- [ ] **PROBE-VAL-09: `Idempotency-Key` cache shape in Postgres (or Redis if interpretation 2 wins).** Pick: extend `idempotency_keys` to support proxy use case OR cut a new table. Verify ON CONFLICT semantics for in-flight requests. Document TTL collision with the chat path's 24h cache (proxy uses different keys → no collision, but verify).
- [ ] **PROBE-VAL-10: Docker bridge IP refresh cadence.** Restart a running container with `docker restart <id>` — does its IP change? On real Linux Docker (not macOS Desktop), validate IP-map refresh semantics. Confirm Docker SDK's `from_env()` exposes `events()` (yes — `client.events(filters={'event': ['start', 'die']})`). Decide: 60s polling (CONTEXT D-07) vs `events()` stream subscription (lower-latency).
- [ ] **PROBE-VAL-11: OpenRouter `/key` endpoint validation.** Hit `GET /api/v1/key` with valid key → 200 + `{"data":{...balance...}}`; with invalid → 401. Confirm sub-keys / scoped keys also return 200. Document the response shape so the deploy-handler can extract balance for future Phase B preflight.
- [ ] **PROBE-VAL-12: Bearer-prefix placeholder injection.** Set `OPENAI_API_KEY=ap-proxy-<random>` on the bot container; verify `openai` Python SDK ≥1.x and `langchain-openai` accept any non-empty bearer value (don't probe key shape). Confirm `Idempotency-Key` header passes through both libraries' request layers.
- [ ] **PROBE-VAL-13: Anthropic SSE shape — cumulative vs delta.** Real Anthropic streaming call; capture raw SSE; verify `message_start.message.usage` carries `cache_creation_input_tokens`/`cache_read_input_tokens`/`input_tokens`; verify `message_delta.usage.output_tokens` is cumulative; verify the FINAL `message_delta` carries the total (last-wins-on-output). Document the subtlety that summing all `message_delta.usage` produces the wrong answer.
- [ ] **PROBE-VAL-14: Streaming 4xx mid-stream.** Force OpenRouter into a context-overflow on chunk 5 (send a deliberately huge prompt with a low max_tokens that lets the first few chunks come back before the upstream model errors). Inspect: is the response status 200 + embedded SSE error, OR is the stream terminated with a TCP reset? Document parser strategy that survives both.
- [ ] **PROBE-VAL-15: `agent_containers.bridge_ip` uniqueness.** Stop a container, deploy a new one — does it get the same IP? If yes, the IP→user map MUST scope to `container_status='running'` to avoid identifying a freshly-removed user. Verify the partial unique index `ix_agent_containers_agent_instance_running` doesn't collide with a future bridge_ip column index.

## Risk Register

> 6 explicit risks from CONTEXT.md + 9 gray-area risks. Probability is the planner's estimate based on the spike outcome.

| # | Risk | Probability | Blast radius | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Streaming `include_usage` not honored on `stream=false` (or vice versa) | LOW | Recipe migration delayed | PROBE-VAL-01 | Wave 0 spike |
| R2 | `X-Generation-Id` missing on OpenRouter error / streaming responses | LOW-MED | OR backfill rows orphan | PROBE-VAL-02 + fall-back to pre-stream-close response header capture | Wave 0 spike |
| R3 | OpenRouter `/api/v1/generation` lookup latency >5s (target ≤2s) | MED | Backfill UPDATE arrives slow → ticker shows stale `cost_usd` for ~3-5s | PROBE-VAL-03; if >5s, raise the activity delay; also: don't block ticker on backfill (use proxy's inline final-chunk usage as the canonical "displayed" value, with backfill as a refinement) | Wave 0 spike |
| R4 | Auth header semantics drift (Anthropic `x-api-key` vs OpenAI `Authorization`) | LOW | Bot calls 401 | PROBE-VAL-04; codify in `PROVIDERS` dict (Architecture §3) | Plan 29-03 |
| R5 | Bot recipe ignores `OPENAI_BASE_URL` (langchain wrapper / hardcoded) | MED-HIGH (per CONTEXT, multiple recipes have quirks already) | Phase 30 recipes break one-by-one | PROBE-VAL-05 — surface BEFORE Phase 30 plans them; flag affected recipes | Wave 0 spike |
| R6 | Idempotency double-charge on concurrent retry | MED (in-flight gap is real per O-03) | $0.01–$0.10 per double-charge; for $0 ticker that's just a cosmetic dup; for Phase B that's unacceptable | PROBE-VAL-06 + O-03 mitigation (insert "reserved" row at request start) | Plan 29-05 |
| R7 | age-cipher master key not loaded at lifespan startup → all decrypts fail post-restart | LOW | api_server boots but every chat fails | PROBE-VAL-07; lifespan startup invokes a single round-trip encrypt/decrypt to fail-loud | Plan 29-04 |
| R8 | StreamingResponse buffers entire response (defeats "real-time chat") | LOW (httpx + FastAPI is well-trodden) | Bot UX regresses by 2-30s | PROBE-VAL-08 | Wave 0 spike |
| R9 | Idempotency cache shape ambiguity (Redis per CONTEXT vs PG per existing primitive) | HIGH (CONTEXT inconsistency) | Plan rewrites; potentially TWO idempotency primitives in the codebase | O-02 — escalate before sealing | Discuss-phase amendment |
| R10 | Docker bridge IP changes on container restart | LOW on Linux; HIGH on macOS Desktop | IP-map serves stale → 401 | PROBE-VAL-10 + 60s refresh + `docker events` subscription | Plan 29-04 |
| R11 | OpenRouter `/key` endpoint doesn't reliably distinguish valid/invalid | LOW | D-02b deploy-time validation produces false negatives | PROBE-VAL-11 | Wave 0 spike |
| R12 | OpenAI SDK rejects placeholder Bearer (`ap-proxy-...`) | LOW (per OpenAI source: SDK accepts any non-empty string) | Bot fails at startup before reaching proxy | PROBE-VAL-12 — verify both `openai` Python and langchain | Wave 0 spike |
| R13 | Anthropic streaming cumulative-usage double-count | HIGH if not handled (multiple integrations bugged) | OVER-COUNT cost by 30-50% | PROBE-VAL-13 + parser implementation strictly mirroring MSV's `extractTokensFromSSE` | Plan 29-03 |
| R14 | Streaming 4xx parser strategy missing | MED | `usage_logs.status='failed'` rows missing → user reports "ticker doesn't update" | PROBE-VAL-14 | Plan 29-05 |
| R15 | `agent_containers.bridge_ip` uniqueness — stale row in `running` state with same IP as a new container | LOW (partial unique index already enforces 1 running per agent) | Cross-user identification — SECURITY incident | PROBE-VAL-15 + scope every IP→user lookup to `container_status='running'` | Plan 29-04 |

## Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| HTTP reverse proxy with body mutation + streaming tee | Custom asyncio TCP forwarder | `httpx.AsyncClient.stream` + FastAPI `StreamingResponse` | Both are battle-tested; httpx handles chunked transfer encoding, gzip, redirect, retries-on-connect-error; FastAPI is the existing app framework |
| Per-user encrypted secret storage | Custom Fernet/AES-GCM wrapper | Existing `crypto/age_cipher.py` | Already audited; per-user KEK derivation; same primitive Phase 22+ uses for `channel_config_enc`. PROBE-VAL-07 confirms reuse. |
| SSE parsing | Hand-rolled regex | The MSV pattern: byte-level `bytes.Split` on `\n`, prefix-strip `data: `, `json.Unmarshal` per chunk, last-wins | Anthropic's cumulative gotcha + OpenRouter's post-DONE-edge are well-understood; mirror MSV's two extractors verbatim. |
| Docker container IP discovery | Custom subprocess parsing | Existing `services/inapp_recipe_index.get_container_ip` (already tested + cached) | The inverse map (IP → container_id) is new but builds on the same primitive |
| Idempotency cache | New Redis hash schema | Existing `services/idempotency.py` (PG-backed; tested; correct semantics) | See O-02 — the existing primitive handles 90% of Phase 29's needs; the in-flight gap is a single SQL pattern (insert-reserved-row) |
| Temporal activity for backfill | Inline asyncio.create_task | Real Temporal activity (per D-10) | Survives api_server restart; observable; built-in retry budget |

## Common Pitfalls

### Pitfall 1: Anthropic `message_delta.usage` cumulative double-count
**What goes wrong:** parser sums `output_tokens` across all `message_delta` events → cost is 2-5× over real.
**Why:** Anthropic SSE spec says `message_delta.usage` is **cumulative** — `output_tokens` in the LAST event is the total, not a delta.
**Avoid:** Use last-wins (only the FINAL `message_delta` value matters). Mirror MSV `extractTokensFromSSE` lines 222-264.
**Warning sign:** comparing `total_cost` from OpenRouter `/api/v1/generation` vs proxy-computed cost shows proxy cost is HIGHER for streaming Anthropic calls.

### Pitfall 2: `[DONE]` sentinel breaks parsing of post-DONE usage chunk
**What goes wrong:** parser stops on `data: [DONE]` → never sees the trailing `data: {...usage...}` chunk → `tokens=0`.
**Why:** OpenRouter (and some OpenAI-compatible impls) emit usage AFTER the DONE sentinel.
**Avoid:** Don't break on `[DONE]`. Continue scanning until end-of-stream. Mirror MSV `extractTokensFromOpenAISSE` (`recorder.go:148-150`).
**Warning sign:** OpenRouter `/api/v1/generation` cost is non-zero, proxy `usage_logs.input_tokens=0`, `output_tokens=0`.

### Pitfall 3: Source IP changes mid-stream (proxy chain)
**What goes wrong:** if there's a load balancer or sidecar between bot and api_server, `request.client.host` is the LB's IP, not the bot's → IP-map lookup fails → 401.
**Why:** the existing AP topology has bot → api_server directly on the Docker bridge — NO proxy in between today. But H8 (CI gating) might add one.
**Avoid:** treat `request.headers.get('x-forwarded-for')` as the truth IF the runner is configured to set it; add a **`X-AP-Bridge-IP` request header** the bot sets to its own bridge IP at startup; cross-reference with `request.client.host` for defense.
**Warning sign:** proxy logs show `client.host=172.18.0.1` (the bridge's gateway, NOT a container).

### Pitfall 4: Streaming response client disconnect leaves orphan in-flight upstream
**What goes wrong:** bot disconnects (Temporal cancellation, network blip); StreamingResponse generator's iterator is `aclose()`d; but the upstream `httpx` request keeps streaming bytes that go nowhere.
**Why:** httpx stream cleanup needs explicit `await response.aclose()`.
**Avoid:** wrap `_stream_proxy_response` in `try/finally` that calls `await upstream_resp.aclose()`. Verified in PROBE-VAL-08.
**Warning sign:** OpenRouter dashboard shows orphaned generations / pending billing.

### Pitfall 5: Lifespan rehydration runs BEFORE Docker SDK is connected
**What goes wrong:** `proxy_byok_cache.rehydrate_from_db()` works (just reads from PG), but `proxy_ip_map.refresh()` fails because `app.state.docker_client` isn't set yet.
**Why:** lifespan is line-by-line; ordering matters.
**Avoid:** rehydrate AFTER `app.state.docker_client = _docker_for_index.from_env()` (currently line 188). Wrap in try/except so a transient Docker daemon hiccup at boot doesn't crash api_server.
**Warning sign:** lifespan logs show `proxy_ip_map.refresh_failed_init`.

### Pitfall 6: `Idempotency-Key` cache size explosion
**What goes wrong:** `idempotency_keys` table grows by 1 row per chat message; at 1000 msgs/day it's manageable, at 100k/day it's a 24h buffer of 100k rows.
**Why:** existing primitive has 24h TTL but no built-in GC.
**Avoid:** existing cron in Plan 19-07 already handles this for `/v1/runs`. Verify it covers the proxy namespace too (likely yes — same table, same expires_at column).

### Pitfall 7: BYOK key leaks into proxy's structured logs via httpx exception
**What goes wrong:** an httpx-level exception (`ConnectError`, `ReadTimeout`) surfaces with the request URL + headers in the traceback → BYOK leaks into stdout.
**Why:** zerolog (Python: `structlog`) doesn't auto-redact request headers.
**Avoid:** mirror `agent_lifecycle.py:_redact_creds` — explicit replace pass on every exception string before it reaches the logger. Verified by acceptance gate #6.
**Warning sign:** PROBE-VAL-07 fails or `tests/test_log_redact.py::test_proxy_byok_redaction` fails.

## Code Examples

### Bot-side (recipe `via_proxy: true`) env injection (Plan 29-08)

```python
# tools/run_recipe.py — extends build_activation_substitutions

if recipe.get("runtime", {}).get("via_proxy"):
    # Strip the real provider key; bot won't see it
    process_env.pop("OPENROUTER_API_KEY", None)
    process_env.pop("ANTHROPIC_API_KEY", None)
    process_env.pop("OPENAI_API_KEY", None)
    # Wire the SDK to the proxy
    api_var = recipe["runtime"]["process_env"]["api_key"]  # "OPENROUTER_API_KEY" etc.
    base_url_var = api_var.replace("_API_KEY", "_BASE_URL")  # "OPENROUTER_BASE_URL"
    process_env["OPENAI_BASE_URL"] = "http://api_server:8000/v1/llm/forward"
    process_env[base_url_var] = "http://api_server:8000/v1/llm/forward"  # for non-OpenAI providers
    # Placeholder so OpenAI SDK doesn't bail on missing key validation
    process_env["OPENAI_API_KEY"] = f"ap-proxy-{inapp_auth_token}"
```

### Proxy route handler (Plan 29-04)

```python
# Source: based on MSV anthropicproxy/proxy.go lines 65-180, 217-298, 446-457
# Translated to FastAPI/asyncio idiom

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter()

@router.post("/llm/forward/{path:path}")
async def forward(path: str, request: Request) -> StreamingResponse:
    # 1. Identify caller (D-07)
    bridge_ip = request.client.host
    caller = await request.app.state.proxy_ip_map.get(bridge_ip)
    if caller is None:
        raise HTTPException(401, "unknown caller")
    user_id, agent_instance_id, expected_token = caller

    # Defense-in-depth: validate Authorization Bearer matches inapp_auth_token
    auth = request.headers.get("Authorization", "")
    bearer = auth.removeprefix("Bearer ").strip()
    if bearer != f"ap-proxy-{expected_token}":
        raise HTTPException(401, "auth token mismatch")

    # 2. Resolve provider + decrypted key
    provider, key = await request.app.state.proxy_byok_cache.get(user_id, agent_instance_id)
    if key is None:
        raise HTTPException(500, "BYOK key not in cache (D-02 rehydration failed)")

    spec = PROVIDERS[provider]

    # 3. Read + mutate body
    body_bytes = await request.body()
    body = json.loads(body_bytes) if body_bytes else {}
    if provider in ("openrouter", "openai"):
        if body.get("stream"):
            body["stream_options"] = {"include_usage": True}
        if provider == "openrouter":
            body["user"] = f"ap_{user_id}_{agent_instance_id}"
    body_out = json.dumps(body, separators=(",", ":")).encode()

    # 4. Build upstream URL + headers
    upstream_url = f"{spec.base_url}/{path}"
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body_out)),
        spec.auth_header_name: spec.auth_value_template.format(key=key),
        **spec.extra_headers,
    }
    if provider == "anthropic":
        headers["OpenTelemetry"] = f"ap_user={user_id}"  # D-14

    # 5. Idempotency check (D-16)
    idem_key = request.headers.get("Idempotency-Key")
    if idem_key:
        cached = await proxy_idempotency_check(user_id, idem_key, body_out)
        if cached is not None:
            return JSONResponse(cached["verdict"], status_code=200)

    # 6. Open upstream stream
    client = request.app.state.proxy_upstream_client
    is_streaming = body.get("stream", False)
    upstream_resp = await client.send(
        client.build_request("POST", upstream_url, content=body_out, headers=headers),
        stream=True,
    )

    # 7. Capture metadata (X-Generation-Id, status)
    generation_id = upstream_resp.headers.get("X-Generation-Id")
    status_code = upstream_resp.status_code

    # 8. Stream back, tee-parsing
    parser = StreamUsageParser(provider=provider, sse_format=spec.sse_format)

    async def _gen():
        try:
            async for chunk in upstream_resp.aiter_raw():
                parser.feed(chunk)
                yield chunk
        finally:
            await upstream_resp.aclose()
            await _record_usage_and_maybe_backfill(
                request.app, parser, user_id, agent_instance_id,
                generation_id, status_code, idem_key, body_out,
            )

    return StreamingResponse(
        _gen(),
        status_code=status_code,
        media_type=upstream_resp.headers.get("content-type", "application/json"),
    )
```

## Sources

### Primary (HIGH confidence)
- [VERIFIED] `api_server/src/api_server/services/usage_recorder.py` — direct read of existing recorder
- [VERIFIED] `api_server/src/api_server/services/idempotency.py` — direct read; PG-backed (NOT Redis as CONTEXT D-16 implies)
- [VERIFIED] `api_server/src/api_server/middleware/idempotency.py` — direct read of existing IdempotencyMiddleware
- [VERIFIED] `api_server/src/api_server/services/inapp_recipe_index.py` — direct read; `get_container_ip` is the inverse-map foundation
- [VERIFIED] `api_server/src/api_server/services/recipes_loader.py` lines 57-61 — `_ENV_TO_PROVIDER` map (D-17 source of truth)
- [VERIFIED] `api_server/src/api_server/services/inapp_dispatcher.py` lines 72-228 — 3-way contract switch the proxy partially replaces
- [VERIFIED] `api_server/src/api_server/temporal/activities/forward_to_agent.py` lines 145-200 — Temporal retry semantics + httpx error taxonomy (D-05 reuse)
- [VERIFIED] `api_server/src/api_server/crypto/age_cipher.py` — direct read; `encrypt_channel_config(user_id, dict)` shape; master key from `AP_CHANNEL_MASTER_KEY`; per-user KEK via HKDF
- [VERIFIED] `api_server/alembic/versions/010_usage_logs_cost_weights.py` — usage_logs schema; `status IN ('success','error','unknown')` CHECK constraint (D-15 widens to add `'failed'`)
- [VERIFIED] `api_server/alembic/versions/003_agent_containers.py` — agent_containers schema; `channel_config_enc bytea` precedent for `provider_key_enc bytea`
- [VERIFIED] `api_server/alembic/versions/012_cost_weights_extra_models.py` — most-recent migration; Phase 29 migration is `013`
- [VERIFIED] `api_server/src/api_server/main.py` lifespan — startup ordering for new resources
- [VERIFIED] `api_server/src/api_server/routes/agent_lifecycle.py` — start_agent flow; `_redact_creds` pattern; provider_key never logged
- [VERIFIED] `recipes/nanobot.yaml` + `recipes/hermes.yaml` — direct reads; `runtime.process_env.api_key` is the canonical D-17 signal
- [VERIFIED] `/Users/fcavalcanti/dev/meusecretariovirtual/api/pkg/anthropicproxy/proxy.go` lines 60-238, 240-300, 436-479 — config + lifecycle + OpenRouter director (mirror)
- [VERIFIED] `/Users/fcavalcanti/dev/meusecretariovirtual/api/pkg/anthropicproxy/recorder.go` lines 21-264 — APICallRecorder + extractTokensFromSSE + extractTokensFromOpenAISSE (mirror)
- [VERIFIED] `/Users/fcavalcanti/dev/meusecretariovirtual/api/internal/service/byok_service.go` lines 25-80 — BYOK validation pattern (D-02b mirror)
- [CITED: docs.openrouter.ai] [OpenRouter Streaming](https://openrouter.ai/docs/api/reference/streaming) — confirmed `X-Generation-Id` header, post-DONE-edge of usage chunks
- [CITED: docs.openrouter.ai] [OpenRouter Generation](https://openrouter.ai/docs/api/api-reference/generations/get-generation) — confirmed `/api/v1/generation` returns canonical USD `total_cost`
- [CITED: docs.openrouter.ai] [OpenRouter Authentication](https://openrouter.ai/docs/api/reference/authentication) — confirmed `GET /api/v1/key` returns 200 with valid key, 401 with invalid
- [CITED: platform.openai.com] [OpenAI Streaming Reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events) — confirmed `stream_options.include_usage`, `usage` on FINAL chunk only with empty `choices`
- [CITED: platform.claude.com] [Anthropic Streaming](https://platform.claude.com/docs/en/build-with-claude/streaming) — confirmed `message_delta.usage` is **cumulative**, NOT delta
- [CITED: platform.claude.com] [Anthropic API Overview](https://platform.claude.com/docs/en/api/overview) — confirmed `anthropic-version: 2023-06-01` REQUIRED on direct API calls

### Secondary (MEDIUM confidence)
- [Anthropic streaming bug — langchain-js](https://github.com/langchain-ai/langchainjs/issues/10249) — corroborates cumulative-usage gotcha
- [Anthropic streaming bug — agno-agi](https://github.com/agno-agi/agno/issues/6537) — same bug class, different framework
- [OpenAI Devs tweet on stream_options](https://x.com/OpenAIDevs/status/1787573348496773423) — confirms feature behavior
- [OpenAI cookbook streaming](https://cookbook.openai.com/examples/how_to_stream_completions) — usage chunk format

### Tertiary (LOW confidence — flagged for verification)
- [ASSUMED] OpenRouter `/api/v1/generation` accepts the same per-deploy key that minted the generation — needs PROBE-VAL-03 verification
- [ASSUMED] `openai` Python SDK ≥1.x accepts arbitrary Bearer prefixes including `ap-proxy-...` without validation — needs PROBE-VAL-12
- [ASSUMED] Docker SDK `events()` stream subscription is reliable for IP-map invalidation — alternative is 60s polling per CONTEXT D-07
- [ASSUMED] Adding `bridge_ip` as a new column to `agent_containers` is preferable to on-the-fly Docker SDK lookups for the hot path — PROBE-VAL-15 measures the latency delta

## Open Questions

> Items the planner should escalate or research-amend BEFORE the plan seals. Each is tagged with the CONTEXT cross-reference.

1. **O-01: `recipes/nano-kaiku.yaml` does not exist.** CONTEXT D-04 + D-18 + D-19 + acceptance-gate-1 all reference "nano-kaiku" as the first cutover recipe. Repo today has `nanobot.yaml` (close, different name). Either:
   - (a) Phase 29 includes "create `recipes/nano-kaiku.yaml`" as a Plan 09 prerequisite (pure new-recipe work; could be ~1 day), OR
   - (b) Substitute `nanobot` as the first cutover target (already validated, openai_compat, simplest existing path).
   Recommendation: **(b)**. Adds zero new recipe-validation surface; `nanobot.yaml` already PASS-verified (cells from 2026-04-29). Plan 29 amendment AMD-01 should rename "nano-kaiku" → "nanobot" throughout CONTEXT.md. Discuss-phase escalation needed.

2. **O-02: Idempotency cache backend — Postgres (existing) vs Redis (CONTEXT D-16 implies).** The existing `IdempotencyMiddleware` is **Postgres-backed**, not Redis. CONTEXT D-16 says "Redis-backed cache with namespace `ap:proxy:idem:`". Two options:
   - (a) Use existing PG primitive (recommended — single source of truth; advisory-lock semantics already correct).
   - (b) Build a new Redis cache (CONTEXT-faithful but duplicates a primitive; adds Redis as a new failure mode for billing correctness).
   Recommendation: **(a)** with a CONTEXT amendment AMD-02. Discuss-phase escalation needed.

3. **O-03: In-flight idempotency gap.** Existing `services/idempotency.py:check_or_reserve` returns `("miss", None)` when no row exists. If retry #1 is upstream-pending (3-second response) and retry #2 arrives 50ms later, retry #2 also gets `miss` → also forwards upstream → **double charge**. Phase 29 needs to close this:
   - (a) Insert a "reserved" row (`verdict_json=NULL`, `expires_at=NOW()+5s`) at the START of the upstream call; retry #2 sees the reserved row and waits / fails.
   - (b) Use Redis `SETNX` for the in-flight slot (and the proper Redis path of O-02).
   Recommendation: **(a)** — extends existing PG primitive; same advisory-lock pattern. Plan 29-05 task.

4. **O-04: `agent_containers.bridge_ip` column.** Today the IP is resolved on-the-fly by `get_container_ip()`. The proxy needs the INVERSE map (IP → container_id) on every request. Two options:
   - (a) Add `bridge_ip TEXT NULL` to `agent_containers` (migration 013); maintain via runner at start time + on Docker network events.
   - (b) Walk all running containers via Docker SDK on every IP map miss.
   Recommendation: **(a)** — sub-millisecond lookup vs ~50-200ms Docker walk. PROBE-VAL-15 verifies uniqueness scope (running-only).

5. **O-05: `bot_http_client` reuse vs separate `proxy_upstream_client`.** Existing `app.state.bot_http_client` has 600s read timeout (matches D-40 chat budget). The proxy makes calls TO upstream LLM, not to bots. Different connection pool sizes (100 vs 50) + different retry profile suggests a **separate client**. Recommendation: separate. Plan 29-04 task.

6. **O-06: Recipe `nano-kaiku` (or `nanobot` per O-01) flag location.** CONTEXT D-18 says `runtime.via_proxy: true` is the recipe field. But the runner reads `runtime.process_env.api_key` (D-17 signal) — should `via_proxy` also live under `runtime`, or is it a sibling key? Recommendation: **`runtime.via_proxy: true`** as CONTEXT specifies — keeps the BYOK-related signals in one block.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| HTTP egress proxy (forward bot → upstream LLM) | api_server (FastAPI route) | — | D-01: same uvicorn process |
| BYOK key custody (encrypt at rest, decrypt at request time) | api_server (PG + age_cipher) | runner (env injection per D-18) | D-02: per-deploy column; runner only sees plaintext at start time |
| BYOK validation on deploy | api_server (deploy handler) | upstream provider | D-02b: synchronous probe BEFORE persistence |
| Streaming usage capture | api_server (proxy tee parser) | — | D-03: parser sits in StreamingResponse generator |
| Post-hoc OpenRouter cost backfill | Temporal worker (activity) | api_server (workflow-trigger) | D-10: needs durable retries; ~2s after stream close |
| User identification | api_server (IP-map service) | Docker daemon (network events) | D-07: source IP + auth_token defense-in-depth |
| Idempotency on retry | api_server (extend `services/idempotency.py`) | — | D-16: existing PG primitive |
| Body mutation (inject `user`, `stream_options`) | api_server (proxy director) | — | D-08, D-14 |
| Auth header swap (Bearer ↔ x-api-key) | api_server (proxy dispatcher) | — | D-17: provider table |
| Recording row write | api_server (`record_usage` direct call) | — | D-10: existing async writer |
| Failure classification | api_server (proxy error handler) | Temporal forward_to_agent retry | D-05 fail-closed; existing `[1s,2s,4s]` budget |

## Standard Stack

> Library + version verified against existing pyproject.toml as of 2026-05-06. Phase 29 adds NO new top-level dependencies (everything is reuse).

| Library | Version | Purpose | Why standard |
|---|---|---|---|
| `fastapi` | 0.115.x (existing) | Proxy route + StreamingResponse | Already the app framework |
| `httpx[http2]` | 0.27.x (existing) | Upstream HTTP client + streaming | Already used by `bot_http_client`; native asyncio; supports `stream=True` |
| `asyncpg` | 0.30.x (existing) | PG access in proxy + activity | Already in lifespan pool |
| `pyrage` (age) | (existing) | Decrypt provider_key_enc | Already in `crypto/age_cipher.py` |
| `temporalio` | 1.x (existing) | Backfill activity | Already wired into worker |
| `redis.asyncio` | (existing) | NOT USED for proxy idempotency per O-02 recommendation; still used for SSE/outbox | (no change for Phase 29) |
| `pydantic` | 2.x (existing) | Request/response models | Existing |
| `cryptography` | (existing) | HKDF for KEK | Already in age_cipher |

### Installation

No new deps. Confirm with: `cd api_server && uv sync` after CONTEXT.md confirmation.

### Version verification

```bash
cd api_server && uv pip show fastapi httpx asyncpg pyrage temporalio
```
[VERIFIED 2026-05-06: all packages already installed; phase adds zero new top-level deps.]

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|---|---|---|---|---|
| Postgres 17 | usage_logs UPDATE, idempotency_keys, provider_key_enc | ✓ (docker-compose.dev.yml) | 17 | — |
| Redis 7 | (NOT used for proxy idempotency per O-02; existing chat path uses it) | ✓ | 7 | — |
| Docker daemon | IP-map lookup + bridge network resolution | ✓ on Linux; PARTIAL on macOS Desktop | — | `make e2e-inapp-docker` for macOS gates (CLAUDE.md gotcha) |
| Temporal frontend | backfill activity scheduling | ✓ (docker-compose.dev.yml) | 1.x | — |
| OpenRouter API | upstream calls + post-hoc generation lookup + key validation | ✓ (live; per-deploy BYOK) | — | none — REQUIRED for Phase 29 acceptance |
| Anthropic API | (Phase 29 doesn't flip an Anthropic-direct recipe; D-04 = nanobot/nano-kaiku is OpenRouter-routed) | n/a for Phase 29 | — | required for Phase 30 cutover |
| OpenAI API | same as above | n/a for Phase 29 | — | required later |

**No missing dependencies blocking Phase 29.** OpenRouter is the only upstream needed; per-deploy BYOK keys are user-supplied.

## Restart Resilience Audit (consolidated)

See "Architectural Approach §4" + "Risk Register R7/R10/R15". The load-bearing claim is:

1. api_server boot rehydrates `proxy_byok_cache` from `agent_containers WHERE container_status='running'`.
2. api_server boot rehydrates `proxy_ip_map` from `agent_containers WHERE container_status='running'` joined with Docker SDK `Container.attrs.NetworkSettings.Networks[<bridge>].IPAddress`.
3. In-flight upstream streams are dropped (intentional per D-05 fail-closed); Temporal retries the bot's call.
4. PROBE-VAL-06 verifies exactly-once `usage_logs` row across the api_server-restart-mid-stream scenario.

## Assumptions Log

> Items tagged `[ASSUMED]` in this research that need PROBE-VAL or discuss-phase confirmation.

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | The same per-deploy BYOK key that minted a generation can be used to fetch `/api/v1/generation` | OpenRouter Post-Hoc Backfill | Backfill activity 401s; `cost_usd` stays at proxy-computed (still correct, just less precise). Mitigation: PROBE-VAL-03 |
| A2 | OpenAI Python SDK + langchain-openai accept any non-empty Bearer prefix without validation | D-18 placeholder injection | Bot fails at startup with "invalid API key format". Mitigation: PROBE-VAL-12 |
| A3 | Docker SDK `events()` reliably emits container start/die in real-time | IP-map invalidation | 60s polling fallback (CONTEXT D-07 default) — degraded not broken. Mitigation: PROBE-VAL-10 |
| A4 | Adding `bridge_ip` column is preferred over on-the-fly Docker walks | O-04 | If Docker walks are cheap enough, the column is unnecessary schema churn. Mitigation: PROBE-VAL-15 measure |
| A5 | OpenRouter's `X-Generation-Id` is on EVERY response (success + 4xx + streaming) | D-03 / D-16 | Backfill misses some rows. Mitigation: PROBE-VAL-02 |
| A6 | The IP→user lookup MUST scope to `container_status='running'` to avoid cross-user mis-identification on container churn | O-04, R15 | SECURITY incident: messages from user A's freshly-removed container's IP get mapped to user B's new container. Mitigation: PROBE-VAL-15 + scope filter |

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; all reuse with proven versions
- Architecture: HIGH — directly mirrors MSV proxy.go + recorder.go pattern; FastAPI/httpx async equivalents are well-trodden
- Streaming capture: MEDIUM — Anthropic cumulative-usage gotcha + post-DONE-edge are known landmines; PROBE-VAL-13/PROBE-VAL-01 close them
- Idempotency: MEDIUM — O-02/O-03 ambiguity needs discuss-phase resolution; in-flight gap is real
- Restart resilience: MEDIUM-HIGH — pattern proven for `bot_http_client` + `recipe_index`; new pieces follow the same shape
- Recipe migration (D-04): LOW until O-01 (nano-kaiku doesn't exist) is resolved

**Research date:** 2026-05-06
**Valid until:** 2026-06-06 (Phase B Stripe paywall scope may invalidate the "ap_multiplier=1.0 forever" assumption)
