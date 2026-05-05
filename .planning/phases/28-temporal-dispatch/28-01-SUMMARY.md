---
phase: 28-temporal-dispatch
plan: 01
subsystem: testing
tags: [temporal, docker-compose, postgres, sandbox, bridge-network, spike, wave-0]

# Dependency graph
requires:
  - phase: 22c.3
    provides: docker bridge-network IP-routing pattern for in-app dispatcher (the gotcha CLAUDE.md banner documents)
provides:
  - Empirical PASS evidence that temporalio/auto-setup:1.29.2 boots cleanly against postgres:17-alpine
  - Empirical PASS evidence that workflow.unsafe.imports_passed_through() shields heavy infra imports (asyncpg/httpx/docker) from the Python sandbox
  - Empirical PASS evidence that a worker-style container can reach an agent-style container's bridge IP via httpx through the compose default network
  - Three reusable spike test files registered under the new pytest "spike" marker (opt-in via `-m spike`)
  - WAVE-0-CLOSED gating signal in 28-01-SPIKE-EVIDENCE.md unblocking Wave 1+
  - Two Wave-0 corrections that Wave-1 plan 28-02 must absorb (DYNAMIC_CONFIG_FILE_PATH path; user:root override on macOS)
affects: [28-02, 28-03, 28-04, 28-05, 28-06, 28-07, 28-08, 28-09]

# Tech tracking
tech-stack:
  added: [temporalio==1.27.0, temporalio/auto-setup:1.29.2 (image only — not yet wired into deploy), temporalio/ui:2.40.0 (image only)]
  patterns:
    - "Spike-as-pytest: marker-gated tests under tests/spikes/ run real Docker / real Temporal SDK; standard pytest invocation excludes them via -m"
    - "Wave-0 evidence ledger pattern: a single markdown file with verbatim spike output + WAVE-0-CLOSED marker is the cross-wave gating signal"
    - "Surgical warning capture: warnings.catch_warnings(record=True) + provenance filter is more precise than -W error::Warning when a single test cares about warnings from one specific module"

key-files:
  created:
    - "api_server/tests/spikes/test_phase28_spike_a_temporal_boot.py"
    - "api_server/tests/spikes/test_phase28_spike_b_workflow_sandbox.py"
    - "api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py"
    - "api_server/tests/spikes/_phase28_b_activities.py"
    - "api_server/tests/spikes/_phase28_b_workflow.py"
    - ".planning/phases/28-temporal-dispatch/28-01-SPIKE-EVIDENCE.md"
  modified:
    - "api_server/pyproject.toml (registered `spike` pytest marker)"

key-decisions:
  - "DYNAMIC_CONFIG_FILE_PATH must be config/dynamicconfig/docker.yaml — not development-sql.yaml — for temporalio/auto-setup:1.29.2 (Wave-0 finding A)"
  - "On macOS, the temporal-worker service must run with user: root in docker-compose.local.yml to access the bind-mounted /var/run/docker.sock; this mirrors the existing api_server local override (Wave-0 finding C)"
  - "Sandbox warnings are detected via warnings.catch_warnings(record=True) with a provenance filter, not via pytest -W error::Warning (the latter caught an unrelated testcontainers DeprecationWarning during conftest import)"
  - "All spike tear-downs run via try/finally with docker compose down -v --remove-orphans; verified by post-test docker ps probe"

patterns-established:
  - "Spike marker registration: `spike` marker in api_server/pyproject.toml [tool.pytest.ini_options] markers list — opt-in via `pytest -m spike`"
  - "Wave-0 gate file shape: each section labeled PASS/FAIL with verbatim command output, ending with `WAVE-0-CLOSED <date> <committer>` marker"
  - "Probe-via-compose pattern for cross-container reachability tests: a tiny target service (nginx:alpine) + a probe service built from the same image the production code uses, both attached to the compose default network"

requirements-completed: [D-01, D-02, D-03, D-04, D-09, D-11, D-25]

# Metrics
duration: 11min
completed: 2026-05-05
---

# Phase 28 Plan 01: Wave-0 Empirical Spike Gate Summary

