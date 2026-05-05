---
phase: 28-temporal-dispatch
plan: 02
subsystem: infra
tags: [temporal, docker-compose, pydantic-settings, sdk-pin, wave-1]

# Dependency graph
requires:
  - phase: 28
    provides: WAVE-0-CLOSED (Wave 0 spike findings absorbed: docker.yaml dynamic config + macOS user:root override)
provides:
  - temporalio==1.27.0 SDK pinned in api_server/pyproject.toml + tools/Dockerfile.api (image bake confirmed)
  - 4 new Pydantic Settings fields (temporal_host, temporal_namespace, temporal_task_queue, bot_timeout_seconds) with AP_TEMPORAL_* + AP_BOT_TIMEOUT_SECONDS env aliases and defaults
  - 3 new compose services (temporal, temporal-ui, temporal-worker) on deploy_default network with healthchecks + correct depends_on graph
  - api_server depends_on extended with temporal: service_healthy gate
  - deploy/docker-compose.local.yml temporal port-publish override + temporal-worker user: root (macOS Docker socket workaround)
  - deploy/.env.prod.example Phase 28 stanza
  - deploy/README.md Phase 28 macOS-worker-in-compose constraint section (RESEARCH §7 R6)
affects: [28-03, 28-04, 28-05, 28-06, 28-07, 28-08, 28-09]

# Tech tracking
tech-stack:
  added:
    - "temporalio==1.27.0 (Python SDK runtime dep, floor 1.27.0 ceiling <1.28)"
    - "temporalio/auto-setup:1.29.2 (Temporal cluster image — frontend + history + matching + worker shards)"
    - "temporalio/ui:2.40.0 (Temporal Web UI image, loopback-only on 127.0.0.1:8088)"
  patterns:
    - "Per-service env file split: api_server-style env_file: .env.prod is reused on temporal-worker so DB pool + Redis + crypto master key reach the worker the same way they reach api_server"
    - "Wave-0 finding absorption: spike-evidence corrections applied verbatim to compose recipe + local override (DYNAMIC_CONFIG_FILE_PATH=docker.yaml; user: root only in local)"
    - "Local-override port-bind discipline: ports stay loopback-only and prod compose carries no public port for temporal — host port lives in docker-compose.local.yml (mirrors redis pattern from Phase 22c.3)"

key-files:
  created:
    - ".planning/phases/28-temporal-dispatch/28-02-SUMMARY.md"
  modified:
    - "api_server/pyproject.toml (add temporalio>=1.27.0,<1.28 to runtime deps)"
    - "tools/Dockerfile.api (append temporalio>=1.27.0,<1.28 to pip install chain)"
    - "api_server/src/api_server/config.py (4 new Settings fields after docker_network_name)"
    - "deploy/docker-compose.prod.yml (temporal + temporal-ui + temporal-worker services; api_server depends_on extension)"
    - "deploy/docker-compose.local.yml (temporal port-publish 7233; temporal-worker user: root)"
    - "deploy/.env.prod.example (Phase 28 stanza with 4 vars)"
    - "deploy/README.md (Phase 28 macOS-worker-in-compose section)"

key-decisions:
  - "DYNAMIC_CONFIG_FILE_PATH points at config/dynamicconfig/docker.yaml (not development-sql.yaml) — Wave 0 spike A finding A absorbed"
  - "user: root override applied to temporal-worker only in docker-compose.local.yml (NOT in prod.yml) — Wave 0 spike C finding absorbed; Hetzner socket is root:docker(999) so the apiuser group membership works natively in prod"
  - "Local-only host-port for temporal lives in docker-compose.local.yml (127.0.0.1:7233) so prod compose stays loopback-internal"
  - "temporal-worker explicitly does NOT get a host-network override — RESEARCH §7 R6 (macOS bridge limitation) requires the worker to stay inside compose; local override file documents this with a comment block"
  - "Floor/ceiling pin discipline mirrors respx + redis: temporalio>=1.27.0,<1.28"
  - "uv.lock is left untracked — pre-existing state at session start; out-of-scope for this plan"

requirements-completed: [D-01, D-02, D-03, D-04, D-05]

# Metrics
duration: 6min
completed: 2026-05-05
---

# Phase 28 Plan 02: Temporal compose stack + SDK pin Summary

