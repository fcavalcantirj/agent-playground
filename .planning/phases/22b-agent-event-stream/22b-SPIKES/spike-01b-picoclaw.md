---
spike: 01b
name: reply-sent-regex-picoclaw
validates: "Given a running picoclaw container with Telegram creds, when a real user DMs the bot and the bot replies, then docker logs contains machine-parsable lines identifying reply-sent, inbound-message, and bonus response-text events"
verdict: PASS
related: [spike-01a, spike-01c, spike-01d, spike-01e]
tags: [picoclaw, telegram, log-regex]
---

# Spike 01b — picoclaw reply_sent regex

## How I ran it

```bash
# /v1/runs smoke to create agent_instance → /v1/agents/:id/start with Telegram creds
# User typed in Telegram DM:
#   "spk01b please reply with only: ok-picoclaw-01"
# Waited 12s; dumped `docker logs <cid>`; grepped for reply/send/response/telegram patterns.
```

Container: `45b6e9bc48d020e28fc2ee81e7502a5621b90740502f0006ce89b950e8956fe6` (picoclaw).
Boot: 2.85s. Round-trip: ~3.2s (user send → bot sendMessage).

## Canonical log sequence captured

```
21:16:22  INF eventbus  loop.go:1049 > Agent event: llm_request agent_id=main event_kind=llm_request
                        inbound_channel=telegram inbound_chat_id=152099202 inbound_sender_id=152099202
                        iteration=1 max_tokens=32768 messages=2 model=claude-haiku-4.5
                        route_channel=telegram ...

21:16:25  INF eventbus  loop.go:1049 > Agent event: llm_response agent_id=main content_len=14
                        event_kind=llm_response inbound_channel=telegram inbound_chat_id=152099202 ...

21:16:25  INF agent     loop.go:2652 > LLM response without tool calls (direct answer) content_chars=14

21:16:25  INF eventbus  loop.go:1049 > Agent event: turn_end duration_ms=3198 final_len=14 ...

21:16:25  INF agent     loop.go:1885 > Response: ok-picoclaw-01 agent_id=main final_length=14 iterations=1

21:16:25  INF agent     loop.go:713  > Published outbound response channel=telegram chat_id=152099202 content_len=14

21:16:25  DBG telego    bot.go:247   > API call to: "https://api.telegram.org/bot<redacted>/sendMessage"

21:16:26  DBG telego    bot.go:173   > API response sendMessage: Ok: true, Err: [<nil>],
                        Result: {"message_id":61,...,"text":"ok-picoclaw-01"}
```

## Authored regexes (committed to recipes/picoclaw.yaml §channels.telegram.event_log_regex)

```yaml
event_log_regex:
  reply_sent: "INF agent [^\\s]*loop\\.go:\\d+ > Published outbound response channel=telegram chat_id=(?P<chat_id>\\d+) content_len=(?P<chars>\\d+)"
  response_text: "INF agent [^\\s]*loop\\.go:\\d+ > Response: (?P<reply_text>.+?) agent_id=\\S+ final_length=(?P<chars>\\d+)"
  inbound_message: "INF eventbus [^\\s]*loop\\.go:\\d+ > Agent event: llm_request .*inbound_channel=telegram inbound_chat_id=(?P<chat_id>\\d+) inbound_sender_id=(?P<user_id>\\d+)"
  agent_error: "(?:ERR|ERROR|FATAL) [^\\s]+ [^\\s]+:\\d+ > (?P<message>.+)"
```

## Bonus finding — picoclaw uniquely logs full reply text

The `Response: <text> agent_id=... final_length=N` line at `loop.go:1885` contains the **entire reply text** before the channel-send happens. Added as the `response_text` regex in the recipe — watcher can attach `correlation_id` directly by matching user-embedded UUIDs against `reply_text`.

**Design implication for D-07 (CONTEXT.md):** correlation-via-reply-text works reliably for picoclaw *without needing* the inbound_message buffer. Other recipes (hermes) need the buffer. The watcher should support both paths — use `response_text` capture when a recipe provides it, fall back to inbound-message buffering otherwise.

## Verdict: PASS

4 regexes authored; reply_sent + response_text + inbound_message all validated against a real round-trip; correlation id (`ok-picoclaw-01`) echoed through and captured in response_text. Recipe YAML updated with verified_cells entry dated 2026-04-18.

## Related

- spike-01a-hermes.md — different log shape, no reply-text-in-log, needs inbound-buffer correlation
- CONTEXT.md D-04, D-07, D-18 — architecture this supports
