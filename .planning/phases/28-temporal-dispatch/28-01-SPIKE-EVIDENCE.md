# Phase 28 — Wave 0 Spike Evidence

This ledger records the empirical PASS evidence for the three Wave 0
spikes that gate every later wave. Run on macOS Docker Desktop (28.5.1)
against `postgres:17-alpine`, `temporalio/auto-setup:1.29.2`,
`temporalio/ui:2.40.0`, `temporalio` Python SDK 1.27.0, and the
`deploy-api_server:latest` image (built locally from
`tools/Dockerfile.api`).

**Combined Wave-0 wall time:** 23.24s (3 spikes, single pytest invocation).

---

**Spike A — Temporal cluster boot vs PG17:** PASS

- Command: `pytest api_server/tests/spikes/test_phase28_spike_a_temporal_boot.py -x -m spike`
- Wall time: 6.5s to healthy + ~10s SDK probe + tear-down ≈ 17s
- Healthcheck reached green at: 6.5s after `docker compose up -d`
  (auto-setup's start_period of 30s was generous; PG17 schema
  bootstrap completed in well under 10s)
- Client.connect status: SUCCESS (`localhost:7233`, namespace `default`)
- `client.list_workflows("")` iterator drained: 0 results (expected on a
  fresh cluster)
- Tear-down: `docker compose down -v` ran via try/finally; post-test
  `docker ps` shows no `phase28spike-temporal-*` containers
- Verbatim output: `SPIKE-A PASS: healthy_in=6.6s
  last_status="service=temporal health='healthy'"
  probe={'address': 'localhost:7233', 'namespace': 'default',
  'list_workflows_drained': '0'}`

**Wave-0 finding routed to Wave-1 plan:**
`temporalio/auto-setup:1.29.2` ships
`config/dynamicconfig/docker.yaml` (empty), NOT
`development-sql.yaml` (which RESEARCH §2 quoted from the upstream
`temporalio/docker-compose` example for older tags). Pointing
`DYNAMIC_CONFIG_FILE_PATH` at `development-sql.yaml` crashes the
Temporal server during boot:
`unable to validate dynamic config: stat ...: no such file or
directory`. The fix is one line in the compose recipe — Wave 1's
`deploy/docker-compose.prod.yml` block must use
`config/dynamicconfig/docker.yaml`. Closes RESEARCH §10 A3
empirically with this correction noted.

---

**Spike B — Workflow sandbox passthrough:** PASS

- Command: `pytest api_server/tests/spikes/test_phase28_spike_b_workflow_sandbox.py -x -m spike`
- Wall time: 3.6s
- Workflow result echo'd correctly: yes (`'echo:hello'`)
- Any sandbox passthrough warnings: no (0 warnings matching
  `temporalio.worker.workflow_sandbox` / `RAISE_ON_UNINTENTIONAL_PASSTHROUGH` /
  `imports_passed_through` / `RestrictedWorkflowAccess`)
- Verbatim output: `SPIKE-B PASS: result='echo:hello' (captured 0 total
  warnings, 0 from sandbox; non-sandbox warnings ignored)`

**Wave-0 finding routed to Wave-1 plan:**
The original plan called for `pytest -W error::Warning` as the load-
bearing assertion. On the first run that flag failed during
`tests/conftest.py` import because of an unrelated
`testcontainers.redis` `DeprecationWarning`. Spike B was rewritten to
use `warnings.catch_warnings(record=True)` with a sandbox-provenance
filter — only warnings whose filename / category / message matches
sandbox-related needles fail the test. This is more surgical and
ignores third-party warnings that have nothing to do with the spike's
subject. Closes RESEARCH §10 A2 empirically — `from . import
_phase28_b_activities` inside `workflow.unsafe.imports_passed_through()`
does NOT trigger the sandbox even when the activity module imports
`asyncpg` / `httpx` / `docker`.

---

**Spike C — Worker → bridge IP:** PASS

- Command: `pytest api_server/tests/spikes/test_phase28_spike_c_worker_bridge_ip.py -x -m spike`
- Wall time: 7.9s
- Bridge IP resolved: `172.20.0.2` (RFC1918, in expected
  `phase28spikec_default` compose-network range)
- httpx.get status: 200 against `http://172.20.0.2/`; 404 against
  `http://172.20.0.2/healthz` (nginx default has no /healthz — the
  spike accepts both as "connection established")
- Verbatim output: `SPIKE-C PASS: ip='172.20.0.2' root_status=200
  healthz_status=404`

**Wave-0 finding routed to Wave-1 plan:**
On macOS Docker Desktop, the `deploy-api_server:latest` image runs as
`apiuser` (UID 1001, group `docker` GID 999). Docker Desktop bind-
mounts `/var/run/docker.sock` as `root:root mode 660`, so `apiuser`
gets `Permission denied` when calling `docker.from_env()` from inside
the container. The existing `deploy/docker-compose.local.yml` solves
this for `api_server` with `user: root` — Wave 1's
`temporal-worker` service block must apply the SAME override in
`docker-compose.local.yml` (not in `prod.yml` — Hetzner's daemon owns
the socket as `root:docker(999)`, where the apiuser group membership
works natively). Closes RESEARCH §7 R6 + §10 A6 empirically.

---

WAVE-0-CLOSED 2026-05-05 felipe.cavalcanti.rj@gmail.com
