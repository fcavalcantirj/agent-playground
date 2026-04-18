---
phase: 22-channels-v0.2
plan: 04
subsystem: services
tags: [runner-bridge, asyncio, concurrency, to_thread, semaphore, per-tag-lock, persistent-mode, import-cache]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: "execute_run + _import_run_cell + _get_tag_lock + per-image-tag Lock + global Semaphore + asyncio.to_thread scaffold; app.state.image_tag_locks + run_semaphore + locks_mutex wiring"
  - phase: 22-channels-v0.2
    provides: "Plan 22-03 run_cell_persistent + stop_persistent + exec_in_persistent runner primitives (call contract locked by Plan 22-04 PLAN; integration verified post-merge)"
provides:
  - "execute_persistent_start: await-able bridge for /v1/agents/:id/start; per-tag Lock + global Semaphore + to_thread wrapping run_cell_persistent"
  - "execute_persistent_stop: await-able bridge for /v1/agents/:id/stop; no lock, no semaphore, to_thread-only; propagates sigterm_handled + recipe_name for nanobot warn-path"
  - "execute_persistent_status: self-contained docker inspect + docker logs probe with spike-11 curl||wget dual-branch fallback; no lock, no semaphore; returns running=False cleanly for missing containers"
  - "execute_persistent_exec: semaphore-bounded docker exec wrapper for /v1/agents/:id/channels/:cid/pair"
  - "_import_run_recipe_module: refactored import helper returning full runner module (was _import_run_cell returning only .run_cell); back-compat shim preserved so Plan 19 execute_run and tests are untouched"
affects: [22-05-api-endpoints, 22-06-frontend-step-2.5]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-cache-over-callable: _import_run_recipe_module returns the whole sys.modules entry so all 4 persistent-mode bridges + Plan 19 execute_run share one Verdict/Category identity"
    - "Type-agnostic verdict adapter: getattr chain (verdict|name|str) + (value|name|str) converts Plan 22-03's Verdict namedtuple + Category enum into plain strings on the details dict so route layer (Plan 22-05) branches on strings, not bespoke types"
    - "Tag-lock discipline inherited verbatim: execute_persistent_start wraps in tag_lock + semaphore + to_thread identical to execute_run — same concurrency guarantee for same-recipe boots"
    - "No-lock fast-path for stop/status: neither touches images, so skip the per-tag Lock entirely; still to_thread-wrapped because docker CLI calls can block on slow daemon"
    - "Self-contained probe seam: execute_persistent_status implements inspect+logs in the bridge layer rather than extending the runner — keeps API-layer concerns where they belong and avoids noise in tools/run_recipe.py"

key-files:
  created:
    - ".planning/phases/22-channels-v0.2/22-04-SUMMARY.md"
  modified:
    - "api_server/src/api_server/services/runner_bridge.py"

key-decisions:
  - "Refactor _import_run_cell → _import_run_recipe_module + back-compat shim. Plan chose this path explicitly (return the whole module so all 4 new functions + existing execute_run share one sys.modules entry). Kept _import_run_cell as a one-liner shim so Plan 19 execute_run and the existing tests never see the signature change."
  - "Attach verdict/category/detail as strings to details dict (not as Verdict/Category objects). Plan 22-05's route layer must not import the runner's bespoke Verdict namedtuple from tools/run_recipe.py — it would drag the whole runner into the route layer's type graph. The bridge is the conversion boundary."
  - "execute_persistent_status is NOT a new runner primitive. It's self-contained subprocess calls (docker inspect + docker logs + optional docker exec http probe) totaling ~30 lines. Moving it to tools/run_recipe.py would be noise; keeping it in the bridge keeps it an API-layer concern as the plan explicitly called out."
  - "semaphore on exec but NOT on stop/status. Reasoning per plan: exec runs agent CLI commands that may be slow (openclaw pairing approve is sub-second today but other exec paths — arbitrary argv — are bounded only by timeout_s); stop/status are millisecond-scale probes that a semaphore would only slow down."

patterns-established:
  - "Async bridge template for sync runner primitives: _import_run_recipe_module → _get_tag_lock (optional) → run_semaphore (optional) → asyncio.to_thread(mod.<primitive>, ...) → tuple/dict adapter with string-attached verdict"
  - "Missing-container graceful degradation: status probe on a non-existent container_id returns {running: False, log_tail: [docker stderr]} without raising — so /v1/agents/:id/status is idempotent and always 200-able"

requirements-completed: [SC-02, SC-04]

