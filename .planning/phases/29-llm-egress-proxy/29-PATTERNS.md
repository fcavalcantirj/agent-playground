# Phase 29: LLM egress proxy + provider-agnostic cost capture — Pattern Map

**Mapped:** 2026-05-06
**Files analyzed:** 25 new + 7 modified = 32 total
**Analogs found:** 32 / 32

## File Classification

### NEW files

| New file | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `api_server/src/api_server/routes/llm_proxy.py` | route (FastAPI router) | streaming + request-response | `api_server/src/api_server/routes/agent_lifecycle.py` (long-await + Bearer header pattern) + `api_server/src/api_server/routes/usage.py` (small router shape) | role-match (no streaming-tee analog exists in codebase yet — see "GREENFIELD" callout below) |
| `api_server/src/api_server/services/proxy_byok_cache.py` | service (in-process cache + DB rehydration) | DB-rehydrate-once + in-memory KV | `api_server/src/api_server/services/inapp_recipe_index.py` (in-process cache + lazy load + `asyncio.Lock`) | role-match (closest existing in-process cache); **MSV mirror** `api/pkg/anthropicproxy/proxy.go:116-117, 332-360` |
| `api_server/src/api_server/services/proxy_ip_map.py` | service (DB-driven IP lookup + 60s refresh task) | poll-loop-driven cache | `api_server/src/api_server/services/inapp_reaper.py` (60s loop + `asyncio.wait_for` on stop_event) + `api_server/src/api_server/services/inapp_recipe_index.py:346-396` (`get_container_ip` raw shape) | role-match; **MSV mirror** `proxy.go:240-298` (`startIPRefresh`, `refreshIPMap`) |
| `api_server/src/api_server/services/proxy_dispatcher.py` | service (provider dispatch table) | pure-function lookup | `api_server/src/api_server/services/recipes_loader.py:57-61` (`_ENV_TO_PROVIDER` const dict pattern) | exact pattern (const dict + dataclass) |
| `api_server/src/api_server/services/stream_parser.py` | service (SSE byte-level parser) | streaming transform | `api_server/src/api_server/services/usage_recorder.py:108-166` (`_parse_openai_compat`) — provides the OpenAI-compat dict-shape extraction the streaming parser must mirror once it has assembled the final chunk | role-match (existing parser is dict-mode; streaming-byte-mode is GREENFIELD); **MSV mirror** `recorder.go:148-264` (`extractTokensFromOpenAISSE`, `extractTokensFromSSE`) |
| `api_server/src/api_server/services/byok_validator.py` | service (synchronous outbound HTTP probe) | request-response | `api_server/src/api_server/services/openrouter_models.py` (httpx GET against OpenRouter; cache_lock + 10s timeout dedicated client) | role-match; **MSV mirror** `api/internal/service/byok_service.go:25-80` |
| `api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py` | activity (Temporal class-bound, async DB UPDATE + httpx GET) | request-response (with retry budget) | `api_server/src/api_server/temporal/activities/forward_to_agent.py` (class-bound activity + `[0,1s,2s,4s]` retry budget + httpx) + `api_server/src/api_server/temporal/activities/record_usage.py` (DB activity wrapping a service-layer function) | exact (combine the two analogs) |
| `api_server/alembic/versions/013_phase29_proxy_columns.py` | migration | DDL | `api_server/alembic/versions/011_phase28_workflow_id_idempotency.py` (column-add + partial index pattern + 32-char revision id gotcha) + `api_server/alembic/versions/010_usage_logs_cost_weights.py` (multi-table DDL + seed data) | exact |
| `tools/migrate_phase29_nanobot_cutover.py` | one-shot migration script | DB UPDATE + Docker stop | `tools/migrate_phase28_stuck_rows.py` (asyncpg connect + `--dry-run` + `--limit` safety cap + `DATABASE_URL` env) | exact |
| `tools/spike_streaming_tee.py`, `tools/spike_openrouter_usage.py`, `tools/spike_openrouter_generation_latency.py`, `tools/spike_anthropic_sse.py`, `tools/spike_byok_validation.py`, `tools/spike_recipe_base_url_honor.py` | spike scripts | one-shot probes | `api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py` (pytest-style spike with `subprocess.run(["docker"])` + Path traversal) | role-match (note: existing spikes live under `api_server/tests/spikes/test_*.py` as pytest modules — recommend mirroring that location/shape over `tools/spike_*.py` per CONTEXT mention) |
| `api_server/tests/services/test_proxy_byok_cache.py` | test | unit + integration | `api_server/tests/services/test_inapp_recipe_index.py` | exact |
| `api_server/tests/services/test_proxy_ip_map.py` | test | unit + integration | `api_server/tests/services/test_inapp_recipe_index.py` (cache + Docker SDK pattern) + `api_server/tests/test_inapp_reaper.py` (loop + stop_event) | exact |
| `api_server/tests/services/test_proxy_dispatcher.py` | test | unit (pure function) | `api_server/tests/services/test_usage_recorder.py:78-88` (pure-function const-dict tests) | exact |
| `api_server/tests/services/test_stream_parser.py` | test | unit (byte-level parser) | `api_server/tests/services/test_usage_recorder.py:90-100+` (`_parse_openai_compat` shape tests) | role-match |
| `api_server/tests/services/test_byok_validator.py` | test | integration (httpx + respx) | `api_server/tests/spikes/test_respx_authlib.py` + `api_server/tests/spikes/test_respx_intercepts_pyjwk_fetch.py` (respx mock-upstream pattern) | role-match |
| `api_server/tests/routes/test_llm_proxy.py` | test | integration (FastAPI + asyncpg + respx) | `api_server/tests/routes/test_agent_messages_post.py` + `api_server/tests/routes/test_agent_lifecycle_inapp.py` | exact |
| `api_server/tests/temporal/test_backfill_openrouter_cost_activity.py` | test | integration (Temporal worker + asyncpg + respx) | `api_server/tests/temporal/test_forward_to_agent_activity.py` | exact |
| `api_server/tests/test_migration_013_proxy_columns.py` | test | DDL round-trip | `api_server/tests/test_migration_011_phase28.py` | exact |
| `api_server/tests/spikes/test_age_cipher_provider_key.py` | test (PROBE-VAL-07) | unit (round-trip) | `api_server/src/api_server/crypto/age_cipher.py` (encrypt + decrypt round-trip; the existing tests live in tests/auth or implicit) | role-match |
| `api_server/tests/spikes/test_idempotency_in_flight.py` | test (PROBE-VAL-06 / O-03 race) | concurrency | `api_server/tests/test_idempotency.py` (existing primitive's race tests) | exact |
| `api_server/tests/spikes/test_docker_bridge_refresh.py` | test (PROBE-VAL-10) | integration (Docker SDK) | `api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py` | exact |
| `api_server/tests/spikes/test_ap_proxy_placeholder_bearer.py` | test (PROBE-VAL-12) | integration (openai SDK probe) | `api_server/tests/spikes/test_respx_intercepts_pyjwk_fetch.py` (respx + library probe pattern) | role-match |

### MODIFIED files

| Modified file | Role | Existing pattern to extend |
|---|---|---|
| `api_server/src/api_server/main.py` | lifespan | extend lifespan ordering pattern (line 99–262); insert proxy-cache + proxy-ip-map + proxy_upstream_client AFTER `app.state.docker_client` (line 188) BEFORE the 22b watcher reattach block (line 264). Mirror the `inapp_tasks` task-spawn shape (line 248–262) for `proxy_ip_refresh_task` |
| `api_server/src/api_server/services/usage_recorder.py` | service | add `_parse_anthropic_native(response)` + `_parse_anthropic_native_stream(events)` next to `_parse_openai_compat` (line 108–166); add cumulative-output-tokens last-wins handling per AMD-07 |
| `api_server/src/api_server/services/recipes_loader.py` | service | extend `to_summary` (line 142–246) — surface `runtime.via_proxy` field on `RecipeSummary` (D-18 + AMD-06); also extend `_synthesize_provider_compat_in_place` (line 64–111) if needed |
| `api_server/src/api_server/services/inapp_recipe_index.py` | service | extend the index — wire env injection for `via_proxy: true` per AMD-06 (dispatch on `process_env.api_key` for OpenAI vs Anthropic placeholder vars). Or — more likely — leave this file alone and put the env-injection in `runner_bridge` / `inapp_substitutions` (verify during planning) |
| `api_server/src/api_server/services/idempotency.py` | service | add AMD-03 reserved-row pattern: extend `check_or_reserve` with an `INSERT ... ON CONFLICT DO NOTHING` "reserved" row + 100ms-poll-on-conflict (5s max) for the in-flight gap. Schema migration adds `status='in_flight'` to `idempotency_keys` |
| `recipes/nanobot.yaml` | recipe (YAML) | add `runtime.via_proxy: true` (single-line addition to the `runtime:` block at lines 40–48) |
| `api_server/src/api_server/temporal/worker.py` (likely) + `api_server/src/api_server/temporal/workflows/dispatch_message.py` (maybe) | temporal | register `BackfillOpenRouterCostActivities.backfill` on the worker; optionally add a workflow shim if D-10 says "go through a workflow not just a bare activity" |

---

## Pattern Assignments

### `api_server/src/api_server/routes/llm_proxy.py` (route, streaming + request-response)

**Primary analog:** `api_server/src/api_server/routes/agent_lifecycle.py`
**Secondary analog:** `api_server/src/api_server/routes/usage.py` (small router shape)
**MSV mirror:** `api/pkg/anthropicproxy/proxy.go:65-180, 217-298, 446-457` (Go ReverseProxy `Director` + `ModifyResponse` lifecycle)
**Greenfield part:** the streaming-tee (`httpx.AsyncClient.stream` → `StreamingResponse(_gen())`) has no existing analog in the codebase — RESEARCH.md §Architectural Approach §4 + §"Code Examples" provide the canonical Python shape; PROBE-VAL-08 verifies it.

**Imports pattern** (mirror `routes/agent_lifecycle.py:38-77`):
```python
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..auth.deps import require_user        # NOT used here — proxy authenticates via IP-map + bearer match
from ..models.errors import ErrorCode, make_error_envelope
from ..services.proxy_byok_cache import ProxyBYOKCache
from ..services.proxy_dispatcher import PROVIDERS, UpstreamSpec
from ..services.proxy_ip_map import ProxyIPMap
from ..services.stream_parser import StreamUsageParser
from ..services.usage_recorder import record_usage

router = APIRouter()
_log = logging.getLogger("api_server.llm_proxy")
```

**Error envelope pattern** (copy verbatim from `routes/agent_lifecycle.py:92-111` and `routes/usage.py:107-121`):
```python
def _err(status: int, code: str, message: str, *, param: str | None = None,
         category: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )
```

**Long-await DB-scope discipline** (mirror `routes/agent_lifecycle.py:34-37` Pitfall 4 — never hold `pool.acquire()` across a long await). The proxy's hot path opens NO DB scope on the streaming branch; the post-stream `record_usage` call opens its own short-lived `pool.acquire()` inside the `_gen()` finally block.

**Core proxy pattern** (RESEARCH.md §Code Examples lines 552-642 — copy as the implementation skeleton):
```python
@router.post("/llm/forward/{path:path}")
async def forward(path: str, request: Request) -> StreamingResponse:
    # 1. Identify caller (D-07): IP-map + auth-token defense-in-depth
    bridge_ip = request.client.host
    caller = await request.app.state.proxy_ip_map.get(bridge_ip)
    if caller is None:
        raise HTTPException(401, "unknown caller")
    user_id, agent_instance_id, expected_token = caller

    auth = request.headers.get("Authorization", "")
    bearer = auth.removeprefix("Bearer ").strip()
    if bearer != f"ap-proxy-{expected_token}":
        raise HTTPException(401, "auth token mismatch")

    # 2. Resolve provider + decrypted key
    provider, key = await request.app.state.proxy_byok_cache.get(user_id, agent_instance_id)
    if key is None:
        raise HTTPException(500, "BYOK key not in cache")
    spec = PROVIDERS[provider]

    # 3. Body mutation (D-08, D-14, AMD-06)
    body_bytes = await request.body()
    body = json.loads(body_bytes) if body_bytes else {}
    if provider in ("openrouter", "openai") and body.get("stream"):
        body["stream_options"] = {"include_usage": True}
    if provider == "openrouter":
        body["user"] = f"ap_{user_id}_{agent_instance_id}"
    body_out = json.dumps(body, separators=(",", ":")).encode()

    # 4. Build upstream URL + headers
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body_out)),
        spec.auth_header_name: spec.auth_value_template.format(key=key),
        **spec.extra_headers,
    }
    if provider == "anthropic":
        headers["OpenTelemetry"] = f"ap_user={user_id}"

    # 5. Idempotency (D-16 + AMD-02 reuse PG primitive + AMD-03 reserved row)
    idem_key = request.headers.get("Idempotency-Key")
    # ... call services.idempotency.check_or_reserve + reserved-row insert ...

    # 6. Open upstream stream
    client: httpx.AsyncClient = request.app.state.proxy_upstream_client
    upstream_resp = await client.send(
        client.build_request("POST", f"{spec.base_url}/{path}",
                             content=body_out, headers=headers),
        stream=True,
    )

    # 7. Stream-tee back, parsing each chunk
    parser = StreamUsageParser(provider=provider, sse_format=spec.sse_format)

    async def _gen():
        try:
            async for chunk in upstream_resp.aiter_raw():
                parser.feed(chunk)
                yield chunk
        finally:
            await upstream_resp.aclose()
            await _record_and_maybe_backfill(
                request.app, parser, user_id, agent_instance_id,
                upstream_resp.headers.get("X-Generation-Id"),
                upstream_resp.status_code, idem_key, body_out,
            )

    return StreamingResponse(
        _gen(),
        status_code=upstream_resp.status_code,
        media_type=upstream_resp.headers.get("content-type", "application/json"),
    )
```

**BYOK redaction pattern** (copy from `routes/agent_lifecycle.py:114-136 _redact_creds`):
```python
def _redact_creds(text: str, key: str) -> str:
    """Replace BYOK key with <REDACTED> before logging — Phase 29 acceptance gate #6."""
    if not text or not key or len(key) < 8:
        return text
    return text.replace(key, "<REDACTED>")
```

---

### `api_server/src/api_server/services/proxy_byok_cache.py` (service, in-process cache + lifespan rehydrate)

**Primary analog:** `api_server/src/api_server/services/inapp_recipe_index.py` lines 219-272, 322-342 (in-process dict-cache + `asyncio.Lock` + lazy load)
**MSV mirror:** `api/pkg/anthropicproxy/proxy.go:116-117, 332-360`

**Class shape** (mirror `InappRecipeIndex.__init__` lines 240-271):
```python
class ProxyBYOKCache:
    """In-memory {(user_id, agent_instance_id) → decrypted_key} cache.

    Restart resilience (D-02): lifespan calls rehydrate_from_db()
    which queries agent_containers WHERE container_status='running',
    decrypts each provider_key_enc via age_cipher.decrypt_channel_config,
    and populates the dict before any chat traffic hits the proxy.
    """
    def __init__(self, db_pool: Any) -> None:
        self._db_pool = db_pool
        self._lock = asyncio.Lock()
        self._cache: dict[tuple[UUID, UUID], tuple[str, str]] = {}
        # value tuple = (provider, decrypted_key)
```

**Rehydrate pattern** (mirror `routes/agent_lifecycle.py:330` for age_cipher usage + `inapp_outbox.py:_pump_once` for batched-DB-read shape):
```python
async def rehydrate_from_db(self) -> int:
    """Lifespan-startup decrypt + populate. Returns count loaded."""
    from ..crypto.age_cipher import decrypt_channel_config
    async with self._db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id, agent_instance_id, upstream_provider, provider_key_enc
            FROM agent_containers
            WHERE container_status = 'running'
              AND provider_key_enc IS NOT NULL
        """)
    loaded = 0
    for row in rows:
        try:
            blob = decrypt_channel_config(row["user_id"], bytes(row["provider_key_enc"]))
            key = blob["key"]
            async with self._lock:
                self._cache[(row["user_id"], row["agent_instance_id"])] = (
                    row["upstream_provider"], key,
                )
            loaded += 1
        except Exception:
            _log.exception("proxy_byok_cache.rehydrate_failed_row",
                           extra={"agent_instance_id": str(row["agent_instance_id"])})
    return loaded
```

**Hot-path get pattern** (mirror `inapp_recipe_index.get_inapp_block` lines 322-342, but async):
```python
async def get(self, user_id: UUID, agent_instance_id: UUID) -> tuple[str | None, str | None]:
    async with self._lock:
        v = self._cache.get((user_id, agent_instance_id))
    return v if v else (None, None)

async def set(self, user_id: UUID, agent_instance_id: UUID,
              provider: str, decrypted_key: str) -> None:
    """Called by start_agent / deploy after a fresh successful BYOK validation."""
    async with self._lock:
        self._cache[(user_id, agent_instance_id)] = (provider, decrypted_key)

async def invalidate(self, user_id: UUID, agent_instance_id: UUID) -> None:
    async with self._lock:
        self._cache.pop((user_id, agent_instance_id), None)
```

---

### `api_server/src/api_server/services/proxy_ip_map.py` (service, DB-driven IP lookup + 60s refresh task)

**Primary analog:** `api_server/src/api_server/services/inapp_reaper.py:167-196 reaper_loop` (60s tick + `asyncio.wait_for(stop_event.wait(), timeout=...)` cancel discipline) + `inapp_recipe_index.py:346-396 get_container_ip` (Docker SDK shape)
**MSV mirror:** `proxy.go:240-298 startIPRefresh + refreshIPMap`

**Class shape** (mirror `InappRecipeIndex` again):
```python
class ProxyIPMap:
    """{bridge_ip → (user_id, agent_instance_id, inapp_auth_token)} cache.

    Source: agent_containers.bridge_ip column (AMD-04 — added in
    migration 013) joined with status='running'.
    """
    def __init__(self, db_pool: Any) -> None:
        self._db_pool = db_pool
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[UUID, UUID, str]] = {}

    async def refresh(self) -> int:
        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT bridge_ip, user_id, agent_instance_id, inapp_auth_token
                FROM agent_containers
                WHERE container_status = 'running'
                  AND bridge_ip IS NOT NULL
                  AND inapp_auth_token IS NOT NULL
            """)
        new_cache = {
            str(r["bridge_ip"]): (r["user_id"], r["agent_instance_id"], r["inapp_auth_token"])
            for r in rows
        }
        async with self._lock:
            self._cache = new_cache
        return len(new_cache)

    async def get(self, bridge_ip: str) -> tuple[UUID, UUID, str] | None:
        async with self._lock:
            return self._cache.get(bridge_ip)
```

**Refresh-loop pattern** (copy verbatim from `inapp_reaper.py:167-196`):
```python
PROXY_IP_REFRESH_INTERVAL_S = 60.0

async def refresh_loop(ip_map: ProxyIPMap, stop_event: asyncio.Event,
                       interval_s: float = PROXY_IP_REFRESH_INTERVAL_S) -> None:
    """Lifespan-managed refresh. Mirrors inapp_reaper.reaper_loop."""
    while not stop_event.is_set():
        try:
            await ip_map.refresh()
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("proxy_ip_map.refresh_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
            return
        except asyncio.TimeoutError:
            pass
```

---

### `api_server/src/api_server/services/proxy_dispatcher.py` (service, const dispatch table)

**Primary analog:** `services/recipes_loader.py:55-61 _ENV_TO_PROVIDER` (const dict + module-level)
**MSV mirror:** `proxy.go:508-521` (multi-upstream-in-one-router pattern)

**Const-dict pattern** (RESEARCH.md §3 lines 152-189 — copy verbatim):
```python
from dataclasses import dataclass

@dataclass(frozen=True)
class UpstreamSpec:
    base_url: str
    auth_header_name: str
    auth_value_template: str  # "Bearer {key}" or "{key}"
    extra_headers: dict[str, str]
    sse_format: str           # "openai" | "anthropic"

PROVIDERS: dict[str, UpstreamSpec] = {
    "openrouter": UpstreamSpec(
        base_url="https://openrouter.ai/api/v1",
        auth_header_name="Authorization",
        auth_value_template="Bearer {key}",
        extra_headers={"HTTP-Referer": "https://agentplayground.dev",
                       "X-Title": "Agent Playground"},
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

**Frozen dataclass pattern** (mirror `inapp_recipe_index.py:51-99 InappChannelConfig`).

---

### `api_server/src/api_server/services/stream_parser.py` (service, byte-level SSE parser with last-wins)

**Primary analog:** `services/usage_recorder.py:108-166 _parse_openai_compat` (the dict-mode shape extraction the streaming parser must mirror once it has the final chunk dict in hand).
**MSV mirror:** `recorder.go:148-264` — explicit landmines:
- OpenAI/OpenRouter: don't break on `[DONE]` (post-DONE-edge)
- Anthropic `message_delta.usage.output_tokens` is **cumulative not delta** — last-wins (AMD-07)

**ParsedUsage reuse:** import the existing `ParsedUsage` dataclass from `usage_recorder.py:63-78` — DO NOT redefine.

**Parser-class shape** (greenfield; pattern from MSV recorder.go translated):
```python
from typing import AsyncIterator
from .usage_recorder import ParsedUsage

class StreamUsageParser:
    """Byte-level SSE parser; assembles ParsedUsage by stream-close.

    Two modes per AMD-07 + RESEARCH §Streaming Capture Strategy:
      - sse_format='openai': scan all `data: {...}` lines, last-wins
        on usage. Don't break on [DONE].
      - sse_format='anthropic': capture input_tokens +
        cache_creation_input_tokens + cache_read_input_tokens from
        message_start (final at first event); overwrite output_tokens
        on EACH message_delta (cumulative — last-wins, NOT sum).
    """
    def __init__(self, provider: str, sse_format: str) -> None:
        self._provider = provider
        self._sse_format = sse_format
        self._buf = bytearray()
        self._upstream_request_id: str | None = None
        # OpenAI fields
        self._final_usage: dict | None = None
        # Anthropic fields (AMD-07)
        self._anthropic_input: int = 0
        self._anthropic_cache_read: int = 0
        self._anthropic_cache_creation: int = 0
        self._anthropic_output: int = 0  # last-wins
        self._was_complete: bool = False

    def feed(self, chunk: bytes) -> None:
        """Append + scan complete `\\n`-terminated lines."""
        self._buf.extend(chunk)
        while b"\n" in self._buf:
            line, _, rest = self._buf.partition(b"\n")
            self._buf = bytearray(rest)
            self._scan_line(bytes(line).strip())

    def _scan_line(self, line: bytes) -> None:
        if not line.startswith(b"data: "):
            return
        payload = line[6:].strip()
        if payload == b"[DONE]":
            self._was_complete = True
            return  # do NOT break — post-DONE usage chunk may still arrive
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return

        if self._sse_format == "openai":
            usage = event.get("usage")
            if isinstance(usage, dict):
                self._final_usage = usage  # last-wins
            self._upstream_request_id = event.get("id") or self._upstream_request_id
        else:  # anthropic
            etype = event.get("type")
            if etype == "message_start":
                msg = event.get("message", {})
                u = msg.get("usage", {})
                self._anthropic_input = int(u.get("input_tokens") or 0)
                self._anthropic_cache_creation = int(u.get("cache_creation_input_tokens") or 0)
                self._anthropic_cache_read = int(u.get("cache_read_input_tokens") or 0)
                self._upstream_request_id = msg.get("id")
            elif etype == "message_delta":
                u = event.get("usage", {})
                # AMD-07 — output_tokens is CUMULATIVE; overwrite, NOT sum.
                self._anthropic_output = int(u.get("output_tokens") or self._anthropic_output)

    def finalize(self) -> ParsedUsage:
        if self._sse_format == "openai" and self._final_usage:
            usage = self._final_usage
            cache_read = int(usage.get("cache_read_input_tokens") or 0)
            if cache_read == 0:
                details = usage.get("prompt_tokens_details") or {}
                cache_read = int(details.get("cached_tokens") or 0)
            return ParsedUsage(
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                cache_read_tokens=cache_read,
                cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
                upstream_request_id=self._upstream_request_id,
                status="success" if self._was_complete else "failed",
            )
        if self._sse_format == "anthropic":
            return ParsedUsage(
                input_tokens=self._anthropic_input,
                output_tokens=self._anthropic_output,  # last-wins, NOT sum
                cache_read_tokens=self._anthropic_cache_read,
                cache_creation_tokens=self._anthropic_cache_creation,
                upstream_request_id=self._upstream_request_id,
                status="success" if self._was_complete else "failed",
            )
        return ParsedUsage(status="failed")
```

---

### `api_server/src/api_server/services/byok_validator.py` (service, synchronous outbound HTTP probe)

**Primary analog:** `api_server/src/api_server/services/openrouter_models.py` (httpx GET against OpenRouter, dedicated client, short timeout)
**MSV mirror:** `api/internal/service/byok_service.go:25-80`

**Per-provider probe pattern** (D-02b table — three short async functions; mirror the `openrouter_models.py` shape but each is a single round-trip with no cache):
```python
import httpx

async def validate_openrouter(client: httpx.AsyncClient, key: str) -> bool:
    """GET /api/v1/key — $0 metadata read; 401 on invalid."""
    resp = await client.get(
        "https://openrouter.ai/api/v1/key",
        headers={"Authorization": f"Bearer {key}"},
        timeout=10.0,
    )
    return resp.status_code == 200

async def validate_anthropic(client: httpx.AsyncClient, key: str) -> bool:
    """POST /v1/messages max_tokens=1 — ~$0.00001; 401 on invalid (MSV pattern)."""
    resp = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={"model": "claude-haiku-4-5", "max_tokens": 1,
              "messages": [{"role": "user", "content": "hi"}]},
        timeout=15.0,
    )
    return resp.status_code in (200, 400)  # 400 on truncation is OK; 401 = invalid

