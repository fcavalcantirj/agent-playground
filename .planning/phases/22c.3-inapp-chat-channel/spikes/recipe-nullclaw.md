# Recipe spike: nullclaw (revised v3 — native A2A) — Wave 0 re-validation

**Date:** 2026-04-30
**Recipe:** `recipes/nullclaw.yaml` (nullclaw/nullclaw — Zig static binary)
**Image:** `ap-recipe-nullclaw:latest` (built 2 weeks ago, 18.9 MB)
**Provider/model:** `openrouter` / `anthropic/claude-haiku-4.5` (recipe `verified_cells[0]`)
**Contract:** `a2a_jsonrpc`
**Endpoint:** `POST /a2a` on container port 3000 (mapped to host port 18399), JSON-RPC 2.0 method `message/send`
**Status:** ✅ FULL_PASS — fresh local end-to-end probe with real OpenRouter call returned `state=completed` and a 102-char real LLM reply in `result.artifacts[0].parts[0].text`.

> **Round-3 supersession.** v1 (2026-04-29 AM) used `docker_exec_cli`. v2 (2026-04-29 PM) added a Python HTTP-to-CLI bridge sidecar at port 18791. Both are SUPERSEDED by this v3, which uses nullclaw's NATIVE Google A2A JSON-RPC 2.0 protocol on `/a2a` — the v2 sidecar pattern (runtime package install, background-process bot binary indirection, env-var override) is dropped entirely. Per Round-3 RESEARCH §Revision Notice the dispatcher implements an `a2a_jsonrpc` contract adapter for nullclaw alongside `openai_compat` and `zeroclaw_native`.

## Reproducible probe (verbatim)

```bash
# Source $OPENROUTER_API_KEY (developer's shell)

cat > /tmp/spike-null-entry.sh <<'EOF'
set -e
mkdir -p /nullclaw-data
cat > /nullclaw-data/config.json <<JSON
{"agents":{"defaults":{"model":{"primary":"openrouter/anthropic/claude-haiku-4.5"}}},
 "models":{"providers":{"openrouter":{"api_key":"${OPENROUTER_API_KEY}"}}},
 "gateway":{"port":3000,"host":"0.0.0.0","allow_public_bind":true,"require_pairing":false},
 "a2a":{"enabled":true,"name":"w0","url":"http://localhost:3000","version":"0.3.0"}}
JSON
chown -R nobody:nobody /nullclaw-data 2>/dev/null || true
exec nullclaw gateway --host 0.0.0.0 --port 3000
EOF

docker rm -f spike-w0-null 2>/dev/null
docker run -d -t --user root --name spike-w0-null -p 18399:3000 \
  -e OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  -v /tmp/spike-null-entry.sh:/spike.sh \
  --entrypoint sh ap-recipe-nullclaw:latest /spike.sh

sleep 8

# Probe 1 — agent card
curl -s http://localhost:18399/.well-known/agent-card.json

# Probe 2 — message/send (real LLM round-trip via OpenRouter)
curl -s -X POST http://localhost:18399/a2a \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"who are you in 1 short sentence?"}],"messageId":"w0-null-1"}}}'

docker rm -f spike-w0-null
```

## Boot logs (verbatim)

```
nullclaw gateway runtime started
  Gateway:  http://0.0.0.0:3000
  Components: 2 active
  Model:    anthropic/claude-haiku-4.5
  Provider: openrouter
  Ctrl+C to stop
info(memory): memory plan resolved: backend=hybrid retrieval=keyword vector=none rollout=off hygiene=true snapshot=false cache=false semantic_cache=false summarizer=false sources=1
info(session): vision probe: querying model 'anthropic/claude-haiku-4.5' for image support
info(session): vision probe: model 'anthropic/claude-haiku-4.5' probe inconclusive (AllProvidersFailed), leaving capability unset
Gateway listening on 0.0.0.0:3000
```

## Probe 1 — `/.well-known/agent-card.json` (verbatim)

