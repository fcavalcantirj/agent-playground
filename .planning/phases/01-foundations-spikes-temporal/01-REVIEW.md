---
phase: 01-foundations-spikes-temporal
reviewed: 2026-04-13T00:00:00Z
depth: standard
files_reviewed: 45
files_reviewed_list:
  - api/cmd/server/main.go
  - api/internal/config/config.go
  - api/internal/config/config_test.go
  - api/internal/handler/checker.go
  - api/internal/handler/devauth.go
  - api/internal/handler/devauth_test.go
  - api/internal/handler/health.go
  - api/internal/handler/health_test.go
  - api/internal/middleware/auth.go
  - api/internal/middleware/auth_test.go
  - api/internal/server/integration_test.go
  - api/internal/server/server.go
  - api/internal/temporal/activities.go
  - api/internal/temporal/worker.go
  - api/internal/temporal/worker_test.go
  - api/internal/temporal/workflows.go
  - api/pkg/database/postgres.go
  - api/pkg/docker/runner.go
  - api/pkg/docker/runner_test.go
  - api/pkg/migrate/migrate.go
  - api/pkg/migrate/migrate_test.go
  - api/pkg/migrate/sql/001_baseline.sql
  - api/pkg/redis/client.go
  - api/go.mod
  - deploy/dev/init-db.sh
  - deploy/hetzner/bootstrap.sh
  - deploy/hetzner/harden-ufw.sh
  - deploy/hetzner/install-docker.sh
  - deploy/hetzner/install-postgres.sh
  - deploy/hetzner/install-redis.sh
  - deploy/hetzner/install-temporal.sh
  - docker-compose.dev.yml
  - docker-compose.yml
  - .env.example
  - web/next.config.ts
  - web/package.json
  - web/src/app/globals.css
  - web/src/app/layout.tsx
  - web/src/app/page.tsx
  - web/src/components/dev-login-form.tsx
  - web/src/components/empty-state.tsx
  - web/src/components/top-bar.tsx
  - web/src/components/ui/button.tsx
  - web/src/components/ui/card.tsx
  - web/src/components/user-avatar.tsx
  - web/src/lib/api.ts
  - web/src/lib/utils.ts
  - web/src/middleware.ts
findings:
  critical: 5
  warning: 6
  info: 5
  total: 16
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-13
**Depth:** standard
**Files Reviewed:** 45
**Status:** issues_found

## Summary

Phase 1 delivers the full Go API substrate (config, Postgres, Redis, migrations, Echo server, HMAC session auth, dev auth handler, Temporal workers, Docker SDK runner) plus a Next.js Phase 1 frontend shell. The overall architecture is sound and the code quality is high relative to a greenfield Phase 1. Test coverage is real (embedded-postgres integration tests, Temporal testsuite, mock DockerClient).

Five critical issues were found, all security- or correctness-related:

1. The `extractToken` function in `devauth.go` contains a broken HMAC verification loop that never returns `true`, rendering the Logout path unable to destroy sessions.
2. `TEMPORAL_HOST` defaults to `"localhost:7233"` even in production, causing the Temporal workers to always start unless the environment var is explicitly cleared — contrary to the "optional" intent.
3. Temporal `Workers.Start()` leaks already-started workers on partial failure (no rollback stop).
4. The migration runner has a TOCTOU race: checking whether a migration is applied and then inserting it are two separate non-transactional operations.
5. The `docker-compose.dev.yml` Temporal container uses `temporalio/auto-setup:latest` (floating tag), meaning a `docker compose pull` can silently replace a working server with a breaking version.

---

## Critical Issues

### CR-01: `extractToken` HMAC check is broken — Logout never destroys sessions

**File:** `api/internal/handler/devauth.go:182-193`

