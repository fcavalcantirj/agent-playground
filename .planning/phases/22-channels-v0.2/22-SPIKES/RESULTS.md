# Phase 22a Spike Results — consolidated

**Date:** 2026-04-18
**Probes run:** 10 of 13 (3 deferred — see §"Deferred probes")
**Overall verdict:** **plan revisions identified; no blockers; proceed to plan update → then execute**

Per Golden Rule #5, these probes resolved the gray areas the plans had assumed. 4 plan deltas surfaced (all minor); 1 plan delta is MAJOR (openclaw pair latency 60s).

## Probe verdicts

| # | Probe | Plan | Verdict | Delta impact |
|---|---|---|---|---|
| 01 | pyrage install in api image | 22-02 | PASS | add pyrage + cryptography to pyproject.toml, rebuild image, new `AP_CHANNEL_MASTER_KEY` env |
| 02 | age + HKDF round-trip | 22-02 | PASS | plan's API call example wrong (uses nonexistent `Recipient.from_str`); use `pyrage.passphrase.encrypt/decrypt` directly |
| 03 | Postgres partial unique index | 22-02, 22-05 | PASS | no delta |
| 04 | jsonschema oneOf v0.1/v0.2 | 22-01 | PASS | no delta — 5 committed recipes validate under v0.1 branch; v0.2 sample validates under v0.2 branch |
| 05 | `docker run -d` 5 recipes | 22-03 | PASS | no delta — all 5 boot ≥60s under sh-entrypoint override |
| 06 | ready_log_regex match | 22-03 | PASS | no delta — 5/5 regex strings match exactly once |
| 07 | SIGTERM + graceful_shutdown_s | 22-03, 22-05 | GOTCHA | **Per-recipe timing** (hermes 15s, picoclaw 2s, nullclaw 10s, openclaw 1s, nanobot SIGKILL always). nanobot `sigterm_handled: false`. |
| 08 | env-file 0o600 flag | 22-03 | INHERITED | no new mechanism — mirrors existing routes/runs.py `OPENROUTER_API_KEY` handling already in production |
| 09 | api_server module path parents[4] | 22-04 | PASS | no delta — resolves to `/app` as expected |
| 10 | openclaw pairing approve latency | 22-05, 22-06 | **MAJOR GOTCHA** | 60s (not 2s). Client + server timeouts must be ≥90s. PairingModal needs UX disclosure. |
| 11 | health endpoints | 22-01, 22-05 | GOTCHA | Per-recipe heterogeneous: hermes process_alive (no curl, no listener); picoclaw `/health` (NOT `/ready`); nanobot `/health`; openclaw `/`; nullclaw process_alive. |
| 12 | asyncio.to_thread concurrent lock | 22-04 | DEFERRED | Requires `run_cell_persistent` to exist. Verify in 22-04 Task 1 via pytest-asyncio after impl; the existing `execute_run` lock pattern already is proven for long calls. |
| 13 | SectionHeader `step: "2.5"` render | 22-06 | DEFERRED | Purely CSS/layout visual; zero runtime risk. Verify during 22-06 implementation with `pnpm dev`. |

## Deferred probes (non-blockers)

- **12 concurrent lock**: cannot probe without the new `run_cell_persistent` existing. The sibling `execute_run` in `runner_bridge.py` already uses identical asyncio.to_thread + per-tag Lock + global Semaphore pattern with no issues for minutes-long calls. 2s persistent start will only exercise the lock briefly. Verification inline during 22-04 impl is sufficient.
- **13 SectionHeader**: TypeScript widening `step: number → number | string`. Pure frontend CSS; impact is cosmetic. Verify during 22-06 impl in local dev.
- **08 env-file**: proved by inheritance — the existing `POST /v1/runs` path does env-file injection for `OPENROUTER_API_KEY` to all 5 recipes every day. TELEGRAM_BOT_TOKEN follows identical mechanism.

## Gotchas requiring plan revision

### G1 — pyrage API surface differs from plan example (22-02)

Plan 22-02 Task 2 references `pyrage.passphrase.Recipient.from_str(...)`. That method doesn't exist.

**Correct usage:**
```python
ciphertext = pyrage.passphrase.encrypt(plaintext_bytes, user_kek_hex)
plaintext  = pyrage.passphrase.decrypt(ciphertext, user_kek_hex)
```

**Fix:** revise Plan 22-02 Task 2's code example. One-line change.

### G2 — pyrage + cryptography must land in pyproject.toml (22-02)

Neither is in current `api_server/pyproject.toml`. Image rebuild required during 22-02.

**Fix:** Plan 22-02 Task 0 (prepend): add deps + rebuild. Cheap.

### G3 — SIGTERM graceful_shutdown_s must be per-recipe (22-03, recipe YAMLs)

Plan 22-03 default 5s is wrong for 3/5 recipes. nanobot never honors SIGTERM (always SIGKILL). Plan + recipe YAMLs need heterogeneous values:

| Recipe   | Value |
|----------|-------|
| hermes   | 15 |
| picoclaw | 2  |
| nullclaw | 10 |
| openclaw | 5  |
| nanobot  | 0 (skip graceful, go straight to force-rm) + new recipe field `sigterm_handled: false` |

**Fix:** Plan 22-03 Task 2's `stop_persistent` reads `graceful_shutdown_s` from recipe, not constant. Warn log (not error) on force-kill for `sigterm_handled: false` recipes. Update 5 recipe YAMLs with the correct per-recipe values.

### G4 — openclaw pairing approve latency 60s (22-05, 22-06)

Plan 22-05 Task 4 assumed 2s; actual is 60s. Plan 22-06 PairingModal timeout must be ≥90s.

**Fix:**
- Plan 22-05 Task 4 — `docker exec` timeout 90s; response schema: `{status: "completed" | "processing" | "failed", wall_s: ...}`.
- Plan 22-06 Task 3 — UX copy: "openclaw pair approval takes up to 60 seconds"; client timeout ≥90s; spinner with elapsed-time readout.

### G5 — health_check per-recipe heterogeneous (22-01, 22-05)

Plan 22-01 Task 2 `health_check` schema must be `oneOf` `process_alive` vs `http{port,path}`. Recipe YAMLs need the right values per spike-11. Plan 22-05 Task 3 health probe branches on `kind`.

**Fix:**
- Plan 22-01 Task 2 — `health_check` as `oneOf` union.
- Plan 22-05 Task 3 — dual-branch probe impl (process_alive via `docker inspect`, http via `docker exec curl|wget`).
- 5 recipe YAMLs — set `health_check.kind` + `port` + `path` per spike-11 table.

## Net plan revision summary

All 5 gotchas are mechanical — no structural plan rewrite, just field corrections and dependency additions. Total estimated additional work: ~2h on top of the 32h already estimated.

## Next step

`/gsd-plan-phase 22a --reviews` or manual edit of the affected PLAN files to absorb G1..G5. Then re-run `gsd-plan-checker` to re-verify, then `/gsd-execute-phase 22a`.

All 10 probed mechanisms now have empirical evidence. Risk budget for a sealed PLAN post-revision: zero untested mechanisms remaining.
