# Spike: hermes — channels.inapp HTTP-localhost feasibility

**Date:** 2026-04-29
**Recipe:** `recipes/hermes.yaml`
**Image:** `ap-recipe-hermes:latest`
**Status:** ✅ HIGH — native OpenAI-compat HTTP server, env-only activation

## Empirical command

```bash
docker run --rm \
  -e API_SERVER_ENABLED=true \
  -e API_SERVER_KEY=test-key-spike \
  -e API_SERVER_PORT=8642 \
  -e OPENROUTER_API_KEY=fake-spike-test \
  --entrypoint sh ap-recipe-hermes:latest -c '
    /opt/hermes/.venv/bin/hermes gateway run -v &
    sleep 15
    /opt/hermes/.venv/bin/python -c "
import urllib.request
r = urllib.request.urlopen(\"http://127.0.0.1:8642/health\", timeout=3)
print(\"GET /health ->\", r.status, r.read()[:200])
req = urllib.request.Request(\"http://127.0.0.1:8642/v1/models\",
                             headers={\"Authorization\": \"Bearer test-key-spike\"})
r2 = urllib.request.urlopen(req, timeout=3)
print(\"GET /v1/models ->\", r2.status, r2.read()[:200])
"'
```

## Verbatim output

```
INFO gateway.platforms.api_server: [Api_Server] API server listening on http://127.0.0.1:8642 (model: hermes-agent)
INFO gateway.run: ✓ api_server connected
INFO gateway.run: Gateway running with 1 platform(s)
GET /health -> 200 b'{"status": "ok", "platform": "hermes-agent"}'
GET /v1/models -> 200 b'{"object": "list", "data": [{"id": "hermes-agent", ... "owned_by": "hermes", ...}]}'
```

## Findings

- Hermes ships a **first-class OpenAI-compatible API server** as a built-in gateway platform (`gateway/platforms/api_server.py`).
- Activation: env vars only. **No config-file edits required.**
  - `API_SERVER_ENABLED=true` (or any non-empty `API_SERVER_KEY`)
  - `API_SERVER_PORT` (default 8642)
  - `API_SERVER_HOST` (default 127.0.0.1)
  - `API_SERVER_KEY` — Bearer token enforced at the HTTP layer
- Endpoints documented in source (`gateway/platforms/api_server.py:5-15`):
  - `POST /v1/chat/completions` — OpenAI Chat Completions
  - `POST /v1/responses` — OpenAI Responses API
  - `GET  /v1/models`
  - `POST /v1/runs` + `GET /v1/runs/{id}/events` — SSE lifecycle
  - `GET  /health`, `GET /health/detailed`
- Auth gate: `Authorization: Bearer <API_SERVER_KEY>` required for `/v1/*`. `/health` is unauthenticated.

## Verdict for `channels.inapp`

**HIGH confidence — no patch required.** The bot already implements the desired contract (OpenAI-compat `/v1/chat/completions`). The recipe's `channels.inapp` block:

```yaml
channels:
  inapp:
    transport: http_localhost
    port: 8642
    contract: openai_chat_completions
    endpoint: /v1/chat/completions
    auth_header: "Authorization: Bearer ${INAPP_API_KEY}"
    ready_log_regex: "\\[Api_Server\\] API server listening"
    activation_env:
      API_SERVER_ENABLED: "true"
      API_SERVER_KEY: "${INAPP_API_KEY}"   # injected per-session by runner
      API_SERVER_PORT: "8642"
      API_SERVER_HOST: "127.0.0.1"
```

Runner generates a per-session opaque token, injects it both as `API_SERVER_KEY` (bot side) and stores it in `agent_containers.inapp_auth_token` (api side) to forward on dispatch.

## Risk flags

- **None blocking.** The api_server platform is in-tree, well-documented, supports concurrent SSE for `/v1/runs/{id}/events` — already battle-tested by the gateway codebase.
- **Co-existence with telegram channel:** the gateway runs MULTIPLE platforms simultaneously (`Gateway running with N platform(s)`). Phase 22c.3 is single-channel-per-instance per D-20, so co-existence isn't required for v1.