**3-service Temporal cluster (auto-setup 1.29.2 + UI 2.40.0 + worker shell) wired into deploy_default; temporalio==1.27.0 SDK pinned in pyproject + Dockerfile.api; 4 Settings fields exposed; cluster reaches healthy in ~10s and UI responds 200 HTML on 127.0.0.1:8088 — Wave 2 unblocked.**

## Performance

- **Duration:** ~6 minutes (PLAN_START 20:37:34Z, PLAN_END 20:43:38Z)
- **Tasks:** 2 (both auto, fully autonomous per plan frontmatter)
- **Files modified:** 7
- **Files created:** 1 (this SUMMARY)
- **temporal cluster wall time to healthy on macOS Docker Desktop:** 10 seconds (against the existing deploy-postgres-1; auto-setup created `temporal` + `temporal_visibility` DBs in <2s)
- **temporal-ui first 200 HTML response:** within 4 seconds of `up -d` (matches RESEARCH §2 expectation)

## Accomplishments

- **Task 1: SDK pin + Settings fields.**
  - `api_server/pyproject.toml` carries `temporalio>=1.27.0,<1.28` in the runtime deps array; floor matches Wave 0 spike evidence (which proved 1.27.0 + auto-setup 1.29.2 are wire-compatible).
  - `tools/Dockerfile.api` appends the same pin to the explicit pip install list — the worker image bakes the SDK at build time. Verified: `docker run --rm ap-test-build python -c "import temporalio; print(temporalio.__version__)"` → `1.27.0`.
  - `api_server/src/api_server/config.py` adds 4 new Pydantic Settings fields after `docker_network_name`: `temporal_host` (default `temporal:7233`, alias `AP_TEMPORAL_HOST`), `temporal_namespace` (default `default`, alias `AP_TEMPORAL_NAMESPACE`), `temporal_task_queue` (default `ap-messages`, alias `AP_TEMPORAL_TASK_QUEUE`), `bot_timeout_seconds` (default `60.0`, alias `AP_BOT_TIMEOUT_SECONDS`). Defaults verified by direct Settings instantiation; env-alias override verified with `AP_TEMPORAL_HOST=custom:1234` → field reads `custom:1234`.
  - `uv sync` clean run (1 added: `temporalio==1.27.0` plus 6 transitive deps incl. `protobuf==6.33.6`, `types-protobuf`, `python-dotenv`).

- **Task 2: Compose services + docs.**
  - `deploy/docker-compose.prod.yml` now carries `temporal:` (auto-setup 1.29.2, healthcheck via `temporal operator cluster health`, depends_on postgres healthy, NO host port), `temporal-ui:` (2.40.0, depends_on temporal healthy, 127.0.0.1:8088:8080 only), and `temporal-worker:` (built from tools/Dockerfile.api, command `python -m api_server.temporal.worker`, env_file .env.prod, depends_on postgres+redis+temporal healthy, mounts /var/run/docker.sock + recipes RO).
  - `api_server` service `depends_on` extended with `temporal: service_healthy` so the lifespan client.connect cannot race against an unhealthy frontend (Wave 2 will exercise this).
  - `deploy/docker-compose.local.yml` adds `temporal: ports: - "127.0.0.1:7233:7233"` for host-venv test/script access AND `temporal-worker: user: root` (macOS Docker Desktop socket fix). NO override for temporal-worker network — RESEARCH §7 R6 requires it stay inside compose.
  - `deploy/.env.prod.example` Phase 28 stanza added with `AP_TEMPORAL_HOST`, `AP_TEMPORAL_NAMESPACE`, `AP_TEMPORAL_TASK_QUEUE`, `AP_BOT_TIMEOUT_SECONDS` (all with default-matching values + comments).
  - `deploy/README.md` Phase 28 section explains the macOS-worker-in-compose constraint, points at `make dev-api-local` as the canonical path, and warns against host-venv worker invocation.
  - **Empirical boot validation:** Reused the existing live `deploy-postgres-1` (created `temporal` + `temporal_visibility` DBs in it on first boot — auto-setup is idempotent) and brought up `temporal` + `temporal-ui` against it. `docker compose ps` showed `deploy-temporal-1  Up 10 seconds (healthy)` and `deploy-temporal-ui-1  Up 4 seconds`. `curl -fsS http://127.0.0.1:8088 | head -3` returned the SPA shell HTML. Tear-down via `compose stop` + `compose rm -f` clean.

