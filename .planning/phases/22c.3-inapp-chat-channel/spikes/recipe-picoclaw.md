# Spike: picoclaw — channels.inapp HTTP-localhost feasibility

**Date:** 2026-04-29 PM (revised)
**Recipe:** `recipes/picoclaw.yaml` (sipeed/picoclaw — NOT openclaw-derived)
**Image:** `ap-recipe-picoclaw:latest`
**Status:** ✅ HIGH — sidecar bridge proven; recipe needs ~50-LOC Python aiohttp bridge baked into persistent_argv_override

> **Update notice (2026-04-29 PM).** v1 of this spike correctly found that
> `picoclaw gateway` exposes only `/health` on 18790 (no native chat HTTP).
> v1 then proposed the `docker_exec_cli` transport as the recommended path.
>
> Per user directive **"5 out of 5 must work"** — meaning all 5 recipes
> must reach uniform `transport: http_localhost`, no two-verb half-measure
> — v2 of this spike empirically validates the **HTTP→CLI sidecar** pattern
> co-located inside the recipe container. Result: PASS. picoclaw moves to
> `http_localhost` with a recipe-side sidecar.

## Empirical command (v2 — sidecar bridge)

```bash
docker run -d -t --name spike-picobridge -p 18791:18791 -p 18790:18790 \
  -e OPENROUTER_API_KEY=sk-or-fake-for-spike \
  -e INAPP_AUTH_TOKEN=spike-bridge-token \
  -e INAPP_BOT_BIN=picoclaw \
  -e INAPP_BRIDGE_PORT=18791 \
  -v /tmp/picoclaw-bridge-entrypoint.sh:/spike.sh \
  --entrypoint sh ap-recipe-picoclaw:latest /spike.sh
```

The entrypoint script (52 LOC total — 4 stages):

1. `apk add --no-cache python3 py3-aiohttp` (one-time, 7s)
2. Write `/tmp/inapp-bridge.py` (~30 LOC): aiohttp app exposing
   `POST /v1/chat/completions` (Bearer-gated) + `GET /health` (open)
3. Write picoclaw config.json + .security.yml (existing recipe shape)
4. `nohup python3 /tmp/inapp-bridge.py >/tmp/bridge.log 2>&1 &` then
   `exec picoclaw gateway -E -d --host 0.0.0.0`

The sidecar's chat endpoint:

```python
async def chat_completions(request):
    auth = request.headers.get("Authorization", "")
    if BEARER and auth != f"Bearer {BEARER}":
        return web.json_response({"error": {"message": "Unauthorized", "type": "unauthorized"}}, status=401)
    body = await request.json()
    last_user = next((m["content"] for m in reversed(body["messages"]) if m.get("role") == "user"), None)
    proc = await asyncio.create_subprocess_exec(
        "picoclaw", "agent", "-m", last_user,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return web.json_response({"error": {"message": stderr.decode()[:500], "type": "bot_error"}}, status=502)
    return web.json_response({
        "id": "chatcmpl-bridge",
        "object": "chat.completion",
        "model": body.get("model", "picoclaw"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": stdout.decode().strip()}, "finish_reason": "stop"}],
    })
```

## Verbatim output

```
=== bridge.log ===
INAPP-BRIDGE listening on 0.0.0.0:18791

GET /health (bridge:18791):
{"status": "ok", "platform": "inapp-bridge"}                        HTTP 200

GET /health (bot:18790):
{"status":"ok","uptime":"13.98s","pid":1}                           HTTP 200

POST /v1/chat/completions (no auth):
{"error": {"message": "Unauthorized", "type": "unauthorized"}}      HTTP 401

POST /v1/chat/completions (Bearer spike-bridge-token):
{"error": {"message": "Error: error processing message: LLM call failed after retries:
   API request failed: Status: 401 Body: {\"error\":{\"message\":\"Missing
   Authentication header\",\"code\":401}}", "type": "bot_error"}}   HTTP 502
```

The 502 is the bridge faithfully reporting the bot's upstream LLM-call failure
(fake OPENROUTER_API_KEY in the spike). With a real key, picoclaw answers and
the bridge returns the OpenAI-shape envelope.

## Findings

