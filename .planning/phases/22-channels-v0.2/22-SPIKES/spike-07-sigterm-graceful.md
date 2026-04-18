# Spike 07 — SIGTERM + graceful_shutdown_s per recipe

**Date:** 2026-04-18
**Plan affected:** 22-03 (runner stop_persistent), 22-05 (POST /stop endpoint)
**Verdict:** GOTCHA CAUGHT — plan revision required

## Probe

`docker stop -t N <container>` on each recipe container. Measure wall time + exit code.

Exit 0/1 = graceful SIGTERM handled before timeout.
Exit 137 = SIGKILL forced after timeout (container ignored SIGTERM).

## Round 1 — default `-t 5`

| Recipe   | Wall    | Exit | Verdict |
|----------|---------|------|---------|
| hermes   | 6.3 s   | 137  | FORCED  |
| nanobot  | 6.7 s   | 137  | FORCED  |
| picoclaw | 0.4 s   | 0    | CLEAN — fastest |
| nullclaw | 5.3 s   | 137  | FORCED  |

## Round 2 — extended `-t 20`

| Recipe   | Wall    | Exit | Verdict |
|----------|---------|------|---------|
| hermes   | 9.2 s   | 1    | CLEAN after ~9s |
| nanobot  | 21.1 s  | 137  | **STILL FORCED — ignores SIGTERM entirely** |

## Verdict: PASS with plan revision

Two gotchas:

### Gotcha A — 5s is too short for hermes/nullclaw

Plan 22-03 default `graceful_shutdown_s: 5` kills hermes/nullclaw before they drain. Rollout:

| Recipe   | Recommended `graceful_shutdown_s` |
|----------|-----|
| hermes   | 15 |
| picoclaw | 2  |
| nullclaw | 10 |
| nanobot  | **(ignored — always force-rm; see Gotcha B)** |
| openclaw | **TBD — spike cycle 2** |

### Gotcha B — nanobot ignores SIGTERM entirely

Nanobot's gateway doesn't handle SIGTERM. Even `-t 20` results in SIGKILL (exit 137). Implication:

- `stop_persistent` must accept SIGKILL as the normal path for nanobot
- Log warning `"graceful shutdown timed out for recipe=nanobot; force-killed"` — not an error
- The `container_status='stopped'` DB row should still write even after force-kill
- Consider filing upstream issue against HKUDS/nanobot for SIGTERM handler missing

## Plan delta required

Plan 22-03 Task 2 (`stop_persistent`):
1. Read `graceful_shutdown_s` from recipe `persistent.spec.graceful_shutdown_s` (per-recipe, no uniform default).
2. On timeout + SIGKILL, log warning but write status='stopped' normally — not an error.
3. Add `force_killed: bool` field to the return value so `POST /stop` endpoint response can surface it.

Recipe YAMLs (already have `graceful_shutdown_s` field in draft blocks) need per-recipe values applied:
- `recipes/hermes.yaml` persistent.spec.graceful_shutdown_s: 15
- `recipes/picoclaw.yaml` persistent.spec.graceful_shutdown_s: 2
- `recipes/nullclaw.yaml` persistent.spec.graceful_shutdown_s: 10
- `recipes/nanobot.yaml` persistent.spec.graceful_shutdown_s: 0 (skip graceful, go straight to force-rm) + new field `sigterm_handled: false`
- `recipes/openclaw.yaml` — TBD after probe 07 cycle 2 against openclaw

## Spike value

Without this probe, Phase 22a would have shipped a 5s default that SIGKILLs 4 of 5 recipes and nobody notices until the E2E test (wave 5). That's exactly the scenario Rule #5 prevents.