async def validate_openai(client: httpx.AsyncClient, key: str) -> bool:
    """GET /v1/models — $0; 401 on invalid."""
    resp = await client.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=10.0,
    )
    return resp.status_code == 200

PROVIDER_VALIDATORS = {
    "openrouter": validate_openrouter,
    "anthropic": validate_anthropic,
    "openai": validate_openai,
}
```

**Caller integration (in `routes/agent_lifecycle.py::start_agent`):** call `PROVIDER_VALIDATORS[provider](app.state.proxy_upstream_client, provider_key)` BEFORE `insert_pending_agent_container` (line 345). On 401 return `_err(401, ErrorCode.UNAUTHORIZED, "BYOK key rejected by upstream", param="Authorization")` — same shape as the existing 401 at line 238.

---

### `api_server/src/api_server/temporal/activities/backfill_openrouter_cost.py` (activity)

**Primary analog:** `api_server/src/api_server/temporal/activities/forward_to_agent.py` (class-bound + retry budget + httpx)
**Secondary analog:** `api_server/src/api_server/temporal/activities/record_usage.py` (DB-write activity wrapping a service-layer call)

**Class-bound activity shape** (copy verbatim from `forward_to_agent.py:73-92` for the `__init__` + `@activity.defn` discipline + module-level placeholder pattern at lines 239-251):
```python
class BackfillOpenRouterCostActivities:
    def __init__(self, *, db_pool: Any, upstream_client: httpx.AsyncClient,
                 byok_cache: ProxyBYOKCache) -> None:
        self.db_pool = db_pool
        self.upstream_client = upstream_client
        self.byok_cache = byok_cache

    @activity.defn(name="backfill_openrouter_cost")
    async def backfill(self, inp: dict[str, Any]) -> None:
        """Fetch /api/v1/generation, UPDATE usage_logs.cost_usd."""
        await asyncio.sleep(2.0)  # PROBE-VAL-03: empirically 1-3s settle

        usage_log_id = UUID(inp["usage_log_id"])
        generation_id = inp["generation_id"]
        user_id = UUID(inp["user_id"])
        agent_instance_id = UUID(inp["agent_instance_id"])

        # Per RESEARCH §A1 ASSUMED: the per-deploy BYOK key that minted
        # the generation can be used to fetch /generation. PROBE-VAL-03 confirms.
        provider, key = await self.byok_cache.get(user_id, agent_instance_id)
        if not key:
            activity.logger.warning("backfill.no_byok_key",
                                    extra={"agent_instance_id": str(agent_instance_id)})
            return

        for retry_idx, backoff_s in enumerate([0.0, 2.0, 5.0]):
            if backoff_s > 0:
                await asyncio.sleep(backoff_s)
            resp = await self.upstream_client.get(
                f"https://openrouter.ai/api/v1/generation?id={generation_id}",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()["data"]
                cost_usd = Decimal(str(data["total_cost"]))
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE usage_logs SET cost_usd = $1 WHERE id = $2",
                        cost_usd, usage_log_id,
                    )
                return
            if resp.status_code == 404 and retry_idx < 2:
                continue
            activity.logger.warning("backfill.gave_up",
                                    extra={"status": resp.status_code,
                                           "usage_log_id": str(usage_log_id)})
            return


