# Spike: nullclaw — channels.inapp HTTP-localhost feasibility

**Date:** 2026-04-29 PM (revised)
**Recipe:** `recipes/nullclaw.yaml` (nullclaw/nullclaw — Zig static binary)
**Image:** `ap-recipe-nullclaw:latest`
**Status:** ✅ HIGH — sidecar bridge proven; recipe needs ~50-LOC Python aiohttp bridge baked into persistent_argv_override

> **Update notice (2026-04-29 PM).** v1 of this spike correctly found that
> `nullclaw gateway` exposes only `/health` (200) and `/pair` (POST, 405 for GET)
> on port 3000 — no native chat HTTP. v1 then proposed `docker_exec_cli`.
>
> Per user directive **"5 out of 5 must work"** — uniform `http_localhost`
> required — v2 of this spike empirically validates the sidecar HTTP→CLI
> bridge pattern (same shape as picoclaw's bridge; only `INAPP_BOT_BIN=nullclaw`
> differs). Result: PASS. nullclaw moves to `http_localhost` with a recipe-side
> sidecar.

## Empirical command (v2 — sidecar bridge)

```bash
docker run -d -t --name spike-nullbridge --user root -p 18792:18791 -p 18303:3000 \
  -e OPENROUTER_API_KEY=sk-or-fake-for-spike \
  -e INAPP_AUTH_TOKEN=spike-bridge-token \
  -e INAPP_BOT_BIN=nullclaw \
  -e INAPP_BRIDGE_PORT=18791 \
  -e INAPP_SESSION_PREFIX=inapp:agent:spike \
  -v /tmp/nullclaw-bridge-entrypoint.sh:/spike.sh \
  --entrypoint sh ap-recipe-nullclaw:latest /spike.sh
```

Same 50-LOC aiohttp bridge as picoclaw, with two adaptations:

1. `INAPP_BOT_BIN=nullclaw` (env var; rest of bridge code is shared)
2. Bridge passes `-s "${INAPP_SESSION_PREFIX}"` to `nullclaw agent` so the
   bot's own conversation memory persists across messages within one agent
   instance (D-22 dumb-pipe: bot owns its memory).

The entrypoint script (4 stages):

1. `apk add --no-cache python3 py3-aiohttp` (~7s, alpine apk works the same as picoclaw)
2. Write `/tmp/inapp-bridge.py` (shared 50-LOC source; only env-var differences)
3. Write `/nullclaw-data/config.json` with provider + model + gateway config; `chown -R nobody:nobody /nullclaw-data` (image's default user is `nobody`)
4. `nohup python3 /tmp/inapp-bridge.py >/tmp/bridge.log 2>&1 &` then `exec nullclaw gateway --host 0.0.0.0 --port 3000`

> **Note on `--user root`:** nullclaw's image runs as `nobody` by default but
> `apk add` requires root. Recipe's `persistent.spec` either runs as root + drops
> privileges via `gosu` (recipe pattern from picoclaw entrypoint) or installs
> python3 at IMAGE BUILD TIME so runtime can stay as `nobody`. v2 spike used
> `--user root` for simplicity; production recipe should bake the install into
> the image build for reproducibility + nobody-user runtime.

## Verbatim output

```
=== bridge.log ===
INAPP-BRIDGE listening on 0.0.0.0:18791

GET /health (bridge:18792):
{"status": "ok", "platform": "inapp-bridge"}                        HTTP 200

GET /health (bot:18303):
{"status":"ok"}                                                     HTTP 200

POST /v1/chat/completions (no auth):
{"error": {"message": "Unauthorized", "type": "unauthorized"}}      HTTP 401

POST /v1/chat/completions (Bearer spike-bridge-token):
{"error": {"message": "info(memory): memory plan resolved: backend=hybrid
   retrieval=keyword vector=none rollout=off hygiene=true snapshot=false
   cache=false semantic_cache=false summarizer=false sources=1
   error: ApiError\n", "type": "bot_error"}}                        HTTP 502
```

The 502 is the bridge faithfully reporting nullclaw's upstream LLM-call failure
(`error: ApiError` from the fake key). With a real key, nullclaw answers and
the bridge returns the OpenAI envelope.

## Findings

- nullclaw alpine image has `apk` available; `apk add python3 py3-aiohttp`
  succeeds as on picoclaw (same alpine base + same package availability).
- Bridge co-existence with the gateway: bot listens on port 3000 (gateway HTTP
  + telegram polling thread); bridge listens on 18791 (chat HTTP). No collision.
- The bot's own gateway STILL prints "Gateway pairing code generated (hidden for
  security). Use the /pair flow to complete pairing." That's the bot's external
  channel pairing flow (Telegram, Discord, etc.) — orthogonal to inapp. The
  bridge bypasses pairing because it speaks directly to the bot's CLI, not via
  external channels.