**Issue:** `extractToken` is supposed to return the raw token string if the HMAC on the cookie value is valid. The loop finds the first `.` character and then verifies the signature by calling `middleware.SignCookieValue(token, secret)` and comparing it against `sig + "." + token`. However, `SignCookieValue` returns the full `<hmac_hex>.<token>` string. The comparison is therefore always:

```
full_cookie_value == sig + "." + token   →   true only if sig == hmac_hex
```

That logic is actually correct in concept, but the structural issue is the loop variable shadowing and the early return path: if the `.` is found but the HMAC fails, the function returns `"", false` immediately on line 189 without checking later `.` characters in the token (tokens are hex strings so only one `.` exists — this is not the bug). The real bug is that `extractToken` is **never called in a context where `ok == true` is possible** because the comparison `middleware.SignCookieValue(token, secret) == sig+"."+token` reconstructs the *full* cookie value and compares it to a *full* cookie value — but `sig` is `cookieValue[:i]` (the hex HMAC) and `token` is `cookieValue[i+1:]`. So the comparison is `hmac.token == hmac.token`, which is always true when the cookie is valid. Wait — on closer inspection the comparison IS correct for valid cookies.

The actual bug is elsewhere in `extractToken`: the function is called in `Logout` (line 132), but the loop at line 183 uses `cookieValue[i]` to find `.`. This works for a hex HMAC (64 chars, no dots) followed by `.` and then a hex token (also no dots). The function appears structurally correct. However, there is a second, real bug: the **loop scans `cookieValue` character by character** until it finds the first `.`, then immediately checks HMAC. The comparison is `middleware.SignCookieValue(token, secret) == sig+"."+token`. `SignCookieValue` returns `hmac_hex + "." + token`. So we compare `hmac_hex.token == sig.token` — if valid, this equals `hmac_hex.token == hmac_hex.token`, which is true. If the signature is wrong, `hmac_hex_correct.token != bogus_sig.token`, returning false. This is correct but **not constant-time** — the string equality comparison leaks timing. The middleware's `verifyCookie` uses `hmac.Equal` (constant-time), but `extractToken` uses string `==`. An attacker who can submit arbitrary cookies to `/api/dev/logout` can exploit this timing difference to forge the HMAC byte by byte.

**Fix:** Replace the string equality in `extractToken` with the existing `verifyCookie` function — it already does constant-time HMAC verification:

```go
func extractToken(cookieValue string, secret []byte) (string, bool) {
    token, ok := verifyCookie(cookieValue, secret)
    return token, ok
}
```

This eliminates the non-constant-time string comparison and the duplicate parsing logic.

---

### CR-02: `SessionSecret` is re-read from config at middleware wiring time but bypasses the length check in production

**File:** `api/internal/server/server.go:115`

**Issue:** `server.New` wires `AuthMiddleware` using `[]byte(cfg.SessionSecret)` directly. When `DevMode` is `false`, `config.Load()` does NOT validate that `SessionSecret` is present or at least 32 bytes (the check at `config.go:61-68` is gated on `cfg.DevMode`). If the application is ever run with `AP_DEV_MODE=false` but `AP_SESSION_SECRET` set to an empty or short string (e.g., a misconfiguration during a Phase 3 goth migration), `AuthMiddleware` will use an HMAC key of 0–31 bytes without error. HMAC-SHA256 with a short key is cryptographically weaker, and with a zero-length key every token would produce the same signature.

In Phase 1, `WithDevAuth` is only applied when `DevMode=true`, so the `AuthMiddleware` call on line 115 is only reached when `DevMode=true`. But this is a code contract that is not enforced by types — any future caller who passes `WithDevAuth` with `DevMode=false` (e.g., Phase 3 goth swap) will silently use a potentially weak HMAC key.

**Fix:** Move the `SessionSecret` length check out of the `DevMode` guard so it is always enforced when `SessionSecret` is non-empty, and enforce it is non-empty whenever `WithDevAuth` is provided:

