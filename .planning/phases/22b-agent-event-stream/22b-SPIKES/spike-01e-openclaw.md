---
spike: 01e
name: reply-sent-regex-openclaw
validates: "Given a running openclaw container with Telegram creds + Anthropic-direct auth, when a real user DMs the bot and the bot replies, identify the observation surface for captured reply events (docker logs vs file log vs session store)"
verdict: PASS_WITH_FLAG
related: [spike-01a, spike-01b, spike-01c, spike-01d]
tags: [openclaw, telegram, log-regex, file-tail-fallback, recipe-gap]
---

# Spike 01e — openclaw reply_sent regex (PASS_WITH_FLAG)

## Outcome summary

Round-trip confirmed end-to-end via direct `docker run` with `ANTHROPIC_API_KEY` in env at boot. User sent `Hi` and `spk01e please reply with only: ok-openclaw-01` — bot replied to both. `ok-openclaw-01` captured verbatim in openclaw's session JSONL. FLAG: reply_sent is NOT observable via docker logs or the file log — must tail the session JSONL.

## How I ran it

The API-server path's `/start` endpoint stored the passed bearer as `OPENROUTER_API_KEY` env (per recipe `process_env.api_key`) regardless of actual provider. openclaw's auto-plugin-enable logic saw the openrouter env var and auto-enabled its broken openrouter plugin. Plus the recipe argv baked `tg:` and `openrouter/` prefixes that openclaw's own migrator interpreted as canonical.

Bypassed via direct `docker run`:

```bash
docker run -d --rm --name spk01e-openclaw-direct-<ts> \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  ap-recipe-openclaw \
  sh -c '
    set -e
    mkdir -p /home/node/.openclaw
    cat > /home/node/.openclaw/openclaw.json <<EOF
    {
      "channels": {
        "telegram": {
          "enabled": true,
          "botToken": "${TELEGRAM_BOT_TOKEN}",
          "dmPolicy": "allowlist",
          "allowFrom": ["*"]
        }
      },
      "agents": {
        "defaults": {
          "model": {
            "primary": "anthropic/claude-haiku-4-5"
          }
        }
      }
    }
EOF
    rm -f /home/node/.openclaw/openclaw.json5
    exec openclaw gateway --allow-unconfigured
  '
```

Boot: 100s. Ready at `[telegram] [default] starting provider (@AgentPlayground_bot)`. **Config post-migrator stayed clean** — `plugins: ['anthropic']`, `allowFrom: ['*']`, `model: {primary: 'anthropic/claude-haiku-4-5'}`. The `ANTHROPIC_API_KEY` env at boot is the unblock — it makes openclaw auto-detect the anthropic provider rather than openrouter.

User DM 1 (`Hi`): bot replied with identity-discovery greeting within ~27s.
User DM 2 (`spk01e please reply with only: ok-openclaw-01`): bot replied with `ok-openclaw-01` within ~6s.

## Where the reply activity DOES live

### docker logs (stdout + stderr) — BARREN

27 lines total. Only boot + lifecycle events. Last line before and after the round-trip: `[telegram] [default] starting provider`. **Per-message activity: none.**

### File log `/tmp/openclaw/openclaw-2026-04-18.log` — BARREN

29 lines (JSON-lines format). Only boot + lifecycle. No per-message activity.

### Session JSONL `/home/node/.openclaw/agents/main/sessions/<session_id>.jsonl` — ✅ AUTHORITATIVE

10 lines after 2 round-trips. Each conversation turn is one JSON line. Roles include:
- `session` (start marker)
- `model_change`, `thinking_level_change`
- `message` — the real content. Inner `message.role` is `user` or `assistant`; `message.content` is the OpenAI-style content-block array (`type: thinking|text`).

Example assistant entry (spike-01e-openclaw):
```json
{"type":"message",
 "id":"3c7038fd",
 "parentId":"eb2e151a",
 "timestamp":"2026-04-18T22:33:54.599Z",
 "message":{
   "role":"assistant",
   "content":[
     {"type":"thinking","thinking":"The user is asking me to reply..."},
     {"type":"text","text":"ok-openclaw-01"}      ← reply body right here
   ]
 }
}
```

