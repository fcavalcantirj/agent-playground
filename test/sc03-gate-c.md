# SC-03 Gate C — Manual User-in-the-Loop Checklist

> Run this **once per release**, NOT per commit. Closes the part of SC-03
> that automation cannot reach: a real human pressing keys on a real
> Telegram client, sending a real DM to the deployed bot, and observing
> a real reply land in their own UI. Spike-01a (2026-04-18) proved the
> Bot API cannot impersonate a user; until MTProto user-impersonation
> ships (deferred), this round-trip remains a manual gate.
>
> Phase 22b decomposed SC-03 into three gates:
>
> | Gate | Surface | Automated by |
> |------|---------|--------------|
> | **A** (15/15) | `direct_interface` round-trip per recipe × 3 rounds | `test/e2e_channels_v0_2.sh` Step 4 → `agent_harness.py send-direct-and-read` |
> | **B** (5/5)   | `reply_sent` event captured for each recipe after a bot→self sendMessage probe | `test/e2e_channels_v0_2.sh` Step 5 → `agent_harness.py send-telegram-and-watch-events` |
> | **C** (5/5)   | Real human DM → bot reply visible in operator's Telegram client | **THIS DOCUMENT** |
>
> Gate A is the per-commit phase exit. Gate B is per-commit when creds
> are present. Gate C is per-release.

## Prerequisites

- Live API at `$API_BASE` (production or staging) with `/v1/healthz` returning `{ok:true}`
- 5 bots created via `@BotFather` and bound (one bot may serve all 5 recipes
  by stopping/starting between rounds; preferred: 5 distinct bots so the
  matrix can run in parallel)
- Operator has a personal Telegram account
- Operator knows each bot's `@handle` (e.g. `@AgentPlayground_bot`)
- API tokens / `AP_SYSADMIN_TOKEN` available to operator for `/v1/agents/...`
  start/stop calls

## Procedure (per recipe)

For each recipe below: deploy the agent, DM the bot with the canonical Gate C
ping, wait up to 30s for the bot's reply, then record observed values.

### hermes

- [ ] `POST /v1/agents/<hermes-agent-id>/start` returns `200 OK` with `container_status:"running"`
- [ ] Operator opens Telegram and DMs the bot's `@handle` with:
      `GATE_C_hermes_<YYYYMMDD-HHMM>_<operator-initials>`
      (example: `GATE_C_hermes_20260418-1530_FC`)
- [ ] Bot replies within 30s (any text reply counts; correlation id echo is bonus)
- [ ] Operator records:
  - sent_time (UTC, second precision): `____________________________________`
  - reply_time (UTC, second precision): `____________________________________`
  - reply_text first 30 chars: `____________________________________`
  - bot @handle observed: `____________________________________`
- [ ] `POST /v1/agents/<hermes-agent-id>/stop` returns `200 OK`

### picoclaw

- [ ] `POST /v1/agents/<picoclaw-agent-id>/start` returns `200 OK` with `container_status:"running"`
- [ ] Operator DMs the bot's `@handle` with:
      `GATE_C_picoclaw_<YYYYMMDD-HHMM>_<operator-initials>`
- [ ] Bot replies within 30s
- [ ] Operator records:
  - sent_time: `____________________________________`
  - reply_time: `____________________________________`
  - reply_text first 30 chars: `____________________________________`
  - bot @handle observed: `____________________________________`
- [ ] `POST /v1/agents/<picoclaw-agent-id>/stop` returns `200 OK`

### nullclaw

- [ ] `POST /v1/agents/<nullclaw-agent-id>/start` returns `200 OK` with `container_status:"running"`
- [ ] Operator DMs the bot's `@handle` with:
      `GATE_C_nullclaw_<YYYYMMDD-HHMM>_<operator-initials>`
- [ ] Bot replies within 30s
- [ ] Operator records:
  - sent_time: `____________________________________`
  - reply_time: `____________________________________`
  - reply_text first 30 chars: `____________________________________`
  - bot @handle observed: `____________________________________`
- [ ] `POST /v1/agents/<nullclaw-agent-id>/stop` returns `200 OK`

### nanobot

- [ ] `POST /v1/agents/<nanobot-agent-id>/start` returns `200 OK` with `container_status:"running"`
- [ ] Operator DMs the bot's `@handle` with:
      `GATE_C_nanobot_<YYYYMMDD-HHMM>_<operator-initials>`
- [ ] Bot replies within 30s (note: nanobot has the slowest cold boot, ~23s,
      so allow extra time after start)
- [ ] Operator records:
  - sent_time: `____________________________________`
  - reply_time: `____________________________________`
  - reply_text first 30 chars: `____________________________________`
  - bot @handle observed: `____________________________________`
- [ ] `POST /v1/agents/<nanobot-agent-id>/stop` returns `200 OK`

### openclaw

- [ ] `POST /v1/agents/<openclaw-agent-id>/start` returns `200 OK` with `container_status:"running"`
- [ ] If `dmPolicy:pairing` enforced (recipe default): operator DMs bot once
      to receive a 4-char pairing code, then `POST /v1/agents/<id>/channels/telegram/pair`
      with `{code:"<CODE>"}` to authorize.
- [ ] Operator DMs the bot's `@handle` with:
      `GATE_C_openclaw_<YYYYMMDD-HHMM>_<operator-initials>`
- [ ] Bot replies within 30s (note: openclaw boot is ~100s; allow time)
- [ ] Operator records:
  - sent_time: `____________________________________`
  - reply_time: `____________________________________`
  - reply_text first 30 chars: `____________________________________`
  - provider used: `____________________________________` (anthropic-direct; openrouter is BLOCKED upstream — see openclaw recipe known_quirks.openrouter_provider_plugin_silent_fail)
  - bot @handle observed: `____________________________________`
- [ ] `POST /v1/agents/<openclaw-agent-id>/stop` returns `200 OK`

## Sign-off

- [ ] All 5 recipes confirmed with a real Telegram round-trip.
- [ ] Operator: ____________________ (name)
- [ ] Date: ____________________ (UTC date of last recipe)
- [ ] Release tag: ____________________ (git tag this gate signs off on)
- [ ] Notes / anomalies (optional): _____________________________________

## When this gate is allowed to be DEFERRED

Gate C is **NOT** required to merge a per-commit change. It IS required
before a release tag is cut. If a release ships without a successful
Gate C run on every recipe in the matrix, the release notes MUST list
the recipes deferred and the gating reason (e.g. "openclaw deferred
pending upstream openrouter plugin fix; see recipe known_quirks").

## Future automation path (out of scope for 22b)

When MTProto user-impersonation lands (telethon/pyrogram with a
dedicated throwaway Telegram user account + api_id/api_hash + session
file), this checklist becomes a `mtproto-send-and-read` subcommand of
`agent_harness.py` and folds into the per-commit Gate A/B run. Until
then, this document is the system of record for SC-03's user-in-the-loop
guarantee.