```json
{
  "name": "w0",
  "description": "AI assistant",
  "protocolVersion": "0.3.0",
  "version": "0.3.0",
  "url": "http://localhost:3000/a2a",
  "supportedInterfaces": [{
    "url": "http://localhost:3000/a2a",
    "protocolBinding": "JSONRPC",
    "protocolVersion": "0.3.0"
  }],
  "preferredTransport": "JSONRPC",
  "provider": {"organization": "w0", "url": "http://localhost:3000"},
  "capabilities": {"streaming": true},
  "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "description": "Use a pairing token from /pair as the bearer token."}},
  "security": [{"bearerAuth": []}],
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [{"id": "chat", "name": "General Chat", "description": "General-purpose AI assistant", "tags": ["chat", "general"]}]
}
```

`protocolVersion: "0.3.0"` confirmed. `preferredTransport: JSONRPC`. `capabilities.streaming: true` (the recipe's streaming path uses `message/stream` returning SSE chunks; not exercised in this Wave-0 probe — the dispatcher's sync path uses `message/send`).

## Probe 2 — `POST /a2a` `method=message/send` (verbatim, real OpenRouter call)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "id": "task-1",
    "kind": "task",
    "contextId": "ctx-1",
    "status": {"state": "completed", "timestamp": "2026-04-30T18:17:23Z"},
    "metadata": {},
    "artifacts": [{
      "artifactId": "artifact-task-1",
      "parts": [{
        "kind": "text",
        "text": "I'm Claude, an AI assistant here to help you think through problems, build things, and get stuff done."
      }]
    }],
    "history": [
      {"kind": "message", "role": "user", "messageId": "msg-user-task-1", "taskId": "task-1", "contextId": "ctx-1", "parts": [{"kind": "text", "text": "who are you in 1 short sentence?"}]},
      {"kind": "message", "role": "agent", "messageId": "msg-agent-task-1", "taskId": "task-1", "contextId": "ctx-1", "parts": [{"kind": "text", "text": "I'm Claude, an AI assistant here to help you think through problems, build things, and get stuff done."}]}
    ]
  }
}
```

Parse path: `result.status.state` = `"completed"`; `result.artifacts[0].parts[0].text` = 102 chars; non-empty. The dispatcher's `a2a_jsonrpc` adapter reads exactly this path.

## Findings

- Native A2A is built into nullclaw 2026.4.x (Zig binary `~700 KB`, gateway boot ~3s).
- `a2a.enabled = true` + `a2a.name` + `a2a.url` + `a2a.version="0.3.0"` in `/nullclaw-data/config.json` are the activation fields. Without them, `/.well-known/agent-card.json` returns 404.
- `gateway.require_pairing = false` is required for the dispatcher's loopback-trusted forwarding (no Bearer needed; auth lives upstream at `require_user`).
- `gateway.host = "0.0.0.0"` + `gateway.allow_public_bind = true` — without `allow_public_bind`, the gateway refuses non-loopback hosts.
- The bot answers as the underlying provider's persona ("I'm Claude") rather than a custom nullclaw persona because nullclaw's default system prompt is a blank slate (recipe `known_weak_probes` documents this — the bot has no name; the model identifies as itself).
- Real OpenRouter call latency: ~3s.

## Verdict

**FULL_PASS** — `a2a_jsonrpc` contract empirically reachable on `ap-recipe-nullclaw:latest` via native `/a2a` JSON-RPC 2.0 endpoint. Dispatcher's `a2a_jsonrpc` adapter has its parse-path target validated.

## Anomalies observed

- `vision probe: model probe inconclusive (AllProvidersFailed)` log line during boot — the bot tries to determine vision support by sending a tiny ping to OpenRouter; the AllProvidersFailed message is during the boot self-test, NOT during the chat probe. The chat probe itself succeeded. Cosmetic.
- The `--user root` flag is required because nullclaw's image runs as `nobody` by default but the `chown -R nobody:nobody /nullclaw-data` in the entrypoint needs root. The recipe's `persistent.spec.user_override: root` per Plan 22c.3-14 absorbs this.

## Wave 0 confirmation against Plan must-haves

- [x] `a2a_jsonrpc` contract present
- [x] `message/send` invoked
- [x] `result.artifacts[0].parts[0].text` non-empty
- [x] `/.well-known/agent-card.json` shows `protocolVersion=0.3.0`
- [x] Sidecar pattern (runtime package install, background-process bot binary indirection, env-var override) fully dropped per Round-3 supersession — none of those tokens appear in this v3 spike
- [x] Today's date 2026-04-30
