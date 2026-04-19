# Spike B — TRUNCATE CASCADE on full FK graph (BLOCKER-4 Option A regression)

**Run date:** 2026-04-19T23:29:52Z
**Command:** `docker exec -e TESTCONTAINERS_RYUK_DISABLED=true -e SPIKE_DOCKER_NETWORK=deploy_default deploy-api_server-1 sh -c "cd /app/api_server && python -m pytest tests/spikes/test_truncate_cascade.py -x -v -m api_integration -s"`
**Mode:** **B** (7 tables — alembic 005 pending, will be delivered by plan 22c-02)
**Result:** **PASS**
**alembic revision at test start:** `004_agent_events`
**alembic revision at test end:** `004_agent_events` (preserved — TRUNCATE did NOT clobber `alembic_version`)

## Rationale

Per BLOCKER-4 Option A from the revision checker: the in-repo
`test_migration_006_truncates_all_data_tables` (plan 22c-06 Task 1) weakens
to an artifact-existence check when HEAD is already 006 in the session-scoped
fixture. This spike carries the runnable regression — fresh container, applies
alembic 001..004 (Mode B; Mode A auto-upgrades to 001..005 once plan 22c-02
ships migration 005), seeds a row into EACH in-scope data table, runs the
same TRUNCATE statement migration 006 will run verbatim, asserts all tables
COUNT=0 AND alembic_version is preserved.

**Mode selection** is automatic at import time via a filesystem check for
`api_server/alembic/versions/005_sessions_and_oauth_users.py`:
- present → Mode A (8 tables, includes `sessions`)
- absent → Mode B (7 tables, no `sessions`)

This spike re-runs in Mode A automatically after plan 22c-02 lands; no test
edit required.

## Version pins verified

- postgres testcontainer: `postgres:17-alpine`
- testcontainers (python): 4.14.2
- asyncpg: 0.31.0
- alembic: 1.18.4
- python: 3.11.15
- pytest: 9.0.3
- pytest-asyncio: 1.3.0

## Tables seeded + cleared (Mode B — actual Wave 0 run)

| Table                 | Pre-truncate COUNT | Post-truncate COUNT |
|-----------------------|--------------------|---------------------|
| `users`               | 2                  | 0                   |
| `agent_instances`     | 1                  | 0                   |
| `agent_containers`    | 1                  | 0                   |
| `runs`                | 1                  | 0                   |
| `agent_events`        | 1                  | 0                   |
| `idempotency_keys`    | 1                  | 0                   |
| `rate_limit_counters` | 1                  | 0                   |

**Note on `users=2` pre-count:** migration 001 seeds the anonymous user row
(`00000000-0000-0000-0000-000000000001`) at upgrade time, so the table
already has 1 row before the spike's own seed INSERT. Post-TRUNCATE both are
gone (COUNT=0), which is exactly what migration 006 intends (AMD-03 —
ANONYMOUS row deleted).

alembic_version before: `004_agent_events`
alembic_version after:  `004_agent_events` (preserved — TRUNCATE explicitly
excluded `alembic_version`)

## What the spike proved

1. A single `TRUNCATE TABLE <7 data tables> CASCADE` statement clears every
   row without FK ordering anxiety — CASCADE handles the
   `agent_events → agent_containers → agent_instances → users` chain +
   `runs → agent_instances → users` + `idempotency_keys → (runs, users)`
   + the partial-unique running-container index on `agent_containers`.
2. `alembic_version` is NOT included in the TRUNCATE table list, so the
   schema-version bookkeeping row survives (`version_num` == `004_agent_events`
   both before and after). This is the property plan 22c-06's migration 006
   depends on: irreversible downgrade + preserved schema version.
3. NOT-NULL + CHECK constraints hold during seed (the INSERTs in the spike
   are the "will this migration's schema accept real data" smoke). Specifically:
   - `agent_instances.name` NOT NULL (post-002) — satisfied by explicit `name=`.
   - `agent_containers.deploy_mode` + `container_status` have server_defaults
     — seed omits them; defaults accepted.
   - `agent_events.kind` CHECK (one of reply_sent|reply_failed|agent_ready|
     agent_error) — seed uses `agent_ready`; accepted.
   - `idempotency_keys.request_body_hash` NOT NULL — satisfied by
     `"spike-request-hash"`.
4. `rate_limit_counters` composite PK `(subject, bucket, window_start)` accepts
   a manually-inserted row; CASCADE doesn't need a FK (there isn't one) but
   TRUNCATE clears the table unconditionally — confirmed.
