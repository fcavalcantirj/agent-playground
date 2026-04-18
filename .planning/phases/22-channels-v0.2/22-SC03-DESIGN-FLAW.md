---
title: SC-03 Design Flaw — getUpdates single-consumer conflict
phase: 22-channels-v0.2
plan: 22-07 (blocks Task 3 human-verify gate)
discovered: 2026-04-18
severity: blocking (for Phase 22 exit gate only; Phases 22-01..22-06 unaffected)
---

# Finding

Phase 22-07's e2e test design (bash driver + Python Telegram harness) is
architecturally incompatible with the persistent-mode bots it's meant to
validate. Found empirically during the first supervised run.

## Observed symptoms

1. `bash test/e2e_channels_v0_2.sh --recipe hermes --rounds 1` — container
   boots cleanly (~11s), user's Telegram chat shows the outbound ping
   `"ping hermes r1 HHMMSS"`, but no bot reply ever arrives.
2. Script aborts mid-round because `python3 telegram_harness.py send-and-wait`
   exits non-zero on timeout and `set -e` kills the shell before the
   `_fail`/JSON-report block runs.
3. Hermes container log records:

   ```
   WARNING [Telegram] Telegram polling conflict (1/3), will retry in 10s.
     Error: Conflict: terminated by other getUpdates request;
     make sure that only one bot instance is running
   ```

## Root cause

Telegram's Bot API `getUpdates` endpoint is **single-consumer by design**.
The moment a second caller opens a `getUpdates` connection, the first is
invalidated (HTTP 409 Conflict on the first's next poll).

Phase 22-07 Task 1 built the harness to *also* call `getUpdates` to catch
the bot's reply. Every 5-second harness poll knocks hermes off its own
polling loop, so hermes never sees our ping, so it never replies, so the
harness times out. The hermes container log above is the smoking gun.

This is **not** a bug in Plans 22-01..22-06, the runner persistence
primitives, the API endpoints, or the frontend. All of those work. The
flaw is specifically in the test's reply-detection strategy.

## Why it wasn't caught in spike/planning

The G1..G5 spikes probed `sendMessage`, `/webhook-off`, recipe-specific
pair flow, and boot-readiness — none of them ran *two* simultaneous
`getUpdates` consumers against the same bot token. The interaction only
manifests when a live bot is polling AND the test harness polls.

## Secondary bug found in same run

The e2e MATRIX hardcoded the LLM model as `openrouter/anthropic/claude-haiku-4.5`.
OpenRouter rejects the `openrouter/` prefix: `"not a valid model ID"`.
Correct form is `anthropic/claude-haiku-4.5` (verified via direct `/v1/runs`
probe — PASS in 20s). Fix committed — the `openrouter/` prefix was dropped
from the four OpenRouter rows in the MATRIX on 2026-04-18 *before* the
getUpdates conflict surfaced. Recording here so the fix doesn't get
double-applied.

## What works (Phase 22a salvage)

Verified live against the local deploy-api_server container running the
Phase 22 image:

- `POST /v1/runs` with `recipe_name=hermes, model=anthropic/claude-haiku-4.5` → **PASS** (20.51s wall)
- `POST /v1/agents/:id/start` with Telegram channel_inputs → **container_status=running, boot_wall_s=~11s**
- `POST /v1/agents/:id/stop` → container reaped cleanly, no `ap-agent-*` leftovers
- `alembic_version = 003_agent_containers` (migration applied)
- Age-KEK crypto round-trips through the start endpoint (after setting `AP_CHANNEL_MASTER_KEY` via shell env — see below)
- OpenAPI exposes all 4 new endpoints: `/v1/agents/:id/{start,stop,status,channels/:cid/pair}`

The backend, migration, runner, bridges, and frontend are real, wired,
and responding. The gate that hasn't passed is the live Telegram
round-trip, and the reason is the test design above.

## Options to fix (sized)

1. **Docker-log scrape inside the harness** — parse each recipe's
   "reply sent" log line; per-recipe regex. Simpler but brittle (regex
   per recipe; log format drift = silent test pass).
2. **Agent event stream via API + Postgres** (recommended) — new
   Phase 22b. api_server watches `docker logs -f` for each running
   agent, parses events, writes to a new `agent_events` table; harness
   polls `GET /v1/agents/:id/events` instead of Telegram. Robust, works
   for all recipes, reuses Phase 22's Postgres + runner_bridge muscle,
   matches CLAUDE.md Rule 2 ("intelligence in the API").
3. **Manual-only SC-03** — declare 15/15 round-trips a human-run gate
   forever. Loses automation but unblocks shipping.

User chose option 2 (2026-04-18). Phase 22b queued — see
`.planning/STATE.md` Resume Anchor.

## Runtime state captured (for local repro)

- API server: `deploy-api_server-1` container, image rebuilt from
  `HEAD~1` on 2026-04-18 (Phase 22 code baked in).
- `AP_CHANNEL_MASTER_KEY` — dev key generated at test time (32 zero
  bytes is the *dev fallback*, but compose sets `AP_ENV=prod` so the
  crypto fails loud without a key). For local dev, set in your shell
  before `docker compose up api_server`:

  ```bash
  export AP_CHANNEL_MASTER_KEY="2JAvJ9FwihbRyukvXDBnqVEK2Umf5ibHEy7KsFq5gTU="
  # OR generate a fresh one:
  export AP_CHANNEL_MASTER_KEY=$(python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())")
  ```

  Deliberately NOT written to `deploy/.env.prod` per CLAUDE.md rule
  "NEVER MODIFY .env files without explicit user permission". Treat
  as per-laptop dev state.

- Telegram creds live in `.env.local` (gitignored):
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_CHAT_ID`. Script expects
  `TELEGRAM_CHAT_ID` — shell-alias before running:
  `export TELEGRAM_CHAT_ID="$TELEGRAM_USER_CHAT_ID"`.

## Cleanup done

- All test containers (`ap-agent-*`) reaped
- No dangling worktrees
- Main branch clean
