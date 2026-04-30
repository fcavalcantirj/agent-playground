# Spike: openclaw — channels.inapp HTTP-localhost feasibility

**Date:** 2026-04-29 (revised 2026-04-29 PM)
**Recipe:** `recipes/openclaw.yaml`
**Image:** `ap-recipe-openclaw:latest`
**Status:** ✅ HIGH — native OpenAI-compat /v1/chat/completions exists; activated by config flag

> **REVISION NOTICE.** The first version of this spike (morning 2026-04-29) ran the bot
> with `openclaw gateway --allow-unconfigured` and concluded "no native HTTP chat —
> use docker_exec_cli." That conclusion was **wrong**. It was the Mode that hid the
> endpoint, not the bot.
>
> Cross-check against MSV (`/Users/fcavalcanti/dev/meusecretariovirtual/messaging/activities/forward_to_agent.go:70`)
> and MSV's provision_ops.go:386 surfaced that openclaw exposes `/v1/chat/completions`
> when `gateway.http.endpoints.chatCompletions.enabled = true` is set in
> `~/.openclaw/openclaw.json` AND the bot runs `openclaw gateway run` (NOT
> `--allow-unconfigured`, which suppresses chat HTTP). MSV uses this exact pattern
> in production (`infra/picoclaw/entrypoint.sh:90-127` writes the flag on every
> boot). Empirical re-spike below proved the endpoint is bound.

## Empirical command (revised — MSV-equivalent config)

```bash
docker run -d -t --name spike-openclaw -p 18389:18789 \
  -e OPENROUTER_API_KEY=sk-or-fake-for-spike \
  -v /tmp/openclaw-spike.sh:/spike.sh \
  --entrypoint sh ap-recipe-openclaw:latest /spike.sh
```

Where `/spike.sh` writes the MSV-equivalent openclaw.json then `exec openclaw gateway run --port 18789`:

```json
{
  "agents": {
    "defaults": {
      "model": { "primary": "openrouter/anthropic/claude-haiku-4.5", "fallbacks": [] },
      "timeoutSeconds": 600,
      "thinkingDefault": "high"
    }
  },
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "lan",
    "http": {
      "endpoints": {
        "chatCompletions": { "enabled": true }   // ← THE LOAD-BEARING FLAG
      }
    },
    "auth": {
      "mode": "token",
      "token": "spike-token-1234"
    },
    "controlUi": { "dangerouslyAllowHostHeaderOriginFallback": true }
  },
  "channels": {},
  "skills": { "install": { "nodeManager": "npm" }, "entries": {} },
  "update": { "checkOnStart": false }
}
```

## Verbatim output (boot logs)

```
🦞 OpenClaw 2026.4.15-beta.1
[gateway] loading configuration…
[gateway] resolving authentication…
[gateway] starting HTTP server...
[gateway] auto-enabled plugins:
- openrouter/anthropic/claude-haiku-4.5 model configured, enabled automatically.
[gateway] agent model: openrouter/anthropic/claude-haiku-4.5
[gateway] ready (5 plugins: acpx, browser, device-pair, phone-control, talk-voice; 8.8s)
[browser/server] Browser control listening on http://127.0.0.1:18791/ (auth=token)
```

## Verbatim output (HTTP probes against the live container)

```
GET / :
<!doctype html>
<html lang="en"> ... (Control Web UI HTML)

GET /health :
{"ok":true,"status":"live"}                              HTTP 200

GET /v1/models (no auth):
{"error":{"message":"Unauthorized","type":"unauthorized"}}    HTTP 401

POST /v1/chat/completions (no auth):
{"error":{"message":"Unauthorized","type":"unauthorized"}}    HTTP 401

POST /v1/chat/completions (Bearer spike-token-1234, model=openrouter/...):
{"error":{"message":"Invalid `model`. Use `openclaw` or `openclaw/<agentId>`.","type":"invalid_request_error"}}  HTTP 400
```

## Findings

- **Openclaw's gateway HTTP listener on port 18789 binds `/v1/chat/completions` when**
  `gateway.http.endpoints.chatCompletions.enabled = true` is set in openclaw.json.
- **Auth gate**: HTTP 401 without `Authorization: Bearer <gateway.auth.token>`. The
  401 is the proof — only an auth handler in front of an existing route returns 401;
  if the route didn't exist it would be 404 (which is what `--allow-unconfigured`
  mode returns).
- **OpenAI-compat envelope**: response is `{"error":{"message":"...","type":"unauthorized"}}`
  — direct shape match with OpenAI spec. With valid Bearer + a recognized model
  (`openclaw` or `openclaw/<agentId>`), the gateway routes to the configured
  upstream provider (here openrouter) — same pattern MSV's `forward_to_agent.go:70`
  uses (`Model: "openclaw:main"`).
