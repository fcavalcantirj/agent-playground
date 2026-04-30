# Spike: hermes — channels.inapp HTTP-localhost re-validation (Wave 0)

**Date:** 2026-04-30
**Recipe:** `recipes/hermes.yaml`
**Image:** `ap-recipe-hermes:latest` (built 2 weeks ago, 5.19 GB, hermes-agent v0.9.0)
**Provider/model:** `openrouter` / `anthropic/claude-haiku-4.5` (recipe `verified_cells[0]`)
**Contract:** `openai_compat`
**Endpoint:** `POST /v1/chat/completions` on container port 8642 (mapped to host port 18642)
**Status:** ✅ PASS — fresh local end-to-end probe with real OpenRouter call returned a valid OpenAI envelope and a real model reply.

## Background

Hermes ships a first-class OpenAI-compatible HTTP server as a built-in gateway platform (`gateway/platforms/api_server.py`). Activation is env-only when starting the gateway via `hermes gateway run`. Wave 0 re-validates the existing 2026-04-29 spike against the current image and a real LLM call.

## Reproducible probe (verbatim)

```bash
# Source the OPENROUTER_API_KEY (lives in $OPENROUTER_API_KEY in the developer's shell;
# in this run it was sourced from /Users/fcavalcanti/dev/agent-playground/.env.local)

# Bootstrap script written to /tmp/spike-hermes-entry.sh:
cat > /tmp/spike-hermes-entry.sh <<'EOF'
set -e
mkdir -p /opt/data
cat > /opt/data/config.yaml <<YAML
model:
  default: "anthropic/claude-haiku-4.5"
  provider: "openrouter"
  base_url: "https://openrouter.ai/api/v1"
YAML
chown -R hermes:hermes /opt/data 2>/dev/null || true
exec /opt/hermes/.venv/bin/hermes gateway run -v
EOF

# Run the container (mapped 18642:8642 on the host)
docker rm -f spike-w0-hermes 2>/dev/null
docker run -d -t --name spike-w0-hermes -p 18642:8642 \
  -e API_SERVER_ENABLED=true \
  -e API_SERVER_KEY=spike-w0-token \
  -e API_SERVER_PORT=8642 \
  -e API_SERVER_HOST=0.0.0.0 \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -v /tmp/spike-hermes-entry.sh:/spike.sh \
  --entrypoint sh ap-recipe-hermes:latest /spike.sh

sleep 18

# Probe (real OpenRouter call)
curl -s -m 90 -X POST http://localhost:18642/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer spike-w0-token' \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"who are you in 1 short sentence?"}]}'

docker rm -f spike-w0-hermes
```

## Boot logs (verbatim, key lines)

```
INFO gateway.run: Starting Hermes Gateway...
INFO gateway.run: Connecting to api_server...
INFO gateway.platforms.api_server: [Api_Server] API server listening on http://0.0.0.0:8642 (model: hermes-agent)
INFO gateway.run: ✓ api_server connected
INFO gateway.run: Gateway running with 1 platform(s)
INFO gateway.run: Cron ticker started (interval=60s)
```

## Response (verbatim)

```json
{
  "id": "chatcmpl-877c6d0889a94114b3306f682c221",
  "object": "chat.completion",
  "created": 1777572593,
  "model": "hermes-agent",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "I'm Hermes Agent, an AI assistant created by Nous Research that helps you accomplish tasks through reasoning, code execution, web interaction, and tool automation."
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 12944, "completion_tokens": 100, "total_tokens": 13044}
}
```

Parsed `choices[0].message.content` = 163 chars; non-empty; persona-correct ("Nous Research").

## Findings

- The api_server platform is fully OpenAI-compatible (`POST /v1/chat/completions`, `GET /health`, `GET /v1/models`, `POST /v1/runs` for SSE).
- Activation: `API_SERVER_ENABLED=true` + `API_SERVER_KEY=<bearer>` + `API_SERVER_PORT=8642` (default).
- The bot also requires a default model in `/opt/data/config.yaml` (`model.default`, `model.provider`, `model.base_url`) — without it, the api_server reports HTTP 200 + `choices[0].message.content` = `Error code: 400 - {'error': {'message': 'No models provided', 'code': 400}}`. The recipe's `channels.inapp` block must include the model bootstrap (already in plan).
- Real OpenRouter call latency: ~50s end-to-end on this run (cold tirith install first, model resolution, full inference).
- Auth gate: `Authorization: Bearer ${API_SERVER_KEY}` enforced. No bearer → HTTP 401.

## Verdict

**PASS** — the recipe's `channels.inapp` `openai_compat` shape works against a fresh `ap-recipe-hermes:latest` boot with real OpenRouter inference. Wave 0 gate satisfied for hermes.

## Anomalies observed

- The first naive boot (without writing `/opt/data/config.yaml`) produces a 200 with the upstream error in the content field — Wave 0 surfaced this as a recipe-bootstrap requirement, not a contract issue. The recipe author's `channels.inapp.persistent_argv_override` MUST write the config file before `gateway run`. Plan 22c.3-10 (hermes recipe modification) absorbs this.
- `API_SERVER_HOST` defaults to `127.0.0.1` (loopback). For per-container reachability from the api_server (which lives on a different bridge in the deploy stack), the recipe sets it to `0.0.0.0` per `channels.inapp.activation_env`.