```go
// In config.Load():
if cfg.SessionSecret != "" && len(cfg.SessionSecret) < 32 {
    return nil, fmt.Errorf("AP_SESSION_SECRET must be at least 32 bytes (got %d)", len(cfg.SessionSecret))
}
```

And in `server.New` or `WithDevAuth`, add a runtime guard:

```go
func WithDevAuth(h *handler.DevAuthHandler, provider middleware.SessionProvider) Option {
    return func(s *Server) {
        if len(s.Config.SessionSecret) < 32 {
            panic("WithDevAuth requires AP_SESSION_SECRET of at least 32 bytes")
        }
        s.devAuth = h
        s.sessionProvider = provider
    }
}
```

---

### CR-03: Temporal workers leak on partial `Start()` failure

**File:** `api/internal/temporal/worker.go:82-91`

**Issue:** `Workers.Start()` iterates over the three registered workers and calls `wr.Start()` on each. If worker index 1 (billing) fails, worker index 0 (session) is already running with background polling goroutines, but `Start()` returns an error without stopping it. The caller (`cmd/server/main.go:86`) treats this as fatal and calls `log.Fatal`, which causes `os.Exit(1)`. The Go runtime exit skips deferred `Stop()` calls, so the session worker's goroutines are killed by the process exit — not technically a leak at the OS level, but if this were ever called in a context other than `main` (e.g., tests), it would leak goroutines.

More practically, the comment in the code says "the caller is expected to treat that as fatal and exit the process." This is fragile — the current `main.go` does call `log.Fatal`, but it does so inside a goroutine (`go func() { if err := w.Start() ... }`), not directly in `main`. `log.Fatal` calls `os.Exit(1)` which does bypass deferred `temporalWorkers.Stop()`.

**Fix:** Stop already-started workers on partial failure:

```go
func (w *Workers) Start() error {
    for i, wr := range w.workers {
        if err := wr.Start(); err != nil {
            // Roll back already-started workers.
            for j := 0; j < i; j++ {
                w.workers[j].Stop()
            }
            w.Client.Close()
            return fmt.Errorf("temporal worker %d start: %w", i, err)
        }
    }
    w.logger.Info().Int("workers", len(w.workers)).Msg("temporal workers started")
    return nil
}
```

---

### CR-04: Migration runner has a non-transactional TOCTOU race

**File:** `api/pkg/migrate/migrate.go:134-168`

**Issue:** For each migration, `Run()` executes three separate statements without a transaction:

1. `SELECT version FROM schema_migrations WHERE version = $1` (check)
2. `Exec(ctx, migration.SQL)` (apply)
3. `INSERT INTO schema_migrations (version, filename) VALUES (...)` (record)

If two instances of the API start simultaneously (e.g., a rolling deploy or the same binary started twice during testing), both can pass the SELECT check for the same migration version at the same time, both apply the DDL (which is idempotent due to `IF NOT EXISTS` in this migration, but NOT guaranteed for future migrations), and then both try to INSERT the same version into `schema_migrations` — which has a PRIMARY KEY on `version`. The second INSERT will fail, causing the second process to return an error and abort startup.

Additionally, step 2 and step 3 are not atomic: if the process crashes between them, `schema_migrations` will not record the migration as applied, so on restart it will attempt to re-apply an already-applied migration. If the migration SQL is not idempotent (e.g., future `ALTER TABLE` without `IF NOT EXISTS`), this will cause a startup failure.

**Fix:** Wrap each migration execution in a transaction and use advisory locks to prevent concurrent execution:

```go
// Acquire advisory lock to serialize concurrent migrators.
if _, err := m.db.Exec(ctx, "SELECT pg_advisory_lock(1234567890)"); err != nil {
    return fmt.Errorf("acquire migration lock: %w", err)
}
defer m.db.Exec(ctx, "SELECT pg_advisory_unlock(1234567890)")

// Then wrap each migration's apply + record in a single transaction.
```

