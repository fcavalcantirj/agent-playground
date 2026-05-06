---
phase: 29
plan: 02
subsystem: llm-egress-proxy
tags: [migration, schema, alembic, postgres, idempotency, byok, proxy]
dependency_graph:
  requires:
    - 29-CONTEXT.md (D-02, D-06, D-11, D-15, AMD-03, AMD-04 — locked decisions for proxy schema)
    - .planning/phases/29-llm-egress-proxy/spikes/PROBE-VAL-09.md (idempotency_keys delta enumeration — verdict_json must be NULLABLE)
    - api_server/alembic/versions/012_cost_weights_extra_models.py (down_revision pointer)
  provides:
    - alembic revision 013_phase29_proxy_columns (live in deploy-postgres-1)
    - agent_containers.bridge_ip / upstream_provider / provider_key_enc columns (read by Plans 04/05/06)
    - usage_logs.proxy_latency_ms / upstream_latency_ms columns (written by Plan 06 record_usage)
    - usage_logs.status='failed' (written by Plan 06 on upstream-error path)
    - idempotency_keys.status with in_flight/success/failed (read+written by Plan 04 reservation pattern)
    - idempotency_keys.verdict_json relaxed to NULLABLE (Plan 04 placeholder rows)
    - ix_agent_containers_bridge_ip_running partial index (Plan 04 IP-map hot path)
  affects:
    - Plans 29-03..29-09 — all subsequent plans now read/write the new columns; the [BLOCKING] live-apply ensures their tests don't fail with `column does not exist`
tech_stack:
  added: []
  patterns:
    - testcontainers PostgresContainer (postgres:17-alpine) round-trip migration test (mirrors test_migration_011_phase28)
    - docker cp + docker exec apply-to-live (Phase 22c-02 / 22c.3-02 pattern; macOS Docker Desktop bridge-IP cannot be reached from host venv)
    - alembic revision id <= 32 chars (013_phase29_proxy_columns = 25 chars; well under varchar(32))
    - down_revision points to DB-stored revision id (012_cost_weights_extra), NOT filename (012_cost_weights_extra_models.py)
key_files:
  created:
    - api_server/alembic/versions/013_phase29_proxy_columns.py
    - api_server/tests/test_migration_013_proxy_columns.py
  modified: []
decisions:
  - down_revision = "012_cost_weights_extra" (the actual revision id stored by migration 012; the filename suffix _models is decorative)
  - verdict_json relaxed to NULLABLE (PROBE-VAL-09 finding; required by AMD-03 in-flight reservation pattern; not in PLAN body but explicit in user spawn prompt)
  - DELETE FROM usage_logs WHERE status='unknown' is irreversible (downgrade does NOT restore the rows; documented in migration downgrade docstring AND round-trip test)
  - downgrade requires operator pre-cleanup of in-flight idempotency reservations + 'failed' usage_logs rows (documented in migration downgrade docstring; mirrored in round-trip test pre-downgrade DELETEs)
metrics:
  duration_minutes: ~30
  tasks_completed: 3
  commits: 3
  files_created: 2
  files_modified: 0
  completed_date: 2026-05-06
---

# Phase 29 Plan 02: Migration 013 Proxy Columns — Schema Surface for Egress Proxy + Idempotency In-Flight

Lands the alembic schema delta Phase 29 needs (proxy session metadata on `agent_containers`, latency split + 'failed' status on `usage_logs`, in-flight reservation on `idempotency_keys`) and applies it to the live `deploy-postgres-1` so Plans 03+ can read/write the new columns without "column does not exist" errors.

## What Shipped

### Schema columns added (5)

| Table | Column | Type | Nullable | Purpose | Decision |
|-------|--------|------|----------|---------|----------|
| `agent_containers` | `bridge_ip` | INET | YES | Docker bridge IP for proxy router IP-map lookup | AMD-04 |
| `agent_containers` | `upstream_provider` | TEXT | YES | Provider dispatch ('openrouter' / 'anthropic' / 'openai') | D-11 |
| `agent_containers` | `provider_key_enc` | BYTEA | YES | age-cipher BYOK key (encrypted with AP_CHANNEL_MASTER_KEY) | D-02 |
| `usage_logs` | `proxy_latency_ms` | INTEGER | YES | Wall-clock inside the proxy router | D-11 |
| `usage_logs` | `upstream_latency_ms` | INTEGER | YES | Wall-clock the upstream provider took | D-11 |
| `idempotency_keys` | `status` | TEXT (NOT NULL DEFAULT 'success') | NO | In-flight reservation transitions ('success' / 'failed' / 'in_flight') | AMD-03 |

