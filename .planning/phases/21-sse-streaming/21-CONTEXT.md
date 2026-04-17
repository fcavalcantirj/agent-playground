---
phase: 21-sse-streaming
status: ready_for_planning
gathered: 2026-04-16
source: Extracted from Phase 19 discuss-phase (D-03 scope split). 4-agent API critique referenced.
depends_on: [19]
---

# Phase 21: SSE Streaming Upgrade — Context

## Phase Boundary

Upgrade the `POST /v1/runs` path from synchronous-blocking (Phase 19) to Server-Sent Events streaming. Client receives stdout/stderr lines as they arrive from the container, plus a final `verdict` event. Adds `GET /v1/runs/{id}/events` endpoint. Introduces `run_cell_streaming()` generator seam in the runner.

**Why a separate phase:** User decision during Phase 19 discuss: "sse after, right. ground basics first?" → Phase 19 ships synchronous HTTP foundation (DB, endpoints, deploy, idempotency, rate limit, error envelope, Bearer auth). Phase 21 adds the streaming layer on top.

## Implementation Decisions (locked — from Phase 19 discuss + 4-agent API critique)

### D-01: Event shape — Anthropic Messages API pattern
- Event types:
  - `run_started` — first event, payload `{run_id, agent_instance_id, started_at}`.
  - `log` — every line of stdout/stderr from the container. Payload `{stream: "stdout"|"stderr", line: "...", ts: <ms>}`.
  - `verdict` — terminal event before the stream closes. Payload = the same verdict JSON that the Phase 19 sync endpoint returns.
  - `heartbeat` — keep-alive comment (`: keep-alive\n\n`) every 15 seconds.
  - `error` — terminal on unrecoverable error. Payload = the Phase 19 error envelope.
