---
phase: 01-foundations-spikes-temporal
plan: 01
subsystem: api-skeleton
tags: [go, echo, pgx, postgres, redis, migrations, auth, dev-cookie, foundations]
requires: []
provides:
  - go-api-binary
  - http-healthz-endpoint
  - postgres-pool
  - redis-client
  - embedded-migrations
  - baseline-schema
  - session-provider-interface
  - dev-cookie-auth-stub
  - server-functional-options
affects:
  - api/cmd/server
  - api/internal
  - api/pkg
tech-stack:
  added:
    - "github.com/labstack/echo/v4 v4.15.1"
    - "github.com/jackc/pgx/v5 v5.9.1"
    - "github.com/rs/zerolog v1.35.0"
    - "github.com/redis/go-redis/v9 v9.18.0"
    - "github.com/google/uuid v1.6.0"
    - "github.com/stretchr/testify v1.11.1"
    - "github.com/fergusstrange/embedded-postgres v1.34.0"
    - "github.com/alicebob/miniredis/v2 v2.37.0"
  patterns:
    - "Functional options on server.New (Option / WithDevAuth / WithWorkers) so later plans extend the constructor without breaking callers"
    - "SessionProvider interface decoupling middleware from storage so Phase 3 can swap goth in without touching middleware/handlers"
    - "Embedded SQL migrations applied at boot via pkg/migrate (mirrors MSV)"
    - "InfraChecker / HealthChecker interface separation so /healthz can be unit-tested with a fake"
    - "HMAC-signed session cookie format <hmac_hex>.<token> with constant-time hmac.Equal verification"
    - "Token-at-rest stored as SHA-256 hash in user_sessions, never the raw cookie value"
key-files:
  created:
    - api/go.mod
    - api/cmd/server/main.go
    - api/internal/config/config.go
    - api/internal/config/config_test.go
    - api/internal/server/server.go
    - api/internal/server/integration_test.go
    - api/internal/handler/checker.go
    - api/internal/handler/health.go
    - api/internal/handler/health_test.go
    - api/internal/handler/devauth.go
    - api/internal/handler/devauth_test.go
    - api/internal/middleware/auth.go
    - api/internal/middleware/auth_test.go
    - api/pkg/database/postgres.go
    - api/pkg/redis/client.go
    - api/pkg/migrate/migrate.go
    - api/pkg/migrate/migrate_test.go
    - api/pkg/migrate/sql/001_baseline.sql
  modified: []
decisions:
  - "Mirror MSV's pkg layout verbatim (database, redis, migrate) -- direct port, no rework"
  - "Pin Echo to v4.15.1 (NOT v5) per CLAUDE.md / 01-RESEARCH.md; defer v5 migration to v2"
  - "Use pgx v5.9.1 (one minor ahead of MSV's 5.8.0) -- 01-RESEARCH.md verified"
  - "Custom embedded migrator instead of golang-migrate -- single-binary deploy, MSV pattern"
  - "Functional options pattern on server.New from day 1 so Plan 01-05 (Temporal workers) and later plans add WithFoo() without breaking signatures"
  - "SessionProvider interface defined now (Plan 01-01) so Phase 3 goth swap is an implementation change, not a refactor"
  - "Cookie value format: hmac_hex.token (constant-time HMAC equality), token stored as sha256 hex in user_sessions to keep raw cookies out of the DB"
  - "Dev login: 404 (not 401, not 403) when AP_DEV_MODE=false -- the route is dead code in production, T-1-03 mitigation"
metrics:
  duration: ~45min
  completed: 2026-04-14
  tasks: 3
  files-created: 18
  commits: 3
  test-suites: 5
  test-execution-seconds: 112
---

# Phase 1 Plan 1: API Skeleton + Auth Stub Summary

JWT-free dev cookie auth and a full Go API substrate (Echo v4 + pgx v5 + Redis + embedded migrations + functional-options server) that every later phase consumes.

## What was built

Plan 01-01 stands up the entire Go API substrate in three TDD-driven tasks. After this plan, `cd api && go build ./cmd/server/` produces a working binary that:

1. Loads config from environment with required-field validation
2. Opens a pgx connection pool (MaxConns=20, MinConns=2) and verifies it
3. Opens a go-redis client and verifies it
4. Runs idempotent embedded SQL migrations on every boot
5. Serves `/healthz` with per-component database + Redis health checks
6. Serves `/api/dev/login`, `/api/dev/logout`, `/api/me` behind HMAC-signed HTTP-only cookies (dev mode only)
7. Gracefully shuts down on SIGINT/SIGTERM

