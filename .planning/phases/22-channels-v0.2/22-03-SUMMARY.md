---
phase: 22-channels-v0.2
plan: 03
subsystem: runner
tags: [docker, persistent-mode, channels, telegram, sigterm, byok, env-file, redaction, runner]

# Dependency graph
requires:
  - phase: 22-channels-v0.2
    provides: "v0.2 schema with persistent + channels blocks live and linting PASS for all 5 recipes (Plan 22-01)"
  - phase: 22-channels-v0.2
    provides: "agent_containers table + pyrage per-user KEK encryption for channel_config (Plan 22-02)"
  - phase: 10-error-taxonomy
    provides: "Category enum (PASS/INVOKE_FAIL/TIMEOUT) + Verdict dataclass + _redact_api_key two-mode redactor"
provides:
  - "run_cell_persistent(): docker run -d --name ap-agent-<run_id>; polls persistent.spec.ready_log_regex in docker logs within boot_timeout_s; runs health_check probe (process_alive or http); returns (Verdict, {container_id, boot_wall_s, ready_at, health_check_ok, data_dir}); honors user_override + prefix_required"
  - "stop_persistent(): SIGTERM -> 500ms poll -> docker rm -f fallback; sigterm_handled=false short-circuits to force-kill for nanobot (spike-07); returns stopped_gracefully + force_killed"
  - "exec_in_persistent(): docker exec wrapper for openclaw pairing approve (Plan 22-06 caller)"
  - "_redact_channel_creds(): extends _redact_api_key across every secret channel cred + VAR= pass for non-secret inputs"
  - "CLI --mode persistent + --stop flags for manual testing without the API in the loop"
