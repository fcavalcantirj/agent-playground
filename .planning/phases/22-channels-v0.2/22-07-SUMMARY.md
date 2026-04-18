---
phase: 22-channels-v0.2
plan: 07
subsystem: testing
tags: [telegram, e2e, bash, python, getUpdates, sc-03, round-trip]

# Dependency graph
requires:
  - phase: 22-channels-v0.2
    provides: "POST /v1/runs smoke + /v1/agents/:id/start|stop|channels/telegram/pair endpoints (Plans 22-01..22-06)"
provides:
  - "test/lib/telegram_harness.py — stdlib-only Python helper for Telegram DM send + getUpdates reply polling"
  - "test/e2e_channels_v0_2.sh — bash driver exercising 5 recipes x 3 rounds = 15 live Telegram round-trips"
  - "JSON report schema at .planning/phases/22-channels-v0.2/22-e2e-report.json (written by the bash driver)"
affects: [phase-23, phase-24, ops/runbooks, SC-03-retros]

# Tech tracking
tech-stack:
  added:
    - "urllib-based Telegram Bot API client (Python stdlib, no requests dep)"
    - "getUpdates offset-baseline pattern (offset=-1 snapshot for race-free reply window)"
  patterns:
    - "bash driver + Python subcommand helper via shell-out (JSON on stdout, exit-code contract)"
    - "trap-based container teardown on EXIT/INT/TERM (no orphan ap-agent-* containers)"
    - "matrix-driven multi-recipe e2e (pipe-delimited tuple rows parsed by IFS)"

key-files:
  created:
    - "test/lib/telegram_harness.py"
    - "test/e2e_channels_v0_2.sh"
  modified: []

key-decisions:
  - "urllib over requests — keep harness dependency-free for CI and bare containers"
  - "offset=-1 baseline after send — sidesteps the send-vs-poll race without strict content correlation (agents rewrite replies)"
  - "First bot message in chat post-baseline counts as reply — status/thinking messages are acceptable SC-03 evidence (round-trip exists)"
  - "Populate BOTH TELEGRAM_ALLOWED_USERS (hermes plural) AND TELEGRAM_ALLOWED_USER (openclaw singular) in channel_inputs — recipes ignore the variant they don't use"
  - "openclaw pair flow handled in-driver: first 'hi' DM extracts pair code via regex, POST /channels/telegram/pair, then real test message"
  - "sleep 2 between rounds — lets docker daemon reap prior container before next start"

patterns-established:
  - "Pattern: python3 <harness> <subcmd> --token ... --chat-id ... --text ... --timeout-s 30 for any future channel e2e (SMS/Slack/Discord would swap the base URL + polling semantics but keep the same exit-code contract)"
  - "Pattern: bash e2e driver with MATRIX array + trap cleanup + JSON report → reusable shape for future per-recipe gates"

requirements-completed: []  # SC-03 will be marked complete AFTER Task 3 (human-verify) passes
# SC-03 is provisioned by this plan but NOT YET signed off — the live round-trip gate is Task 3.

# Metrics
duration: 22min  # Tasks 1+2 authoring + verification; Task 3 pending user-supervised run
completed: 2026-04-18  # (Tasks 1+2 only)
---

# Phase 22 Plan 07: SC-03 e2e Channel Gate Summary

**Automated end-to-end Telegram round-trip driver + Python Bot API harness — 5 recipes x 3 rounds ready to fire; live-run gate (Task 3) pending human supervision.**

## Status

- **Tasks 1 + 2:** COMPLETE, committed atomically.
- **Task 3 (SC-03 live-infra gate):** `CHECKPOINT_PENDING` — requires user to supervise a live Telegram round-trip with real bot credentials. This is the checkpoint the orchestrator owns; the executor explicitly stops here.

## Performance

- **Duration:** ~22 min (Tasks 1+2 only; Task 3 wall time will add ~15-20 min of live-run execution plus supervision)
- **Started:** 2026-04-18T18:39:10Z (approx)
- **Completed (Tasks 1+2):** 2026-04-18T19:01:10Z
- **Tasks:** 2 of 3 complete
- **Files created:** 2

## Accomplishments

