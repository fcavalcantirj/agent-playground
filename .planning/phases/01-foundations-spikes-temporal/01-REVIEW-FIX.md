---
phase: 01-foundations-spikes-temporal
fixed_at: 2026-04-13T23:01:00Z
review_path: .planning/phases/01-foundations-spikes-temporal/01-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-04-13T23:01:00Z
**Source review:** .planning/phases/01-foundations-spikes-temporal/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 11 (5 critical + 6 warning)
- Fixed: 11
- Skipped: 0

## Fixed Issues

### CR-01: `extractToken` HMAC check — non-constant-time string comparison

**Files modified:** `api/internal/middleware/auth.go`, `api/internal/handler/devauth.go`
**Commit:** 43c6499
**Applied fix:** Exported `verifyCookie` as `VerifyCookie` in the middleware package. Replaced the entire `extractToken` body (which used non-constant-time string `==` to compare HMAC signatures) with a single delegation call to `middleware.VerifyCookie`. This eliminates the timing oracle and removes the duplicated parsing logic.

---

### CR-02: `SessionSecret` length check bypassed in non-DevMode paths

**Files modified:** `api/internal/config/config.go`, `api/internal/server/server.go`
**Commit:** 391f7f4
**Applied fix:** In `config.Load()`, moved the `len(SessionSecret) < 32` check outside the `DevMode` guard so it fires unconditionally whenever a non-empty secret is provided. Kept the separate "required when DevMode=true" check. Added a `panic` guard inside `server.WithDevAuth` that fires at wiring time if `cfg.SessionSecret` is shorter than 32 bytes, giving a fast-fail before any request is served.

---

### CR-03: Temporal workers leak on partial `Start()` failure

**Files modified:** `api/internal/temporal/worker.go`
**Commit:** cbd16d5
**Applied fix:** Added a rollback loop in `Workers.Start()`: when worker `i` fails to start, all workers `0..i-1` are stopped and the Temporal client is closed before the error is returned. Updated the doc comment to reflect the new behavior.

---

### CR-04: Migration runner TOCTOU race — non-transactional check + apply + record

**Files modified:** `api/pkg/migrate/migrate.go`
**Commit:** f642408
**Applied fix:** Extended the `DB` interface with `Begin(ctx) (pgx.Tx, error)` (satisfied by both `*pgxpool.Pool` and `*pgx.Conn`). Added a `pg_advisory_lock(8675309)` call at the top of `Run()` (with deferred `pg_advisory_unlock`) to serialize concurrent migrators. Wrapped each migration's SQL execution and `schema_migrations` INSERT in a single transaction with explicit `Rollback` on failure and `Commit` on success. Both `TestMigrator_AppliesBaseline` and `TestMigrator_Idempotent` pass with the new code.

---

### CR-05: Floating `latest` image tags in Temporal compose files

**Files modified:** `docker-compose.dev.yml`, `docker-compose.yml`
**Commit:** 05e5fde
**Applied fix:** Pinned `temporalio/auto-setup` to `1.29.3` and `temporalio/ui` to `2.34.0` in both compose files (dev and production). These are the versions confirmed working with the local stack and compatible with `go.temporal.io/sdk v1.42.0`.

---

### WR-01: `TEMPORAL_HOST` defaults to `localhost:7233`, preventing the "skip Temporal" path

**Files modified:** `api/internal/config/config.go`, `api/internal/config/config_test.go`
**Commit:** 479be7c
**Applied fix:** Changed `TemporalHost` from `getEnvDefault("TEMPORAL_HOST", "localhost:7233")` to `os.Getenv("TEMPORAL_HOST")` so the field is empty when the env var is unset. Updated `TestLoad_TemporalDefaults` to assert empty string, and added `TestLoad_TemporalHostExplicit` to confirm explicit values are passed through. The `main.go` guard `if cfg.TemporalHost != ""` now works as documented.

---

### WR-02: `Server.Shutdown` creates a nested 10s timeout, ignoring the caller's deadline

**Files modified:** `api/internal/server/server.go`
**Commit:** dc4a258
**Applied fix:** Removed the `context.WithTimeout(ctx, 10*time.Second)` inside `Shutdown`. The method now passes the caller's context directly to `s.Echo.Shutdown`. The `main.go` 15-second timeout is the single source of truth for the shutdown window. The `time` import is still used by `zerologRequestLogger` so no import change was needed.

---

### WR-03: Test port selection has low-probability collision under parallel execution

**Files modified:** `api/internal/handler/devauth_test.go`, `api/pkg/migrate/migrate_test.go`
**Commit:** 81dc055
**Applied fix:** Replaced `uint32(46500 + time.Now().UnixNano()%1000)` (devauth) and `uint32(45433 + time.Now().UnixNano()%1000)` (migrate) with the `net.Listen("tcp", "127.0.0.1:0")` / read port / close pattern, which guarantees an OS-assigned free port. Added `"net"` to the imports in both files. All embedded-postgres tests pass.

---

### WR-04: `envKeyPattern` rejects lowercase env var keys used by proxy conventions

**Files modified:** `api/pkg/docker/runner.go`, `api/pkg/docker/runner_test.go`
**Commit:** 9402fe6
**Applied fix:** Changed `envKeyPattern` from `^[A-Z_][A-Z0-9_]*$` to `^[A-Za-z_][A-Za-z0-9_]*$`. Updated the `RunOptions.Env` field doc comment to match. In `runner_test.go`, removed `"lowercase=bad"` from the invalid list and added three lowercase proxy-convention keys (`http_proxy`, `https_proxy`, `no_proxy`) to the valid list.

---

### WR-05: No rollback of applied migrations if a later migration fails; no idempotency contract

**Files modified:** `api/pkg/migrate/migrate.go`
**Commit:** 444e821
**Applied fix:** Added an authoritative package-level doc comment block titled "Migration authoring rules" that mandates idempotent SQL (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, etc.) and explains why. Also noted the transactional and advisory-lock guarantees added by CR-04. The atomicity fix in CR-04 is the structural complement to this documentation change.

---

### WR-06: `web/src/middleware.ts` falsely claims Next.js 16 renames middleware to `proxy.ts`

**Files modified:** `web/src/middleware.ts`
**Commit:** 3250a47
**Applied fix:** Replaced the three-line false comment ("Next.js 16 renamed the middleware file convention to proxy...") with a correction stating the convention remains `middleware.ts` in Next.js 16, that there is no `proxy.ts` rename, and that this file stays as `middleware.ts` in Phase 3 and beyond.

---

_Fixed: 2026-04-13T23:01:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