### Constraint changes

- `ck_usage_logs_status` widened from `('success','error','unknown')` to `('success','error','unknown','failed')` (D-15).
- `ck_idempotency_keys_status` added: `status IN ('success','failed','in_flight')`.
- `idempotency_keys.verdict_json` ALTERed to NULLABLE (was NOT NULL — required for placeholder reservations per PROBE-VAL-09 + AMD-03).

### Indexes added

- `ix_agent_containers_bridge_ip_running` partial btree on `bridge_ip` WHERE `container_status = 'running' AND bridge_ip IS NOT NULL`.

### Row-level state changes

- **`DELETE FROM usage_logs WHERE status='unknown'`** — wiped **11 rows** (legacy from a2a_jsonrpc / native shapes that strip token counts; non-recoverable; D-06).
- The DELETE is irreversible by design: downgrade does NOT restore the rows; documented in migration downgrade() docstring and round-trip integration test.

### Live-infra apply

- Migration applied to `deploy-postgres-1` via `docker cp` + `docker exec deploy-api_server-1 sh -c 'cd /app/api_server && alembic upgrade head'`.
- Final live `alembic_version`: `013_phase29_proxy_columns`.
- Verify gate `BLOCKING-SCHEMA-PUSH-OK` echoed cleanly.

## Tests

7 testcontainers PG 17 round-trip tests in `api_server/tests/test_migration_013_proxy_columns.py`, all PASS:

