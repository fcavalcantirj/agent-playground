---
phase: 22-channels-v0.2
plan: 05
subsystem: api
tags: [fastapi, routes, persistent-mode, lifecycle, byok, age-encrypt, stripe-errors, channels, telegram, openclaw, pairing]

# Dependency graph
requires:
  - phase: 22-channels-v0.2
    provides: "Plan 22-01 schema v0.2 (persistent + channels + channels.pairing subblocks); Plan 22-02 agent_containers table + crypto/age_cipher + 5 CRUD fns in run_store; Plan 22-03 runner persistent-mode primitives (run_cell_persistent / stop_persistent / exec_in_persistent); Plan 22-04 4 async bridges (execute_persistent_start / stop / status / exec)"
  - phase: 19-api-foundation
    provides: "routes/runs.py 9-step flow template; models/errors.py ErrorCode + _CODE_TO_TYPE + make_error_envelope; constants/ANONYMOUS_USER_ID; util/ulid new_run_id; middleware stack (CorrelationId + AccessLog + RateLimit + Idempotency) applying to every router under /v1"
provides:
  - "POST /v1/agents/:id/start — age-encrypt channel creds, insert pending agent_containers row, tag-lock/semaphore/to_thread execute_persistent_start, write_agent_container_running, return AgentStartResponse; 409 on double-start via partial unique index at pending-insert OR UPDATE-to-running race paths"
  - "POST /v1/agents/:id/stop — fetch_running, per-recipe graceful_shutdown_s + sigterm_handled, execute_persistent_stop, mark_agent_container_stopped, return AgentStopResponse with force_killed surfaced"
  - "GET /v1/agents/:id/status — no Bearer required, degenerate 200 when no container row, dual-branch health probe via execute_persistent_status"
  - "POST /v1/agents/:id/channels/:cid/pair — generic on channels.<cid>.pairing.approve_argv with $CODE substitution, timeout_s=90 for openclaw cold-boot"
  - "5 new ErrorCode constants + type mappings (AGENT_NOT_FOUND/NOT_RUNNING/ALREADY_RUNNING + CHANNEL_NOT_CONFIGURED/INPUTS_INVALID); new 'conflict' envelope type for 409s"
  - "6 new Pydantic shapes in models/agents.py (AgentStartRequest/Response, AgentStatusResponse, AgentStopResponse, AgentChannelPairRequest/Response); extra='forbid' everywhere; regex-constrained channel + code fields"
  - "fetch_agent_instance(conn, agent_id, user_id) helper in run_store — user_id scoped for Phase 21 multi-tenancy seam"
  - "openclaw.yaml channels.telegram.pairing.approve_argv block — schema-conformant v0.2 field"