The schema plants `users`, `user_sessions`, and the multi-agent-ready `agents` table with the partial unique index `idx_agents_one_active_per_user` enforcing the v1 "1 active per user" constraint at the DB layer (D-17).

## Tasks Completed

| Task | Name | Commit | Files | Tests |
|------|------|--------|-------|-------|
| 1 | Module init + config + db + redis + migrations + health | `a9b4df9` | 14 created | config (7), health (3), migrate (2 with embedded-postgres) |
| 2 | Dev cookie auth stub + SessionProvider interface | `db481dd` | 4 created, 2 modified | middleware (5), devauth (4 with embedded-postgres) |
| 3 | End-to-end integration smoke test | `482bd8f` | 1 created | integration FullFlow + NoOptionsWiring |

## Architecture Highlights

### Functional options on `server.New`

```go
func New(cfg *config.Config, logger zerolog.Logger, checker handler.HealthChecker, opts ...Option) *Server
```

Plan 01-01 ships two options:

- `WithDevAuth(handler, provider)` — mounts `/api/dev/*` and the AuthMiddleware-protected `/api/me`
- `WithWorkers(w)` — declared, not used yet; Plan 01-05 attaches Temporal workers through this

`TestIntegration_NoOptionsWiring` calls `server.New(cfg, logger, checker)` with **zero options** and asserts that `/healthz` works while `/api/me` returns 404 (not mounted). This locks in the backward-compatibility guarantee.

### `SessionProvider` is the Phase 3 swap surface

```go
type SessionProvider interface {
    CreateSession(ctx context.Context, userID uuid.UUID) (token string, err error)
    ValidateSession(ctx context.Context, token string) (userID uuid.UUID, err error)
    DestroySession(ctx context.Context, token string) error
}
```

Plan 01-01 ships `DevSessionStore` (Postgres-backed, sha256-hashed token storage). Phase 3 will ship `GothSessionStore` (Google + GitHub OAuth) with the **same interface** — middleware, handlers, and routes do not change.

A compile-time `var _ middleware.SessionProvider = (*handler.DevSessionStore)(nil)` assertion lives in the integration test so any future divergence is caught at build time.

### Cookie format

`<hmac_hex>.<token>` where `hmac_hex` is HMAC-SHA256(secret, token). Verified with `hmac.Equal` (constant-time). The raw token is the cookie value; the database stores `sha256(token)` in `user_sessions.token_hash`. Stealing the DB does not give an attacker working cookies; stealing a cookie does not let them rotate or forge new ones.

## Verification

Final test run (full suite, no `-short`):

```
ok  github.com/agentplayground/api/internal/config       0.389s
ok  github.com/agentplayground/api/internal/handler     55.799s
ok  github.com/agentplayground/api/internal/middleware   0.958s
ok  github.com/agentplayground/api/internal/server      20.039s
ok  github.com/agentplayground/api/pkg/migrate          34.812s
```

`go build ./cmd/server/` produces a 16.7 MB binary. `go vet ./...` is clean.

## Acceptance Criteria

All Task 1 / Task 2 / Task 3 acceptance criteria from `01-01-PLAN.md` pass:

- `api/go.mod` contains `module github.com/agentplayground/api` plus `echo/v4 v4.15.1` and `pgx/v5`
- `api/internal/config/config.go` exposes `Load()`, `DATABASE_URL`, `AP_DEV_MODE`, `AP_SESSION_SECRET`
- `api/pkg/database/postgres.go` has `func New(ctx, databaseURL, logger)` and `MaxConns`
- `api/pkg/redis/client.go` has `func New(ctx, redisURL, logger)`
- `api/pkg/migrate/migrate.go` uses `//go:embed sql/*.sql` and tracks `schema_migrations`
- `api/pkg/migrate/sql/001_baseline.sql` creates all three tables and the partial unique index
- `api/internal/handler/health.go` serves `Health(c echo.Context) error`
- `api/internal/handler/checker.go` defines `HealthChecker`, `PingDB`, `PingRedis`
- `api/internal/server/server.go` contains `type Option func`, `opts ...Option`, registers `e.GET("/healthz"`, `HideBanner`
- `api/internal/middleware/auth.go` defines `SessionProvider`, `CreateSession`, `ValidateSession`, `DestroySession`, references `ap_session` and `crypto/hmac`
- `api/internal/handler/devauth.go` has `Login`, references `devMode`, `HttpOnly`, `SameSite`, `ON CONFLICT`
- `api/internal/server/server.go` mounts `/api/dev/login`, `/api/dev/logout`, `/api/me` (via WithDevAuth)
- `api/internal/server/integration_test.go` exercises `TestIntegration_FullFlow` against embedded-postgres + miniredis with `server.New(...)` plus a no-options variant
- `cd api && go build ./cmd/server/` exits 0
- `cd api && go test ./... -count=1` exits 0
- `cd api && go vet ./...` clean