| # | Test | Coverage |
|---|------|----------|
| 1 | `test_agent_containers_columns` | bridge_ip / upstream_provider / provider_key_enc shape |
| 2 | `test_usage_logs_proxy_and_upstream_latency_columns` | proxy_latency_ms / upstream_latency_ms shape |
| 3 | `test_usage_logs_status_check_allows_failed` | INSERT status='failed' succeeds (no constraint violation) |
| 4 | `test_idempotency_keys_status_column_with_in_flight` | status NOT NULL DEFAULT 'success'; verdict_json NULLABLE; INSERT status='in_flight' OK; bogus status fails CHECK |
| 5 | `test_partial_index_bridge_ip_running` | Partial index exists with correct predicate |
| 6 | `test_unknown_status_rows_deleted` | D-06 wipe: pre-seeded 'unknown' row at rev 012 is gone after upgrade head |
| 7 | `test_round_trip_clean` | upgrade head → downgrade -1 → upgrade head leaves identical schema for additive columns |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `a854b94` | test | Task 1 — RED: 7-test integration module (all fail, migration 013 doesn't exist) |
| `dfcdc0d` | feat | Task 2 — GREEN: migration 013 body + round-trip pre-cleanup fix in test |
| `f944137` | feat | Task 3 — [LIVE] applied to deploy-postgres-1 (empty source-diff commit; recorded for traceability) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Corrected `down_revision` pointer**
- **Found during:** Task 2 (writing migration body)
- **Issue:** PLAN's spec and 29-PATTERNS.md both prescribe `down_revision = "012_cost_weights_extra_models"`. That string does NOT exist as an alembic revision id — migration 012's actual `revision = "012_cost_weights_extra"` (the filename `012_cost_weights_extra_models.py` is just decorative; the DB-stored identity uses the abbreviated form, mirroring 011's `011_phase28_workflow_id_idem` pattern). Using the spec'd string would have left alembic unable to resolve the chain (`Can't locate revision identified by 012_cost_weights_extra_models`).
- **Fix:** Set `down_revision = "012_cost_weights_extra"` to match migration 012's actual revision id.
- **Files modified:** `api_server/alembic/versions/013_phase29_proxy_columns.py`
- **Commit:** `dfcdc0d`

**2. [Rule 2 - Missing critical functionality] Added `verdict_json` NULLABLE relaxation**
- **Found during:** Pre-Task-1 reading of PROBE-VAL-09.md
- **Issue:** PLAN body's migration code adds the `idempotency_keys.status` column but does NOT alter `verdict_json` to NULLABLE. PROBE-VAL-09 explicitly enumerates this as a required delta for the AMD-03 in-flight reservation pattern: a placeholder row reserves the (user_id, key) tuple BEFORE the upstream call lands, so its `verdict_json` is NULL until the success/failed transition. The user's spawn instructions also explicitly require this. Without the relaxation, the placeholder INSERT would fail NOT NULL.
- **Fix:** Added `op.alter_column("idempotency_keys", "verdict_json", existing_type=postgresql.JSONB(), nullable=True)` to upgrade(); reversed in downgrade(). Test 4 asserts the post-upgrade `is_nullable='YES'`.
- **Files modified:** `api_server/alembic/versions/013_phase29_proxy_columns.py`, `api_server/tests/test_migration_013_proxy_columns.py`
- **Commit:** `dfcdc0d`

**3. [Rule 1 - Bug] Round-trip test pre-cleanup for downgrade narrowing**
- **Found during:** Task 2 first GREEN run
- **Issue:** The round-trip test ran fine in isolation but failed in the full module suite — when `test_round_trip_clean` ran after `test_idempotency_keys_status_column_with_in_flight` and `test_usage_logs_status_check_allows_failed`, the downgrade tried to (a) restore `verdict_json` to NOT NULL while in-flight rows had NULL and (b) recreate the narrower `ck_usage_logs_status` while a `'failed'` row existed. Both raised IntegrityErrors during alembic downgrade.
- **Fix:** Added pre-downgrade DELETEs in the round-trip test — purge in-flight idempotency reservations (`WHERE verdict_json IS NULL`) and 'failed' usage_logs rows. This mirrors the operator pre-condition the migration's downgrade() docstring requires (watchdog cleanup of in-flight rows; manual purge of 'failed' rows). The fix is a test correction, not a migration change.
- **Files modified:** `api_server/tests/test_migration_013_proxy_columns.py`
- **Commit:** `dfcdc0d`

**4. [Rule 1 - Test ergonomics] Captured alembic stderr in `_alembic` helper**
- **Found during:** Task 2 GREEN debugging
- **Issue:** The mirrored `_alembic` helper from 011 uses `subprocess.run(check=True, capture_output=True)` which suppresses stderr, making downgrade failures opaque (only saw `CalledProcessError` exit code 1, no SQL detail).
- **Fix:** Replaced `check=True` with manual `if returncode != 0: raise RuntimeError(stdout + stderr)`. This is a test-only ergonomics fix; it does not change behavior on success.
- **Files modified:** `api_server/tests/test_migration_013_proxy_columns.py`
- **Commit:** `a854b94` (initial test) and `dfcdc0d` (refined during GREEN debugging)

### Authentication Gates
None — Task 3 used local Docker socket (no remote auth required).

## Threat Flags
None new. T-29-04 (`provider_key_enc` confidentiality) and T-29-05 (irreversible DELETE acceptance) from the plan's threat_model are already mitigated/accepted at this layer; downstream plans (Plan 05 BYOK encrypt-on-write) own the encryption-key plumbing.

## Self-Check: PASSED

**Files exist:**
- FOUND: `api_server/alembic/versions/013_phase29_proxy_columns.py`
- FOUND: `api_server/tests/test_migration_013_proxy_columns.py`

**Commits exist:**
- FOUND: `a854b94` test(29-02): task 1
- FOUND: `dfcdc0d` feat(29-02): task 2
- FOUND: `f944137` feat(29-02): task 3 [LIVE]

**Live state:**
- FOUND: `deploy-postgres-1` `alembic_version = '013_phase29_proxy_columns'`
- FOUND: All 5 new columns visible in `\d agent_containers` / `\d usage_logs` / `\d idempotency_keys`
- FOUND: 0 rows with `usage_logs.status='unknown'` (was 11 pre-apply; D-06 wipe successful)
- FOUND: `ix_agent_containers_bridge_ip_running` partial index live with correct predicate
- FOUND: `idempotency_keys.verdict_json` is_nullable='YES' (AMD-03 relaxation live)

**Tests:**
- 7/7 PASS via `cd api_server && uv run pytest tests/test_migration_013_proxy_columns.py -v -m api_integration`