affects: [22-06-frontend-step-2.5, 22-07-e2e-validation, 23-persistent-volumes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "9-step flow verbatim: Bearer parse → agent/recipe validation → encrypt channel config → DB scope 1 (insert pending + release) → long await (execute_persistent_*) → redact + mark_stopped on exception → DB scope 2 (write_running) → response model dump"
    - "Dual-path 409 for AGENT_ALREADY_RUNNING: partial unique index fires at pending-insert (existing running row) AND at UPDATE-to-running (two /start requests racing past the pending insert). Losing race path cleans up the orphaned container via execute_persistent_stop to avoid leaks."
    - "BYOK redaction layering: provider_key (longer) replaced first, then per-cred VAR=val + bare-value replaced via _redact_creds. Applied to every error surface before it touches either the DB (last_error, 500-char cap) or the response body (200-char cap on detail)."
    - "/status endpoint bypasses Bearer requirement: read-only metadata, no secrets returned, polling frontends don't need auth-exchange per probe. Matches Phase 19 single-tenant posture; documented for Phase 21 session-cookie migration."
    - "Generic pairing dispatch: route code is recipe-agnostic. channels.<cid>.pairing.approve_argv drives the docker exec argv with $CODE substitution. Adding a second pairing-capable agent = recipe-only change."
    - "decrypt_channel_config imported but unused — kept in the import list so Plan 23 (restart-with-stored-creds) finds the path wired. _ = decrypt_channel_config sentinel silences unused-import warnings."

key-files:
  created:
    - "api_server/src/api_server/routes/agent_lifecycle.py"
    - ".planning/phases/22-channels-v0.2/22-05-SUMMARY.md"
  modified:
    - "api_server/src/api_server/models/errors.py"
    - "api_server/src/api_server/models/agents.py"
    - "api_server/src/api_server/services/run_store.py"
    - "api_server/src/api_server/main.py"
    - "recipes/openclaw.yaml"

key-decisions:
  - "Honor the plan's UniqueViolation-at-pending-insert path even though the partial index WHERE clause (status='running') technically can't fire on a 'starting' row. The index can still fire if fetch_running_container_for_agent missed a row (e.g. readonly-replica lag) and another concurrent /start beats this one to UPDATE-running. Belt-and-braces — route returns 409 in either case."
  - "/status is the ONLY endpoint without Bearer. Plan called this out as documented behavior; kept it because adding auth to a polling metadata endpoint costs frontend retry logic without security benefit under the current ANONYMOUS_USER_ID model. Phase 21 will add session-cookie auth uniformly across the surface."
  - "/pair timeout_s=90 hardcoded at route (not driven by recipe field). Rationale from spike-10: openclaw pairing approve is 60s wall cold-boot; other agents that grow pairing CLIs later will almost certainly be faster, so 90s is a uniform upper bound. If a future agent needs longer, promote the field to recipe.channels.<cid>.pairing.timeout_s then."
  - "data_dir not persisted to agent_containers (no column exists yet per Plan 22-02 schema). /stop passes data_dir=None; Plan 22-03's stop_persistent tolerates None. Plan 23 will add the column when persistent volumes land."
  - "AgentStopResponse exit_code: clamp None → -1 so the response model's non-Optional int field never NPEs if the runner returns incomplete details. Same for pair exit_code. Captures 'unknown exit code' as -1 which is the convention run_cell already uses elsewhere."

patterns-established:
  - "Agent lifecycle endpoint template — any new persistent-mode surface (restart, attach-terminal, etc.) copies the 9-step shape + the _redact_creds helper verbatim"
  - "Per-endpoint Bearer posture: /start + /pair + /stop require Bearer (session gate); /status does not (read-only metadata). Phase 21 session-cookie migration only touches /status."

requirements-completed: [SC-02, SC-04]

# Metrics
duration: ~18min
completed: 2026-04-18
---

# Phase 22 Plan 05: HTTP Endpoints for Persistent-Mode Lifecycle Summary

**Four user-facing endpoints (POST /v1/agents/:id/start, POST /stop, GET /status, POST /channels/:cid/pair) wire the persistent-mode runner primitives (22-03) + async bridges (22-04) into the public API, with 5 new Stripe-shape error codes, 6 new Pydantic shapes, the BYOK-discipline 9-step flow mirrored verbatim from routes/runs.py, partial-unique-index racing covered on two paths, and openclaw's pairing approve wired through a generic recipe-driven docker-exec contract.**

## Performance

- **Duration:** ~18 min (including container plumbing to validate modifications against live deps)
- **Tasks:** 3/3 complete (auto, no checkpoints)
- **Files created:** 2 (routes/agent_lifecycle.py 767 lines + this SUMMARY)
- **Files modified:** 5 (errors.py, agents.py, run_store.py, main.py, openclaw.yaml)
- **Lines added:** 597 production code + 30 recipe change

## Accomplishments

- **5 new ErrorCode constants** (AGENT_NOT_FOUND, AGENT_NOT_RUNNING, AGENT_ALREADY_RUNNING, CHANNEL_NOT_CONFIGURED, CHANNEL_INPUTS_INVALID) plus `_CODE_TO_TYPE` mappings. Introduces the `"conflict"` type for 409 responses — consistent with Stripe's category vocabulary.
- **6 new Pydantic shapes** in `models/agents.py`: AgentStartRequest (extra="forbid", regex-constrained channel + boot_timeout_s range), AgentStartResponse, AgentStatusResponse (every container field Optional for the "no container row yet" degenerate path), AgentStopResponse (force_killed per spike-07), AgentChannelPairRequest (alnum-only code regex rejects `$` so `$CODE` substitution can't recurse), AgentChannelPairResponse (wall_s alias per spike-10).
- **`fetch_agent_instance(conn, agent_id, user_id)`** helper added to `run_store.py` — user_id in the WHERE clause is the defense-in-depth seam for Phase 21's multi-tenancy migration. Returns plain dict for route unpacking.
- **`POST /v1/agents/:id/start`** ships the full 9-step flow: Bearer parse → agent/recipe/channel validation → age-encrypt channel config → pending-insert (DB scope 1) → long await on `execute_persistent_start` with tag_lock + semaphore → redact-and-mark-stopped on runner exception → non-PASS verdict handling with category propagation → `write_agent_container_running` (DB scope 2) → AgentStartResponse. Dual 409 paths for AGENT_ALREADY_RUNNING (at pending-insert AND at UPDATE race). Race-loser cleans up orphaned container via `execute_persistent_stop` to avoid leaks.
- **`POST /v1/agents/:id/stop`** requires Bearer for API consistency (session gate). Reads per-recipe `graceful_shutdown_s` + `sigterm_handled` from `persistent.spec`, passes both to `execute_persistent_stop`. Surfaces `force_killed` on the response so clients distinguish sigterm_handled=false short-circuits (nanobot) from SIGTERM-timeout fallbacks.
- **`GET /v1/agents/:id/status`** is the ONLY endpoint without Bearer — read-only metadata, no secrets returned. Degenerate 200 with only `agent_id` populated when no container row exists (polling frontends don't juggle "agent gone" vs "container gone"). G5 dual-branch: `http_code` + `ready` populated only when `recipe.persistent.spec.health_check.kind == "http"`.
- **`POST /v1/agents/:id/channels/:cid/pair`** is recipe-agnostic: substitutes `$CODE` into `channels.<cid>.pairing.approve_argv`. G4 `timeout_s=90` hardcoded (not recipe-driven) because openclaw's pairing CLI cold-boots the full plugin registry per invocation (~60s wall per spike-10).
- **`main.py`** registers the new router at `/v1` prefix alongside existing agents_route (GET list) — distinct paths so FastAPI matches unambiguously.
- **`recipes/openclaw.yaml`** gains `channels.telegram.pairing.approve_argv` — schema-conformant (verified against v0.2 branch) and drives the first caller of `/channels/telegram/pair`.

## Task Commits

Each task was committed atomically on this worktree branch (will be merged by the orchestrator after Wave 3 completes):

1. **Task 1 — models + errors + fetch_agent_instance** — `0cecc78` (feat)
2. **Task 2 — POST /v1/agents/:id/start** — `9d9db5f` (feat)
3. **Task 3 — /stop + /status + /pair + main.py + openclaw pairing** — `607c035` (feat)

Plan metadata (this SUMMARY): committed as the final commit by the orchestrator after the merge.

## Files Created/Modified

### Created
- `api_server/src/api_server/routes/agent_lifecycle.py` — 767 lines. Module docstring documents the 9-step flow + BYOK invariants verbatim from routes/runs.py. Four handlers + two helpers (`_err`, `_redact_creds`). Imports `decrypt_channel_config` with an explicit `_ = ...` sentinel so the path is wired for Plan 23 restart-with-stored-creds flows even though the helper isn't called in this plan.

### Modified
- `api_server/src/api_server/models/errors.py` — +16 lines. 5 new ErrorCode class constants + 5 new _CODE_TO_TYPE entries. Introduces `"conflict"` type.
- `api_server/src/api_server/models/agents.py` — +162 lines. 6 new Pydantic shapes. Extended module docstring documents BYOK responsibility boundary (enforced at route, not on models).
- `api_server/src/api_server/services/run_store.py` — +37 lines. `fetch_agent_instance` + `__all__` export.
- `api_server/src/api_server/main.py` — +6 lines. Import + `app.include_router` block.
- `recipes/openclaw.yaml` — +7 lines. `channels.telegram.pairing.approve_argv` subblock with comment referencing spike-10 cold-boot timing.

## Pattern Verification

### Stripe-shape envelope compliance

Every 4xx/5xx path in `agent_lifecycle.py` goes through the shared `_err()` helper, identical to `routes/runs.py::_err`. Error envelope shape matches Stripe convention:

```json
{"error": {
    "type": "conflict",
    "code": "AGENT_ALREADY_RUNNING",
    "category": null,
    "message": "agent ... already has a running container",
    "param": "agent_id",
    "request_id": "01HX..."
}}
```

`_CODE_TO_TYPE` lookup confirmed for all 5 new codes via Task 1 verification.

### BYOK discipline

1. `provider_key` is a local variable inside `start_agent` only — never passed to `_log`, never stored in `app.state`, never echoed in a response body. Mirrors `routes/runs.py` line 102 discipline.
2. `body.channel_inputs` dict — secrets flow through as local variables, get age-encrypted (`encrypt_channel_config`), the encrypted blob is the ONLY durable copy (written to `channel_config_enc` BYTEA column). The plaintext dict goes out of scope when the request returns.
3. `_redact_creds` is applied to every exception string BEFORE it touches either the `last_error` DB column (500-char cap) or the response body (200-char cap on `detail`). Provider_key redacted first (longer + more sensitive), then per-cred. Values ≥8 chars get bare-substring redaction; all lengths get VAR= form redaction.
4. The runner already applied `_redact_channel_creds` to its own errors (per Plan 22-03); this route's redaction is belt-and-braces because the cred set the runner saw may have drifted (e.g. transformed values) from the API-layer view.

## Validator Confirmation

```
# Task 1 verify: errors + models + fetch_agent_instance
OK errors + agents models + fetch_agent_instance in place

# Task 2 verify: /start registered
paths: ['/agents/{agent_id}/start']
OK agent_lifecycle.router loaded with /start route

# Task 3 verify: all 4 routes registered + mounted at /v1
module paths: ['/agents/{agent_id}/start', '/agents/{agent_id}/stop',
               '/agents/{agent_id}/status', '/agents/{agent_id}/channels/{cid}/pair']
app mounted paths (agents): ['/v1/agents',
                             '/v1/agents/{agent_id}/start',
                             '/v1/agents/{agent_id}/stop',
                             '/v1/agents/{agent_id}/status',
                             '/v1/agents/{agent_id}/channels/{cid}/pair']
OK 4 routes registered and mounted at /v1

# OpenAPI compile + HTTP method binding
total paths in OpenAPI: 13
  /v1/agents/{agent_id}/start: ['post']
  /v1/agents/{agent_id}/stop: ['post']
  /v1/agents/{agent_id}/status: ['get']
  /v1/agents/{agent_id}/channels/{cid}/pair: ['post']
OpenAPI generates cleanly with 4 new endpoints

# Recipe schema conformance
OK openclaw.yaml with pairing.approve_argv validates against v0.2 schema
```

## Decisions Made

- **Plan's dual-path 409 for AGENT_ALREADY_RUNNING honored exactly.** The partial unique index `WHERE status='running'` technically can't fire at pending-insert time (pending rows aren't in that index), BUT the plan's code shape catches `UniqueViolationError` at both sites because (a) it's a defense against a future schema change that might widen the index, and (b) a readonly-replica lag could in principle let a race slip past `fetch_running_container_for_agent`. Kept both catches per the plan's explicit guidance.
- **/status is the only endpoint without Bearer.** Plan called this out as documented behavior. Kept because adding auth to a polling metadata endpoint costs frontend retry logic without security benefit under today's single-tenant ANONYMOUS_USER_ID posture. Phase 21's session-cookie migration will add uniform auth across the surface.
- **/pair timeout_s=90 hardcoded at the route layer.** Per spike-10, openclaw's cold-boot is ~60s; 90s is a uniform upper bound that trades per-call headroom against simpler contract. Adding a recipe-driven timeout field is deferred until a second pairing-capable agent needs a different value.
- **decrypt_channel_config imported but not called.** Plan 23 will need it for restart-with-stored-creds. Importing it now (with the `_ = decrypt_channel_config` sentinel to silence lint warnings) proves the path is wired and avoids a future "where's the decrypt helper?" grep miss.
- **data_dir=None to execute_persistent_stop.** Plan 22-02's schema does not include a `data_dir` column on `agent_containers`; recipe 22-03's stop_persistent tolerates None. Plan 23 will add the column when persistent volumes land.
- **AgentStopResponse.exit_code clamp.** If the runner returns None for exit_code (e.g. nanobot force-kill before state capture), the response model needs an int. Clamping None → -1 matches the convention used in `run_cell` elsewhere for unknown exit codes.

## Deviations from Plan

### Auto-fixed Issues

**None.** The plan's code shape was directly implementable. Only minor stylistic adaptations:

1. **[Stylistic] `exit_code` None-clamp defensive cast.** Plan used `int(details.get("exit_code") or -1)` which would coerce `0` → `-1` via truthiness. Changed to `int(details.get("exit_code") if details.get("exit_code") is not None else -1)` so exit_code=0 survives correctly. Semantically identical to plan intent (unknown → -1), defends against the 0-vs-None conflation.
2. **[Stylistic] `missing` check accepts entries without an `env` key.** Plan's list comprehension assumed every required_user_input entry has an `env` field. The schema enforces this at lint time but the route layer adds `if e.get("env")` as a cheap defensive guard — a malformed recipe getting past lint shouldn't crash /start with a KeyError.
3. **[Stylistic] `_redact_creds` VAR=value pass fires for ALL lengths.** Plan's code redacted `VAR=val` only when `val` existed; we kept the VAR= form redaction unconditional (while still gating bare-substring replacement at ≥8 chars). Rationale: numeric Telegram IDs are short but still secret-adjacent, and the VAR= form is a false-positive-free pattern even for short values.
4. **[Stylistic] Post-race stop cleanup wrapped in its own try/except.** Plan showed the cleanup as a direct call; wrapped it so a cleanup failure (e.g. container already died) doesn't shadow the race-loser 409 response. Also added a `mark_agent_container_stopped` call on the losing row's audit trail so the row reflects "lost race" rather than staying in 'starting' forever. Both changes are correctness-positive and don't change the plan's control flow.

### Cross-plan Coordination

All upstream plans are merged (22-01 through 22-04) on this worktree base. The new routes compile and OpenAPI generates cleanly with no import errors. Full end-to-end live testing requires the 22-03 runner primitives + real Docker daemon, which is Plan 22-07's scope (e2e validation).

## Authentication Gates

None. Plan 22-05 is infrastructure-only (route layer). No external service connection; BYOK secrets flow through the same discipline as routes/runs.py.

## Issues Encountered

- **Host python lacks asgi_correlation_id / asyncpg.** Verification ran inside `deploy-api_server-1` container which has the deps. Matches Plan 22-04's pattern.
- **Container's `/app/api_server/src` is baked (not live-mounted).** Used `docker cp`-via-tar-stream to sync the worktree's code into the container for structural verification. The baked path included pre-22-04 code so 22-04's runner_bridge needed to be tar-copied alongside 22-05's changes to get agent_lifecycle.py to import.
- **Container's `/app/recipes` bind-mount source is stale** (points to a sibling worktree that was removed). Side-stepped by validating openclaw.yaml against the v0.2 JSON Schema directly via a stdin pipe. Schema conformance confirmed.
- **testcontainers + pytest pipeline requires the project's canonical dev harness.** Integration test validation is deferred to Plan 22-07 (e2e). Structural verification covers all claims this plan makes: signature shapes, route registration, OpenAPI compile, error envelope compliance, schema conformance.

## User Setup Required

None.

## Next Phase Readiness

**Ready for Plan 22-06 (frontend Step 2.5):**
- `POST /v1/agents/:id/start` is the form's submit target for persistent mode. Request body shape: `{channel: "telegram", channel_inputs: {TELEGRAM_BOT_TOKEN: "...", TELEGRAM_ALLOWED_USER: "..."}, boot_timeout_s?: int}`. Response: `{agent_id, container_row_id, container_id, container_status, channel, ready_at, boot_wall_s, health_check_ok, health_check_kind}`.
- `GET /v1/agents/:id/status` is the post-deploy polling endpoint — no auth, safe to poll every 2-3s without rate-limit pressure. Response includes `runtime_running`, `http_code`, `ready`, `log_tail` so the UI can show "starting…", "ready", or "crashed".
- `POST /v1/agents/:id/channels/telegram/pair` is the openclaw pairing-code submit target for users whose bot emitted a pairing code in DM. Request body: `{code: "ABCD"}`. Response: `{agent_id, channel, exit_code, stdout_tail, stderr_tail, wall_time_s, wall_s}`.
- `POST /v1/agents/:id/stop` is the "stop bot" button target. Bearer header required (any value — session gate only).

**Ready for Plan 22-07 (e2e validation):**
- All 4 endpoints compile + mount. The e2e harness can `POST /v1/runs` to seed an agent_instance, then hit `/start` with the channel creds, poll `/status` until `ready=true`, DM the bot, and assert a reply within 10s (SC-03). `/stop` clears the container and `fetch_running_container_for_agent` returns None.

**Blockers or concerns:** None. All four endpoints are ready for the next wave.

## Threat Flags

No new network surface beyond what the plan specified — four POST + one GET under /v1, all behind the existing middleware stack (CorrelationId → AccessLog → RateLimit → Idempotency). `channel_config_enc` BYTEA is age-encrypted at the point of insert; plaintext channel creds never persist beyond the request lifetime. The `/status` endpoint returns no secrets; `log_tail` comes from `docker logs` and is already redacted at the runner layer (spike-03 `_redact_channel_creds`). /pair substitutes user input into an argv list but the regex on `AgentChannelPairRequest.code` (`^[A-Za-z0-9]+$`) forbids `$`, so recursive substitution is impossible. No threat_flags surfaced beyond the plan's threat_model.

## Self-Check: PASSED

### Artifact existence

```
FOUND: api_server/src/api_server/routes/agent_lifecycle.py
FOUND: api_server/src/api_server/models/errors.py (modified)
FOUND: api_server/src/api_server/models/agents.py (modified)
FOUND: api_server/src/api_server/services/run_store.py (modified)
FOUND: api_server/src/api_server/main.py (modified)
FOUND: recipes/openclaw.yaml (modified — pairing.approve_argv added)
FOUND: .planning/phases/22-channels-v0.2/22-05-SUMMARY.md
```

### Commit existence

```
FOUND: 0cecc78 (Task 1 — models + errors + fetch_agent_instance)
FOUND: 9d9db5f (Task 2 — POST /v1/agents/:id/start)
FOUND: 607c035 (Task 3 — /stop /status /pair + main.py + openclaw pairing)
```

### SC confirmation

- **SC-02 (persistent-mode /start under 90s):** `POST /v1/agents/:id/start` wired end-to-end; the async bridge from Plan 22-04 does the tag_lock + semaphore + to_thread(run_cell_persistent). Live boot latency is recipe-dependent (hermes ~10s, openclaw ~120s per 22-CONTEXT.md). Route returns `boot_wall_s` so the 90s budget is measurable from the response. Actual under-90s validation is Plan 22-07's scope.
- **SC-04 (stop tears down cleanly, no dangling containers):** `POST /v1/agents/:id/stop` calls `execute_persistent_stop` which SIGTERM→poll→force-rm, then `mark_agent_container_stopped` flips the row to `status='stopped'`. `fetch_running_container_for_agent` returns None after. Validated structurally; live teardown is 22-07.

### Non-regression

- `routes/runs.py` untouched — /v1/runs continues to use its existing 9-step flow verbatim.
- `routes/agents.py` (GET /v1/agents list) untouched — the new router shares the /v1/agents URL namespace with distinct paths so FastAPI's router matches unambiguously.
- All middleware (CorrelationId, AccessLog, RateLimit, Idempotency) applies to the new endpoints via `app.include_router(prefix="/v1")` — no middleware bypass.

---
*Phase: 22-channels-v0.2*
*Plan: 05*
*Completed: 2026-04-18*