## Task Commits

1. **Task 1: Pin temporalio SDK + add Settings fields** — `3322ec0` (feat)
2. **Task 2: Add temporal + temporal-ui + temporal-worker compose services + README stanza** — `5dbd367` (feat)

## Files Created/Modified

- `api_server/pyproject.toml` — `temporalio>=1.27.0,<1.28` added to runtime deps with comment pointing at Wave 0 spike evidence
- `tools/Dockerfile.api` — same pin appended to the explicit `pip install --prefix=/install` chain so the worker image carries the SDK at build time
- `api_server/src/api_server/config.py` — 4 new Settings fields (Field with validation_alias + description) for Temporal client/worker config
- `deploy/docker-compose.prod.yml` — 3 new service blocks (temporal/temporal-ui/temporal-worker) inserted between `redis:` and `api_server:`; api_server `depends_on` extended with `temporal: service_healthy`
- `deploy/docker-compose.local.yml` — `temporal:` host-port override (127.0.0.1:7233) and `temporal-worker: user: root` macOS workaround; explicit no-override-for-network-on-worker comment
- `deploy/.env.prod.example` — Phase 28 stanza appended after the AP_FRONTEND_BASE_URL entry, listing all 4 new env vars with comments
- `deploy/README.md` — Phase 28 macOS section inserted before "Troubleshooting", citing memory/feedback_check_msv_when_stuck.md and the dockerized e2e harness pattern
- `.planning/phases/28-temporal-dispatch/28-02-SUMMARY.md` — this file

## Decisions Made

- **`docker.yaml` over `development-sql.yaml`** — absorbed verbatim from Wave 0 spike A finding. The `temporalio/auto-setup:1.29.2` image only ships `config/dynamicconfig/docker.yaml`; pointing at `development-sql.yaml` (the path quoted in upstream `temporalio/docker-compose` for older tags) crashes the server during boot. The compose file now carries an inline comment documenting the upstream-doc drift so a future maintainer doesn't re-introduce the bug.
- **`user: root` only in local** — absorbed verbatim from Wave 0 spike C finding. macOS Docker Desktop bind-mounts /var/run/docker.sock as `root:root mode 660`; `apiuser` (UID 1001, group `docker` GID 999) gets `Permission denied` calling `docker.from_env()` from inside the container. On Hetzner the socket is `root:docker(999)` and the apiuser+group setup works natively, so `prod.yml` carries NO override.
- **Worker image = api_server image, separate command** — reuses `tools/Dockerfile.api` so the worker carries the same pin graph + runtime deps + entrypoints (DOCKER_BUILDKIT, AP_RECIPES_DIR, etc.) as the API. Only `command` changes. Matches D-04 — independent process, shared image.
- **No `prod.yml` host port for temporal** — D-03 says 7233 is internal-only. Local-only override gives host-venv tests a path; prod stays loopback-internal.
- **Floor pin matches the Wave 0 spike evidence** (`1.27.0`) — the spike proved the version-handshake path works against `auto-setup:1.29.2`, so we lock the floor at the proven version. Ceiling at `<1.28` matches the project's same-major upper-bound discipline.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] PLAN body specified the WRONG dynamic config path; Wave 0 finding overrides**
- **Found during:** Pre-task review (read of 28-01-SPIKE-EVIDENCE.md before starting Task 2)
- **Issue:** The PLAN body's compose YAML block specified `DYNAMIC_CONFIG_FILE_PATH: config/dynamicconfig/development-sql.yaml`, but the Wave 0 spike evidence (`28-01-SPIKE-EVIDENCE.md` and `28-01-SUMMARY.md`) and the orchestrator's `<wave_0_findings>` prompt section both explicitly require `docker.yaml`. The `development-sql.yaml` path crashes the Temporal server during boot on `temporalio/auto-setup:1.29.2`.
- **Fix:** Used `docker.yaml` per Wave 0 evidence + orchestrator prompt; added an explanatory comment block to the compose file pointing at the spike-evidence file.
- **Files modified:** `deploy/docker-compose.prod.yml`
- **Verification:** Boot test brought `deploy-temporal-1` to `healthy` in 10 seconds with no boot crash.
- **Forward signal:** None — Wave 0 finding now permanently absorbed in the compose recipe.

### Other deviations