`grep -c "ok-openclaw-01" <session_file>` → **2 hits** (user send + assistant echo). Verified correlation-via-reply-text works identically to picoclaw.

### Session manifest `/home/node/.openclaw/agents/main/sessions/sessions.json`

Maps `agent:main:main` → `{sessionId, origin:{from:telegram:152099202, provider:telegram,...}}`. Watcher resolves which JSONL file to tail by reading this manifest first.

## Authored config (committed to recipes/openclaw.yaml)

```yaml
event_log_regex:
  reply_sent: null        # not in docker logs
  inbound_message: null   # not in docker logs
  agent_error: "\"logLevelName\":\"(?:ERROR|FATAL)\""   # file-log fallback for errors

event_source_fallback:
  kind: file_tail_in_container
  spec:
    sessions_manifest: /home/node/.openclaw/agents/main/sessions/sessions.json
    session_log_template: "/home/node/.openclaw/agents/main/sessions/{session_id}.jsonl"
```

Watcher design (for planner):
1. On container start, read `sessions_manifest` to find session_ids per telegram chat.
2. `docker exec <cid> tail -f <session_log_template>` per session.
3. Parse each new line; when `message.role=="assistant"` with `content[].type=="text"`, emit `reply_sent` event with text as body.
4. Correlation-via-reply-text works (reply echoes user's prompt including correlation id).

## 2nd-order architecture finding — reinforces spike 01c

**Two of five recipes (nullclaw, openclaw) cannot use docker-logs-scrape.** That's 40% of the catalog. CONTEXT.md D-01's default-to-docker-logs is correct, but the `event_source_fallback` field is **load-bearing, not an edge case**. Watcher service MUST support at least:
- `docker_logs_stream` (default — hermes, picoclaw, nanobot)
- `docker_exec_poll` (nullclaw — `nullclaw history show --json`)
- `file_tail_in_container` (openclaw — session JSONL)

Recommend D-23 in CONTEXT.md formalizes this as a first-class requirement.

## Verdict: PASS_WITH_FLAG

- **Round-trip confirmed** end-to-end (user → Telegram → openclaw → Anthropic → Telegram → user).
- **reply_sent via docker logs: NOT AVAILABLE.** Documented.
- **Alternative observation path: session JSONL file tail.** Wired into recipe YAML.
- **Architecture-impact:** reinforces spike 01c's finding — per-recipe event_source_fallback is architecturally required, not edge case.
- **Not BLOCKED.** Observation path exists and is documented. Recipe overhaul for the /start path (mapping ANTHROPIC_API_KEY properly) is a separate concern — doesn't block Phase 22b planner from starting.

## What's still needed (separate phase, not blocking)

1. **Recipe `process_env` needs per-provider branch** — when bearer is an Anthropic key, inject it as `ANTHROPIC_API_KEY` env, not `OPENROUTER_API_KEY`. The API server's `/v1/agents/:id/start` handler must know the target provider so it can set the right env. This is API-runner plumbing, not spike-01e scope.
2. **Recipe `persistent.spec.argv` removes `tg:` and `openrouter/` prefixes OR uses `dmPolicy=allowlist + allowFrom=["*"]` as the canonical zero-config form.** Without either approach, the recipe is broken for Anthropic-direct persistent mode.
3. **Watcher `file_tail_in_container` implementation.** Planner adds this as a kind.

## Files modified

- `recipes/openclaw.yaml` — added `event_log_regex` (nulls) + `event_source_fallback` (file_tail_in_container pointing at session JSONL) + 2026-04-18 verified_cells entry (PASS_WITH_FLAG).

## Related

- spike-01c-nullclaw.md — sibling FLAG (docker_exec_poll fallback)
- CONTEXT.md D-23 (proposed) — per-recipe fallback sources are mandatory
- 22-CONTEXT.md §openclaw deferred-openrouter block — upstream provenance