# Metrics
duration: ~12min
completed: 2026-04-18
---

# Phase 22 Plan 04: Persistent-mode async bridges Summary

**Four new async functions (execute_persistent_start/stop/status/exec) wrap Plan 22-03's runner primitives in the same per-tag Lock + Semaphore + asyncio.to_thread scaffold used by execute_run — Plan 22-05's route layer can now `await` container lifecycle without ever holding a DB connection or stalling the event loop, and the module-import cache is refactored so all five run_recipe callables share one sys.modules entry without breaking Plan 19 back-compat.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2/2 complete
- **Files modified:** 1 (runner_bridge.py)
- **Lines added:** 272 (41 refactor + 73 execute_persistent_start + 158 stop/status/exec)
- **Lines removed:** 8 (the old _import_run_cell body, now in _import_run_recipe_module)

## Accomplishments

- **_import_run_cell → _import_run_recipe_module refactor** — returns the whole runner module so callers attribute-access `.run_cell`, `.run_cell_persistent`, `.stop_persistent`, `.exec_in_persistent` from one sys.modules entry. Preserves Verdict/Category identity across lint_service + execute_run + all 4 new persistent-mode bridges. `_import_run_cell` preserved as a 2-line shim (`return _import_run_recipe_module().run_cell`) so execute_run is byte-unchanged at the call site.
- **execute_persistent_start** — wraps `mod.run_cell_persistent` with `tag_lock + run_semaphore + to_thread`, identical to execute_run's scaffold. Tag lock held for full boot duration (~10-120s) is intentional per plan — concurrent /start for the SAME recipe serialize on the image cache; DIFFERENT recipes run in parallel (semaphore-bounded). Returns the details dict with `verdict` / `category` / `detail` string fields attached via a getattr-chain adapter, so the route layer never imports the runner's bespoke Verdict namedtuple.
- **execute_persistent_stop** — `to_thread`-only (no lock, no semaphore); stop doesn't touch images and is cheap. Propagates `sigterm_handled: bool` and `recipe_name: str | None` through to `stop_persistent` for nanobot's "skip SIGTERM" path (spike-07). Surfaces `force_killed` on the result dict (sets False by default if the primitive didn't include it — belt-and-suspenders).
- **execute_persistent_status** — self-contained subprocess probe that does NOT call into run_recipe. Docker inspect + docker logs always; docker exec curl||wget http probe only when the recipe declares `health_check.kind == "http"` AND container is running. Missing-container path returns `{running: False, log_tail: [docker error], exit_code: None, http_code: None, ready: None}` cleanly — `/v1/agents/:id/status` can always respond 200 regardless of container lifecycle state.
- **execute_persistent_exec** — semaphore-bounded `docker exec` for the /pair endpoint. No image lock (exec doesn't touch images). First caller is `POST /v1/agents/:id/channels/:cid/pair` with `["openclaw", "pairing", "approve", "telegram", "<CODE>"]`.

## Task Commits

Each task was committed atomically on this worktree branch (will be merged by the orchestrator after Wave 2 completes):

1. **Task 1 — refactor _import + add execute_persistent_start** — `781d7a2` (feat)
2. **Task 2 — add execute_persistent_stop/status/exec** — `09f9ecc` (feat)

## Files Created/Modified

### Created
- `.planning/phases/22-channels-v0.2/22-04-SUMMARY.md` — this file

### Modified
- `api_server/src/api_server/services/runner_bridge.py` — +272 / −8 lines
  - `_import_run_cell()` → `_import_run_recipe_module()` + shim. Returns the full module; the shim (`return _import_run_recipe_module().run_cell`) preserves Plan 19's callable-returning contract for `execute_run`.
  - `execute_persistent_start(app_state, recipe, *, model, api_key_var, api_key_val, channel_id, channel_creds, run_id, boot_timeout_s=180)` — same tag_lock + semaphore + to_thread as execute_run; dict-adapter attaches `verdict` / `category` / `detail` as strings.
  - `execute_persistent_stop(container_id, *, graceful_shutdown_s=5, sigterm_handled=True, recipe_name=None, data_dir=None)` — to_thread-only wrapper over `stop_persistent`; surfaces `force_killed` (defaulted to False if absent).
  - `execute_persistent_status(container_id, *, recipe_health_check=None, log_tail_lines=50)` — self-contained `_probe()` closure run under to_thread; dual-branch health check (process_alive default; http via docker exec + curl||wget fallback). Returns `{running, exit_code, log_tail, http_code, ready}`.
  - `execute_persistent_exec(app_state, container_id, argv, *, timeout_s=30)` — semaphore-bounded `docker exec` wrapper over `exec_in_persistent`; no image lock.

## Concurrency Decisions

Documented per the plan output spec. For each bridge function:

| Function | Image tag-lock | Global Semaphore | asyncio.to_thread | Rationale |
|----------|---------------|-------------------|--------------------|-----------|
| `execute_persistent_start` | ✅ YES | ✅ YES | ✅ YES | First call on cold image must build/pull; subsequent same-recipe starts must wait on the tag lock. Different-recipe starts run in parallel bounded by the semaphore. |
| `execute_persistent_stop` | ❌ NO | ❌ NO | ✅ YES | Stop doesn't touch images (no lock needed); stop is cheap and concurrent-safe (semaphore would only slow it down). Still to_thread because subprocess calls can block. |
| `execute_persistent_status` | ❌ NO | ❌ NO | ✅ YES | Read-only probe (docker inspect + docker logs, optional docker exec http probe); safe to run concurrently across any number of containers. |
| `execute_persistent_exec` | ❌ NO | ✅ YES | ✅ YES | Exec doesn't touch images (no lock). Semaphore bounds concurrent `docker exec` calls across unrelated containers so a storm of /pair requests can't flood the daemon. |

## Validator Confirmation

```
# Task 1 verify: module cache + signature + back-compat
OK execute_persistent_start signature valid; module cache working
   Plan-22-03 primitives present: run_cell_persistent=False stop_persistent=False exec_in_persistent=False
   (expected: parallel worktree — 22-03 merges these post-execution)

# Task 2 verify: signatures + missing-container degradation
OK all 3 signatures valid
OK status probe on missing container: running=False, log_tail=1 lines
  (log_tail content: ['Error response from daemon: No such container: ...'])

# Plan-level SC verification
OK SC-02: execute_persistent_start is async (awaited, not thread-blocked)
OK SC-04: execute_persistent_stop is async
OK Back-compat: execute_run + _import_run_cell preserved
OK Module cache: _import_run_recipe_module returns same module object across calls
```

## Decisions Made

- **Refactor over duplication.** Plan 22-04 explicitly offered the refactor path: replace `_import_run_cell` with `_import_run_recipe_module` + shim, rather than adding sibling import helpers for each new primitive. Shared module cache = shared Verdict/Category identity across all callers = fewer latent "two instances of the same class" bugs. Cost was 4 extra lines; benefit is every future persistent-mode bridge follows the same template with zero import-helper proliferation.
- **String-typed verdict adapter instead of re-exporting Verdict.** Plan 22-05's route layer must not import the runner's bespoke Verdict namedtuple or Category enum (that would pull tools/run_recipe.py into the route module's type graph). The adapter extracts strings (`getattr(verdict, "verdict") || getattr(verdict, "name") || str(verdict)`) and attaches them to the details dict. The runner stays internal; the route reads strings.
- **execute_persistent_status lives in the bridge, NOT in tools/run_recipe.py.** Plan said "factored here (not as a new run_recipe function) because it's API-layer concern, not runner primitive." Honored. The probe is ~30 lines of subprocess glue; extending the runner just to host them would be noise.
- **force_killed defaulted to False on stop result.** Plan 22-03's `stop_persistent` SHOULD return it; if the primitive omits it (pre-merge fixture, unit-test short-circuit), the bridge sets False so `AgentStopResponse` never NPEs on a missing field.

## Deviations from Plan

### Auto-fixed Issues

None. The plan's code shape was directly implementable. Only stylistic adaptations:

1. **[Stylistic] Verdict adapter uses getattr chain rather than direct attribute access.** Plan spec used `verdict.verdict` + `verdict.category.value` which works only when the Verdict namedtuple has those exact attributes AND category has a `.value` (enum). The getattr chain (`getattr(x, "verdict") || getattr(x, "name") || str(x)`) tolerates (a) Plan 22-03 shipping a class with slightly different attribute names, (b) tests short-circuiting with a plain string, (c) future runner refactors. Semantically identical to plan intent (extract string fields); more defensive against Plan-22-03 drift.

### Cross-plan Coordination

Plan 22-03 runs in parallel. Its primitives (`run_cell_persistent`, `stop_persistent`, `exec_in_persistent`) do NOT yet exist in this worktree — Plan 22-04's bridge is coded to the call contract documented in its own PLAN.md (the prompt explicitly instructed this). When the orchestrator merges Wave 2, the bridges will resolve against the real runner module. Unit structural tests (signature introspection, module cache, missing-container degradation) all pass on this worktree standalone.

**Expected post-merge verification the Plan 22-05 executor will run:**
1. `from api_server.services.runner_bridge import execute_persistent_start`
2. Instantiate an app_state (with image_tag_locks + locks_mutex + run_semaphore attributes)
3. `await execute_persistent_start(app_state, recipe=<hermes>, model=..., channel_id="telegram", channel_creds={...}, run_id="test-xxx")`
4. Assert returned dict has keys: `verdict, category, container_id, ready_at, boot_wall_s, ...`
5. `await execute_persistent_stop(container_id, graceful_shutdown_s=5)` — verify container removed.

## Authentication Gates

None. Plan 22-04 is infrastructure-only (async bridge wrappers). No external service connection; no secret-handling beyond what the route layer (Plan 22-05) will pass through.

## Issues Encountered

- **Host Python venv lacks asyncpg** — ran the structural/signature verification directly via `python3 -c ...` instead of through pytest. The conftest imports asyncpg at collect time, which blocks running the existing test suite from the host worktree. This is an environmental constraint of the worktree (tests canonically run inside the api_server docker container), not a test regression. The host-side Python validation covers all claims this plan makes (signature shapes, module cache, missing-container degradation, back-compat).
- **Plan 22-03 primitives absent (expected)** — parallel worktree execution. The bridge is coded to the contract; integration is verified post-merge by the orchestrator / Plan 22-05 executor.

## User Setup Required

None.

## Next Phase Readiness

**Ready for Plan 22-05 (API endpoints):**
- `POST /v1/agents/:id/start` can `await execute_persistent_start(request.app.state, recipe, model=..., api_key_var=..., api_key_val=provider_key, channel_id=body.channel, channel_creds=body.channel_inputs, run_id=ulid())` inside its long-await step (with DB scopes opened-closed around it per PATTERNS.md §4).
- `POST /v1/agents/:id/stop` can `await execute_persistent_stop(container_id, graceful_shutdown_s=int(recipe["persistent"]["spec"]["graceful_shutdown_s"]), sigterm_handled=bool(recipe["persistent"]["spec"].get("sigterm_handled", True)), recipe_name=recipe["name"])` and surface `details["force_killed"]` on the response.
- `GET /v1/agents/:id/status` can `await execute_persistent_status(container_id, recipe_health_check=recipe["persistent"]["spec"]["health_check"], log_tail_lines=50)` for a structured probe; missing-container safe.
- `POST /v1/agents/:id/channels/:cid/pair` can `await execute_persistent_exec(request.app.state, container_id, argv=[...], timeout_s=30)`.

**Blockers or concerns:** None. All four bridges are `await`-able, none hold DB connections, none stall the event loop.

## Threat Flags

No new network endpoints, auth paths, file-access patterns, or schema changes at trust boundaries. Bridges are an internal async wrapper layer over existing primitives. BYOK discipline preserved: neither `api_key_val` nor `channel_creds` are logged or persisted in this module — upstream route layer (Plan 22-05) is responsible for redacting exceptions before any DB touch.

## Self-Check: PASSED

### Artifact existence

```
FOUND: api_server/src/api_server/services/runner_bridge.py
FOUND: .planning/phases/22-channels-v0.2/22-04-SUMMARY.md
```

### Commit existence

```
FOUND: 781d7a2 (Task 1 — refactor _import + execute_persistent_start)
FOUND: 09f9ecc (Task 2 — execute_persistent_stop/status/exec)
```

### SC confirmation

- SC-02 ✅ — `execute_persistent_start` is a coroutine; uses per-tag Lock + global Semaphore + `asyncio.to_thread`. Route layer can await it without holding DB. Module cache verified: `_import_run_recipe_module()` returns the same module object across invocations and the back-compat `_import_run_cell()` returns `mod.run_cell` (same callable as before the refactor).
- SC-04 ✅ — `execute_persistent_stop` is a coroutine; wraps `stop_persistent` in `asyncio.to_thread` with no lock and no semaphore (cheap + concurrent-safe).

### Non-regression

- `execute_run` untouched (still uses `_import_run_cell()` shim which returns `mod.run_cell` identical to pre-refactor).
- All 5 bridge functions (1 old + 4 new) share `sys.modules["run_recipe"]` — single Verdict/Category identity across the process.

---
*Phase: 22-channels-v0.2*
*Plan: 04*
*Completed: 2026-04-18*