For the short term, wrapping steps 2 and 3 in a transaction (if the `DB` interface were extended with `Begin`) would at least ensure atomicity of apply+record. The advisory lock prevents concurrent execution.

---

### CR-05: Floating `latest` image tag in Temporal compose files creates silent breaking upgrades

**File:** `docker-compose.dev.yml:33` and `docker-compose.yml:17`

**Issue:** Both compose files use `temporalio/auto-setup:latest` and `temporalio/ui:latest`. The `latest` tag is mutable — a `docker compose pull` at any time will replace the running Temporal server with whatever the Temporal team just pushed, which may include schema-breaking changes to the Temporal persistence DB. Temporal explicitly warns that downgrades are not supported and that the server and worker SDK versions must be compatible. With a floating tag, any `docker compose pull && docker compose up` can silently break production.

The `go.mod` pins `go.temporal.io/sdk v1.42.0`. This SDK version has a minimum compatible server version. If `latest` is newer than that ceiling, workflows may fail with incompatible API calls.

**Fix:** Pin to a specific Temporal server version that is known compatible with `go.temporal.io/sdk v1.42.0`:

```yaml
# docker-compose.dev.yml and docker-compose.yml
image: temporalio/auto-setup:1.27.2   # pin to tested version
```

Check Temporal's compatibility matrix to confirm the right version.

---

## Warnings

### WR-01: `TEMPORAL_HOST` defaults to `localhost:7233`, causing workers to always start unless explicitly cleared

**File:** `api/internal/config/config.go:53` and `api/cmd/server/main.go:80`

**Issue:** `getEnvDefault("TEMPORAL_HOST", "localhost:7233")` means `cfg.TemporalHost` is never empty — it always falls back to `"localhost:7233"`. The `main.go` guard `if cfg.TemporalHost != ""` therefore always evaluates true, and the process always attempts to dial Temporal at startup. The intent, documented in the comment on line 80 (`When TEMPORAL_HOST is empty we skip the dial entirely`), can never be triggered. Operators who want a deployment without Temporal must set `TEMPORAL_HOST=` (empty string), which is counter-intuitive with `getEnvDefault` semantics.

**Fix:** Use an empty default for `TEMPORAL_HOST` so the "skip Temporal" behavior works as documented:

```go
TemporalHost: os.Getenv("TEMPORAL_HOST"),
// Remove the getEnvDefault wrapper — empty means "no Temporal"
```

If Temporal is required in some environments, add explicit validation instead of a silent default.

---

### WR-02: `server.Shutdown` creates a nested timeout context, ignoring the caller's deadline

**File:** `api/internal/server/server.go:134-139`

**Issue:** `Shutdown(ctx context.Context)` immediately creates a new `context.WithTimeout(ctx, 10*time.Second)`. The caller in `main.go` already creates a 15-second timeout context (`shutdownCtx`) and passes it to `srv.Shutdown`. `Shutdown` ignores the caller's deadline and replaces it with a new 10-second one derived from the caller's context. If the caller's context has already been cancelled (e.g., a tight outer timeout), the inner 10-second timeout will also be cancelled immediately. This is the expected behavior for context derivation, but the 10-second cap embedded in `Shutdown` makes the 15-second outer timeout in `main.go` misleading — the effective shutdown window is always 10 seconds. The two timeouts are inconsistent and will confuse operators reading the logs.

**Fix:** Remove the internal timeout from `Shutdown` and honor only the caller's deadline:

```go
func (s *Server) Shutdown(ctx context.Context) error {
    s.Logger.Info().Msg("shutting down server")
    return s.Echo.Shutdown(ctx)
}
```

The caller in `main.go` already provides a deadline. Let the caller own the policy.

---

### WR-03: `devauth_test.go` port selection has a low-probability collision

**File:** `api/internal/handler/devauth_test.go:31` and `api/pkg/migrate/migrate_test.go:25`