- **Python harness (`test/lib/telegram_harness.py`)** — 314 LOC, stdlib-only (urllib + argparse + uuid). Two subcommands: `drain` (ACK backlog so subsequent polls see a clean window) and `send-and-wait` (send DM, baseline `offset=-1`, poll `getUpdates` until bot reply or timeout). JSON output on stdout; exit codes 0/1/2 for pass/timeout/send-fail. HTTPError bodies are surfaced in `description` so upstream Telegram errors (bad token, webhook mode on, etc.) become readable diagnostics rather than silent hangs.
- **Bash driver (`test/e2e_channels_v0_2.sh`)** — 232 LOC, conforms to `smoke-api.sh` conventions (`set -euo pipefail`, `_pass/_fail/_info` helpers, `API_BASE` override). Matrix covers all 4 OpenRouter recipes (hermes/picoclaw/nullclaw/nanobot) + openclaw-via-Anthropic. Trap cleanup on EXIT/INT/TERM guarantees no orphan `ap-agent-*` containers even on Ctrl-C or mid-assertion failure. Writes a structured JSON report to `.planning/phases/22-channels-v0.2/22-e2e-report.json` for retro review.
- **openclaw pair loop in-line** — driver handles the pair-code extraction + POST `/v1/agents/:id/channels/telegram/pair` before the real test message, so the 5-recipe matrix runs uniformly end-to-end.

## Task Commits

1. **Task 1: Python Telegram harness — send + poll getUpdates with reply correlation** — `e505dc9` (feat)
2. **Task 2: bash driver test/e2e_channels_v0_2.sh — 5 recipes x 3 rounds** — `5802166` (feat)
3. **Task 3: SC-03 gate — manual supervised first-run + stability run** — `CHECKPOINT_PENDING`

**Plan metadata commit:** pending (this SUMMARY.md commit)

## Files Created

- `test/lib/telegram_harness.py` — 314 LOC. urllib-based Telegram Bot API client with `drain` + `send-and-wait` subcommands. Exit-code contract: 0 pass, 1 timeout, 2 send-fail, 3 usage.
- `test/e2e_channels_v0_2.sh` — 232 LOC. End-to-end bash driver. Flow per round: smoke (`POST /v1/runs`) → `POST /v1/agents/:id/start` → (openclaw only: send pair DM, extract code, `POST …/channels/telegram/pair`) → send test DM → poll reply via harness → `POST /v1/agents/:id/stop`. Repeat ROUNDS times (default 3) per recipe. JSON report on exit.

## Verification (Automated Gates)

Both gates from `<verification>` PASSED:

1. `bash -n test/e2e_channels_v0_2.sh` — PASS (no syntax errors)
2. `test/e2e_channels_v0_2.sh --help` — PASS (prints usage + design notes, sed range extracts lines 2-32)
3. `python3 test/lib/telegram_harness.py --help` + subcommand helps — PASS (argparse emits usage, both `drain` and `send-and-wait` subcommands reachable)
4. AST parse + import of harness module — PASS (`cmd_send_and_wait` function present)
5. Executable bit set on bash driver — PASS

## Verification (Human Gate — Task 3)

**NOT YET EXECUTED.** Task 3 is a `checkpoint:human-verify` that requires the user to:

1. Ensure local API server is running (`make dev` or equivalent) and Postgres + docker daemon are healthy.
2. Confirm `@AgentPlayground_bot` is NOT on webhook mode (`curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo` should return an empty `url`). If webhook is set, call `deleteWebhook` first (the harness uses `getUpdates`, which is mutually exclusive with webhooks).
3. Run `bash test/e2e_channels_v0_2.sh --recipe hermes --rounds 1` and visually confirm: outgoing "ping hermes r1 HHMMSS" DM appears in Telegram, bot replies within 10s, `PASS hermes r1 round-trip (X.Xs)` prints, final `1 / 1 round-trips passed`, `docker ps -a | grep ap-agent-` is empty.
4. Run the full `bash test/e2e_channels_v0_2.sh` and confirm `15 / 15 round-trips passed` with JSON report written.
5. Respond `approved` if 15/15; otherwise paste console output + `22-e2e-report.json` for triage.

Resume signal for the orchestrator is `approved` (PASS) or `partial: <recipe> failed because <reason>` (triage).

## Decisions Made

- **urllib over `requests`** — keeps the harness dependency-free. `requests` is ubiquitous but adds install overhead inside bare containers or CI runners that don't yet have it. `urllib` is guaranteed by Python stdlib.
- **Baseline via `offset=-1` after send** — rather than correlating by message content (agents rewrite/paraphrase), we snapshot the most recent `update_id` AFTER a successful `sendMessage` and accept the next bot message in the target chat as the reply. Simpler and robust to agent phrasing variance.
- **Accept first bot message as the reply, including "thinking…" status messages** — SC-03 is "round-trip exists within 10s", not "content matches a regex". A follow-up phase (tentative 23-observability) can add reply-content assertions if we later need them.
- **Populate BOTH `TELEGRAM_ALLOWED_USERS` (CSV, hermes shape) AND `TELEGRAM_ALLOWED_USER` (singular, openclaw shape) in `channel_inputs`** — the runner's env-file drops unused keys; this keeps the driver recipe-agnostic.
- **openclaw pair code regex `[A-Za-z0-9]{4,8}`** — matches any alphanumeric token 4-8 chars. If openclaw's reply format changes (longer codes, hyphens), this regex is the single-point tuning knob (Task 3 may surface this).
- **`sleep 2` inter-round** — empirically sufficient for docker reap between stop and next start based on Plan 22-05 boot timing; can be shortened once Plan 22-03's container-lifecycle observability proves reap happens sub-second.