5. Network-attached testcontainer works. The spike's fixture places the
   ephemeral Postgres on `deploy_default` so it's reachable from the
   api_server container; the DSN is built from the PG container's
   network-attached IP (not the host-mapped ephemeral port), which is what
   the api_server's alembic subprocess and the asyncpg test client need.

## Test output (captured — `python -m pytest -v -s`)

```
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-9.0.3, pluggy-1.6.0 -- /usr/local/bin/python
cachedir: .pytest_cache
rootdir: /app/api_server
configfile: pyproject.toml
plugins: asyncio-1.3.0, respx-0.23.1, anyio-4.13.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/spikes/test_truncate_cascade.py::test_truncate_cascade_clears_all_tables_preserves_alembic_version
[SPIKE-B] mode=B target_rev=004_agent_events tables=7 pre={'users': 2, 'agent_instances': 1, 'agent_containers': 1, 'runs': 1, 'agent_events': 1, 'idempotency_keys': 1, 'rate_limit_counters': 1} post={'users': 0, 'agent_instances': 0, 'agent_containers': 0, 'runs': 0, 'agent_events': 0, 'idempotency_keys': 0, 'rate_limit_counters': 0} alembic_version_preserved=True
PASSED

============================== 1 passed in 3.66s ===============================
```

## Deviations (Rule 3 — blocking issues resolved inline)

Two test-rig adjustments were needed to run the spike against the real
live-infra stack (not test bugs, but test-rig bugs):

**D1 — testcontainers Ryuk unreachable from inside the api_server container.**
When the spike runs via `docker exec deploy-api_server-1 pytest ...`,
testcontainers' default Ryuk reaper fires up but cannot be reached on its
TCP port because the api_server container and the Ryuk container land on
different Docker networks. Resolution: `TESTCONTAINERS_RYUK_DISABLED=true`
(documented testcontainers env knob). Acceptable for a spike — cleanup on
pytest exit relies on the `with PostgresContainer(...)` context manager
which already calls `stop()` on unwind.

**D2 — Spawned PG container unreachable via host-mapped DSN from inside
deploy_default network.** `PostgresContainer.get_connection_url()` returns
a DSN like `postgresql://...@172.17.0.1:<eph>/...` (docker host gateway +
ephemeral port). That address routes from the host-laptop into the default
bridge, but NOT from inside a container attached to `deploy_default`.
Resolution: `with_kwargs(network="deploy_default")` + build the DSN from
the PG container's network-attached IP on `deploy_default` (via
`docker inspect → NetworkSettings.Networks.deploy_default.IPAddress`).
The spike's `fresh_pg_at_target_rev` fixture stashes that DSN on the
returned object as `pg._spike_dsn`; the test body prefers it over
`get_connection_url()`. Env override knob: `SPIKE_DOCKER_NETWORK` (default
`deploy_default`) so CI or different dev setups can point at their own
network name.

Both deviations are applied in the test file (`api_server/tests/spikes/test_truncate_cascade.py`) and in the `docker exec` invocation. Neither affects the migration 006 design — they're purely "how the spike harness talks to the ephemeral PG" concerns.

## Decision

- **PASS → migration 006 (plan 22c-06) uses the single `TRUNCATE ... CASCADE`
  statement as written.** R8 regression is covered by this spike end-to-end
  (seed → truncate → empty + alembic_version preserved).
- Plan 22c-06's own `test_migration_006_truncates_all_data_tables` can
  retain its current weaker artifact-check shape (since it will skip when
  HEAD is already 006 in the session-scoped fixture); this spike carries
  the runnable regression.
- **Mode A upgrade path:** after plan 22c-02 ships
  `005_sessions_and_oauth_users.py`, this spike auto-switches to Mode A
  (8 tables, includes `sessions`). No test edit needed — the import-time
  `_ALEMBIC_005_PATH.exists()` check flips and the conditional
  `tables_seeded.append("sessions")` + expanded TRUNCATE statement kick
  in. Re-run this spike after 22c-02 to confirm the 8-table Mode A result.
- Wave 0 Spike B hard gate: **CLEARED**.

## Execution note

Same rationale as SPIKE-A: `/app/api_server/` is baked into the image, so
the spike test file was `docker cp`'d into `/app/api_server/tests/spikes/`
before `python -m pytest` ran. The authoritative copy lives at
`api_server/tests/spikes/test_truncate_cascade.py` on the host; downstream
image rebuilds bake it in naturally (the Dockerfile.api at `tools/Dockerfile.api`
currently only `COPY`s `api_server/src/`, `alembic/`, and `alembic.ini`, so
the tests tree is not yet in the image — that's intentional for a
production build, and acceptable for Wave 0: spike tests don't ship to prod).
