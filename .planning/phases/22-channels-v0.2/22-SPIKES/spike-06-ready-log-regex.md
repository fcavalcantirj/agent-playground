# Spike 06 — ready_log_regex match per recipe

**Date:** 2026-04-18
**Plan affected:** 22-03 (run_cell_persistent ready_log polling)
**Verdict:** PASS — 5/5 regex match real boot output

## Probes

Each regex from the recipe's `persistent.spec.ready_log_regex` grep'd against actual `docker logs`.

| Recipe   | Regex | Hits | Sample match |
|----------|-------|------|--------------|
| hermes   | `gateway\.run: ✓ (\w+) connected` | 1 | `INFO gateway.run: ✓ telegram connected` |
| nanobot  | `Telegram bot @\w+ connected` | 1 | `nanobot.channels.telegram:start:338 - Telegram bot @AgentPlayground_bot connected` |
| picoclaw | `Telegram bot connected username=` | 1 | `channels/telegram/telegram.go:141 > Telegram bot connected username=AgentPlayground_bot` |
| nullclaw | `channel_manager.*telegram polling thread started` | 1 | `info(channel_manager): telegram polling thread started` |
| openclaw | `\[telegram\] \[default\] starting provider` | 1 | `[telegram] [default] starting provider (@AgentPlayground_bot)` |

## Verdict: PASS

All 5 regex patterns from the committed recipes match the actual boot log exactly once, in the expected line format. The `run_cell_persistent` poller can grep `docker logs --follow` for the regex and return `ready_at` when the first match appears.

## Plan citation

Plan 22-03 Task 1's `ready_log_regex` poll loop is validated. No plan delta.