**Three pytest spikes (A: Temporal-vs-PG17 boot; B: workflow sandbox passthrough; C: worker → bridge-IP routing) all PASS against real infra; WAVE-0-CLOSED marker committed at 7ae2cea; two compose-recipe corrections captured for Wave 1.**

## Performance

- **Duration:** ~11 minutes
- **Started:** 2026-05-05T20:22:52Z
- **Completed:** 2026-05-05T20:33:40Z
- **Tasks:** 4 (3 auto + 1 checkpoint, the latter auto-approved under auto mode)
- **Files modified:** 1 (pyproject.toml — added `spike` marker)
- **Files created:** 6 (3 spike tests + 2 helper modules + 1 evidence ledger)
- **Combined Wave-0 wall time on real infra:** 23.24s (single pytest -m spike invocation)

## Accomplishments

- **Spike A — Temporal cluster boot vs PG17:** `temporalio/auto-setup:1.29.2` reaches `Health: healthy` in **6.5s wall time** against `postgres:17-alpine` (well under the planned 90s deadline). Python SDK `Client.connect("localhost:7233", namespace="default")` succeeds; `list_workflows("")` iterator works; tear-down clean.
- **Spike B — Workflow sandbox passthrough:** `workflow.unsafe.imports_passed_through()` does NOT trip the Python SDK sandbox at workflow registration or execution time, even when the activity module imports `asyncpg`, `httpx`, and `docker` (the libraries `forward_to_agent` will pull). 0 sandbox-class warnings captured. Workflow result `'echo:hello'` returned via `WorkflowEnvironment.start_time_skipping()`.
- **Spike C — Worker → agent bridge IP:** `worker-probe` container (built FROM `deploy-api_server:latest`, mounting `/var/run/docker.sock`) resolves an nginx target's compose-network IP (`172.20.0.2`, RFC1918) and `httpx.get` returns 200. Confirms RESEARCH §10 A6 — the macOS bridge-IP routing constraint applies symmetrically to the worker so long as the worker runs INSIDE the compose stack (matches `make e2e-inapp-docker` semantics).
- **Two Wave-0 corrections delivered to Wave 1:** the compose recipe in 28-02 must (a) point `DYNAMIC_CONFIG_FILE_PATH` at `docker.yaml` and (b) add `user: root` to `temporal-worker` in `docker-compose.local.yml` (NOT in `prod.yml`).

## Task Commits

Each task was committed atomically (worktree mode, `--no-verify` to avoid pre-commit hook contention with sibling executors):

1. **Task 1: Spike A — Temporal cluster boot against deploy postgres:17-alpine** — `a13248a` (test)
2. **Task 2: Spike B — Workflow sandbox passthrough verification** — `b660f2e` (test)
3. **Task 3: Spike C — Worker bridge-IP reachability + evidence ledger** — `7ae2cea` (test)
4. **Task 4: Wave-0 closure gate** — auto-approved under `--auto` (no separate commit; the gate is the WAVE-0-CLOSED marker already in `7ae2cea`)

## Files Created/Modified

- `api_server/pyproject.toml` — added `spike` marker registration so `pytest -m spike` opts into Phase-28 Wave-0 spikes (and only those)
- `api_server/tests/spikes/test_phase28_spike_a_temporal_boot.py` — Spike A: spawns ephemeral compose project (postgres:17-alpine + temporalio/auto-setup:1.29.2), polls healthcheck, connects via SDK, tears down via try/finally
- `api_server/tests/spikes/test_phase28_spike_b_workflow_sandbox.py` — Spike B: registers SpikeBWorkflow against in-process WorkflowEnvironment, executes once, asserts no sandbox-class warnings via warnings.catch_warnings(record=True)
- `api_server/tests/spikes/_phase28_b_workflow.py` — Spike B helper: workflow file using `workflow.unsafe.imports_passed_through()` to bring in the activity module
- `api_server/tests/spikes/_phase28_b_activities.py` — Spike B helper: activity module that imports asyncpg, httpx, docker (deliberately the heavy libs forward_to_agent will pull)
- `api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py` — Spike C: spawns nginx + worker-probe (image: deploy-api_server:latest, user: root, mounts docker.sock), worker-probe uses docker-py to resolve nginx IP and httpx.get against it
- `.planning/phases/28-temporal-dispatch/28-01-SPIKE-EVIDENCE.md` — Wave-0 evidence ledger with verbatim PASS output for all 3 spikes, two Wave-0 findings, and the literal `WAVE-0-CLOSED 2026-05-05 felipe.cavalcanti.rj@gmail.com` marker that gates Waves 1+

