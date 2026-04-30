# Recipe spike: zeroclaw (Round-3 substitution for picoclaw) — Wave 0 re-validation

**Date:** 2026-04-30
**Recipe:** `recipes/zeroclaw.yaml` (NEW; substitutes picoclaw in Phase 22c.3 inapp scope per user direction 2026-04-30)
**Image:** `ghcr.io/zeroclaw-labs/zeroclaw:latest` (Rust, distroless, 66.2 MB, USER 65534, EXPOSED 42617/tcp)
**Provider/model:** `openrouter` / `anthropic/claude-haiku-4.5`
**Contract:** `zeroclaw_native`
**Endpoint:** `POST /webhook` on container port 42617 (mapped to host port 18617); native `{message}` request → `{response, model}` reply envelope
**Status:** ✅ FULL_PASS — fresh local end-to-end probe with real OpenRouter call returned a 100-char persona-correct reply with `model` field. Idempotency probe (`X-Idempotency-Key`) confirmed: duplicate request returns `{idempotent: true, status: "duplicate"}`.

> **Round-3 substitution.** picoclaw is DEFERRED per user direction 2026-04-30 (recipes/picoclaw.yaml UNTOUCHED, stays in repo for backward compat with smoke suite). ZeroClaw is the highest-starred clawclones.com agent we don't yet have (30,845 ★ Rust, top of `recipes/BACKLOG.md`). Round-3 RESEARCH §Per-Recipe Feasibility Matrix records the swap.

## Reproducible probe (verbatim)

```bash
# Source $OPENROUTER_API_KEY (developer's shell)

# Cleanup any prior state
docker rm -f spike-w0-zero 2>/dev/null
docker volume rm w0-zero-data 2>/dev/null

# Step 1 — onboard with provider+model (writes .zeroclaw/config.toml + auth.json into the volume)
docker run --rm -v w0-zero-data:/zeroclaw-data --entrypoint zeroclaw \
  ghcr.io/zeroclaw-labs/zeroclaw:latest \
  onboard --quick --force --provider openrouter --api-key "$OPENROUTER_API_KEY" --model anthropic/claude-haiku-4.5

# Step 2 — open public bind + disable pairing (loopback-trusted dispatcher mode)
docker run --rm -v w0-zero-data:/zeroclaw-data --entrypoint zeroclaw \
  ghcr.io/zeroclaw-labs/zeroclaw:latest config set gateway.allow-public-bind true

docker run --rm -v w0-zero-data:/zeroclaw-data --entrypoint zeroclaw \
  ghcr.io/zeroclaw-labs/zeroclaw:latest config set gateway.host '0.0.0.0'

docker run --rm -v w0-zero-data:/zeroclaw-data --entrypoint zeroclaw \
  ghcr.io/zeroclaw-labs/zeroclaw:latest config set gateway.require-pairing false

# Step 3 — run daemon
docker run -d --name spike-w0-zero -p 18617:42617 -v w0-zero-data:/zeroclaw-data \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  --entrypoint zeroclaw ghcr.io/zeroclaw-labs/zeroclaw:latest daemon

sleep 5

# Probe 1 — synchronous /webhook
curl -s -X POST http://localhost:18617/webhook \
  -H 'Content-Type: application/json' \
  -d '{"message":"who are you in 1 short sentence?"}'

# Probe 2 — idempotency
IDEM_KEY="ik-w0-test-$(date +%s)"
curl -s -X POST http://localhost:18617/webhook \
  -H 'Content-Type: application/json' \
  -H "X-Idempotency-Key: $IDEM_KEY" \
  -d '{"message":"hello, one-line greeting"}'
curl -s -X POST http://localhost:18617/webhook \
  -H 'Content-Type: application/json' \
  -H "X-Idempotency-Key: $IDEM_KEY" \
  -d '{"message":"hello, one-line greeting"}'

docker rm -f spike-w0-zero
docker volume rm w0-zero-data
```

## Boot logs (verbatim)

```
2026-04-30T18:17:47.880006Z  INFO zeroclaw_gateway: Gateway session persistence enabled (SQLite)
2026-04-30T18:17:47.883219Z  INFO zeroclaw_gateway: Web dashboard: not available (set gateway.web_dist_dir or ZEROCLAW_WEB_DIST_DIR)
🦀 ZeroClaw Gateway listening on http://0.0.0.0:42617
  🌐 Web Dashboard: http://0.0.0.0:42617/
  ⚠️  Pairing: DISABLED (all requests accepted)

  POST /pair      — pair a new client (X-Pairing-Code header)
  POST /webhook   — {"message": "your prompt"}
  GET  /api/*     — REST API (bearer token required)
  GET  /ws/chat   — WebSocket agent chat
  GET  /health    — health check
  GET  /metrics   — Prometheus metrics
  Press Ctrl+C to stop.
```