# Module-level placeholder — fail-loud import path (mirror forward_to_agent.py:239-251)
@activity.defn(name="backfill_openrouter_cost")
async def backfill_openrouter_cost(inp: dict[str, Any]) -> None:
    raise NotImplementedError(
        "Workers register BackfillOpenRouterCostActivities.backfill (bound method); "
        "the module-level function is an import-path placeholder only."
    )
```

**Worker registration** (the `BackfillOpenRouterCostActivities` instance is constructed in `temporal/worker.py` and added to the activities list — mirror however `ForwardActivities` is registered there).

---

### `api_server/alembic/versions/013_phase29_proxy_columns.py` (migration)

**Primary analog:** `api_server/alembic/versions/011_phase28_workflow_id_idempotency.py` (column-add + partial index + 32-char revision id gotcha)
**Secondary analog:** `api_server/alembic/versions/010_usage_logs_cost_weights.py` (multi-table DDL + seed/wipe DML)

**Revision-id gotcha** (copy from `011_phase28_workflow_id_idempotency.py:62-77, 84-87`):
- Filename: `013_phase29_proxy_columns.py`
- DB-stored `revision = "013_phase29_proxy_columns"` (28 chars — fits the `varchar(32)` constraint)
- `down_revision = "012_cost_weights_extra_models"`

**Column-add + partial-index pattern** (copy from `011_phase28_workflow_id_idempotency.py:93-137`):
```python
def upgrade() -> None:
    # AMD-04: agent_containers.bridge_ip + partial index for IP-map hot path
    op.add_column(
        "agent_containers",
        sa.Column("bridge_ip", postgresql.INET(), nullable=True),
    )
    op.create_index(
        "ix_agent_containers_bridge_ip_running",
        "agent_containers",
        ["bridge_ip"],
        unique=False,
        postgresql_where=sa.text("container_status = 'running' AND bridge_ip IS NOT NULL"),
    )

    # D-11 + D-02: agent_containers schema additions
    op.add_column(
        "agent_containers",
        sa.Column("upstream_provider", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_containers",
        sa.Column("provider_key_enc", sa.LargeBinary(), nullable=True),
    )

    # D-11: usage_logs columns for ops debugging
    op.add_column("usage_logs", sa.Column("proxy_latency_ms", sa.Integer(), nullable=True))
    op.add_column("usage_logs", sa.Column("upstream_latency_ms", sa.Integer(), nullable=True))

    # D-15: widen status enum to include 'failed' (alongside existing 'success'/'unknown')
    op.drop_constraint("ck_usage_logs_status", "usage_logs", type_="check")
    op.create_check_constraint(
        "ck_usage_logs_status",
        "usage_logs",
        "status IN ('success','error','unknown','failed')",
    )

    # D-06: wipe legacy rows that can't be backfilled
    op.execute("DELETE FROM usage_logs WHERE status = 'unknown'")

    # AMD-03: idempotency_keys gains in_flight status
    # (Either widen verdict_json semantics OR add explicit 'status' column —
    # planner picks; existing schema in services/idempotency.py uses
    # verdict_json IS NULL as the in-flight signal in some patterns.
    # If a status column is added, mirror migration 010's check-constraint shape.)


def downgrade() -> None:
    # Reverse order; the DELETE in upgrade() is non-reversible
    # (those rows don't come back). This is documented per Plan 29-XX truths.
    op.drop_constraint("ck_usage_logs_status", "usage_logs", type_="check")
    op.create_check_constraint(
        "ck_usage_logs_status",
        "usage_logs",
        "status IN ('success','error','unknown')",
    )
    op.drop_column("usage_logs", "upstream_latency_ms")
    op.drop_column("usage_logs", "proxy_latency_ms")
    op.drop_column("agent_containers", "provider_key_enc")
    op.drop_column("agent_containers", "upstream_provider")
    op.drop_index("ix_agent_containers_bridge_ip_running", table_name="agent_containers")
    op.drop_column("agent_containers", "bridge_ip")
```

---

### `tools/migrate_phase29_nanobot_cutover.py` (one-shot script)

**Primary analog:** `tools/migrate_phase28_stuck_rows.py` — copy structure verbatim (argparse → DSN normalization → asyncpg connect → `--dry-run` branch → `--limit` safety cap → transactional UPDATE).

**Differences from analog:**
- WHERE clause filters `recipe_name='nanobot' AND container_status IN ('running','starting')`
- BEFORE the UPDATE: invokes `docker stop` for each container (via `docker` SDK or `subprocess.run`) — copy the docker-shutdown pattern from `services/runner_bridge.py::execute_persistent_stop` (or its caller in `routes/agent_lifecycle.py`)
- After Docker stop succeeds (or 404), UPDATE row `container_status='stopped', stopped_at=NOW()`

**Skeleton** (copy from `tools/migrate_phase28_stuck_rows.py` and tweak):
```python
SWEEP_SQL = """
SELECT id, container_id, agent_instance_id FROM agent_containers
WHERE recipe_name = 'nanobot' AND container_status IN ('running', 'starting')
"""
# ... mirror the rest: args.dry_run branch + safety cap + per-row docker stop + UPDATE ...
```

---

### Spike scripts (`api_server/tests/spikes/test_proxy_*.py`)

**Primary analog:** `api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py` — pytest module under `tests/spikes/` (NOT `tools/spike_*.py` despite CONTEXT phrasing). Uses `pytest.mark.spike`, `subprocess.run(["docker", ...])`, builds the `tools/Dockerfile.api` image on demand, asserts via `assert resp.status_code == ...`.

**Convention:** name each spike `test_phase29_<probe-id>_<short-name>.py` and store under `api_server/tests/spikes/`. Each spike emits a verbatim transcript artifact at `.planning/phases/29-llm-egress-proxy/spikes/PROBE-VAL-NN.md` (per RESEARCH.md §"Wave 0 spike artifacts").

**Pytest mark:** `pytestmark = [pytest.mark.spike, pytest.mark.api_integration]`.

---

### Tests under `api_server/tests/services/test_proxy_*.py`

**Primary analog:** `api_server/tests/services/test_usage_recorder.py` (real PG + helpers + pure-function tests + integration tests).

**Pytest marker** (copy from `test_usage_recorder.py:32`):
```python
pytestmark = pytest.mark.api_integration
```

**Helper pattern** (copy `_seed_user_and_agent` lines 40-58 — adapted for `agent_containers` row insertion in proxy tests):
```python
async def _seed_running_container(pool, *, user_id, agent_instance_id,
                                   bridge_ip="172.18.0.42",
                                   inapp_auth_token="test-token-32hex",
                                   provider_key_enc=None):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO agent_containers (
                id, agent_instance_id, user_id, recipe_name, channel_type,
                container_status, bridge_ip, inapp_auth_token,
                upstream_provider, provider_key_enc
            ) VALUES (gen_random_uuid(), $1, $2, 'nanobot', 'inapp',
                      'running', $3, $4, 'openrouter', $5)
        """, agent_instance_id, user_id, bridge_ip, inapp_auth_token,
            provider_key_enc)
```

---

### Tests under `api_server/tests/routes/test_llm_proxy.py`

**Primary analog:** `api_server/tests/routes/test_agent_messages_post.py` + `test_agent_lifecycle_inapp.py` (real PG + real FastAPI app + httpx-mock-via-respx for upstream).

**respx pattern for upstream mocking:** copy from `api_server/tests/spikes/test_respx_authlib.py` and `test_respx_intercepts_pyjwk_fetch.py`.

---

### Tests under `api_server/tests/test_migration_013_proxy_columns.py`

**Primary analog:** `api_server/tests/test_migration_011_phase28.py` — copy verbatim (testcontainers Postgres 17, alembic upgrade head, asyncpg fetch column metadata, downgrade -1 round-trip).

**Asserts (per Phase 29 acceptance gate #4 + AMD-04 + D-11):**
- `agent_containers.bridge_ip` exists (INET, nullable)
- `ix_agent_containers_bridge_ip_running` partial index has WHERE `container_status='running' AND bridge_ip IS NOT NULL`
- `agent_containers.upstream_provider` (text, nullable)
- `agent_containers.provider_key_enc` (bytea, nullable)
- `usage_logs.proxy_latency_ms`, `usage_logs.upstream_latency_ms` (int, nullable)
- `ck_usage_logs_status` allows `'failed'`
- INSERT a pre-migration `status='unknown'` row, run upgrade, assert it was DELETEd
- Round-trip downgrade-then-upgrade leaves identical schema (no orphan column / index)

---

## Shared Patterns

### Authentication / authorization

**Source:** `api_server/src/api_server/auth/deps.py::require_user` (used by `routes/usage.py:165-168`, `routes/agent_lifecycle.py:230-233`)

**Apply to:** the proxy route does NOT use `require_user` — it authenticates via IP-map + bearer-token-match (D-07 defense-in-depth). The bot is the caller, not a session-cookie-bearing browser. **However, the BYOK validator integration in `start_agent` DOES use `require_user`** (already wired). New BYOK validation is added BEFORE the `insert_pending_agent_container` call.

### Error envelope

**Source:** `api_server/src/api_server/models/errors.py::make_error_envelope` (used by every route file — pattern at `routes/agent_lifecycle.py:92-111`, `routes/usage.py:107-121`).

**Apply to:** `routes/llm_proxy.py` (`_err` helper), `services/byok_validator.py` (raises propagate up to the deploy handler that uses the envelope).

### BYOK redaction in logs

**Source:** `routes/agent_lifecycle.py:114-136 _redact_creds` + `crypto/age_cipher.py` (encrypted at rest).

**Apply to:** `routes/llm_proxy.py` (every exception string passes through `_redact_creds(text, key)` before being logged); `services/proxy_byok_cache.py::rehydrate_from_db` (NEVER log the decrypted key — only log `agent_instance_id` + count). Verified by Phase 29 acceptance gate #6.

### Lifespan resource lifecycle

**Source:** `main.py:80-262` (resource creation + `app.state.X = ...`); `main.py:339-418` (drain + close, reverse order).

**Apply to:** `main.py` modifications for Phase 29:
- **Add (after line 188 `app.state.docker_client = ...`, before line 264 watcher reattach):**
  - `app.state.proxy_byok_cache = ProxyBYOKCache(app.state.db); await app.state.proxy_byok_cache.rehydrate_from_db()`
  - `app.state.proxy_ip_map = ProxyIPMap(app.state.db); await app.state.proxy_ip_map.refresh()`
  - `app.state.proxy_upstream_client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=5.0), limits=httpx.Limits(max_connections=100, max_keepalive_connections=20))` (AMD-05)
  - `app.state.proxy_ip_refresh_task = asyncio.create_task(refresh_loop(app.state.proxy_ip_map, app.state.inapp_stop), name="proxy_ip_refresh")` — append to `app.state.inapp_tasks`
- **Add (in finally block around line 374-385, BEFORE redis close):**
  - `await app.state.proxy_upstream_client.aclose()`
- The `proxy_ip_refresh_task` joins the `inapp_tasks` list (line 249-258) so it's drained by the existing 5s budget at shutdown (line 348-352).

### Test infra (Postgres + Docker + asyncpg)

**Source:** `api_server/tests/conftest.py` + `api_server/tests/test_migration_011_phase28.py:77-80` (testcontainers `PostgresContainer("postgres:17-alpine")`, module-scoped fixture, alembic upgrade head).

**Apply to:** all `api_server/tests/services/test_proxy_*.py` and `tests/routes/test_llm_proxy.py` and `tests/test_migration_013_proxy_columns.py`. Pytest marker: `pytestmark = pytest.mark.api_integration`.

### Activity-class registration on the worker

**Source:** `api_server/src/api_server/temporal/worker.py` (registers `ForwardActivities`, `RecordUsageActivities`, `EmitInappOutboundActivities`, `MarkMessageDoneActivities`, `MarkMessageFailedActivities`, `CheckContainerReadyActivities`, `DebitBalanceActivities`).

**Apply to:** worker.py gains a `BackfillOpenRouterCostActivities(...)` instance + adds its `.backfill` bound method to the worker's activities list. Constructor takes `(db_pool=app.state.db, upstream_client=app.state.proxy_upstream_client, byok_cache=app.state.proxy_byok_cache)` — same shape as the other activity constructors.

### MSV reference table (transferred patterns)

| Pattern | MSV file:line | AP target file |
|---|---|---|
| Proxy lifecycle (Config + Start) | `api/pkg/anthropicproxy/proxy.go:65-180, 217-238` | `main.py` lifespan + `routes/llm_proxy.py` |
| IP-based user identification | `proxy.go:240-298, 446-457` | `services/proxy_ip_map.py` |
| BYOK key cache + hot refresh | `proxy.go:116-117, 332-360` | `services/proxy_byok_cache.py` |
| `wrapDirectorForRecording` body mutation | `proxy.go:438-467` | `routes/llm_proxy.py` (steps 3+4) |
| `extractTokensFromOpenAISSE` | `recorder.go:148-220` | `services/stream_parser.py` (sse_format='openai') |
| `extractTokensFromSSE` (Anthropic cumulative) | `recorder.go:222-264` | `services/stream_parser.py` (sse_format='anthropic') — AMD-07 |
| `APICallRecorder` async write | `recorder.go:21-60` | direct call to `usage_recorder.record_usage` (already exists) |
| BYOK validation pattern | `byok_service.go:25-80` | `services/byok_validator.py` |

---

## No Analog Found

Files with no close match in the codebase. Use RESEARCH.md / MSV patterns instead.

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `services/stream_parser.py` (the byte-level streaming-tee parser) | service | streaming transform | First streaming-byte parser in api_server. The closest existing code is `usage_recorder._parse_openai_compat` which operates on a fully-assembled JSON dict. Use RESEARCH.md §Streaming Capture Strategy + MSV `recorder.go:148-264` as the canonical sources. |
| The full streaming-tee in `routes/llm_proxy.py` (`_gen()` + `httpx.AsyncClient.stream` + `StreamingResponse`) | route | streaming | First proxy-style streaming-tee in api_server. PROBE-VAL-08 verifies the pattern empirically. Use RESEARCH.md §Code Examples lines 552-642 as the canonical implementation skeleton. |
| Provider-key-aware idempotency (AMD-03 reserved-row in-flight pattern) | service | concurrency | First in-flight idempotency primitive (existing `services/idempotency.py` only handles completed rows). PROBE-VAL-06 + RESEARCH.md §Idempotency Strategy spec the missing piece. |

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/routes/`
- `api_server/src/api_server/services/`
- `api_server/src/api_server/temporal/activities/`
- `api_server/src/api_server/middleware/`
- `api_server/src/api_server/crypto/`
- `api_server/alembic/versions/`
- `api_server/tests/{services,routes,temporal,spikes}/`
- `tools/`
- `recipes/`
- MSV `/Users/fcavalcanti/dev/meusecretariovirtual/api/pkg/anthropicproxy/` (verbatim mirror as RESEARCH directs)

**Files scanned:** ~50 (focused reads of analog files only; targeted Reads with offset+limit for >500-line files).

**Pattern extraction date:** 2026-05-06

**Open issue for the planner:** `tools/spike_*.py` paths in CONTEXT.md don't match the existing convention — the codebase has spikes under `api_server/tests/spikes/test_*.py` (pytest modules). Recommend the planner adopt the existing convention; if standalone scripts under `tools/spike_*.py` are still wanted, model them on `tools/migrate_phase28_stuck_rows.py` (argparse + asyncpg + `if __name__ == "__main__": sys.exit(asyncio.run(main()))`).