- Each event carries `id:` line with the run_id + sequence so the client can use `Last-Event-ID` for its own bookkeeping (but WE don't support reconnect-replay — documented in D-06).

### D-02: API surface — split POST + GET pattern
- `POST /v1/runs` with `Accept: text/event-stream` returns the stream directly (inline streaming).
- `POST /v1/runs` with `Accept: application/json` (default) → still returns JSON synchronously (Phase 19 behavior preserved for non-streaming clients).
- `GET /v1/runs/{id}/events` → SSE stream for a run_id created by a prior POST. Useful for:
  (a) A second tab watching the same run.
  (b) Replay of already-completed runs (returns final verdict event immediately + closes).
- The split matches the 4-agent API critique recommendation: POST returns `run_id` → GET subscribes to events.

### D-03: Runner streaming seam — Iterator[Event] generator
- `run_cell_streaming(...) -> Iterator[tuple[str, Any]]` in `tools/run_recipe.py`.
- Yields `("stdout", line)`, `("stderr", line)`, `("verdict", Verdict, details_dict)` events.
- Keeps cidfile + docker kill + env-file lifecycle IN the runner — do not lift into server.
- `run_cell(...)` keeps its existing signature — thin wrapper: `return list(run_cell_streaming(...))[-1]`.
- Implementation uses `subprocess.Popen(..., stdout=PIPE, stderr=PIPE, bufsize=1, text=True)` with selectors-based multiplexing, replacing the current `subprocess.run(timeout=...)` call at line 721 of run_cell.
- CLI `run_recipe.py --json` path unchanged. Streaming only activates via the new entry.

### D-04: Server bridge — asyncio.to_thread + queue
- FastAPI handler calls `run_cell_streaming()` via `asyncio.to_thread` with a `asyncio.Queue` bridge (thread produces events, async handler consumes).
- Queue is bounded (size ~100); on overflow drop a `log` event and emit a `log_dropped` counter event. Slow clients MUST NOT block the runner's reap loop.
- Handler responds with `media_type="text/event-stream"` and headers:
  - `X-Accel-Buffering: no`
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`

### D-05: Keep-alive heartbeats
- Emit `:keep-alive\n\n` every 15 seconds of silence. Prevents AWS ALB (60s default idle) and Cloudflare free-tier SSE buffering from dropping connections.
- Server tracks time-since-last-emit per run and injects heartbeat independently of the runner generator.

### D-06: Disconnect → docker kill
- Handler registers `await request.is_disconnected()` watcher alongside the queue consumer.
- When client disconnects: cancel the runner thread, trigger docker kill via the cidfile path (already wired by runner for `TimeoutExpired`; reuse the same primitive).
- NO reconnect-replay. Documented client expectation: once a run is killed by disconnect, it's gone. To resume, start a new run. Matches the 4-agent API critique's "do not pretend it's resumable" guidance.

### D-07: Idempotency interaction
- Idempotency-Key semantics unchanged from Phase 19: a second POST with the same key returns the cached `run_id` + verdict.
- In SSE mode: server emits `run_started` with the cached run_id, then immediately `verdict` with the cached result, then closes. Replay-from-cache path is always synthetic; the original container is long gone.
- `GET /v1/runs/{id}/events` on a completed run: same pattern — replay cached `verdict` event and close.

### D-08: Backpressure + resource accounting
- Disk usage on `/tmp/ap-cid-*` and `/tmp/ap-env-*` — cleanup still runs in `run_cell_streaming`'s `finally`.
- Bound Concurrent streams per user at the rate-limit layer (same slots as Phase 19's run semaphore). Streams don't bypass limits just because they're long-lived.

### D-09: OpenAPI declaration
- Declare `POST /v1/runs` with two `responses` entries: 200 (application/json verdict) and 200 (text/event-stream). Content-type negotiation via `Accept` header.
- `GET /v1/runs/{id}/events` is always text/event-stream.
- OpenAPI 3.0.3 supports `content` with multiple media types on a single response. FastAPI has to be coaxed here; plan may need a custom response class.

### D-10: Client-side — fetch-event-source (not native EventSource)
- Native `EventSource` is GET-only; our flow needs POST+SSE.
- Frontend uses `@microsoft/fetch-event-source` (or an equivalent maintained fork).
- Document this in Phase 20 frontend-alicerce notes.

## Success Criteria

1. `curl -N -H "Accept: text/event-stream" -H "Authorization: Bearer $KEY" -X POST https://<domain>/v1/runs -d '{"recipe_name":"hermes","prompt":"..."}'` streams `run_started`, `log` events, terminal `verdict`.
2. Closing the curl connection mid-stream results in the backing docker container being reaped (observable via `docker ps`).
3. Idle keep-alive: a stream with no runner output receives `:keep-alive` comment every ~15s — connection survives >60s idle.
4. `POST /v1/runs` with `Accept: application/json` keeps Phase 19 sync behavior byte-identical (regression).
5. `GET /v1/runs/{id}/events` on a completed run replays final `verdict` event within 50ms.
6. `run_cell_streaming()` has its own unit tests (mocked Popen) and integration test (real alpine container streaming sleep + echo).
7. Full runner test suite (Phase 18's 171 tests + Phase 19 additions) passes with no behavior change in `run_cell()`.

## Out of scope (deferred)

- Resumable SSE streams (client reconnect with Last-Event-ID to replay missed events). Too much server-side buffering; not worth before a user asks.
- Bidirectional WebSocket — explicitly a different phase (terminal, phase 22+).
- Streaming metrics (tokens-per-second, cost-per-event) — requires LLM-layer proxying, phase 23+.

## Canonical References

### Load-bearing prior work
- `.planning/phases/19-api-foundation/19-CONTEXT.md` — the foundation this builds on
- `.planning/phases/18-schema-maturity/18-CONTEXT.md` — schema contract
- `tools/run_recipe.py` — runner to be refactored
- `tools/tests/conftest.py` — existing fixtures including `mock_subprocess_timeout` and `fake_cidfile`

### External patterns
- Anthropic Messages API streaming spec (event names)
- `@microsoft/fetch-event-source` docs (client library)
- Starlette `Request.is_disconnected()` docs
- FastAPI `StreamingResponse` conventions
- 4-agent API critique synthesis (captured inline in `.planning/phases/19-api-foundation/19-CONTEXT.md`)

## Claude's Discretion

- Exact queue size (100 is a starting point; planner tunes based on runner throughput).
- Whether to offer `Last-Event-ID` parsing (we won't reconnect-replay, but we can accept the header to let clients label events).
- Whether `run_cell_streaming()` uses threading (selectors) or true async I/O (aiofile + process) — both viable; threading is simpler.

---

*Phase: 21-sse-streaming*
*Context extracted from Phase 19 discuss (2026-04-16). Do not plan or execute before Phase 19 completes.*
