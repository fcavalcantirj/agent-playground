---
phase: 22c-oauth-google
plan: 01
subsystem: testing
tags: [authlib, respx, itsdangerous, httpx, testcontainers, postgres, alembic, oauth, truncate-cascade, spike]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: SPEC + CONTEXT + RESEARCH + PATTERNS + VALIDATION + 9 sealed PLANs
  - phase: 22b-agent-event-stream
    provides: api_server test harness (conftest.py postgres_container + migrated_pg fixtures)
  - phase: 19-api-foundation
    provides: alembic baseline (migrations 001-004), pyproject.toml shape, testcontainers[postgres]>=4.14.2
provides:
  - authlib + itsdangerous + respx installed + importable in the live api_server container
  - tests/spikes/ + tests/auth/ + tests/middleware/ scaffolds for Wave 1+2 plans to drop files in
  - SPIKE-A green evidence — respx 0.23.1 correctly intercepts authlib 1.6.11's httpx 0.28.1 token-exchange (AMD-05 validated)
  - SPIKE-B green evidence — single TRUNCATE CASCADE statement clears the full 7-table FK graph + preserves alembic_version (D-22c-MIG-03 validated as Mode B; Mode A auto-activates after 22c-02 ships migration 005)
  - runnable R8 regression test that survives the session-fixture-scope weakness of the in-plan migration-006 test
affects: [22c-02, 22c-03, 22c-04, 22c-05, 22c-06, 22c-07, 22c-08, 22c-09]