## Threat Model Disposition

Each STRIDE entry from the plan was applied during implementation:

| ID | Threat | How addressed |
|----|--------|---------------|
| T-1-01 | Cookie spoofing | HMAC-SHA256 sig on cookie value, verified with `hmac.Equal` |
| T-1-02 | Cookie tampering | Same HMAC verification; DB stores sha256 of token, never raw value |
| T-1-03 | `/api/dev/login` in production | Handler returns 404 when `cfg.DevMode` is false |
| T-1-04 | SQL injection via dev login | All queries use pgx `$N` parameterized placeholders -- no string interpolation |
| T-1-05 | `/healthz` DoS | Accepted; rate limiting deferred to OSS-07 (Phase 7) |
| T-1-06 | Audit gap on dev login | Accepted; dev mode only, audit log lands in OSS-08 (Phase 7) |

## Deviations from Plan

None. Plan executed exactly as written. The plan was thorough enough to require zero auto-fixes:

- All required env vars and validation rules already specified
- Functional options pattern signature pre-decided (variadic ...Option)
- Cookie format and hashing strategy spelled out
- D-17 partial unique index DDL provided verbatim
- Test framework choices (testify + embedded-postgres + miniredis) pre-pinned

Two minor implementation choices made within Claude's discretion (per plan):

1. **`Login` handler accepts an empty body.** The plan's behavior list says the JSON body is "optional ... with defaults if empty"; the handler only attempts JSON decode when `ContentLength > 0`. This makes `curl -X POST /api/dev/login` work with no flags.
2. **`server.New` builds the `/api` group AFTER applying options.** Necessary so `WithDevAuth` can supply the handler/provider before route registration. No external visibility — callers pass options, routes appear if and only if the option was supplied.

## Authentication Gates

None encountered. All work was local: embedded-postgres + miniredis + `go test`. No external API keys, no OAuth callbacks, no Stripe webhooks (Phase 6 territory).

## What's Next

Plan 01-01 unlocks every other Phase 1 plan:

- **Plan 01-02** (Hetzner provisioning + docker-compose.dev.yml) can now reference the Go binary that's expected to land in containers
- **Plan 01-03** (Next.js 16 mobile-first shell) consumes the `/api/dev/login` and `/api/me` endpoints
- **Plan 01-04** (`pkg/docker/runner.go`) lives next to this code in `api/pkg/`
- **Plan 01-05** (Temporal worker) attaches via `server.WithWorkers(...)` -- the option is already declared
- **Plan 01-06** (FND-07 spike report) is independent

Phase 3 (auth) will replace `DevSessionStore` with a goth-backed implementation behind the same `SessionProvider` interface — no changes required to middleware, server, or routes.

## Self-Check: PASSED

**Files verified to exist:**
- api/cmd/server/main.go FOUND
- api/go.mod FOUND
- api/internal/config/config.go FOUND
- api/internal/config/config_test.go FOUND
- api/internal/server/server.go FOUND
- api/internal/server/integration_test.go FOUND
- api/internal/handler/checker.go FOUND
- api/internal/handler/health.go FOUND
- api/internal/handler/health_test.go FOUND
- api/internal/handler/devauth.go FOUND
- api/internal/handler/devauth_test.go FOUND
- api/internal/middleware/auth.go FOUND
- api/internal/middleware/auth_test.go FOUND
- api/pkg/database/postgres.go FOUND
- api/pkg/redis/client.go FOUND
- api/pkg/migrate/migrate.go FOUND
- api/pkg/migrate/migrate_test.go FOUND
- api/pkg/migrate/sql/001_baseline.sql FOUND

**Commits verified to exist:**
- a9b4df9 FOUND (Task 1: skeleton)
- db481dd FOUND (Task 2: dev cookie auth)
- 482bd8f FOUND (Task 3: integration test)

**Build + tests:**
- `cd api && go build ./cmd/server/` exits 0 (16.7 MB binary)
- `cd api && go vet ./...` clean
- `cd api && go test ./... -count=1` all packages PASS