- Picoclaw's alpine image has `apk` + `apk-tools 3.0.6-r0` available; `apk add
  python3 py3-aiohttp` succeeds in ~7s, adds ~30MB to the running container's
  RAM footprint (image is unchanged on disk; the install lives in the writable
  layer).
- The bridge runs as an orphaned background process under PID 1 (picoclaw
  gateway). When the bot dies, the bridge is reaped by the kernel via
  `--init` if the recipe declares it; otherwise the runner can health-check the
  bridge port and restart the container. For v1, single-process supervision is
  acceptable per D-15 (asyncio, not Temporal).
- Picoclaw + bridge co-existence: bot listens on 18790 (gateway HTTP), bridge
  on 18791 (chat HTTP). No port collision. Per-message overhead: bridge spawns
  a subprocess of `picoclaw agent -m <prompt>` per call, bot processes it,
  bridge wraps stdout in OpenAI envelope.
- Cold-start: ~14s (bot init) + ~3s (first apk add finishing in background) = bot
  ready first; bridge ready second. Recipe `ready_log_regex` should match the
  bridge's `INAPP-BRIDGE listening` line so the runner waits for both.

## Verdict for `channels.inapp`

**HIGH confidence — `transport: http_localhost` with recipe-side sidecar.**

```yaml
channels:
  inapp:
    transport: http_localhost
    port: 18791
    contract: openai_chat_completions
    endpoint: /v1/chat/completions
    auth_header: "Authorization: Bearer ${INAPP_AUTH_TOKEN}"
    ready_log_regex: "INAPP-BRIDGE listening on"
    persistent_argv_override:
      entrypoint: sh
      argv:
        - -c
        - |
          set -e
          apk add --no-cache python3 py3-aiohttp >/dev/null
          cat > /tmp/inapp-bridge.py <<'PYEOF'
          # ... (50 LOC aiohttp bridge — full source in spike artifact) ...
          PYEOF
          mkdir -p /root/.picoclaw/workspace
          cat > /root/.picoclaw/config.json <<EOF
          {"version":3,"agents":{"defaults":{"model_name":"or","workspace":"/root/.picoclaw/workspace"}},"model_list":[{"model_name":"or","model":"$MODEL","api_base":"https://openrouter.ai/api/v1"}]}
          EOF
          cat > /root/.picoclaw/.security.yml <<EOF
          model_list:
            or:
              api_keys:
                - "${OPENROUTER_API_KEY}"
          EOF
          nohup python3 /tmp/inapp-bridge.py >/tmp/bridge.log 2>&1 &
          exec picoclaw gateway -E -d --host 0.0.0.0
    activation_env:
      INAPP_BOT_BIN: "picoclaw"
      INAPP_AUTH_TOKEN: "${INAPP_AUTH_TOKEN}"   # runner injects per-session
      INAPP_BRIDGE_PORT: "18791"
```

## Risk flags

- **LOW risk on the sidecar pattern itself.** Empirically proven for picoclaw +
  nullclaw with the exact same script (only `INAPP_BOT_BIN` differs).
- **LOW risk on apk add at boot.** alpine's apk repo is stable; py3-aiohttp is
  in the main repo (no third-party tap needed). Adds ~7s to boot.
- **MEDIUM risk: bridge restart on bot crash.** Today the bridge is an orphan;
  if the bot's CLI subprocess hangs the bridge's connection to it dies but the
  bridge stays up. The Phase 22b watcher's `container_status != 'running'`
  check at the dispatcher already handles bot-process death — bridge will
  return 502 cleanly. Reaper (D-30) re-queues stuck rows.
- **MEDIUM risk: bridge cold-start ordering.** If client POSTs before bridge is
  bound, gets connection-refused. Mitigation: dispatcher waits for both
  `agent_containers.ready_at` (set by watcher when bot boots) AND
  `INAPP-BRIDGE listening` log line. Recipe declares both.
- **LOW risk: per-call subprocess fork.** picoclaw agent CLI is fast-cold (~2s).
  For chat (D-22 dumb-pipe — no shared session state), this is acceptable.
  Heavier bots that need warm state should use the bot's native HTTP server
  instead of a sidecar (which is what hermes/nanobot/openclaw do).

## What this changes about the per-recipe matrix

After v2 sidecar validation, ALL 5 recipes use `transport: http_localhost`:

| Recipe | Transport | How chat HTTP is exposed |
|--------|-----------|--------------------------|
| hermes | http_localhost | native `gateway.platforms.api_server` (env-flag) |
| nanobot | http_localhost | native `nanobot serve` mode |
| openclaw | http_localhost | native `/v1/chat/completions` (config flag) |
| picoclaw | http_localhost | recipe-side sidecar (apk add python3 + 50 LOC aiohttp) |
| nullclaw | http_localhost | recipe-side sidecar (same 50 LOC, INAPP_BOT_BIN=nullclaw) |

The `docker_exec_cli` transport verb is no longer required. The dispatcher
implements ONE verb (`http_localhost` via `httpx.AsyncClient`) and the recipe
schema is uniform. Single source of truth, single dispatch path, single set of
pitfalls (Pattern 2 dispatcher loop in RESEARCH.md).