**Issue:** Both test files pick an embedded-postgres port via `time.Now().UnixNano() % 1000`. With modulus 1000 the port range is fixed (e.g., 46500–47499 and 45433–46432 respectively). If two test binaries run in parallel on the same machine (e.g., `go test ./...` with default parallelism), they can select the same port simultaneously, causing a "port already in use" failure that is not deterministic and is hard to diagnose.

**Fix:** Use `net.Listen("tcp", ":0")` to acquire an ephemeral OS-assigned port, then close the listener and pass that port to embedded-postgres:

```go
l, err := net.Listen("tcp", ":0")
require.NoError(t, err)
port := uint32(l.Addr().(*net.TCPAddr).Port)
l.Close()
```

This is a common Go test pattern that eliminates the collision risk.

---

### WR-04: `docker/runner.go` — `envKeyPattern` rejects lowercase env var keys used by some valid tooling

**File:** `api/pkg/docker/runner.go:318`

**Issue:** `envKeyPattern = regexp.MustCompile(`^[A-Z_][A-Z0-9_]*$`)` rejects any env var key that contains lowercase letters, such as `http_proxy`, `https_proxy`, `no_proxy` (all lowercase by POSIX convention and used by Go's `net/http` and `curl`). Container recipes that depend on proxy vars or any tool using lowercase env keys will silently fail validation. The test suite confirms this: `"lowercase=bad"` is in the "invalid" list, but many real-world containers and tools use lowercase env vars.

**Fix:** Accept both cases in the key pattern, or document that callers must uppercase all keys:

```go
// Accept POSIX-style keys: upper- or lower-case, starting with letter or underscore.
envKeyPattern = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)
```

---

### WR-05: `migrate.go` — no rollback of already-applied migrations if a later migration fails

**File:** `api/pkg/migrate/migrate.go:158-167`

**Issue:** If migration 001 applies successfully but migration 002 fails mid-way, `Run()` returns an error but migration 001 is permanently recorded in `schema_migrations`. On the next restart, migration 001 is skipped (already recorded), and migration 002 is retried from the beginning. If migration 002's SQL is not idempotent (e.g., `ALTER TABLE ADD COLUMN` without `IF NOT EXISTS`), the retry will also fail, leaving the database in a permanently broken state. This is an edge case for Phase 1 (only one migration exists), but the current design gives no rollback option.

**Fix:** Wrap each migration's `Exec + INSERT` in a database transaction so partial migration SQL is rolled back on failure. This requires extending the `DB` interface to expose `Begin`, or switching to `*pgx.Conn` for the migration runner (which already has transaction support via `pgx.Tx`). At minimum, document in a code comment that each migration SQL file must be idempotent.

---

### WR-06: `web/src/middleware.ts` comment claims Next.js 16 renamed `middleware.ts` to `proxy.ts` — this appears incorrect and may cause a future migration mistake

**File:** `web/src/middleware.ts:18-19`

**Issue:** The comment states: _"Note: Next.js 16 renamed the `middleware` file convention to `proxy`, but the `middleware.ts` file is still supported (deprecated). Phase 3 (auth) will migrate this to `proxy.ts` alongside the goth OAuth swap."_ Next.js 16 does NOT rename the middleware convention to `proxy.ts`. This is factually incorrect documentation. If a future developer follows this comment and renames the file to `proxy.ts`, the middleware will stop working silently.

**Fix:** Remove or correct the comment. The correct filename for Next.js middleware remains `middleware.ts` (or `middleware.js`). Check the Next.js 16 release notes (`node_modules/next/dist/docs/`) before asserting breaking API changes in comments.

---

## Info

### IN-01: `devauth.go` — `extractToken` duplicates logic already in `verifyCookie`

**File:** `api/internal/handler/devauth.go:182-193`

**Issue:** The `extractToken` function in the `handler` package re-implements cookie parsing (finding the `.`, splitting sig from token, comparing HMAC) that is already implemented (and constant-time) in `middleware.verifyCookie`. The duplication means if the cookie format ever changes, two places must be updated. See CR-01 for the security implication of this duplication.

**Fix:** Export `verifyCookie` from the middleware package (rename to `VerifyCookie`) and use it from `extractToken`, or make `extractToken` a thin wrapper as shown in CR-01.

---

### IN-02: `config.go` — `TEMPORAL_HOST` and `TEMPORAL_NAMESPACE` are always populated from defaults regardless of intent

**File:** `api/internal/config/config.go:53-54`

**Issue:** Related to WR-01. The `TemporalNamespace` default `"default"` is benign (it is the correct namespace name), but `TemporalHost` defaulting to `"localhost:7233"` masks a missing configuration in environments where Temporal is not desired. See WR-01.

---

### IN-03: `docker-compose.dev.yml` — no health check on the Temporal service

**File:** `docker-compose.dev.yml:31-45`

**Issue:** The `temporal` service depends on `postgresql` with `condition: service_healthy`, which is correct. But the `temporal-ui` service depends on `temporal` with a simple dependency (not `condition: service_healthy`), and the API itself has no compose dependency on Temporal at all. During local dev, if the API starts before Temporal is ready, the first Temporal dial will fail and the process will abort (since `NewWorkers` is called synchronously in `main.go`). The `install-temporal.sh` script compensates with a polling loop, but the compose file does not.

**Fix:** Add a health check to the `temporal` service and use `condition: service_healthy` in the `temporal-ui` depends_on:

```yaml
temporal:
  healthcheck:
    test: ["CMD", "temporal", "operator", "namespace", "list"]
    interval: 5s
    timeout: 5s
    retries: 30
    start_period: 30s
```

---

### IN-04: `web/src/lib/api.ts` — `API_BASE` is empty string in browser context when `NEXT_PUBLIC_API_URL` is unset

**File:** `web/src/lib/api.ts:5`

**Issue:** `const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""`. In the browser, if `NEXT_PUBLIC_API_URL` is not set at build time (which is common in local dev where the Next.js rewrite proxy handles `/api/*`), `API_BASE` is `""` and all fetch calls use relative URLs. This is the correct behavior for the proxy path. However, if the app is built and served from a different origin than the Go API (e.g., a CDN), `API_BASE=""` will send API calls to the CDN, not the Go API. This is a silent misconfiguration risk.

**Fix:** Document the expected values more clearly in `.env.example` and add a startup warning (or build-time assertion via `next.config.ts`) when running in production mode with `NEXT_PUBLIC_API_URL` unset.

---

### IN-05: `install-postgres.sh` — password interpolation inside a heredoc SQL block is done via shell string substitution, not parameterized queries

**File:** `deploy/hetzner/install-postgres.sh:76-93`

**Issue:** The passwords `${AP_API_PG_PASSWORD}` and `${TEMPORAL_PG_PASSWORD}` are interpolated directly into the SQL heredoc passed to `psql`. If a password contains a single quote or a `$` character (common in randomly generated passwords), the SQL will be malformed or could be exploited if a human supplies the password. The `openssl rand -hex 24` output is hex-only and safe, but an operator who sets a custom password with punctuation could break the script or create a SQL injection in the provisioning path.

**Fix:** Use `psql`'s `--variable` / `-v` flag with `:'variable'` quoting to safely pass the password:

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 \
  -v "ap_pw=$AP_API_PG_PASSWORD" \
  -v "temporal_pw=$TEMPORAL_PG_PASSWORD" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ap_api') THEN
    CREATE ROLE ap_api LOGIN PASSWORD :'ap_pw';
  ...
SQL
```

Or use `ALTER ROLE ap_api PASSWORD $escaped$...${escaped}$` escaping. For the auto-generated hex passwords the current code is safe, but it is fragile for user-supplied passwords.

---

_Reviewed: 2026-04-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