## Deviations from Plan

None — plan executed exactly as written for Tasks 1 and 2. The `<action>` blocks were implemented verbatim with the following minor robustness enhancements that the plan's `<action>` code already indicated or implied:

1. **HTTP error handling in harness** — `_post`/`_get` now catch `urllib.error.HTTPError` and surface the server-side `description` (Telegram error payload) rather than raising a traceback. This makes bot-token-bad / chat-unreachable failures report cleanly in the JSON output's `error` field. Plan's exit-code contract (`2 send failed`) remains unchanged; this is a pure UX improvement on the same contract.
2. **`TELEGRAM_ALLOWED_USER` fallback to `TELEGRAM_CHAT_ID`** — if the env defines only `TELEGRAM_CHAT_ID` (user DM), the driver reuses that as the allowed user id. The plan's `channel_inputs` builder already populates both `TELEGRAM_ALLOWED_USERS` (plural) and `TELEGRAM_ALLOWED_USER` (singular) from the same var, so this fallback just removes a var-name footgun without changing semantics.
3. **`jq -r '.boot_wall_s // 0'`** in report line (plan had `jq -r '.boot_wall_s'` which would print `null` for an empty response). Keeps the JSON report parseable even if the API response elides the field in some error path.

All three are Rule 2 (missing critical resilience) per CLAUDE.md — keeping the e2e gate readable when the infra misbehaves is part of its job.

**Total deviations:** 3 auto-fixes (all Rule 2 — resilience/UX on the same contract).
**Impact on plan:** Zero scope change; the verify gates and `done` criteria still hold.

## Issues Encountered

None during Tasks 1 and 2. Task 3 may surface:
- openclaw cold-boot timeout (plan 22-05 exposes `boot_timeout_s`; if >180s boots happen, the first round can pass `"boot_timeout_s": 240` in the START body).
- Webhook conflict (if `@AgentPlayground_bot` has a webhook set from prior debugging; `deleteWebhook` resolves).
- Pair code regex mismatch (if openclaw's pair reply format differs from `[A-Za-z0-9]{4,8}`).

These are explicitly called out in the plan's `<how-to-verify>` and will be triaged when Task 3 runs.

## User Setup Required

**External service actions required for Task 3:**
- `.env.local` or `deploy/.env.local` must contain `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALLOWED_USER` (defaults to CHAT_ID), `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`.
- `@AgentPlayground_bot` must NOT be on webhook mode — verified via `curl https://api.telegram.org/bot$TOK/getWebhookInfo`.
- Local API server + Postgres + docker daemon must be up before running the driver.

## Known Stubs

None — harness and driver are fully implemented, no placeholder logic, no mock HTTP client. The harness talks to live Telegram; the driver talks to the live API.

## Next Phase Readiness

- **For Task 3 (this plan):** Driver + harness are ready for supervised execution. Orchestrator can spawn a continuation agent (or pass control to the user) to run the live gate.
- **For phase 22 exit gate:** Plans 22-01..22-06 are shipped; 22-07's live-run gate is the final SC-03 signoff. Once Task 3 returns `approved`, REQUIREMENTS SC-03 gets checked and the phase is mergeable.
- **No blockers** on downstream phases (23-api-observability, 24-billing) introduced by this plan.

## Self-Check: PASSED

Verified files exist and commits are present:

- `test/lib/telegram_harness.py` — FOUND
- `test/e2e_channels_v0_2.sh` — FOUND (executable)
- Commit `e505dc9` (Task 1) — FOUND in git log
- Commit `5802166` (Task 2) — FOUND in git log
- `.planning/phases/22-channels-v0.2/22-07-SUMMARY.md` — written

---
*Phase: 22-channels-v0.2*
*Completed (Tasks 1+2): 2026-04-18*
*Task 3 status: CHECKPOINT_PENDING — awaiting user-supervised live-infra run (SC-03 gate)*
