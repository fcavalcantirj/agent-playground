---
spike: 01a
name: reply-sent-regex-hermes
validates: "Given a running hermes container with Telegram creds, when a real user DMs the bot and the bot replies, then docker logs contains a machine-parsable line that identifies the reply-sent event"
verdict: PASS_WITH_PIVOT
related: [spike-01b, spike-01c, spike-01d, spike-01e, spike-06]
tags: [hermes, telegram, log-regex, architecture-pivot]
---

# Spike 01a — Reply-sent regex for hermes

## What this validates

Probe hermes's log output during a real Telegram round-trip to:

1. Author a `reply_sent` regex with a correlation-id capture group
2. Confirm docker logs (not just an internal file) carries the event
3. Add a `channels.telegram.event_log_regex` entry + `verified_cells[]` note to `recipes/hermes.yaml`

## How I ran it

```bash
# 1. Reap any dangling container
docker rm -f ap-agent-01KPH0B8QSDEEND24DAFWE696Z

# 2. Load env
set -a; source .env.local; set +a
export TELEGRAM_CHAT_ID="$TELEGRAM_USER_CHAT_ID"
export TELEGRAM_ALLOWED_USER="$TELEGRAM_CHAT_ID"

# 3. Create agent_instance via smoke
curl -sS -X POST http://localhost:8000/v1/runs \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"recipe_name":"hermes","model":"anthropic/claude-haiku-4.5","agent_name":"spike-22b-01a-hermes-TS","personality":"polite-thorough"}'
# → verdict: PASS, agent_instance_id: 531f3012-…

# 4. Start persistent container
curl -sS -X POST http://localhost:8000/v1/agents/$AGENT_ID/start \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"channel":"telegram","channel_inputs":{"TELEGRAM_BOT_TOKEN":"...","TELEGRAM_ALLOWED_USERS":"152099202","TELEGRAM_ALLOWED_USER":"152099202"}}'
# → container_status: running, boot_wall_s: 8.76, container_id: bd307cbb96d6…

# 5. Human user typed "oi" in Telegram DM to @AgentPlayground_bot,
#    waited for bot reply. Then dumped logs:
docker logs bd307cbb96d6 2>&1

# 6. Stop
curl -sS -X POST http://localhost:8000/v1/agents/$AGENT_ID/stop -H "Authorization: Bearer $OPENROUTER_API_KEY"
# → stopped_gracefully: true, stop_wall_s: 8.14
```

## What I observed

### Canonical 3-line sequence per Telegram round-trip (confirmed in docker logs stdout)

```
INFO gateway.run: inbound message: platform=telegram user=Felipe chat=152099202 msg='oi'
INFO gateway.run: response ready: platform=telegram chat=152099202 time=13.9s api_calls=1 response=65 chars
INFO gateway.platforms.base: [Telegram] Sending response (65 chars) to 152099202
```

Also mirrored in `/opt/data/logs/agent.log` inside the container (with timestamps).

### Authored regexes

```
# fires when the bot actually calls Telegram sendMessage
reply_sent: ^INFO gateway\.platforms\.base: \[Telegram\] Sending response \((?P<chars>\d+) chars\) to (?P<chat_id>\d+)

# fires when the bot processes an incoming DM — source of correlation id
inbound_message: ^INFO gateway\.run: inbound message: platform=telegram user=(?P<user>\S+) chat=(?P<chat_id>\d+) msg='(?P<text>[^']*)'

# fires when the agent finishes LLM work before delivery (optional — useful for latency metrics)
response_ready: ^INFO gateway\.run: response ready: platform=telegram chat=(?P<chat_id>\d+) time=(?P<time_s>[\d.]+)s api_calls=(?P<api_calls>\d+) response=(?P<chars>\d+) chars
```

### Correlation id discovery

The `reply_sent` line itself has **no user-text content** — only byte count + chat_id. The preceding `inbound_message` line DOES contain full `msg='<user text>'`. The watcher keeps a "last-inbound-per-chat" buffer and attaches correlation_id to reply_sent events as they land. Schema stays 4-kind (correlation is watcher-internal).

### Batching surprise

Rapid pings from the same user get merged into a single batch:

```
INFO gateway.platforms.telegram: [Telegram] Flushing text batch agent:main:telegram:dm:152099202 (2 chars)
```

`(2 chars)` matched only `"oi"` — subsequent rapid pings were silently absorbed into the same batch's input. Harness must serialize (one ping, wait for reply, next ping).

### 🛑 Load-bearing finding — Bot API cannot inject user→bot messages

Telegram Bot API `sendMessage` sends AS the bot. There is NO "send as user" primitive. When I tried to automate the probe via `sendMessage`, the message appeared in the chat as a bot-originated message (left-side in Telegram UI, from @AgentPlayground_bot). The bot never "received" these as inbound input.

This means **SC-03 as defined ("user deploys → bot receives inbound DM → agent replies") cannot be automated through the Bot API at all.** Real user→bot automation requires **MTProto (Client API)** with a second Telegram user account (phone number + api_id/api_hash + session file).