## Decisions Made

- **`docker.yaml` over `development-sql.yaml`** for the dynamic config path — Spike A's first run crashed Temporal during boot (`unable to validate dynamic config: stat ...: no such file`); inspection of the 1.29.2 image showed only `config/dynamicconfig/docker.yaml` (empty) ships at runtime. Recorded in the evidence ledger so Wave 1's compose recipe absorbs the fix without re-discovering it.
- **`user: root` on `worker-probe` in Spike C** — matches the documented `deploy/docker-compose.local.yml` lines 12-15 workaround for `api_server`. Confirms the same fix applies to `temporal-worker` on macOS Docker Desktop (Hetzner doesn't need it because the host daemon owns the socket as `root:docker(999)` and the apiuser group membership works natively there).
- **Surgical warning capture** instead of `pytest -W error::Warning` — Spike B's first attempt with the CLI flag caught an unrelated `testcontainers.redis` DeprecationWarning during conftest import. The narrowed `warnings.catch_warnings(record=True)` + provenance filter is more precise (only `temporalio.worker.workflow_sandbox`-class warnings fail the test) and immune to third-party noise.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Wrong dynamic config filename in compose recipe**
- **Found during:** Task 1 (Spike A first run)
- **Issue:** The compose template hardcoded `DYNAMIC_CONFIG_FILE_PATH: config/dynamicconfig/development-sql.yaml`, copied verbatim from RESEARCH §2 (which inherited it from the upstream `temporalio/docker-compose` example for older tags). `temporalio/auto-setup:1.29.2` only ships `docker.yaml` (empty) at that path; pointing at `development-sql.yaml` crashed the Temporal server during boot with `unable to validate dynamic config: stat ...: no such file or directory`.
- **Fix:** Updated the spike's compose template to `DYNAMIC_CONFIG_FILE_PATH: config/dynamicconfig/docker.yaml` and embedded a docstring comment explaining the upstream-doc drift.
- **Files modified:** `api_server/tests/spikes/test_phase28_spike_a_temporal_boot.py`
- **Verification:** Spike A re-run reached `Health: healthy` in 6.5s and the SDK probe succeeded.
- **Committed in:** `a13248a` (Task 1 commit)
- **Forward signal:** This finding MUST be absorbed into Wave 1's `deploy/docker-compose.prod.yml` recipe — same one-line fix.

**2. [Rule 3 — Blocking] Pre-existing DeprecationWarning blocks `-W error::Warning`**
- **Found during:** Task 2 (Spike B first run)
- **Issue:** The PLAN's automated verify line used `pytest ... -W error::Warning`. On the first run that flag failed during `tests/conftest.py` import because `testcontainers.redis` emits an unrelated `DeprecationWarning` about the `@wait_container_is_ready` decorator. The spike never reached its actual subject under test.
- **Fix:** Rewrote the spike body to use `warnings.catch_warnings(record=True) + warnings.simplefilter("always")` and post-filter for sandbox provenance (substring matches against `temporalio.worker.workflow_sandbox`, `RAISE_ON_UNINTENTIONAL_PASSTHROUGH`, `imports_passed_through`, `RestrictedWorkflowAccess`). Documented the change in the file's module docstring + the evidence ledger.
- **Files modified:** `api_server/tests/spikes/test_phase28_spike_b_workflow_sandbox.py`
- **Verification:** Spike B passes; the assertion message reports `captured 0 total warnings, 0 from sandbox; non-sandbox warnings ignored`.
- **Committed in:** `b660f2e` (Task 2 commit)
- **Forward signal:** Wave 2's real workflow-test files should adopt the same surgical-warning pattern, not the `-W error::Warning` flag.

**3. [Rule 3 — Blocking] `apiuser` cannot access bind-mounted Docker socket on macOS**
- **Found during:** Task 3 (Spike C first run)
- **Issue:** `deploy-api_server:latest` runs as `apiuser` (UID 1001, group `docker` GID 999). On macOS Docker Desktop, `/var/run/docker.sock` is bind-mounted as `root:root mode 660`; `apiuser` gets `Permission denied` calling `docker.from_env()`. The probe never reached its actual subject test (the bridge-IP HTTP GET).
- **Fix:** Added `user: root` to the `worker-probe` service in the spike's compose file, with a comment pointing at `deploy/docker-compose.local.yml` lines 12-15 (the existing same-shape workaround for `api_server`).
- **Files modified:** `api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py`
- **Verification:** Spike C passes — bridge IP `172.20.0.2` resolves, `httpx.get(.../healthz)` answers 404 (nginx default has no /healthz), `httpx.get(.../)` answers 200.
- **Committed in:** `7ae2cea` (Task 3 commit)
- **Forward signal:** Wave 1's `deploy/docker-compose.local.yml` MUST add `user: root` to the new `temporal-worker` service. NOT in `prod.yml` — the Hetzner host owns the socket as `root:docker(999)` so the apiuser+group setup there works natively.

---

**Total deviations:** 3 auto-fixed (3 blocking issues, 0 missing critical, 0 bugs)
**Impact on plan:** Each fix turned a blocked spike into a green one without changing the spike's intent. All three findings are surfaced explicitly to Wave 1 (compose recipe correction, surgical-warning pattern adoption, macOS user-override) so the cost of discovery is paid once. No scope creep.

## Issues Encountered

- **None beyond the three documented deviations above.** All issues surfaced were direct consequences of probing real infra (which is exactly Wave-0's job per Golden Rule #5: "every non-trivial mechanism must be spiked against real infra and the spike result captured as evidence BEFORE the planner consumes it"). The spikes did their job.

## User Setup Required

None — the spikes are infrastructure tests; no end-user configuration is required. The `temporalio/auto-setup:1.29.2`, `temporalio/ui:2.40.0`, and `nginx:alpine` images were pulled on demand by Docker Compose. The `deploy-api_server:latest` image was already built from prior phases.

## Next Phase Readiness

- **Wave 1 unblocked:** `WAVE-0-CLOSED` marker committed in `7ae2cea`. Plan 28-02 (compose recipe + SDK pin) can land. **Two corrections it MUST absorb verbatim:**
  1. `DYNAMIC_CONFIG_FILE_PATH: config/dynamicconfig/docker.yaml` (not `development-sql.yaml`)
  2. `user: root` for `temporal-worker` in `docker-compose.local.yml` (NOT in `prod.yml`)
- **Wave 2 unblocked:** Spike B confirms the planned workflow-file shape (`workflow.unsafe.imports_passed_through()` around the activity-module import) is sandbox-safe. Plan 28-03 (workflows + activities) can land.
- **Wave 3+ readiness:** Spike C confirms the macOS routing constraint applies symmetrically to the worker; Plan 28-05's E2E story can rely on `make e2e-inapp-docker`-shape semantics for the worker → agent path.

## Self-Check: PASSED

- `api_server/tests/spikes/test_phase28_spike_a_temporal_boot.py` — FOUND
- `api_server/tests/spikes/test_phase28_spike_b_workflow_sandbox.py` — FOUND
- `api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py` — FOUND
- `api_server/tests/spikes/_phase28_b_activities.py` — FOUND
- `api_server/tests/spikes/_phase28_b_workflow.py` — FOUND
- `.planning/phases/28-temporal-dispatch/28-01-SPIKE-EVIDENCE.md` — FOUND (contains `WAVE-0-CLOSED`)
- Commit `a13248a` (Task 1 — Spike A) — FOUND in git log
- Commit `b660f2e` (Task 2 — Spike B) — FOUND in git log
- Commit `7ae2cea` (Task 3 — Spike C + evidence ledger) — FOUND in git log

---
*Phase: 28-temporal-dispatch*
*Completed: 2026-05-05*