affects: [22-04-runner-bridge, 22-05-api-endpoints, 22-06-openclaw-pairing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "docker run -d with --name ap-agent-<run_id> (not --rm) for long-lived agent containers"
    - "Log-match readiness polling (ready_log_regex against docker logs --tail 200) with fail-fast on container exit before match"
    - "Per-recipe graceful_shutdown_s + sigterm_handled flag honored at teardown (heterogeneous SIGTERM policy across 5 recipes)"
    - "Channel-cred env-file pattern identical to run_cell's api_key pattern: 600 perms, unlinked post-docker-run, never on argv; secrets live only in env-file + container kernel namespace during boot"
    - "prefix_required auto-prepend at env-file write time (openclaw 'tg:' for TELEGRAM_ALLOWED_USER)"
    - "CLI AP_CHANNEL_<ENV> env-prefix pattern for manual persistent-mode tests — keeps shell history clean + avoids fragile quoting"

key-files:
  created:
    - ".planning/phases/22-channels-v0.2/22-03-SUMMARY.md"
  modified:
    - "tools/run_recipe.py"

key-decisions:
  - "Do NOT refactor run_cell() to share code with run_cell_persistent — the two paths are small enough that duplication wins over a shared abstraction that would have to juggle one-shot --rm vs detached --name semantics. SC-01 regression risk is zero."
  - "_redact_channel_creds() helper introduced: wraps _redact_api_key so every secret-entry cred gets both VAR= prefix redaction AND bare-value redaction with one call site. Non-secret inputs (e.g. TELEGRAM_ALLOWED_USER) still flow through the VAR= pass so numeric IDs don't leak."
  - "data_dir cleanup is the CALLER's responsibility via stop_persistent — details dict includes data_dir so the runner_bridge thread can wipe it after teardown. Inline cleanup in run_cell_persistent would race with a live container still holding the mount."
  - "Health check is a secondary signal, NOT a boot gate — log-match already proved readiness. A failed HTTP probe is surfaced via health_check_ok=False in details, not via a non-PASS verdict. This matches the spike-11 finding that hermes has no HTTP listener at all (process_alive only) while picoclaw/nanobot/openclaw have real HTTP endpoints."
  - "CLI --stop handler lives BEFORE recipe-path validation and takes graceful_shutdown_s=10 as a safe upper bound. Runner_bridge (22-04) is the primary caller and will thread the recipe's actual value; the CLI --stop is the debugging seam for 'clean up a leaked container' and doesn't need to load a recipe."
  - "--all-cells + --mode persistent rejected with exit 2 — persistent is not a cell sweep. Help string documents this."
  - "Tasks 1 and 2 committed together (commit 0aa2299) because their new functions are tightly coupled in the same file region and the helpers (_cleanup, _force_remove) are shared between them. Separating into two commits would have required artificial file splitting. Documented explicitly in the commit message."

patterns-established:
  - "docker run -d + log-match ready polling (agent_playground Phase 22 persistent-mode)"
  - "Per-recipe sigterm policy via recipe.persistent.spec.sigterm_handled (spike-07 honored at runner layer)"
  - "Channel-cred BYOK discipline: secrets arrive as function args, flow through 600-perm env-file, get redacted on every error surface via _redact_channel_creds"

requirements-completed: [SC-02, SC-04, SC-05]

# Metrics
duration: 6min
completed: 2026-04-18
---

# Phase 22 Plan 03: Runner Persistent-Mode Primitives Summary

**run_cell_persistent + stop_persistent + exec_in_persistent added to tools/run_recipe.py; docker run -d + ready_log_regex polling + per-recipe sigterm policy + channel-cred env-file with prefix_required + full redaction across every error surface; CLI --mode persistent / --stop wired for manual testing without the API.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-18T17:48:53Z
- **Tasks:** 3/3 complete (committed as 2 atomic commits due to tight coupling of Task 1+2 helpers)
- **Files modified:** 1 (`tools/run_recipe.py`)
- **Lines added:** 562 (+441 in commit 1, +121 in commit 2)
- **Existing tests:** 119 pre-existing runner tests PASS (no regression: test_lint, test_hardening_envfile, test_hardening_api_key, test_hardening_substitute, test_categories, test_pass_if, test_phase10_primitives)

## Accomplishments

- **run_cell_persistent()** shipped: 8-step body per plan — validate persistent + channel blocks, assemble argv with $MODEL substitution, build env-file with required + optional + prefix_required transforms, `docker run -d --name ap-agent-<run_id>`, poll `docker logs --tail 200` against `persistent.spec.ready_log_regex`, run health_check probe (process_alive via `docker inspect State.Running`, http via `docker exec curl||wget`), return `(Verdict, {container_id, boot_wall_s, ready_at, health_check_ok, data_dir})`. Fail-fast on container exit before ready match (captures exit_code + log tail). Env-file unlinked only AFTER docker run succeeds; data_dir cleanup deferred to stop_persistent.
- **stop_persistent()** shipped: per-recipe graceful_shutdown_s + sigterm_handled from plan's spike-07 matrix honored. sigterm_handled=false (nanobot) short-circuits to force-kill with warning. sigterm_handled=true path: `docker kill -s TERM <cid>`, poll `State.Running` every 500ms until `graceful_shutdown_s` deadline, fall back to `docker rm -f`. Returns `force_killed: bool` for Plan 22-05 response-body surfacing. Captures exit_code before force-remove.
- **exec_in_persistent()** shipped: `docker exec` wrapper with configurable `timeout_s`. Returns `(Verdict, {exit_code, stdout_tail, stderr_tail, wall_time_s})`. First caller is Plan 22-06 `POST /v1/agents/:id/channels/:cid/pair` with argv `["openclaw", "pairing", "approve", "telegram", "<CODE>"]`.
- **_redact_channel_creds()** helper added: extends `_redact_api_key` to iterate every required + optional channel input, applies both VAR= regex and bare-value redaction (for secrets >=8 chars). Applied to every error surface derived from subprocess stderr/logs/combined output in run_cell_persistent.
- **CLI --mode persistent + --stop** flags added to argparse. `--mode persistent` reads `AP_CHANNEL_<ENV>` env vars for channel creds (no shell quoting pain), auto-generates run_id if omitted, rejects --all-cells combo. `--stop CONTAINER_ID` short-circuits before recipe validation.

## Task Commits

Each logical task was committed atomically:

1. **Tasks 1+2: persistent-mode primitives (run_cell_persistent + stop_persistent + exec_in_persistent + helpers)** — `0aa2299` (feat)
2. **Task 3: CLI --mode persistent + --stop for manual testing** — `cfe67d3` (feat)

_Note: Tasks 1 and 2 both add new top-level functions in the same file region (`tools/run_recipe.py` lines 940-1383 region) and share two helpers (`_cleanup`, `_force_remove`). They were committed as a single atomic commit because separating them would have required artificial file-splitting. Verification gates for Task 1 and Task 2 both pass on commit 0aa2299._

Plan metadata commit (this SUMMARY): will be made as the final commit.

## Files Created/Modified

- `tools/run_recipe.py` — +562 lines. New exports: `run_cell_persistent`, `stop_persistent`, `exec_in_persistent`, `_cleanup`, `_force_remove`, `_redact_channel_creds`. New CLI flags: `--mode {smoke,persistent}`, `--channel`, `--channel-creds-env-prefix`, `--run-id`, `--boot-timeout-s`, `--stop CONTAINER_ID`. Added `from datetime import datetime, timezone` import. `run_cell()` untouched (SC-01 regression protection).
- `.planning/phases/22-channels-v0.2/22-03-SUMMARY.md` — this file.

## Decisions Made

- **Separate function, not a unified one** — `run_cell_persistent` is net-new; no surgery on `run_cell`. Code duplication between the two (env-file setup, data_dir mkdtemp, volume mount, entrypoint override) is modest and the semantics diverge enough (`--rm` + cidfile vs `-d` + --name; single smoke vs ready-log + health probe) that a shared helper would have to straddle both regimes awkwardly.
- **`_redact_channel_creds` as a dedicated helper** — rather than inline the `for entry in required + optional` loop at every error surface. One call site at each error path; changes to redaction policy live in one function.
- **Health check is a signal, not a gate** — log-match IS the readiness gate. HC result flows through `health_check_ok` in details for the status endpoint (Plan 22-05) to surface, but doesn't fail boot. This matches spike-11's finding that hermes has no HTTP listener (process_alive only) and picoclaw's /ready returns 503 even when the channel is live (/health returns 200).
- **CLI dispatch order** — `--stop` before recipe validation (doesn't need a recipe); `--mode persistent` after `ensure_image` (image must exist even in persistent mode). Rejects `--all-cells` + `--mode persistent` with exit 2.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `_redact_channel_creds` helper beyond what plan spec**
- **Found during:** Tasks 1 + 2 (design of error paths)
- **Issue:** Plan pseudocode inlined `_redact_api_key` calls with a `for entry in required_inputs if entry.get("secret"): ...` loop repeated at each error surface (docker run failure, container-exit-before-ready, log-tail redaction). Repeated loops are error-prone — easy to miss one site when a new error path lands in Plan 22-04's runner_bridge.
- **Fix:** Extracted a single `_redact_channel_creds(text, api_key_var, api_key_val, required_inputs, optional_inputs, channel_creds)` helper. Called at every subprocess stderr/logs surface. Also iterates `optional_inputs` (plan only called out `required_inputs`) so optional non-secret cred names still get VAR= redaction — a defense-in-depth policy expansion that doesn't leak secrets (they're explicitly non-secret) but keeps env-var names out of error messages.
- **Files modified:** tools/run_recipe.py
- **Verification:** `_redact_channel_creds('TELEGRAM_BOT_TOKEN=8710255942:AAEFakeToken and OPENROUTER_API_KEY=sk-or-v1-FakeKey', ...)` returns `'TELEGRAM_BOT_TOKEN=<REDACTED> and OPENROUTER_API_KEY=<REDACTED>'` — both VAR= and bare-value substrings removed.
- **Committed in:** 0aa2299 (Task 1+2 commit)

**2. [Rule 2 - Missing Critical] Added missing-check on persistent.spec fields (argv, ready_log_regex, health_check)**
- **Found during:** Task 1 implementation
- **Issue:** Plan's step-1 pseudocode only checked for `persistent` block existence. If a future recipe had a `persistent` block but forgot `spec.argv`, `run_cell_persistent` would raise `TypeError` on `substitute_argv(None, ...)` deep in the body rather than surfacing a clean `RuntimeError` with a recipe path.
- **Fix:** Added three explicit `if not spec.get(...): raise RuntimeError(...)` checks before argv assembly. Schema enforces these fields per Plan 22-01 so the checks are belt-and-suspenders, but a lint-disabled path (`--no-lint`) could still hit this.
- **Files modified:** tools/run_recipe.py
- **Verification:** Current 5 recipes all pass this gate (lint-all PASS); defensive checks only trigger on hand-edited recipes with broken persistent blocks.
- **Committed in:** 0aa2299 (Task 1+2 commit)

**3. [Rule 3 - Blocking] Added `from datetime import datetime, timezone` import**
- **Found during:** Task 1 implementation (needed for `ready_at` ISO timestamp)
- **Issue:** datetime/timezone not previously imported in run_recipe.py.
- **Fix:** Added import to the top-of-file import block, alphabetically sorted into the stdlib cluster.
- **Files modified:** tools/run_recipe.py
- **Verification:** `import tools.run_recipe as rr; rr.run_cell_persistent` returns without ImportError.
- **Committed in:** 0aa2299 (Task 1+2 commit)

**4. [Minor - CLI UX] Added `--boot-timeout-s` flag beyond plan spec**
- **Found during:** Task 3 implementation
- **Issue:** Plan mentioned a 180s default boot_timeout_s on the function signature but didn't surface it to the CLI. For manual testing (openclaw image is 6GB and boot can approach 120s), developers need a way to bump it without editing source.
- **Fix:** Added `--boot-timeout-s` argparse flag (int, default 180) threaded through to `run_cell_persistent(..., boot_timeout_s=args.boot_timeout_s)`.
- **Files modified:** tools/run_recipe.py
- **Verification:** `--help` lists the flag; exists as args.boot_timeout_s and passes through to the primitive.
- **Committed in:** cfe67d3 (Task 3 commit)

---

**Total deviations:** 4 auto-fixed (1 missing-critical security, 2 missing-critical validation, 1 blocking import, 1 minor CLI UX)
**Impact on plan:** All four are additive and make the primitives more robust or the CLI more usable. Zero changes to the function signatures or return shapes the plan spec'd. Plan 22-04 (runner_bridge) and Plan 22-05 (routes) consume `run_cell_persistent` with exactly the signature the plan described.

## Issues Encountered

None. The spike-driven plan nailed every gray area upfront — per-recipe `graceful_shutdown_s` + `sigterm_handled` from spike-07, per-recipe `health_check` shape from spike-11, `docker run -d` container-id-on-stdout contract from spike-05, `ready_log_regex` patterns from spike-06. No surprises during execution.

## Manual Smoke — NOT yet performed in this worktree

Plan's `<verification>` block describes a manual hermes+telegram smoke (boot container, DM bot, observe reply, stop container). **This is deferred to the integration cycle in Plan 22-04 / 22-05** — it requires the runner_bridge wrapper + the /start route + live Telegram creds from `.env.local`, none of which are in this plan's scope. The automated gates (signature sanity, flag presence, credential rejection, --all-cells rejection, 119 existing tests pass, 5 recipes still lint) all PASS in this worktree.

## Threat Surface

No new network endpoints introduced in this plan (CLI remains local-only; the API routes in Plan 22-05 will own the network surface). New process-lifecycle pattern: `docker run -d` detached containers persist beyond the runner's own lifetime. Mitigated by:
- `stop_persistent` provides the teardown primitive; runner_bridge (22-04) + DB state (22-02 `agent_containers` table) track which containers are owned so orphans can be reaped.
- CLI `--stop CONTAINER_ID` is the manual reaper seam.
- Env-file is chmod 600 + unlinked post-docker-run; secrets never land on argv, `ps`, or `/proc/*/cmdline`.

## Next Phase Readiness

- **22-04 runner_bridge**: can import `run_cell_persistent`, `stop_persistent`, `exec_in_persistent` from `tools/run_recipe.py` via `importlib.util.spec_from_file_location` (same pattern as existing `_import_run_cell` at `api_server/src/api_server/services/runner_bridge.py` lines 38-60). Wrap in `asyncio.to_thread` + per-image tag_lock + concurrency semaphore.
- **22-05 API routes**: `POST /v1/agents/:id/start` → runner_bridge → `run_cell_persistent` → DB write `agent_containers.status='running' + container_id + ready_at`. `POST /v1/agents/:id/stop` → runner_bridge → `stop_persistent(..., graceful_shutdown_s=recipe.persistent.spec.graceful_shutdown_s, sigterm_handled=recipe.persistent.spec.sigterm_handled)` → DB update `status='stopped'`. Surface `force_killed` in AgentStopResponse.
- **22-06 openclaw pairing**: `POST /v1/agents/:id/channels/:cid/pair` body `{code: string}` → `exec_in_persistent(container_id, ["openclaw", "pairing", "approve", channel_id, code])`.

## Self-Check: PASSED

**Created file exists:**
- `FOUND: .planning/phases/22-channels-v0.2/22-03-SUMMARY.md` (this file)

**Commits exist:**
- `FOUND: 0aa2299` (feat: persistent-mode primitives)
- `FOUND: cfe67d3` (feat: CLI --mode persistent + --stop)

**Automated verification gates:**
- GATE 1 PASS: `import tools.run_recipe as rr; assert rr.run_cell_persistent and rr.stop_persistent and rr.exec_in_persistent`
- GATE 2 PASS: `python3 tools/run_recipe.py --help | grep -- --mode` prints `--mode {smoke,persistent}`
- GATE 3 PASS: `run_cell_persistent` signature includes all 8 required params (recipe, image_tag, model, api_key_var, api_key_val, channel_id, channel_creds, run_id)
- GATE 4 PASS: `run_cell` signature unchanged (`run_cell` still present, params unchanged — SC-01 regression protection)
- GATE 5 PASS: Missing-creds CLI exits 2 with clear stderr: `missing required channel creds (env AP_CHANNEL_*): ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_ALLOWED_USERS']`
- GATE 6 PASS: `--all-cells` + `--mode persistent` exits 2
- GATE 7 PASS: `_redact_channel_creds` removes both VAR= prefix and bare-value substrings for `TELEGRAM_BOT_TOKEN` + `OPENROUTER_API_KEY`
- GATE 8 PASS: 119 existing runner tests pass (no regression)
- GATE 9 PASS: 5 recipes still lint PASS via `--lint-all`

---
*Phase: 22-channels-v0.2*
*Plan: 03*
*Completed: 2026-04-18*