## Probe 1 — `POST /webhook` (verbatim, real OpenRouter call)

```json
{
  "model": "anthropic/claude-haiku-4.5",
  "response": "I'm ZeroClaw, a Rust-built AI assistant built to be genuinely helpful without the corporate fluff. 🦀"
}
```

Parse path: `body["response"]` = 100 chars; `body["model"]` = `"anthropic/claude-haiku-4.5"`. The dispatcher's `zeroclaw_native` adapter reads exactly this path:

```python
async def forward(http_client, agent_url, ..., message, idempotency_key, session_id):
    headers = {"Content-Type": "application/json"}
    if idempotency_key: headers["X-Idempotency-Key"] = idempotency_key
    if session_id:      headers["X-Session-Id"]      = session_id
    resp = await http_client.post(f"{agent_url}/webhook",
                                  json={"message": message},
                                  headers=headers, timeout=600)
    resp.raise_for_status()
    return resp.json()["response"]
```

## Probe 2 — `X-Idempotency-Key` (verbatim, two posts with same key)

```
First request:
  X-Idempotency-Key: ik-w0-test-1777573087
  body: {"message":"hello, one-line greeting"}
  → HTTP 200
  {"model":"anthropic/claude-haiku-4.5","response":"Hey! 🦀 I'm ZeroClaw — what's on your mind?"}

Second request (identical body + identical key):
  → HTTP 200
  {"idempotent":true,"message":"Request already processed for this idempotency key","status":"duplicate"}
```

The bot's built-in idempotency replays a deterministic shape `{idempotent: true, status: "duplicate"}` instead of re-executing the LLM call. The dispatcher's `zeroclaw_native` adapter passes through `inapp_messages.id` as `X-Idempotency-Key` so retries are deduped by the bot itself (in addition to the api-server's own `IdempotencyMiddleware`).

## `GET /health` excerpt (rich, runtime-componentized)

```json
{
  "paired": false,
  "require_pairing": false,
  "runtime": {
    "components": {
      "channels": {"status": "ok", "last_ok": "2026-04-30T18:17:47..." },
      "daemon":   {"status": "ok", ...},
      "gateway":  {"status": "ok", ...},
      "heartbeat":{"status": "ok", ...}
    }
  }
}
```

## Findings

- ZeroClaw IS the inapp channel — built-in synchronous HTTP, idempotent, session-aware, with bonus streaming WebSocket (`/ws/chat`) and Prometheus metrics for free.
- The native shape `{message}` → `{response, model}` differs from OpenAI Chat Completions — the dispatcher needs a `zeroclaw_native` adapter (Plan 22c.3-05).
- Built-in `X-Idempotency-Key` is a feature unique to zeroclaw across the 5 recipes — recipe declares `idempotency_header` in `channels.inapp` so the dispatcher knows to forward our `inapp_messages.id` as the key.
- `gateway.require-pairing = false` is required for loopback-trusted dispatch (auth lives upstream at `require_user`).
- Cold-boot wall: ~5s to ready (Rust + distroless + SQLite session-store init); subsequent dispatches reuse the running container.
- Real OpenRouter call latency: ~3s.

## Verdict

**FULL_PASS** — `zeroclaw_native` contract empirically reachable on `ghcr.io/zeroclaw-labs/zeroclaw:latest`. Idempotency built-in. Dispatcher's `zeroclaw_native` adapter parse path validated.

## Anomalies observed

- None blocking. Two minor observations:
  - The `Web dashboard: not available` boot log reflects that we don't ship a web dashboard build inside the image; orthogonal to inapp.
  - The volume-keyed config (`/zeroclaw-data/.zeroclaw/config.toml`) means the recipe's `persistent_argv_override.pre_start_commands` (`onboard --quick` + 3 `config set`s) runs ONCE per volume; subsequent boots reuse the same config. Plan 22c.3-13 absorbs this in the recipe.

## Wave 0 confirmation against Plan must-haves

- [x] `zeroclaw_native` contract present
- [x] `/webhook` endpoint reachable
- [x] `{message}` request body → `{response, model}` reply parse path validated
- [x] Real LLM round-trip via OpenRouter (3s wall, 100-char persona-correct reply)
- [x] Idempotency probe — duplicate `X-Idempotency-Key` returns `{idempotent: true, status: "duplicate"}`
- [x] No picoclaw spike was created or modified by this Wave-0 probe
- [x] Today's date 2026-04-30