### 🎯 Golden finding — every recipe has a direct programmatic surface

Not explicit in CONTEXT.md D-01..D-18, but surfaced by probing `hermes --help`:

- `hermes chat -q "<prompt>" -Q` → single non-interactive query, reply on stdout
- Confirmed working: `docker run --rm -e OPENROUTER_API_KEY=... ap-recipe-hermes chat -q "reply with just: ok-spk42" -Q -m "anthropic/claude-haiku-4.5" --provider openrouter` → stdout contained exactly `ok-spk42`.

**Cross-recipe check** (from `--help`):

- **picoclaw**: `picoclaw agent -m "<text>"`
- **nullclaw**: `nullclaw agent -m MESSAGE` AND `nullclaw gateway` (HTTP/WS)
- **nanobot**: `nanobot agent` (CLI) AND `nanobot serve` (OpenAI-compatible `/v1/chat/completions` — MSV's exact pattern)
- **openclaw**: port 18000+ `/v1/chat/completions` (documented via MSV's `messaging/activities/forward_to_agent.go`)

Universal pattern: **`<recipe> agent -m "<text>"`** (hermes uses `chat -q`). Subset also have HTTP surfaces when run with `serve`/`gateway`.

### MSV validates the pattern

`/Users/fcavalcanti/dev/meusecretariovirtual/messaging/activities/forward_to_agent.go`:

```go
agentURL := fmt.Sprintf("http://localhost:%d/v1/chat/completions", input.Port)
// ... OpenAI-compatible POST; pod returns reply as JSON choices[0].message.content
```

MSV never relies on Telegram round-trip for automated testing. Telegram input is routed through their external bot/router service, which then calls the pod's local HTTP endpoint. The pod's OpenAI-compatible API is the ground truth surface.

## Verdict: PASS_WITH_PIVOT

Both the spike's narrow question AND the broader architecture question got answered:

**Narrow (original) question:** regex for hermes reply_sent. ✅ Authored, capturable from docker logs stdout.

**Broader (surfaced) question:** Can SC-03 be automated? **Not via Bot API alone.** But yes via direct_interface — a new architectural primitive the CONTEXT.md didn't have. This pivot is the central recommendation.

## Evidence artifacts

- Hermes container boot log (stored inline above)
- User confirmed bot reply arrived in Telegram DM after `/sethome` setup
- `hermes chat -q "reply with just: ok-spk42" -Q` returned `ok-spk42` (stdout, proven outside any container orchestrator)
- All 4 other recipes' `--help` output confirmed a `agent -m` or `serve` surface

## Impact on 22b design

### Additive recipe field `direct_interface`

```yaml
# Option A: CLI via docker exec
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["<binary>", "agent", "-m", "{prompt}"]
    stdout_reply: true
    reply_extract_regex: "(?P<reply>.+)"

# Option B: HTTP (OpenAI-compatible)
direct_interface:
  kind: http_chat_completions
  spec:
    port: 8000
    path: /v1/chat/completions
    auth:
      header: Authorization
      value_template: "Bearer {api_key}"
    request_template:
      model: "<recipe>:main"
      messages:
        - {role: user, content: "{prompt}"}
    response_jsonpath: "$.choices[0].message.content"
```

Per-recipe mapping (proposed, pending spikes 01b-01e):

| Recipe | kind | argv / url |
|---|---|---|
| hermes | docker_exec_cli | `hermes chat -q "{prompt}" -Q -m "{model}" --provider openrouter` |
| picoclaw | docker_exec_cli | `picoclaw agent -m "{prompt}"` |
| nullclaw | docker_exec_cli OR http | `nullclaw agent -m "{prompt}"` / `nullclaw gateway` on port N |
| nanobot | http_chat_completions | `nanobot serve` on port N |
| openclaw | http_chat_completions | port 18000+, `/v1/chat/completions` |

### Harness path

1. Start container (Telegram creds optional for Gate B)
2. `docker exec <cid>` the direct_interface argv (or HTTP POST to mapped port)
3. Parse reply, assert contains correlation id or expected substring
4. Optionally: send a controlled Telegram DM via Bot API `sendMessage` (bot → self-chat, valid) and observe `Sending response` log line for Telegram delivery verification

### CONTEXT.md edits needed

- Add a new decisions section: **Direct interface** (D-19..D-22)
- Revise D-18 harness strategy to prefer direct_interface
- Revise spike gate — add spike 06 for direct_interface per recipe; keep spikes 01b-01e for Telegram delivery regex (still needed for the secondary observability branch)
- Document Bot API user-impersonation constraint as a permanent gotcha
- Add MSV's `forward_to_agent.go` to canonical_refs

## Related spikes

- 01b hermes-peer → picoclaw reply_sent regex (still needed)
- 06 direct_interface per recipe (NEW — must run before spike 01b..e and before planning)

## Next steps

Before continuing the spike chain: update CONTEXT.md with the direct_interface paradigm, then return to spike 01b (picoclaw). Without the CONTEXT.md update, planner may read the original D-18 harness strategy and build the wrong thing.