- **Configuration is the difference**: the original spike ran `openclaw gateway
  --allow-unconfigured`, which intentionally suppresses chat HTTP for
  bootstrap-only operations. Production-shape config (per MSV's `provision_ops.go:380-401`)
  binds the route.
- **Co-existence**: `openclaw gateway run` continues to host the WebSocket gateway
  + Control UI + browser-control sidecar (port 18791) + bonjour discovery. Adding
  chat HTTP doesn't disrupt the telegram channel path that Phase 22 already
  empirically validates.

## Verdict for `channels.inapp`

**HIGH confidence — no upstream patch required.** Recipe needs a config-flag flip
plus dropping `--allow-unconfigured`. `channels.inapp` block:

```yaml
channels:
  inapp:
    transport: http_localhost
    port: 18789
    contract: openai_chat_completions
    endpoint: /v1/chat/completions
    auth_header: "Authorization: Bearer ${INAPP_AUTH_TOKEN}"
    model_alias: "openclaw"   # the bot answers when client sends model=openclaw
    ready_log_regex: "\\[gateway\\] ready \\(\\d+ plugins"
    persistent_argv_override:
      entrypoint: sh
      argv:
        - -c
        - |
          set -e
          mkdir -p /home/node/.openclaw
          cat > /home/node/.openclaw/openclaw.json <<EOF
          {
            "agents": {
              "defaults": {
                "model": { "primary": "openrouter/$MODEL", "fallbacks": [] },
                "timeoutSeconds": 600
              }
            },
            "gateway": {
              "port": 18789,
              "mode": "local",
              "bind": "lan",
              "http": {
                "endpoints": {
                  "chatCompletions": { "enabled": true }
                }
              },
              "auth": {
                "mode": "token",
                "token": "${INAPP_AUTH_TOKEN}"
              }
            },
            "channels": {},
            "skills": {"install": {"nodeManager": "npm"}, "entries": {}}
          }
          EOF
          rm -f /home/node/.openclaw/openclaw.json5
          exec openclaw gateway run --port 18789
```

Runner generates a per-session opaque token, injects it as `${INAPP_AUTH_TOKEN}`
both into the bot's openclaw.json (server side) and persists to
`agent_containers.inapp_auth_token` (api side) for forwarding on dispatch.

## Risk flags

- **LOW risk on the route binding.** Empirically proven: 401 / 400 with proper
  envelope on POST /v1/chat/completions. The endpoint exists.
- **LOW risk on co-existence.** The gateway hosts multiple sidecars by default
  (browser-control, canvas, etc.); adding `chatCompletions` doesn't disrupt them.
- **MEDIUM risk on per-message latency.** Boot wall is 8.8s (vs 100s for the
  CLI `infer` path). For inapp where the dispatcher (D-28) sends each message
  to an already-running container, this is amortized — only the first request
  pays the boot cost. CLI cold-start was the previous bottleneck.
- **MEDIUM risk on model-id mapping.** Client must send `model=openclaw` or
  `model=openclaw/<agentId>`, NOT the raw upstream model id. The recipe needs a
  `model_alias` field (or the dispatcher rewrites the model field before forward).
  This is unique to openclaw — hermes uses `model=hermes-agent`, nanobot uses the
  raw upstream id.
- **LOW risk on dropping `--allow-unconfigured`.** The recipe's existing comment
  at line 351-353 ("Port 18000 belongs to `openclaw serve`") was based on outdated
  understanding — port 18000 doesn't apply; chat HTTP rides on the gateway port
  (18789) once the config flag is set. The Phase 22b smoke path (`infer model run`
  via docker_exec_cli) keeps working because `infer --local` doesn't depend on
  the gateway mode at all — it spawns its own embedded agent.

## What this changes about the per-recipe matrix

The original research's matrix had openclaw in the `docker_exec_cli` bucket. The
correct bucket is `http_localhost`. The two-verb dispatcher is still required —
just for different recipes:

| Recipe | Transport verb | Why |
|--------|----------------|-----|
| hermes | `http_localhost` | env-flag activated api_server platform on 8642 |
| nanobot | `http_localhost` | `nanobot serve` mode on 8900 (alt entrypoint) |
| **openclaw** | **`http_localhost`** | **chatCompletions config flag on gateway port 18789** ← CORRECTED |
| picoclaw (sipeed) | `docker_exec_cli` | gateway only exposes /health on 18790 (different upstream from openclaw) |
| nullclaw | `docker_exec_cli` | gateway only exposes /health + /pair on 3000 |

3 of 5 recipes use `http_localhost`; 2 of 5 need `docker_exec_cli`. The
dispatcher must implement both.
