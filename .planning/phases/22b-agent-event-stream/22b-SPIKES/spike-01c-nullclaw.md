---
spike: 01c
name: reply-sent-regex-nullclaw
validates: "Given a running nullclaw container with Telegram creds, when a real user DMs the bot and the bot replies, observe where the reply-sent event surfaces and author a machine-parsable signal"
verdict: PASS_WITH_FLAG
related: [spike-01a, spike-01b, spike-01d, spike-01e]
tags: [nullclaw, telegram, log-regex, architecture-impact, second-order-finding]
---

# Spike 01c — nullclaw reply_sent regex (FLAGGED)

## How I ran it

Same pattern as 01a/01b — `/v1/runs` smoke + persistent `/start` with Telegram creds. User sent `spk01c please reply with only: ok-nullclaw-01`. Bot replied `ok-nullclaw-01` (confirmed via Telegram UI). Dumped docker logs + probed gateway HTTP + inspected container filesystem.

Container: `b6ec0e8cb577a8a20eb8f83c7adee80a801aff6c1f52c0baa21fde529c3c9f5f`. Boot: 2.46s. Round-trip: ~3s.

## What I found — and didn't find

### Docker logs stdout/stderr — BARREN

```
stdout lines:  9
stderr lines:  4
```

That's TOTAL, across the entire session including the reply round-trip. Nothing about inbound messages, outbound sends, LLM calls, or Telegram API hits. Just boot banner + "telegram polling thread started" + the memory plan.

```
nullclaw gateway runtime started
  Gateway:  http://127.0.0.1:3000
  Components: 3 active
  Model:    openrouter/anthropic/claude-haiku-4.5
  Provider: openrouter
Gateway listening on 127.0.0.1:3000
Gateway pairing code generated (hidden for security). Use the /pair flow to complete pairing.
info(memory): memory plan resolved: backend=hybrid ...
info(channel_manager): telegram polling thread started
```

### Gateway HTTP surface at 127.0.0.1:3000 — only /health

Probed: `/`, `/api/v1/`, `/v1/`, `/api/`, `/messages`, `/stats`, `/logs`, `/status`, `/sessions`, `/events`, `/history`, `/agents` → all 404.

`/health` → `{"status":"ok"}`.

No message/event/activity endpoint exists.

### Where the activity DOES live

1. **`nullclaw history show <session_id> --json`** returns structured conversation:
   ```json
   {"session_id":"agent:main:telegram:direct:152099202","total":2,"limit":100,"offset":0,
    "messages":[
      {"role":"user","content":"spk01c please reply with only: ok-nullclaw-01","created_at":"2026-04-18 21:19:56"},
      {"role":"assistant","content":"ok-nullclaw-01","created_at":"2026-04-18 21:19:56"}
    ]}
   ```
2. **`/nullclaw-data/llm_token_usage.jsonl`** — one line per LLM call:
   ```json
   {"ts":1776547196,"provider":"OpenRouter","model":"openrouter/anthropic/claude-haiku-4.5","prompt_tokens":0,"completion_tokens":4,"total_tokens":4,"success":true}
   ```
3. **`/nullclaw-data/state/telegram/update-offset-main.json`** — last processed Telegram update_id.

## 🛑 Second-order architecture finding

**CONTEXT.md D-01 (docker logs scrape) does not universally work.** Nullclaw requires a different observation path. The watcher architecture needs per-recipe source configuration, not a single "always docker logs" assumption.

### Proposed fix (already landed in recipes/nullclaw.yaml)

Add a fallback `event_source_fallback` block to the recipe schema:

```yaml
event_log_regex:
  reply_sent: null      # not observable via docker logs
  inbound_message: null # not observable via docker logs

event_source_fallback:
  kind: docker_exec_poll
  spec:
    argv_template: ["nullclaw", "history", "show", "{session_id}", "--json"]
    session_id_template: "agent:main:telegram:direct:{chat_id}"
    tail_file: "/nullclaw-data/llm_token_usage.jsonl"
```

### Planner implications for 22b

1. **D-01 must be revised** — "primary source is docker logs; recipes may declare `event_source_fallback` for alternative paths."
2. **Log-watcher service must support multiple source kinds:**
   - `docker_logs_stream` (default — hermes, picoclaw)
   - `docker_exec_poll` (nullclaw — poll CLI periodically, diff session)
   - `file_tail_in_container` (future — tail a file inside the container via `docker exec tail -f`)
3. **For SC-03 automation, Gate A (direct_interface) covers nullclaw cleanly.** `docker exec <cid> nullclaw agent -m "{prompt}"` works as documented in spike 06. Gate B (reply_sent event) for nullclaw would use the docker_exec_poll fallback — slower and less elegant, but functional.
4. **Watcher polling interval for fallback** — 500ms is a reasonable default; frontend UI might want faster; planner decides.

## Verdict: PASS_WITH_FLAG

- Round-trip **confirmed** via Telegram UI + `nullclaw history show`.
- Reply-sent event via docker logs: **NOT AVAILABLE** — flagged.
- Alternative observation path: **documented + wired into recipe YAML**.
- **Architecture-impact:** CONTEXT.md D-01 needs revision to accept per-recipe fallback sources.

## Impact on CONTEXT.md (post-spike edits needed)

1. Revise D-01 to "primary=docker logs; recipes MAY declare event_source_fallback".
2. Add a new decision D-23 — `event_source_fallback` field, enumerate supported `kind`s, declare that the watcher supports all kinds the catalog uses.
3. Add a spike-derived caveat to the spike gate: post-01c finding means the watcher's interface must abstract over source kinds, not hard-code `docker logs -f`.

**Not editing CONTEXT.md this iteration** — user is running sequential sub-spikes; will batch all 01b-01e impacts into one CONTEXT.md update at the end.

## Related

- spike-01a-hermes.md — different log shape, full activity IS in docker logs
- spike-01b-picoclaw.md — very rich docker logs with structured eventbus + reply text
- spike-01d-nanobot.md (pending) — will find out which bucket nanobot falls into
- spike-01e-openclaw.md (pending) — same