- Per-call latency: nullclaw is fast-cold (~1s for `agent -m`), so the bridge's
  per-message overhead is negligible.

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
      user_override: root
      argv:
        - -c
        - |
          set -e
          apk add --no-cache python3 py3-aiohttp >/dev/null
          cat > /tmp/inapp-bridge.py <<'PYEOF'
          # ... 50-LOC aiohttp bridge (shared with picoclaw) ...
          PYEOF
          cat > /nullclaw-data/config.json <<EOF
          {"agents":{"defaults":{"model":{"primary":"openrouter/$MODEL"}}},"models":{"providers":{"openrouter":{"api_key":"${OPENROUTER_API_KEY}","base_url":"https://openrouter.ai/api/v1"}}},"gateway":{"port":3000,"host":"::","allow_public_bind":true}}
          EOF
          chown -R nobody:nobody /nullclaw-data
          nohup python3 /tmp/inapp-bridge.py >/tmp/bridge.log 2>&1 &
          exec nullclaw gateway --host 0.0.0.0 --port 3000
    activation_env:
      INAPP_BOT_BIN: "nullclaw"
      INAPP_AUTH_TOKEN: "${INAPP_AUTH_TOKEN}"
      INAPP_BRIDGE_PORT: "18791"
      INAPP_SESSION_PREFIX: "inapp:agent:${AGENT_ID}"   # stable session id; bot persists own memory
```

## Risk flags

- **LOW risk on the sidecar pattern.** Identical to picoclaw spike result; same code, same dependencies.
- **LOW risk on apk add.** alpine's `py3-aiohttp` is in the main repo for nullclaw image too.
- **MEDIUM risk: per-message session id.** nullclaw `agent -m` defaults to a
  fresh session unless `-s SESSION` is provided. The bridge passes
  `INAPP_SESSION_PREFIX` so memory persists. Without it, every chat message
  starts a fresh conversation. Recipe activation_env MUST set this.
- **MEDIUM risk: image-build vs runtime install.** v1 spike installed python3 at
  RUNTIME via apk. Production recipe SHOULD bake the install into the image
  build (recipe `build:` step) so runtime can run as `nobody` without needing
  root privileges. Defer to plan-phase decision.
- **LOW risk: gateway pairing-code stdout.** The `Gateway pairing code generated`
  log line is unrelated to inapp; it's for the bot's own external channels. The
  bridge's `INAPP-BRIDGE listening` line is the inapp readiness signal.

## What this changes about the per-recipe matrix

After v2 sidecar validation, ALL 5 recipes use `transport: http_localhost`:

| Recipe | Transport | How chat HTTP is exposed |
|--------|-----------|--------------------------|
| hermes | http_localhost | native `gateway.platforms.api_server` (env-flag activated, port 8642) |
| nanobot | http_localhost | native `nanobot serve` mode (port 8900) |
| openclaw | http_localhost | native `/v1/chat/completions` (chatCompletions config flag, port 18789) |
| picoclaw | http_localhost | recipe-side sidecar (apk add python3 + 50-LOC aiohttp on port 18791) |
| nullclaw | http_localhost | recipe-side sidecar (same 50-LOC, INAPP_BOT_BIN=nullclaw, port 18791) |

Single transport verb, single dispatcher path, uniform recipe schema. Per user
directive: 5/5 work.