# Tech tracking
tech-stack:
  added:
    - authlib==1.6.11 (StarletteOAuth2App over httpx — OAuth2/OIDC client)
    - itsdangerous==2.2.0 (Starlette SessionMiddleware cookie signing — AMD-07)
    - respx==0.23.1 (httpx-native mock library — AMD-05; pin bumped from RESEARCH's 0.21 via Rule-3 deviation)
  patterns:
    - "Wave 0 spike gate: golden rule 5 enforcement — probe gray-area mechanisms against real infra BEFORE downstream waves enter sealed PLANs"
    - "Spike-evidence markdown artifacts: pytest output captured verbatim, mode flag documented, deviation trail preserved"
    - "Network-attached testcontainers pattern: when running pytest from inside a compose-network container, spawn PG via with_kwargs(network='deploy_default') + build DSN from container's private IP (get_connection_url() returns host-gateway DSN unreachable from inside the network)"
    - "Mode A/B auto-detect: import-time filesystem check for alembic migration presence — spike auto-upgrades scope as downstream waves land"

key-files:
  created:
    - api_server/tests/spikes/__init__.py
    - api_server/tests/spikes/test_respx_authlib.py
    - api_server/tests/spikes/test_truncate_cascade.py
    - api_server/tests/auth/__init__.py
    - api_server/tests/middleware/__init__.py
    - .planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md
    - .planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md
  modified:
    - api_server/pyproject.toml (+11 lines: 2 prod deps + 1 dev dep w/ explanatory comments + respx pin bump)

key-decisions:
  - "respx pin bumped from RESEARCH-specified >=0.21,<0.22 to >=0.22,<0.24 (Rule-3 deviation; respx 0.21.1 is NOT compatible with httpx 0.28.1 which authlib 1.6.11 transitively pulls in — empirically verified)"
  - "SPIKE-B runs in Mode B (7 tables, alembic HEAD=004) for Wave 0; auto-upgrades to Mode A (8 tables, HEAD=005) once plan 22c-02 ships migration 005 — no test edit required"
  - "SPIKE-B uses a dedicated function-scoped PostgresContainer (NOT the session-scoped migrated_pg fixture) so the test can pin a specific revision even after downstream 006 lands HEAD"
  - "Testcontainers inside a compose-network container requires: TESTCONTAINERS_RYUK_DISABLED=true + spawned PG joining the caller's network + DSN built from container IP (Rule-3 test-rig deviation, applied inline to test file)"

patterns-established:
  - "Wave 0 mandatory spike gate: 2 spikes, 2 evidence markdowns, 2 green pytest runs BEFORE any Wave 1+ plan executes (golden rule 5)"
  - "Spike-evidence markdown convention: Run date, Command, Result, Rationale, Version pins, Deviation(s) if any, Pre/post matrix, Test output verbatim, Decision, Execution note"
  - "respx + authlib interop pattern: @respx.mock decorator + respx.post(url).mock(return_value=httpx.Response(...)) stubs authlib's internal httpx calls to Google/GitHub endpoints (AMD-05)"
  - "TRUNCATE CASCADE destructive-migration verification pattern: fresh PG → apply up-to-N → seed each FK-graph table → run the migration's TRUNCATE statement verbatim → assert COUNT=0 + alembic_version preserved"

requirements-completed: [SPIKE-A, SPIKE-B, AMD-05]

# Metrics
duration: 24min
completed: 2026-04-19
---

# Phase 22c-oauth-google Plan 01: Wave 0 Spike Gate Summary

**Both Wave 0 spikes PASS. authlib+respx+httpx interop verified (AMD-05); single TRUNCATE CASCADE clears 7-table FK graph + preserves alembic_version (D-22c-MIG-03 Mode B). Downstream waves (22c-02..22c-09) authorized to execute.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-04-19T23:07:21Z
- **Completed:** 2026-04-19T23:31:11Z
- **Tasks:** 3 (all autonomous, no checkpoints)
- **Files modified:** 8 (7 created + 1 modified)

## Accomplishments

- **SPIKE-A PASS** — respx 0.23.1 correctly intercepts authlib 1.6.11's httpx 0.28.1 token-exchange call. `@respx.mock` + `respx.post('https://oauth2.googleapis.com/token').mock(return_value=httpx.Response(200, json={...}))` matches; `token_route.called == True`; authlib parses the canned payload without any real network egress. AMD-05 strategy (use respx not responses for all OAuth integration tests) is valid.
- **SPIKE-B PASS (Mode B — 7 tables)** — single `TRUNCATE TABLE agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, users CASCADE` statement against alembic HEAD=004 clears all 7 data-bearing tables (pre=1-2 rows, post=0) AND preserves `alembic_version.version_num='004_agent_events'`. R8 regression-covered end-to-end; plan 22c-06 migration 006 can ship as-written. Mode A (8 tables including sessions) auto-activates once plan 22c-02 ships migration 005 — no test edit needed.
- **Test directory scaffolds** — `api_server/tests/spikes/__init__.py`, `api_server/tests/auth/__init__.py`, `api_server/tests/middleware/__init__.py` exist. Wave 1/2 plans can drop test files in without repo-layout scramble.
- **Three new deps wired + verified in live container** — `authlib==1.6.11`, `itsdangerous==2.2.0`, `respx==0.23.1`; all importable in `deploy-api_server-1`; pinned in `api_server/pyproject.toml` with explanatory docstrings.
- **Two evidence markdowns committed** under `.planning/phases/22c-oauth-google/spike-evidence/` — pytest output captured verbatim, pre/post count matrix, mode flag, alembic revision before/after, deviation trail, decision.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add authlib + itsdangerous + respx to pyproject.toml** — `dc43879` (chore)
2. **Task 2: Scaffold test directories + SPIKE-A** — `4f37b58` (test)
3. **Task 3: SPIKE-B — TRUNCATE CASCADE on 7-table FK graph** — `9cf282c` (test)

_Note: Tasks 1+2 both touched `pyproject.toml` (Task 1 added deps, Task 2 bumped the respx pin via Rule-3 deviation discovered mid-Task-2). Both edits live in the same file but are in separate commits — Task 1's commit pre-dates the Rule-3 discovery._

## Files Created/Modified

- `api_server/pyproject.toml` — added `authlib>=1.6.11,<1.7` + `itsdangerous>=2.2.0,<3` to prod deps; added `respx>=0.22,<0.24` to dev deps (bumped from RESEARCH's `>=0.21,<0.22` per Rule-3 deviation; see SPIKE-A evidence for full trace)
- `api_server/tests/spikes/__init__.py` — empty package marker
- `api_server/tests/spikes/test_respx_authlib.py` — SPIKE-A: ~10-line `@respx.mock` test proving authlib+respx interop
- `api_server/tests/spikes/test_truncate_cascade.py` — SPIKE-B: fresh-PG-per-test fixture + 7-table seed + TRUNCATE + COUNT=0 assertion + alembic_version preservation check. Auto-detects 005 presence (Mode A vs Mode B) at import time. Network-attached testcontainer via `SPIKE_DOCKER_NETWORK=deploy_default` (overridable via env)
- `api_server/tests/auth/__init__.py` — empty scaffold for Wave 2/3 plans (22c-04, 22c-05)
- `api_server/tests/middleware/__init__.py` — empty scaffold for Wave 2 plan (22c-04)
- `.planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md` — Spike A run record: PASS verdict, versions, deviation trail, pytest output
- `.planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md` — Spike B run record: PASS verdict, 7-table pre/post matrix, alembic_version preservation proof, pytest output

## Decisions Made

- **respx pin bumped** — `>=0.22,<0.24` instead of the RESEARCH-specified `>=0.21,<0.22`. Empirical: respx 0.21.1 raises `AllMockedAssertionError: RESPX: <Request(...)> not mocked!` against httpx 0.28.1 requests (both via authlib's wrapped AsyncOAuth2Client and via a bare `httpx.AsyncClient`). respx 0.22.0 is the compatibility bump for httpx 0.28; 0.23.1 is current latest — tested, works. Downstream plans should cite `spike-a-respx-authlib.md` if the pin is questioned.
- **SPIKE-B runs Mode B at Wave 0** — alembic migration 005 (`sessions` table) is delivered by plan 22c-02 (Wave 1). At Wave 0, `_MODE_A = (API_SERVER_DIR / "alembic/versions/005_sessions_and_oauth_users.py").exists()` is False, so the spike runs against HEAD=004 with 7 tables. The evidence markdown documents this explicitly; Mode A auto-activates on the next spike run after 22c-02 lands. Plan 22c-06 must re-run this spike post-22c-02 to confirm 8-table Mode A.
- **Dedicated function-scoped PG container in SPIKE-B** — not reusing `conftest.py::migrated_pg` (session-scoped). Rationale: downstream migration 006 will advance session-scoped HEAD to 006, which would invalidate the spike's pin to HEAD=005/004. The spike's own fixture spawns a fresh container per test run — ~3-4s cost is acceptable for a Wave 0 hard gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] respx version pin incompatible with httpx 0.28**
- **Found during:** Task 2 (SPIKE-A first run)
- **Issue:** RESEARCH specified `respx>=0.21,<0.22`. When pinned exactly, `pip install` got respx 0.21.1, which raises `AllMockedAssertionError: RESPX: <Request(b'POST', 'https://oauth2.googleapis.com/token')> not mocked!` even though the route was correctly registered (visible in `router.routes`). Root cause: respx 0.21.1 cannot match httpx 0.28.1 request objects — respx 0.22.0 was the compatibility bump. authlib 1.6.11 transitively requires httpx 0.28, so the respx/httpx mismatch blocks the entire OAuth test strategy if uncorrected.
- **Fix:** Bumped the pin in `pyproject.toml` to `respx>=0.22,<0.24`. Upgraded the in-container install to respx 0.23.1 (current latest). Re-ran SPIKE-A: PASS.
- **Files modified:** `api_server/pyproject.toml`
- **Verification:** `docker exec deploy-api_server-1 pip show respx` → 0.23.1; minimal httpx+respx reproducer PASS; full authlib+respx spike PASS (0.06-0.08s).
- **Committed in:** `4f37b58` (Task 2 commit — the pin bump and the SPIKE-A test file ship together since they're only useful in tandem).

**2. [Rule 3 — Blocking] testcontainers Ryuk reaper unreachable from inside compose network**
- **Found during:** Task 3 (SPIKE-B first run)
- **Issue:** `with PostgresContainer("postgres:17-alpine") as pg:` fails with `ConnectionRefusedError: [Errno 111] Connection refused` when running pytest via `docker exec deploy-api_server-1 ...`. testcontainers spawns a Ryuk auto-cleanup container on the default bridge network, but the api_server container is on `deploy_default` — Ryuk's IP:port pair isn't reachable from the caller.
- **Fix:** Set `TESTCONTAINERS_RYUK_DISABLED=true` in the `docker exec` invocation. Documented knob; the `with ... as pg:` context manager still handles cleanup on unwind (PG container stops at block exit). Acceptable for a spike run.
- **Files modified:** none (env-var-only fix; documented in evidence markdown + Task 3 commit message).
- **Verification:** Re-ran fixture setup; PG container spawns without Ryuk-connection error.
- **Committed in:** `9cf282c` (Task 3 commit — documented in the evidence markdown's "Deviations" section).

**3. [Rule 3 — Blocking] Spawned PG container's `get_connection_url()` returns host-gateway DSN unreachable from inside `deploy_default`**
- **Found during:** Task 3 (SPIKE-B second run, post-Ryuk fix)
- **Issue:** After Ryuk was disabled, the PG container started, but alembic's subprocess exited 1 with `ConnectionRefusedError: [Errno 111] Connect call failed ('172.17.0.1', 54881)`. Root cause: testcontainers returns a DSN pointing at the docker host gateway (172.17.0.1) + an ephemeral port. That's reachable from the host laptop into the default bridge, but NOT from inside the api_server container (which lives on `deploy_default` and has no route to 172.17.0.1's ephemeral port).
- **Fix:** Modified the `fresh_pg_at_target_rev` fixture to (a) attach the spawned PG container to `deploy_default` via `with_kwargs(network=_DOCKER_NETWORK)` and (b) build the DSN from the PG's private IP on `deploy_default` (via `docker inspect → NetworkSettings.Networks.deploy_default.IPAddress`). Added `SPIKE_DOCKER_NETWORK` env override (default `deploy_default`) for CI / different dev setups. Test body uses the stashed `_spike_dsn` attribute instead of `get_connection_url()`.
- **Files modified:** `api_server/tests/spikes/test_truncate_cascade.py` (fixture + one line in test body).
- **Verification:** Re-ran fixture + test: PG reachable from inside api_server; alembic subprocess succeeds; asyncpg connects; TRUNCATE runs; 7 tables COUNT=0 asserted; alembic_version preserved. Green in 3.35s end-to-end.
- **Committed in:** `9cf282c` (Task 3 commit).

---

**Total deviations:** 3 auto-fixed (all Rule 3 — blocking issues in test rig / dep pinning)
**Impact on plan:** All three fixes were necessary to get the spike gate green. None expanded scope beyond Task 1-3 deliverables. The respx pin bump is the most consequential — downstream plans that author real OAuth integration tests (22c-04, 22c-05) can cite the SPIKE-A evidence for the pin floor. The two test-rig deviations are localized to the SPIKE-B fixture file and don't affect how migration 006 itself is designed — they're purely about "how does a pytest process inside one compose-network container talk to a PG testcontainer on the same network."

## Schema invariants discovered during SPIKE-B seed writing

These NOT-NULL + shape rules were read from the alembic 001-004 migration files and hardened into the spike's seed INSERTs. Downstream plans 22c-02 (migration 005) and 22c-06 (migration 006) can rely on these being true:

- `users` — id UUID PK (default `gen_random_uuid()`), `display_name` NOT NULL, email + provider + created_at optional/defaulted. Baseline (001) seeds the anonymous row `00000000-0000-0000-0000-000000000001`.
- `agent_instances` — id UUID PK, user_id UUID FK(users.id), `recipe_name` TEXT NOT NULL, `model` TEXT NOT NULL; **post-002** `name` TEXT NOT NULL added; unique constraint changed from `(user_id, recipe_name, model)` to `(user_id, name)`.
- `agent_containers` (003) — id UUID PK, agent_instance_id FK ON DELETE CASCADE, user_id FK, recipe_name NOT NULL; `deploy_mode` + `container_status` have server_defaults ('persistent' / 'starting') so they can be omitted on INSERT; `channel_type`, `channel_config_enc`, `container_id` all nullable. CHECK constraint `deploy_mode IN ('one_shot','persistent')`; CHECK `container_status IN ('starting','running','stopping','stopped','start_failed','crashed')`. Partial unique index `ix_agent_containers_agent_instance_running` on `agent_instance_id` WHERE `container_status='running'` — a seed row with default 'starting' status does NOT conflict.
- `runs` (001) — id **TEXT** (26-char ULID), agent_instance_id UUID FK, prompt TEXT NOT NULL. Verdict + category + detail + timings all nullable.
- `agent_events` (004) — id **BIGSERIAL** auto, agent_container_id UUID FK ON DELETE CASCADE, `seq` BIGINT NOT NULL, `kind` CHECK IN ('reply_sent','reply_failed','agent_ready','agent_error'), `payload` JSONB default '{}', `ts` DEFAULT NOW().
- `idempotency_keys` (001) — id UUID auto, user_id FK, `key` NOT NULL, `run_id` TEXT FK(runs.id) NOT NULL, `verdict_json` JSONB NOT NULL, `request_body_hash` TEXT NOT NULL, `expires_at` TIMESTAMPTZ NOT NULL. Unique `(user_id, key)`.
- `rate_limit_counters` (001) — composite PK `(subject TEXT, bucket TEXT, window_start TIMESTAMPTZ)`; `count` INT default 0.

## Issues Encountered

- **Host-venv install for spike execution hung** — first tried creating a host-side venv (`/tmp/ap-spike-venv`) via `python3 -m venv + pip install -e .[dev]` so the tests could run from the host Python. Pip dependency resolution spun at 99% CPU for >10 minutes without completing. Pivoted to `docker exec deploy-api_server-1 pip install ...` for the 3 new deps directly, then `docker cp` the spike test files into `/app/api_server/tests/spikes/` + `docker exec ... pytest ...`. This bypasses the host-venv resolve entirely — the container already has 40+ deps resolved from its image build. Documented in both evidence markdowns under "Execution note."

## User Setup Required

None — no external service configuration required for Wave 0. All OAuth provider credentials (Google + GitHub client_id/client_secret) are consumed by downstream waves (22c-03 onwards); Wave 0 is pure infra + spike-gate work against local Docker + ephemeral testcontainers.

## Next Phase Readiness

- **Wave 0 gate CLEARED.** Both spikes return PASS; evidence markdowns committed under `.planning/phases/22c-oauth-google/spike-evidence/`.
- **Wave 1 (22c-02 + 22c-03) authorized to execute in parallel.** No blockers remaining.
- **Plan 22c-06 design note:** single `TRUNCATE ... CASCADE` statement confirmed safe. R8 regression is carried by SPIKE-B + in-plan artifact check (the session-scoped migration-006 test weakens to artifact-existence when HEAD is already 006 — that's acceptable because SPIKE-B carries the runnable regression).
- **Plan 22c-05 design note:** OAuth integration tests MUST use `@respx.mock` (or `async with respx.mock():` context manager). `respx.post('oauth2.googleapis.com/token').mock(return_value=httpx.Response(200, json={...}))` is the verified stub pattern. pytest-respx plugin (pulled in transitively with respx==0.23.1) is also wired.
- **Image rebuild deferred:** the running `deploy-api_server-1` has the 3 new deps installed in-flight via `pip install`, but the baked image at `tools/Dockerfile.api` still has the old pyproject. Downstream waves that rely on the new deps being present after a container rebuild (e.g. a CI pipeline or a prod deploy) MUST rebuild the image. The plan 22c-05 integration tests are the natural forcing function.

## Self-Check: PASSED

All 8 required files exist at the expected paths; all 3 task commits (`dc43879`, `4f37b58`, `9cf282c`) are present in the git log. Both spike tests pass when re-run from scratch (`docker exec -e TESTCONTAINERS_RYUK_DISABLED=true -e SPIKE_DOCKER_NETWORK=deploy_default deploy-api_server-1 sh -c "cd /app/api_server && python -m pytest tests/spikes/ -v -m api_integration && python -m pytest tests/spikes/test_respx_authlib.py -v"` → `1 passed ... 1 passed`).

---
*Phase: 22c-oauth-google*
*Completed: 2026-04-19*
