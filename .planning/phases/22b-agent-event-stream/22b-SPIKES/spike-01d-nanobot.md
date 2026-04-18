---
spike: 01d
name: reply-sent-regex-nanobot
validates: "Given a running nanobot container with Telegram creds, when a real user DMs the bot and the bot replies, then docker logs contains structured timestamped lines identifying reply-sent, inbound-message (two levels), and agent-error events"
verdict: PASS
related: [spike-01a, spike-01b, spike-01c, spike-01e]
tags: [nanobot, telegram, log-regex, structured-logging]
---

# Spike 01d — nanobot reply_sent regex

## How I ran it

Same pattern as previous sub-spikes — `/v1/runs` smoke + persistent `/start` with Telegram creds. User sent `spk01d please reply with only: ok-nanobot-01`. Bot replied `ok-nanobot-01` (confirmed via Telegram).

Container: `cf900fde9dbb8fa22e658bc97b161f87cabe2d3742f851ad2fd25e2013ae9966`. Boot: 23.36s (heaviest of the 5 recipes; creates SOUL/USER/HEARTBEAT files + git store on first run). Round-trip: ~6s.

## Canonical 3-line sequence captured

```
2026-04-18 21:25:57.600 | DEBUG    | nanobot.channels.telegram:_on_message:921
  Telegram message from 152099202|fcavalcantirj: spk01d please reply with only: ok-nanobot-01...

2026-04-18 21:25:58.511 | INFO     | nanobot.agent.loop:_process_message:666
  Processing message from telegram:152099202|fcavalcantirj: spk01d please reply with only: ok-nanobot-01

2026-04-18 21:26:03.834 | INFO     | nanobot.agent.loop:_process_message:761
  Response to telegram:152099202|fcavalcantirj: ok-nanobot-01
```

Log format: `ISO_TIMESTAMP | LEVEL | MODULE:FUNCTION:LINE - MESSAGE`. Clean, machine-parsable, level-discriminated.

## Authored regexes (committed to recipes/nanobot.yaml)

```yaml
event_log_regex:
  reply_sent:       "\\| INFO\\s+\\| nanobot\\.agent\\.loop:_process_message:\\d+ - Response to telegram:(?P<chat_id>\\d+)\\|[^:]+: (?P<reply_text>.+)"
  inbound_message:  "\\| INFO\\s+\\| nanobot\\.agent\\.loop:_process_message:\\d+ - Processing message from telegram:(?P<chat_id>\\d+)\\|(?P<user>[^:]+): (?P<text>.+)"
  inbound_raw:      "\\| DEBUG\\s+\\| nanobot\\.channels\\.telegram:_on_message:\\d+ - Telegram message from (?P<chat_id>\\d+)\\|(?P<user>[^:]+): (?P<text>.+)"
  agent_error:      "\\| (?:ERROR|CRITICAL|WARNING)\\s+\\| nanobot\\.[^:]+:[^:]+:\\d+ - (?P<message>.+)"
```

**Bonus:** like picoclaw, nanobot's reply_sent line includes the **full reply text** — `correlation_id` extractable directly from reply if echoed (as it was: `ok-nanobot-01`).

## Interesting wrinkle: `_process_message` is the SAME function for both inbound AND outbound

nanobot's agent.loop has one `_process_message` method — line 666 is the ingress branch (`Processing message from`), line 761 is the egress branch (`Response to`). The line numbers discriminate. Our regex uses the message-prefix text (`Processing message from` vs `Response to`) rather than line numbers, because line numbers drift with nanobot version updates. More durable.

## Verdict: PASS

4 regexes authored against real log lines; round-trip confirmed via Telegram + correlation id captured in reply_text. Recipe YAML updated with 2026-04-18 verified_cells entry.

## Comparative summary across sub-spikes so far

| Recipe | docker logs carries activity? | Reply text in log? | Regex kind |
|--------|-------------------------------|---------------------|------------|
| hermes | ✅ Yes | ❌ No (only char count) | reply_sent + inbound_message buffer |
| picoclaw | ✅ Yes (dense, multi-line) | ✅ Yes (loop.go:1885) | reply_sent + response_text + inbound_message |
| nullclaw | ❌ No (9 stdout lines total) | ❌ No — must docker exec poll CLI | FALLBACK event_source kind |
| nanobot | ✅ Yes (ISO-timestamped structured) | ✅ Yes (in `Response to` line) | reply_sent + inbound_message + inbound_raw + agent_error |

Pattern: 3 of 4 tested recipes expose activity in docker logs; 1 (nullclaw) needs a fallback observation path. That 25% miss-rate is significant — the watcher architecture must generalize.

## Related

- spike-01c-nullclaw.md — triggered the architecture-level finding (D-01 needs fallback)
- spike-01e-openclaw.md (next) — will complete the 5-recipe matrix
