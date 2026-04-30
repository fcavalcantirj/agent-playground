# Spike: nanobot — channels.inapp HTTP-localhost re-validation (Wave 0)

**Date:** 2026-04-30
**Recipe:** `recipes/nanobot.yaml`
**Image:** `ap-recipe-nanobot:latest` (built 2 weeks ago, 842 MB)
**Provider/model:** `openrouter` / `anthropic/claude-haiku-4-5` (recipe `verified_cells[0]` model is `openai/gpt-4o-mini`; haiku-4-5 is the equivalent fixed-prompt model used here for parity with the rest of the matrix; both are listed in nanobot spike sources)
**Contract:** `openai_compat`
**Endpoint:** `POST /v1/chat/completions` on container port 8900 (mapped to host port 18900)
**Status:** ✅ PASS — fresh local end-to-end probe with real OpenRouter call returned a valid OpenAI envelope with persona-correct content.

## Background

Nanobot ships `nanobot serve` — a first-class OpenAI-compatible HTTP server. Documented in `nanobot --help`: `serve   Start the OpenAI-compatible API server (/v1/chat/completions).` Per the existing 2026-04-29 spike, the recipe activates inapp via `persistent_argv_override` that writes a small config and then runs `nanobot serve`. Wave 0 re-validates against the current image with a real LLM round-trip.

## Reproducible probe (verbatim)

```bash
# Source $OPENROUTER_API_KEY (developer's shell; in this run /Users/fcavalcanti/dev/agent-playground/.env.local)

# Bootstrap script written to /tmp/spike-nanobot-entry.sh:
cat > /tmp/spike-nanobot-entry.sh <<'EOF'
set -e
mkdir -p /home/nanobot/.nanobot
cat > /home/nanobot/.nanobot/config.json <<JSON
{
  "agents": {
    "defaults": {
      "provider": "openrouter",
      "model": "anthropic/claude-haiku-4-5"
    }
  },
  "providers": {
    "openrouter": {
      "api_key": "${OPENROUTER_API_KEY}",
      "api_base": "https://openrouter.ai/api/v1"
    }
  }
}
JSON
exec nanobot serve --port 8900 --host 0.0.0.0 --timeout 600
EOF

docker rm -f spike-w0-nanobot 2>/dev/null
docker run -d -t --name spike-w0-nanobot -p 18900:8900 \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -v /tmp/spike-nanobot-entry.sh:/spike.sh \
  --entrypoint sh ap-recipe-nanobot:latest /spike.sh

sleep 10

curl -s -m 90 -X POST http://localhost:18900/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"anthropic/claude-haiku-4-5","messages":[{"role":"user","content":"who are you in 1 short sentence?"}]}'

docker rm -f spike-w0-nanobot
```

## Boot logs (verbatim, key lines)

```
🐈 Starting OpenAI-compatible API server
  Endpoint : http://0.0.0.0:8900/v1/chat/completions
  Model    : anthropic/claude-haiku-4-5
  Session  : api:default
  Timeout  : 600.0s
Warning: API is bound to all interfaces. Only do this behind a trusted network boundary, firewall, or reverse proxy.
```

## Response (verbatim)

```json
{
  "id": "chatcmpl-b5b9d2c7b721",
  "object": "chat.completion",
  "created": 1777572638,
  "model": "anthropic/claude-haiku-4-5",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "I'm nanobot 🐈, a personal AI assistant that solves problems by doing, not describing."
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

Parsed `choices[0].message.content` = 90 chars; non-empty; persona-correct ("I'm nanobot 🐈").

## Findings

- `nanobot serve` is the canonical activation for inapp — distinct from `nanobot gateway` used for telegram. Single-channel-per-instance per D-20.
- Per-request timeout via `--timeout 600` honors D-40 (10-minute bot timeout).
- No built-in auth gate — the recipe binds 127.0.0.1 in production and the api_server's dispatcher reaches it via Docker bridge networking; auth is enforced upstream by `require_user`.
- Real OpenRouter call latency: ~5s on this run.
- `usage` block is all zeros — nanobot does not propagate token counts upstream from the provider response. Not a contract concern (api_server doesn't meter via this path).

## Verdict

**PASS** — the `channels.inapp` `openai_compat` shape works against a fresh `ap-recipe-nanobot:latest` boot with real OpenRouter inference. Wave 0 gate satisfied for nanobot.

## Anomalies observed

- None blocking. Two minor observations:
  - The `Session  : api:default` log line indicates a single shared HTTP-server session — fine for D-22 dumb-pipe (bot owns its memory; inapp routes by api-server-side `agent_id`).
  - `--host 0.0.0.0` is required for the api_server dispatcher to reach the bot from a different Docker network — recipe `channels.inapp.activation_env` must reflect this.