**None beyond the documented Wave-0 absorption.** Both tasks executed exactly as specified once the dynamic-config-path override was applied.

**Pre-existing untracked file noted (NOT modified):** `api_server/uv.lock` was already untracked at session start (`git status` from session start banner) and remains untracked — out of scope for this plan. `uv sync` rewrote the lock during Task 1 but committing it would be a separate cross-cutting decision (uv.lock has never been in git history per `git log --all -- api_server/uv.lock`).

## Issues Encountered

- **None.** Wave 0 corrections absorbed cleanly; compose validation, container boot, and SDK import all passed first-try (after applying the spike-evidence corrections to the literal PLAN body text). The boot test relied on the existing live `deploy-postgres-1` which already carried the `agent_playground_api` DB; auto-setup additively created `temporal` + `temporal_visibility` DBs in the same Postgres instance per D-02.

## User Setup Required

- **None for this plan.** Wave 1 ships infrastructure plumbing only; the worker container is in restart-loop until Plan 28-04 lands `python -m api_server.temporal.worker`. Operators on macOS who later run `make dev-api-local` will get the full stack including temporal cluster + UI + worker shell automatically (the Makefile's existing `DEPLOY_COMPOSE` already layers prod.yml + local.yml).

## Next Phase Readiness

- **Wave 2 (Plans 28-03 + 28-04) unblocked:**
  - `temporalio` SDK is import-safe inside the api_server / worker image (verified by `docker run ... python -c "import temporalio"`).
  - `Settings.temporal_host`/`temporal_namespace`/`temporal_task_queue` fields are read-ready for `client.connect(...)` and `Worker(client, task_queue=..., ...)` invocations.
  - The `temporal-worker` service block exists with the correct `command: ["python", "-m", "api_server.temporal.worker"]` invocation; Plan 28-04 just needs to land that module for the worker to leave restart-loop and start consuming the `ap-messages` task queue.
  - Compose stack reaches `temporal: healthy` reliably in ~10s, well under the workflow execution timeout window.
- **Cross-wave invariants preserved:**
  - No public Postgres port (temporal connects via compose-internal `postgres` DNS).
  - No public Temporal port in prod (loopback-only via local override).
  - api_server depends_on graph guarantees `client.connect("temporal:7233", ...)` cannot race against a still-booting cluster.
- **macOS local-dev path documented:** `deploy/README.md` Phase 28 section + `docker-compose.local.yml` comments tell future contributors WHY they cannot run `python -m api_server.temporal.worker` from a host venv — the lesson is captured at the surface they'd hit.

## Self-Check: PASSED

- `api_server/pyproject.toml` carries `temporalio>=1.27.0,<1.28` — FOUND (`grep -c` returns 1)
- `tools/Dockerfile.api` carries `temporalio` — FOUND (`grep -c` returns 1)
- `api_server/src/api_server/config.py` exposes `temporal_host`/`temporal_namespace`/`temporal_task_queue`/`bot_timeout_seconds` — FOUND (Settings instantiation prints `temporal:7233 default ap-messages 60.0`)
- `deploy/docker-compose.prod.yml` carries `image: temporalio/auto-setup:1.29.2` — FOUND (1)
- `deploy/docker-compose.prod.yml` carries `image: temporalio/ui:2.40.0` — FOUND (1)
- `deploy/docker-compose.prod.yml` carries `command: ["python", "-m", "api_server.temporal.worker"]` — FOUND (1)
- `deploy/docker-compose.prod.yml` `temporal:` block has NO `ports:` directive — VERIFIED (grep -A3 "^  temporal:$" returns 0 matches for `ports:`)
- `deploy/.env.prod.example` carries `AP_TEMPORAL_HOST` — FOUND (1)
- `deploy/README.md` carries `temporal-worker` and `make dev-api-local` references — FOUND (3 each)
- `docker compose -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml config` exits 0 with --env-file present — VERIFIED
- `temporal` container reached `Up (healthy)` within 90s deadline — VERIFIED (10s actual)
- `curl -fsS http://127.0.0.1:8088 | head -1` returned HTML — VERIFIED (`<!doctype html>`)
- Commit `3322ec0` (Task 1) — FOUND in git log
- Commit `5dbd367` (Task 2) — FOUND in git log

---
*Phase: 28-temporal-dispatch*
*Completed: 2026-05-05*
