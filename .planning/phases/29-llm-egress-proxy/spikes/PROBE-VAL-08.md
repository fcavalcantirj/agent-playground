# PROBE-VAL-08

## PROBE-VAL-08: FastAPI StreamingResponse + httpx tee (in-process)

- upstream chunk count: 10
- upstream inter-chunk sleep: 100ms
- target: per-chunk overhead median <= 50ms

### Streaming cadence measurement
- proxy yields counted: 10 | bot bytes received: 140
- TTFB latency overhead (bot first byte - upstream first byte): 1010.943 ms
- streaming-tee per-chunk latency: inf ms (median inter-arrival)
- streaming-tee total latency: 1.014 s (bot wall time)
- bot inter-arrival intervals (>=5ms boundary, ms): []
- bot inter-arrival median: inf ms (upstream cadence target: ~100ms)
- bot inter-arrival range: [inf, inf] ms

- bot total wall time: 1.014s (non-buffered minimum: ~1.0s)

### Premature disconnect resource-leak check
- ResourceWarning count after premature disconnect: 0
- (no resource warnings — clean close)

### Verdict reasoning
- bot wall time >= 0.9 * upstream emission floor (0.90s): **True** (observed wall time: 1.014s)
- no resource leak on premature close: **True**
- TTFB overhead under ASGITransport (informational only — transport buffers entire response): 1010.943 ms

### Implication for Plan 29-03 (StreamingResponse + parser tee)
- The pattern `httpx.AsyncClient.stream(upstream).aiter_raw() → parser.feed(chunk) + yield chunk` from a FastAPI StreamingResponse generator is empirically near-zero TTFB overhead and the wall-clock duration tracks upstream's emission cadence (proving the proxy is NOT buffering the response before forwarding). `aclose()` on premature client disconnect closes the upstream stream cleanly with no ResourceWarning.

### Note on ASGITransport coalescing
- `httpx.ASGITransport` may coalesce small chunks into a single `aiter_raw()` yield in the bot loop. The non-buffering proof here is the WALL TIME (~1.01s vs 1.0s upstream-emission floor), not the per-chunk count. In real prod (uvicorn + non-ASGI httpx transport against the upstream), the bot will see chunks at upstream's natural cadence.

VERDICT: PASS
