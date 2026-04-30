# Spike: nanobot — channels.inapp HTTP-localhost feasibility

**Date:** 2026-04-29
**Recipe:** `recipes/nanobot.yaml`
**Image:** `ap-recipe-nanobot:latest`
**Status:** ✅ HIGH — native OpenAI-compat via `nanobot serve`

## Empirical command

```bash
docker run --rm -e OPENROUTER_API_KEY=fake-spike-test \
  --entrypoint sh ap-recipe-nanobot:latest -c '
    mkdir -p /home/nanobot/.nanobot
    cat > /home/nanobot/.nanobot/config.json <<EOF
    {
      "agents": {"defaults": {"provider": "openrouter", "model": "anthropic/claude-haiku-4-5"}},
      "providers": {"openrouter": {"api_key": "${OPENROUTER_API_KEY}",
                                   "api_base": "https://openrouter.ai/api/v1"}}
    }
    EOF
    nanobot serve --port 8900 --host 127.0.0.1 &
    sleep 8
    curl -s -m 3 http://127.0.0.1:8900/v1/models'
```

## Verbatim output

```
🐈 Starting OpenAI-compatible API server
  Endpoint : http://127.0.0.1:8900/v1/chat/completions
  Model    : anthropic/claude-haiku-4-5
  Session  : api:default
  Timeout  : 120.0s

{"object": "list", "data": [{"id": "anthropic/claude-haiku-4-5",
  "object": "model", "created": 0, "owned_by": "nanobot"}]}
```

## Findings

- Nanobot ships `nanobot serve` — a **first-class OpenAI-compatible HTTP server**.
- Documented in `nanobot --help`: `serve   Start the OpenAI-compatible API server (/v1/chat/completions).`
- CLI flags: `--port` (configurable), `--host`, `--timeout` (default 120s; per-request), `--workspace`, `--config`.
- Default port: 8900 (recipe already documents this in `direct_interface` comments at line 271).
- Activation requires `nanobot serve` as the container entrypoint — **NOT** `nanobot gateway` (the existing persistent block uses `gateway` for telegram).
- Co-existence with `gateway`: documented in recipe but NOT empirically verified — the recipe's `direct_interface` falls back to `nanobot agent -m` via `docker exec` rather than serve.

## Verdict for `channels.inapp`

**HIGH confidence — no patch required, but the persistent.argv changes.** The recipe's `channels.inapp` block:

```yaml
channels:
  inapp:
    transport: http_localhost
    port: 8900
    contract: openai_chat_completions
    endpoint: /v1/chat/completions
    ready_log_regex: "Endpoint : http://127.0.0.1:8900"
    persistent_argv_override:
      entrypoint: sh
      argv:
        - -c
        - |
          mkdir -p /home/nanobot/.nanobot
          # ... same config heredoc as gateway ...
          exec nanobot serve --port 8900 --host 127.0.0.1
```

Per D-20 (single-channel-per-instance v1) the inapp deployment swaps `nanobot gateway` for `nanobot serve` — they're alternative entrypoints, not concurrent.

## Risk flags

- **MEDIUM risk:** `nanobot serve`'s `--timeout` is hard-capped at the per-request CLI flag (default 120s). D-40 requires 600s (10min). Override with `--timeout 600` in the persistent_argv_override.
- **LOW risk:** `nanobot serve` does NOT have a built-in auth gate the way hermes does. Need to verify whether the server accepts unauthenticated POSTs, or fronts via `Authorization: Bearer`. Spike-MEDIUM finding: verify before plan locks the spec — fall-back is the runner adds a tiny aiohttp auth proxy as a sidecar (5-10 LOC) if nanobot has no auth.
- **Empirical model on `serve` activation:** `Session  : api:default` — sessions are scoped to one HTTP server. Multi-tab SSE outbound is fine (D-09/10 fan-out via Redis); inbound forwards to the same `api:default` session. Bot's own conversation memory (D-22) handles ordering.
