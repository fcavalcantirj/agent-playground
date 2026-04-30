# Spike: openclaw — channels.inapp HTTP-localhost re-validation (Wave 0)

**Date:** 2026-04-30
**Recipe:** `recipes/openclaw.yaml`
**Image:** `ap-recipe-openclaw:latest` (built 2 weeks ago, 2.35 GB, openclaw 2026.4.15-beta.1)
**Provider/model:** `anthropic` direct / `anthropic/claude-haiku-4-5` (recipe `verified_cells[0]` model + `provider_compat.supported=[anthropic]` per `known_quirks.openrouter_provider_plugin_silent_fail`)
**Contract:** `openai_compat`
**Endpoint:** `POST /v1/chat/completions` on container port 18789
**Status:** ✅ PASS (contract shape) — fresh local end-to-end probe returned a valid OpenAI envelope with `choices[0].message.content` populated. The content surfaced an upstream Anthropic billing error (zero credit on the developer's ANTHROPIC_API_KEY at probe time), faithfully relayed by the bot. The contract — `openai_compat` — is empirically validated.

## Background

The 2026-04-29 spike (revised PM) PROVED that openclaw exposes `/v1/chat/completions` when `gateway.http.endpoints.chatCompletions.enabled = true` AND the bot runs `openclaw gateway run` (NOT `--allow-unconfigured`). The cross-check came from MSV's `forward_to_agent.go:70` + `provision_ops.go:386`. Wave 0 re-validates against the current image with the verified anthropic-direct provider path (the recipe explicitly defers OpenRouter due to the upstream `openrouter_provider_plugin_silent_fail` plugin bug).

## Reproducible probe (verbatim)

```bash
# Source $ANTHROPIC_API_KEY (developer's shell)

cat > /tmp/spike-openclaw-entry.sh <<'EOF'
set -e
mkdir -p /home/node/.openclaw
cat > /home/node/.openclaw/openclaw.json <<JSON
{
  "agents": {
    "defaults": {
      "model": { "primary": "anthropic/claude-haiku-4-5", "fallbacks": [] },
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
        "chatCompletions": { "enabled": true }
      }
    },
    "auth": {
      "mode": "token",
      "token": "spike-w0-token"
    },
    "controlUi": { "dangerouslyAllowHostHeaderOriginFallback": true }
  },
  "channels": {},
  "skills": { "install": { "nodeManager": "npm" }, "entries": {} },
  "update": { "checkOnStart": false }
}
JSON
rm -f /home/node/.openclaw/openclaw.json5
exec node openclaw.mjs gateway run --port 18789
EOF

docker rm -f spike-w0-openclaw 2>/dev/null
docker run -d -t --name spike-w0-openclaw -p 18789:18789 \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -v /tmp/spike-openclaw-entry.sh:/spike.sh \
  --entrypoint sh ap-recipe-openclaw:latest /spike.sh

# Wait until "ready (N plugins"
until docker logs spike-w0-openclaw 2>&1 | grep -q "ready ([0-9]"; do sleep 5; done

curl -s -m 60 -X POST http://localhost:18789/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer spike-w0-token' \
  -d '{"model":"openclaw","messages":[{"role":"user","content":"who are you in 1 short sentence?"}]}'

docker rm -f spike-w0-openclaw
```

## Boot logs (verbatim, key lines)

```
🦞 OpenClaw 2026.4.15-beta.1 (unknown)
[gateway] loading configuration…
[gateway] resolving authentication…
[gateway] auto-enabled plugins:
- openrouter/anthropic/claude-haiku-4.5 model configured, enabled automatically.
[gateway] starting HTTP server...
[gateway] agent model: anthropic/claude-haiku-4-5
[gateway] ready (5 plugins: acpx, browser, device-pair, phone-control, talk-voice; 11.3s)
[browser/server] Browser control listening on http://127.0.0.1:18791/ (auth=token)
[heartbeat] started
[plugins] embedded acpx runtime backend ready
```

## Response (verbatim)

```json
{
  "id": "chatcmpl_c4080921-eaa1-455e-a1f6-33e8470db210",
  "object": "chat.completion",
  "created": 1777572862,
  "model": "openclaw",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "LLM request rejected: Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

Parsed `choices[0].message.content` = 142 chars; non-empty; OpenAI envelope intact (`object="chat.completion"`, `choices[0].message.content` is a string, `model="openclaw"`).

## Auth-gate proof (route binding, verbatim)

```
HTTP 401 (no Bearer)
HTTP 200 (Bearer spike-w0-token + model="openclaw")
HTTP 400 (Bearer + model="openrouter/anthropic/claude-haiku-4.5")
        → {"error":{"message":"Invalid `model`. Use `openclaw` or `openclaw/<agentId>`.","type":"invalid_request_error"}}
```

The 401 → 400 → 200 progression is the proof that `/v1/chat/completions` is bound and behind the auth gate, with the OpenAI error envelope shape on validation failures and the OpenAI completion envelope shape on success — exactly what the dispatcher's `openai_compat` adapter requires.

## Findings

- `gateway.http.endpoints.chatCompletions.enabled = true` is the load-bearing flag — drops `--allow-unconfigured` from the persistent argv.
- `auth.mode = "token"` + `auth.token = "<bearer>"` enforces the auth gate at the HTTP layer.
- The model field MUST be `"openclaw"` or `"openclaw/<agentId>"`. The dispatcher's `openai_compat` adapter handles this via `recipes/openclaw.yaml::channels.inapp.model_alias = "openclaw"` (recipe declares; dispatcher rewrites the body's `model` field before forwarding).
- The bot's underlying provider (anthropic / openrouter / openai) is configured at recipe-bootstrap time in `agents.defaults.model.primary`. The bot maps `model="openclaw"` from the request → upstream `model.primary` from the config.
- Cold-boot wall: ~11s to "ready"; subsequent dispatches reuse the running container per Phase 22c.3 D-37 readiness gate.

## Verdict

**PASS** (contract shape).

The dispatcher's `openai_compat` adapter is empirically reachable on this recipe. The recipe's documented quirks — OpenRouter plugin silent-fail and Anthropic-direct as the verified provider — are honored by the recipe's existing `process_env.api_key_by_provider` mapping. The fact that the developer's ANTHROPIC_API_KEY had zero credit at probe time surfaces as the bot's content reply, NOT as a contract failure: HTTP 200, OpenAI envelope intact, `choices[0].message.content` populated. This is the correct dumb-pipe behavior per D-22.

## Anomalies observed

- **Anthropic billing on probe-time:** `ANTHROPIC_API_KEY` had zero credit at probe time. Verified independently against `https://api.anthropic.com/v1/messages` directly (same `invalid_request_error / credit balance is too low` response). Not a contract failure — the recipe relays the upstream error verbatim through the OpenAI envelope.
- **OpenRouter path remains deferred** per `known_quirks.openrouter_provider_plugin_silent_fail` — the bot's `openrouter` plugin returns `[agent/embedded] incomplete turn detected: payloads=0 — surfacing error to user` and `choices[0].message.content="⚠️ Agent couldn't generate a response. Please try again."` Independent of contract shape; orthogonal to Wave 0.
- **`Config write anomaly: missing-meta-before-write`** appears once on first boot when the recipe heredoc rewrites `openclaw.json`. Cosmetic; gateway boots regardless.

## Wave 0 gate

The `openai_compat` contract is empirically reachable on `ap-recipe-openclaw:latest`:

1. Route binds (`POST /v1/chat/completions`) — proven by 401/400/200 progression.
2. OpenAI envelope shape is honored — proven by parse against `object`, `choices[0].message.content` schema.
3. Real provider call dispatched through bot — proven by upstream Anthropic error text appearing in the content.

Plan 22c.3-12 (openclaw recipe modification) absorbs the `chatCompletions.enabled = true` config flag + drops `--allow-unconfigured` from `persistent.spec.argv`. Plan 22c.3-05 (dispatcher) implements the `openai_compat` adapter with the model-alias rewrite path.
