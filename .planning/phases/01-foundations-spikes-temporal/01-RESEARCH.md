# Phase 01: Foundations, Spikes & Temporal - Research

**Researched:** 2026-04-13
**Domain:** Go API skeleton + Next.js shell + Temporal + Docker runner + Hetzner provisioning + spike investigations
**Confidence:** HIGH

## Summary

Phase 1 bootstraps the entire project substrate. Every subsequent phase depends on the Go API binary (Echo v4 + pgx v5 + zerolog), the Next.js 16 frontend shell, Temporal worker infrastructure, Docker runner, Postgres 17 + Redis 7 on the host, and the baseline schema. The MSV codebase at `/Users/fcavalcanti/dev/meusecretariovirtual/api/` provides directly portable patterns for database setup (`pkg/database/postgres.go`), Redis client (`pkg/redis/client.go`), embedded migrations (`pkg/migrate/migrate.go`), server skeleton (`internal/server/server.go`), health checks (`internal/handler/health.go`), config loading (`internal/config/config.go`), and Docker runner (`pkg/docker/runner.go`). These are not aspirational -- they are verified, working code that maps 1:1 to Phase 1 requirements.

Temporal is the one area where MSV's pattern is light -- MSV only creates a Temporal client optionally and uses it for executor workflows. Agent Playground needs a full worker setup with three task queues (`session`, `billing`, `reconciliation`) and registered stub workflows from day 1. The `temporalio/auto-setup` Docker image handles schema provisioning automatically, and the Go SDK v1.42.0 provides a clean worker/workflow/activity registration API.

The spike report (FND-07) requires hands-on testing of four unknowns: per-agent `HTTPS_PROXY` vs `*_BASE_URL` behavior, `chat_io.mode` per agent, tmux + named-pipe round-trip latency, and gVisor `runsc` feasibility on the Hetzner kernel. These are empirical tests that cannot be resolved by documentation alone -- the planner must schedule them as distinct tasks with explicit pass/fail criteria.

**Primary recommendation:** Port MSV's `pkg/` and `internal/` skeleton verbatim (database, redis, migrate, server, config, handler/health, docker/runner), add Temporal worker setup with stub workflows, write the baseline migration with the agents table, and stand up the Next.js 16 mobile-first shell. The spike report is a parallel workstream that tests on the actual Hetzner host.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Mirror MSV shape -- `api/` (Go) + `web/` (Next.js) + `deploy/` (provisioning scripts + compose files) at repo root
- **D-02:** Ship `docker-compose.dev.yml` that brings up Postgres 17 + Redis 7 + Temporal (auto-setup) locally -- contributors can hack without a Hetzner box from day 1
- **D-03:** Tests use `embedded-postgres` per MSV pattern; docker-compose.dev is for running the full stack locally, not for test isolation
- **D-04:** Idempotent shell scripts in `deploy/hetzner/` -- `bootstrap.sh`, `install-docker.sh`, `install-postgres.sh`, `install-redis.sh`, `install-temporal.sh`, `harden-ufw.sh` -- all committed, all re-runnable
- **D-05:** OSS-06 self-hosted deployment guide (Phase 7) will reference these scripts directly -- they are the production runbook
- **D-06:** `temporalio/auto-setup` as a docker-compose service, same image in dev and prod -- one deployment artifact
- **D-07:** Temporal persists to Postgres 17 (separate `temporal` schema/database), bound to `127.0.0.1:7233`
- **D-08:** Temporal Web UI as a companion compose service on `127.0.0.1:8233`
- **D-09:** Dev-cookie auth stub: `POST /api/dev/login` (enabled only when `AP_DEV_MODE=true`) sets a signed HTTP-only session cookie; auth middleware reads it on every protected route. Phase 3 swaps `goth` behind the same middleware interface -- zero frontend churn.
- **D-10:** Migration `0001_baseline.sql` creates `users`, `user_sessions`, and `agents` tables as specified
- **D-11:** Phase 1 does NOT populate or exercise the `agents` table beyond schema creation
- **D-12:** All frontend work is mobile-first -- design for mobile viewport, scale up to desktop
- **D-13:** Touch-friendly targets (min 44px), responsive breakpoints, standard shadcn/ui mobile patterns
- **D-14:** Phase 1 landing page must look and feel good on a phone
- **D-15:** Each user can create N agent instances -- each is its own dockerized container
- **D-16:** On the mobile UI, agents appear as tabs for quick-switch chat (Phase 5 builds this; Phase 1 ships the schema)
- **D-17:** v1 enforces 1 active (running) agent at a time -- but schema, API types, and UI components are designed for N-active
- **D-18:** "Active" means a running container the user can chat with via a tab

### Claude's Discretion
- Mobile navigation pattern (bottom tabs, drawer, etc.)
- Exact breakpoints, spacing, and typography
- Loading states, skeleton design, error states
- Dev login page styling and layout
- docker-compose.dev.yml exact service configuration
- Spike report format and structure

### Deferred Ideas (OUT OF SCOPE)
- SSH access to agent containers (Phase 5)
- Webhook URL per agent (Phase 5)
- Native app / installable PWA (v2)
- PROJECT.md + REQUIREMENTS.md text updates (capture before planning but not code work)
- Multi-agent concurrent billing (Phase 6/v2)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FND-01 | Hetzner host with Docker 27.x + `userns-remap` | Deploy scripts section, Docker daemon.json config pattern, UFW hardening |
| FND-02 | Postgres 17 + Redis 7 as loopback-bound systemd services | Deploy scripts section, docker-compose.dev.yml for local dev |
| FND-03 | Go 1.25 + Echo v4.15 + pgx v5.8 serving `/healthz` | MSV code port section (server.go, health.go, database.go, config.go patterns) |
| FND-04 | Next.js 16.2 mobile-first login-gated landing page | Next.js + Tailwind v4 + shadcn/ui section, mobile-first patterns |
| FND-05 | `golang-migrate`-driven schema migration at API start | MSV migrate.go embedded pattern, migration file naming |
| FND-06 | `pkg/docker/runner.go` ported from MSV | MSV runner analysis, required method additions (run, exec, inspect, rm) |
| FND-07 | Spike report: HTTPS_PROXY, chat_io, tmux pipes, gVisor | Spike methodology section |
| FND-08 | Temporal server + Go worker with registered workflows | Temporal setup section, docker-compose config, worker code pattern |
| FND-09 | Temporal namespace + 3 task queues observable via tctl/Web UI | Temporal namespace/task queue config, CLI registration |
| FND-10 | Baseline migration with `agents` table | Schema design section with exact DDL |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech stack**: Go API + Next.js frontend, mirror MSV patterns
- **Workflow engine**: Temporal (user override -- do NOT recommend alternatives)
- **Infra**: Hetzner dedicated box, Docker on host
- **Auth**: Phase 1 uses dev-cookie stub; Phase 3 swaps goth (Google + GitHub OAuth)
- **Code change protocol**: Never change code not directly asked for without user confirmation
- **Process management**: Always kill previous process before starting app
- **Testing**: Check test folders before testing; study test folder structure
- **Commits**: Only commit and push when asked by user

## Standard Stack

### Core (Go Backend -- Phase 1)

| Library | Version | Purpose | Verified |
|---------|---------|---------|----------|
| Go | 1.25.x | Runtime | MSV uses 1.25.6; local is 1.25.3 [VERIFIED: go version] |
| `github.com/labstack/echo/v4` | v4.15.1 | HTTP framework | [VERIFIED: Go proxy, 2026-02-22] |
| `github.com/jackc/pgx/v5` + `pgxpool` | v5.9.1 | Postgres driver + pool | [VERIFIED: Go proxy, 2026-03-22] MSV pins v5.8.0; use latest v5.9.1 |
| `github.com/rs/zerolog` | v1.35.0 | Structured logging | [VERIFIED: Go proxy, 2026-03-27] MSV pins v1.34.0 |
| `github.com/redis/go-redis/v9` | v9.18.0 | Redis client | [VERIFIED: Go proxy, 2026-02-16] |
| `go.temporal.io/sdk` | v1.42.0 | Temporal worker + client | [VERIFIED: Go proxy, 2026-04-08] MSV pins v1.40.0 |
| `github.com/google/uuid` | v1.6.0 | UUIDv7 generation | [VERIFIED: Go proxy] |

### Core (Frontend -- Phase 1)

| Library | Version | Purpose | Verified |
|---------|---------|---------|----------|
| `next` | 16.2.3 | App Router framework | [VERIFIED: npm registry] |
| `react` / `react-dom` | 19.2.5 | UI runtime | [VERIFIED: npm registry] |
| `tailwindcss` | 4.2.2 | Styling (CSS-first config) | [VERIFIED: npm registry] |
| `shadcn` (CLI) | 4.2.0 | Component generator | [VERIFIED: npm registry] |

### Supporting (Go Backend)

| Library | Version | Purpose | Verified |
|---------|---------|---------|----------|
| `github.com/stretchr/testify` | v1.11.1 | Test assertions | [VERIFIED: Go proxy] |
| `github.com/fergusstrange/embedded-postgres` | v1.34.0 | Test DB | [VERIFIED: Go proxy, 2026-03-17] |
| `github.com/pashagolub/pgxmock/v4` | v4.9.0 | Postgres mock | [VERIFIED: Go proxy] |
| `github.com/alicebob/miniredis/v2` | v2.37.0 | Redis mock | [VERIFIED: Go proxy, 2026-02-25] |
| `github.com/coder/websocket` | v1.8.14 | WebSocket (future phases) | [VERIFIED: Go proxy] |

### Not Used in Phase 1

These are in the project stack but NOT needed yet:
- `moby/moby/client` -- Phase 1 runner uses CLI via `os/exec` (MSV pattern); SDK comes in Phase 5 if needed
- `markbates/goth` -- Phase 3 (auth)
- `stripe-go/v82` -- Phase 6 (billing)
- `@xterm/xterm` -- Phase 5 (terminal)

**Installation (Go):**
```bash
cd api && go mod init github.com/agentplayground/api
go get github.com/labstack/echo/v4@v4.15.1
go get github.com/jackc/pgx/v5@v5.9.1
go get github.com/rs/zerolog@v1.35.0
go get github.com/redis/go-redis/v9@v9.18.0
go get go.temporal.io/sdk@v1.42.0
go get github.com/google/uuid@v1.6.0
go get github.com/stretchr/testify@v1.11.1
go get github.com/fergusstrange/embedded-postgres@v1.34.0
go get github.com/pashagolub/pgxmock/v4@v4.9.0
go get github.com/alicebob/miniredis/v2@v2.37.0
```

**Installation (Frontend):**
```bash
cd web && pnpm create next-app@latest . --app --ts --tailwind --eslint --src-dir --import-alias "@/*"
pnpm dlx shadcn@latest init
```

## Architecture Patterns

### Recommended Project Structure

```
agent-playground/
├── api/                          # Go backend
│   ├── cmd/
│   │   └── server/
│   │       └── main.go           # Entry point: config, DB, Redis, Temporal, Echo, migrations
│   ├── internal/
│   │   ├── config/
│   │   │   └── config.go         # Env-based config (mirror MSV pattern)
│   │   ├── handler/
│   │   │   ├── health.go         # GET /healthz - DB + Redis ping
│   │   │   ├── health_test.go
│   │   │   ├── checker.go        # InfraChecker implements HealthChecker interface
│   │   │   └── devauth.go        # POST /api/dev/login (dev mode only)
│   │   ├── middleware/
│   │   │   ├── auth.go           # Session cookie middleware (reads signed cookie, extracts user)
│   │   │   ├── auth_test.go
│   │   │   └── ratelimit.go      # Token bucket rate limiter (mirror MSV)
│   │   ├── server/
│   │   │   └── server.go         # Echo setup: HideBanner, Recover, RequestID
│   │   └── temporal/
│   │       ├── worker.go         # Worker setup: 3 task queues, workflow/activity registration
│   │       ├── workflows.go      # Stub workflows: PingPong, SessionSpawn, SessionDestroy, etc.
│   │       └── activities.go     # Stub activities
│   ├── pkg/
│   │   ├── database/
│   │   │   └── postgres.go       # pgxpool wrapper (mirror MSV)
│   │   ├── redis/
│   │   │   └── client.go         # go-redis wrapper (mirror MSV)
│   │   ├── migrate/
│   │   │   ├── migrate.go        # Embedded FS migrator (mirror MSV)
│   │   │   ├── migrate_test.go
│   │   │   └── sql/
│   │   │       └── 001_baseline.sql
│   │   └── docker/
│   │       ├── runner.go          # Ported from MSV + run/exec/inspect/rm additions
│   │       └── runner_test.go
│   ├── go.mod
│   └── go.sum
├── web/                          # Next.js frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx        # Root layout: mobile viewport meta, font, Tailwind
│   │   │   ├── page.tsx          # Landing page (login-gated, mobile-first)
│   │   │   ├── login/
│   │   │   │   └── page.tsx      # Dev login page
│   │   │   └── globals.css       # Tailwind v4: @import "tailwindcss"
│   │   ├── components/
│   │   │   └── ui/               # shadcn/ui components (copied in)
│   │   ├── lib/
│   │   │   ├── api.ts            # Fetch wrapper for Go API
│   │   │   └── auth.ts           # Cookie-based auth helpers
│   │   └── middleware.ts         # Next.js middleware: redirect unauthenticated to /login
│   ├── package.json
│   ├── next.config.ts
│   └── tailwind.config.ts        # Tailwind v4 may not need this (CSS-first)
├── deploy/
│   ├── hetzner/
│   │   ├── bootstrap.sh          # Master script, calls all others idempotently
│   │   ├── install-docker.sh     # Docker 27.x + userns-remap
│   │   ├── install-postgres.sh   # Postgres 17 as systemd service
│   │   ├── install-redis.sh      # Redis 7 as systemd service
│   │   ├── install-temporal.sh   # Temporal via docker-compose (auto-setup)
│   │   └── harden-ufw.sh         # UFW: allow 443, deny rest
│   └── docker-compose.dev.yml    # Local dev: PG + Redis + Temporal + UI
├── docker-compose.yml            # Prod: Temporal + UI (PG/Redis are systemd on host)
├── .planning/                    # GSD artifacts
└── CLAUDE.md
```

### Pattern 1: MSV Server Skeleton (Echo Setup)
**What:** Minimal Echo server with health check, middleware, graceful shutdown
**When to use:** The exact pattern for `api/internal/server/server.go`
**Example:**
```go
// Source: MSV api/internal/server/server.go [VERIFIED: local file read]
func New(cfg *config.Config, logger zerolog.Logger, checker handler.HealthChecker) *Server {
    e := echo.New()
    e.HideBanner = true
    e.HidePort = true
    e.Use(echomw.Recover())
    e.Use(echomw.RequestID())

    healthHandler := handler.NewHealthHandler(checker)
    e.GET("/healthz", healthHandler.Health)  // Note: /healthz for AP, MSV uses /health

    return &Server{Echo: e, Config: cfg, Logger: logger}
}
```

### Pattern 2: MSV Database Pool
**What:** pgxpool wrapper with connection config
**When to use:** `api/pkg/database/postgres.go`
**Example:**
```go
// Source: MSV api/pkg/database/postgres.go [VERIFIED: local file read]
func New(ctx context.Context, databaseURL string, logger zerolog.Logger) (*DB, error) {
    poolCfg, err := pgxpool.ParseConfig(databaseURL)
    if err != nil { return nil, fmt.Errorf("parse database URL: %w", err) }
    poolCfg.MaxConns = 20
    poolCfg.MinConns = 2
    pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
    // ... ping, return &DB{Pool: pool, Logger: logger}
}
```

### Pattern 3: MSV Embedded Migrations
**What:** SQL files embedded via `//go:embed`, run at boot, idempotent
**When to use:** `api/pkg/migrate/migrate.go`
**Example:**
```go
// Source: MSV api/pkg/migrate/migrate.go [VERIFIED: local file read]
//go:embed sql/*.sql
var embeddedFS embed.FS

// Migration file naming: NNN_name.sql (e.g., 001_baseline.sql)
// Migrator creates schema_migrations table, checks version, applies in order
```
**Critical detail:** MSV's migrator is custom (not `golang-migrate` library). It uses pgx directly, embeds SQL files, and tracks applied versions in a `schema_migrations` table. The CLAUDE.md says "golang-migrate" but MSV implements its own. **Recommendation: Port MSV's custom migrator** -- it's simpler (160 lines), uses pgx natively, and avoids the `golang-migrate` library's `database/sql` adapter complexity. The naming convention (`NNN_name.sql`) is identical. [VERIFIED: MSV source code read]

### Pattern 4: MSV Config Pattern
**What:** Environment-variable-based config with required/optional fields and defaults
**When to use:** `api/internal/config/config.go`
**Example:**
```go
// Source: MSV api/internal/config/config.go [VERIFIED: local file read]
// Required: DATABASE_URL, must fail if missing
// Optional with defaults: REDIS_URL (redis://localhost:6379), LOG_LEVEL (info), API_PORT (8080)
// Temporal: TEMPORAL_HOST (optional, empty = Temporal disabled), TEMPORAL_NAMESPACE (default: "default")
```

### Pattern 5: Temporal Worker Setup
**What:** Create client, create worker per task queue, register workflows/activities, start
**When to use:** `api/internal/temporal/worker.go`
**Example:**
```go
// Source: Temporal Go SDK docs + blog [CITED: glukhov.org/post/2026/03/workflow-applications-temporal-in-go/]
c, err := client.Dial(client.Options{
    HostPort:  cfg.TemporalHost,
    Namespace: cfg.TemporalNamespace,
})
defer c.Close()

// One worker per task queue
sessionWorker := worker.New(c, "session", worker.Options{})
sessionWorker.RegisterWorkflow(workflows.PingPong)
sessionWorker.RegisterWorkflow(workflows.SessionSpawn)
sessionWorker.RegisterWorkflow(workflows.SessionDestroy)
sessionWorker.RegisterActivity(activities.PingActivity)

billingWorker := worker.New(c, "billing", worker.Options{})
billingWorker.RegisterWorkflow(workflows.ReconcileBilling)

reconWorker := worker.New(c, "reconciliation", worker.Options{})
reconWorker.RegisterWorkflow(workflows.ReconcileContainers)

// Start all workers (non-blocking)
sessionWorker.Start()
billingWorker.Start()
reconWorker.Start()
```

### Pattern 6: Dev-Cookie Auth Stub
**What:** HMAC-signed session cookie for dev mode; swappable interface for Phase 3
**When to use:** `api/internal/middleware/auth.go` + `api/internal/handler/devauth.go`
**Example:**
```go
// Source: Alex Edwards blog + gorilla/securecookie pattern [CITED: alexedwards.net/blog/working-with-cookies-in-go]
// Interface that Phase 3 swaps behind:
type SessionProvider interface {
    CreateSession(ctx context.Context, userID uuid.UUID) (token string, err error)
    ValidateSession(ctx context.Context, token string) (userID uuid.UUID, err error)
    DestroySession(ctx context.Context, token string) error
}

// Dev implementation: POST /api/dev/login with {email, display_name}
// 1. Upsert user in DB
// 2. Create user_sessions row with random token
// 3. HMAC-sign the token: hmac.New(sha256.New, []byte(cfg.SessionSecret))
// 4. Set HTTP-only cookie: ap_session=<hmac_hex>.<token_hex>; Path=/; HttpOnly; SameSite=Lax
// Auth middleware: split cookie, verify HMAC, look up session row, inject user into echo.Context
```

### Anti-Patterns to Avoid
- **Using `golang-migrate` library when MSV has a working custom migrator:** The custom migrator is simpler, uses pgx natively, and avoids the `database/sql` adapter. Port it.
- **Using Docker SDK (moby/moby/client) in Phase 1:** MSV's runner uses `os/exec` with strict validation. Port that pattern; Phase 5 can evaluate SDK migration if `exec` proves limiting.
- **Putting Temporal worker in a separate binary:** Keep it in the same Go binary as the API server. MSV does the same -- one binary, one deploy unit.
- **Using JWT tokens for dev auth:** Cookie + server-side session is the locked pattern. JWT creates a different auth model that won't map to Phase 3's goth integration.
- **Building Tailwind v3-style config files:** Tailwind v4 uses CSS-first configuration (`@import "tailwindcss"` in CSS). No `tailwind.config.js` needed for basic setup.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Database migrations | Custom migration framework | MSV's `pkg/migrate` pattern (already custom, 160 lines) | Battle-tested, embedded FS, pgx-native [VERIFIED: MSV source] |
| Session cookie signing | Raw crypto/hmac | `crypto/hmac` + `crypto/rand` (stdlib) | Simple enough to hand-roll correctly with stdlib; no library needed for HMAC signing |
| Docker CLI wrapper | Raw `os/exec` without validation | MSV's `pkg/docker/runner.go` pattern with `validateContainerID` | Prevents command injection [VERIFIED: MSV source] |
| Echo middleware stack | Custom logger, recovery, request ID | `echo/v4/middleware` Recover + RequestID + custom zerolog logger | Standard Echo stack [VERIFIED: MSV source] |
| Temporal auto-setup schema | Manual SQL for Temporal tables | `temporalio/auto-setup` Docker image | Handles schema creation automatically [CITED: hub.docker.com/r/temporalio/auto-setup] |
| Mobile-responsive components | Custom CSS from scratch | shadcn/ui + Tailwind v4 responsive utilities | Pre-built, accessible, mobile-friendly [CITED: ui.shadcn.com/docs] |
| UUIDv7 generation | Custom time-ordered UUID | `github.com/google/uuid` v1.6.0 with `uuid.NewV7()` | Standard, correct implementation [VERIFIED: Go proxy] |

## Common Pitfalls

### Pitfall 1: Temporal Auto-Setup Blocks on Missing Postgres
**What goes wrong:** `temporalio/auto-setup` container starts before Postgres is ready; schema creation fails silently or the container exits
**Why it happens:** docker-compose `depends_on` only checks container start, not service readiness
**How to avoid:** Use `depends_on` with `condition: service_healthy` and add a healthcheck to the Postgres service. Also add restart: `on-failure` to the Temporal service.
**Warning signs:** Temporal container exits with code 1; `tctl namespace list` returns connection refused
```yaml
# docker-compose.dev.yml pattern
postgresql:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U temporal"]
    interval: 5s
    timeout: 5s
    retries: 10
temporal:
  depends_on:
    postgresql:
      condition: service_healthy
```

### Pitfall 2: MSV Runner Uses CLI, Not SDK
**What goes wrong:** Developer assumes `pkg/docker/runner.go` uses the Docker SDK; tries to add `run`, `exec`, `inspect` via SDK calls alongside CLI calls
**Why it happens:** CLAUDE.md mentions `moby/moby/client` as the recommended SDK, but MSV's actual code shells out to `docker` via `os/exec`
**How to avoid:** Phase 1 ports MSV's CLI pattern verbatim. The runner interface abstracts the implementation -- Phase 5 can swap in SDK calls behind the same interface if needed.
**Warning signs:** Mixed `os/exec` and SDK calls in the same package; error handling diverges

### Pitfall 3: Embedded Postgres Test Isolation
**What goes wrong:** Tests that share a single embedded-postgres instance corrupt each other's data
**Why it happens:** Parallel test execution without per-test schemas or transactions
**How to avoid:** Each test function should either: (a) use a unique schema via `CREATE SCHEMA test_xxx`, (b) wrap in a transaction that's rolled back, or (c) start a fresh embedded-postgres per test suite (slower but bulletproof). MSV uses option (c) sparingly.
**Warning signs:** Tests pass individually but fail when run together

### Pitfall 4: Tailwind v4 CSS-First Config
**What goes wrong:** Developer creates `tailwind.config.js` like v3; none of the configuration applies
**Why it happens:** Tailwind v4 moved to CSS-first configuration with `@theme` directive
**How to avoid:** Use `@import "tailwindcss"` in `globals.css`. Customize via `@theme { ... }` in CSS, not JavaScript config. shadcn/ui init handles this correctly for new projects.
**Warning signs:** Custom colors/fonts not applying despite being in config file

### Pitfall 5: Temporal Namespace Must Exist Before Worker Connects
**What goes wrong:** Worker starts, connects to Temporal, but fails because the namespace doesn't exist
**Why it happens:** `temporalio/auto-setup` creates the `default` namespace automatically, but custom namespaces (if used) must be created via CLI
**How to avoid:** Use the `default` namespace in Phase 1. If a custom namespace is needed, create it in `install-temporal.sh` or the compose entrypoint. The `temporal` CLI can do this: `temporal operator namespace create --namespace agent-playground`.
**Warning signs:** Worker logs "namespace not found" error

### Pitfall 6: Next.js Middleware Auth Redirect Loop
**What goes wrong:** Next.js middleware redirects to `/login`, which itself requires auth, creating an infinite redirect
**Why it happens:** Middleware matcher doesn't exclude public routes
**How to avoid:** Configure the middleware matcher to exclude `/login`, `/api/dev/login`, `/_next/`, `/favicon.ico`, and static assets:
```typescript
export const config = {
  matcher: ['/((?!login|api/dev|_next/static|_next/image|favicon.ico).*)'],
};
```

### Pitfall 7: Docker `userns-remap` Breaks Volume Permissions
**What goes wrong:** After enabling `userns-remap`, containers can't read/write mounted volumes
**Why it happens:** UID mapping changes which host UID owns files inside the container
**How to avoid:** Ensure the remapped subordinate UID range owns the volume directories. For Phase 1, this matters less (no persistent volumes yet), but the provisioning script should document the remapping so Phase 7 (persistent tier) doesn't hit it.
**Warning signs:** Permission denied errors inside containers on mounted paths

## MSV Code Port Analysis

### What to Port Verbatim

| MSV File | AP Destination | Changes Needed |
|----------|---------------|----------------|
| `pkg/database/postgres.go` | `api/pkg/database/postgres.go` | Change module path only |
| `pkg/redis/client.go` | `api/pkg/redis/client.go` | Change module path only |
| `pkg/migrate/migrate.go` | `api/pkg/migrate/migrate.go` | Change module path, new SQL files |
| `pkg/docker/runner.go` | `api/pkg/docker/runner.go` | Add `Run`, `Exec`, `Inspect`, `Remove` methods |
| `pkg/docker/runner_test.go` | `api/pkg/docker/runner_test.go` | Add tests for new methods |
| `internal/server/server.go` | `api/internal/server/server.go` | Change `/health` to `/healthz`, add route groups |
| `internal/handler/health.go` | `api/internal/handler/health.go` | Minor: version string source |
| `internal/handler/checker.go` | `api/internal/handler/checker.go` | Same pattern |
| `internal/config/config.go` | `api/internal/config/config.go` | Strip MSV-specific fields, add AP fields |
| `internal/middleware/ratelimit.go` | `api/internal/middleware/ratelimit.go` | Change module path, adjust paths to skip |

### What to Add (Not in MSV)

| New File | Purpose |
|----------|---------|
| `api/internal/temporal/worker.go` | Temporal worker setup with 3 task queues |
| `api/internal/temporal/workflows.go` | Stub workflows (PingPong, SessionSpawn, SessionDestroy, RecipeInstall, ReconcileContainers, ReconcileBilling) |
| `api/internal/temporal/activities.go` | Stub activities (PingActivity, etc.) |
| `api/internal/handler/devauth.go` | Dev login handler (POST /api/dev/login) |
| `api/internal/middleware/auth.go` | Session cookie auth middleware (interface-based) |
| `api/pkg/migrate/sql/001_baseline.sql` | Baseline schema (users, user_sessions, agents) |

### Runner Method Additions

MSV's runner has: `Kill` (stop), `Restart`, `Logs`, `LogsSince`, `validateContainerID`, `validateSince`.

Phase 1 needs to add for FND-06:
```go
// Run creates and starts a container. Returns container ID.
func (r *Runner) Run(ctx context.Context, image string, opts RunOptions) (string, error)

// Exec runs a command inside a running container. Returns stdout.
func (r *Runner) Exec(ctx context.Context, containerID string, cmd []string) ([]byte, error)

// Inspect returns container state (running, exited, etc).
func (r *Runner) Inspect(ctx context.Context, containerID string) (*ContainerInfo, error)

// Stop stops a running container (alias for Kill, but clearer naming).
func (r *Runner) Stop(ctx context.Context, containerID string) error

// Remove removes a stopped container.
func (r *Runner) Remove(ctx context.Context, containerID string) error
```

All must use `validateContainerID` and validate all user-controlled args. The `RunOptions` struct must validate image names (alphanumeric + `/` + `:` + `.` + `-` only), env vars (key=value format only, no shell metacharacters), and volume mounts.

## Temporal Setup Details

### docker-compose.dev.yml Temporal Services

```yaml
# Source: temporalio/docker-compose (archived) + auto-setup docs
# [CITED: github.com/temporalio/docker-compose/blob/main/docker-compose-postgres.yml]
services:
  postgresql:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: temporal
      POSTGRES_PASSWORD: temporal
      POSTGRES_DB: temporal
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U temporal"]
      interval: 5s
      timeout: 5s
      retries: 10

  temporal:
    image: temporalio/auto-setup:latest
    depends_on:
      postgresql:
        condition: service_healthy
    environment:
      - DB=postgres12
      - DB_PORT=5432
      - POSTGRES_USER=temporal
      - POSTGRES_PWD=temporal
      - POSTGRES_SEEDS=postgresql
      - DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development-sql.yaml
    ports:
      - "127.0.0.1:7233:7233"

  temporal-ui:
    image: temporalio/ui:latest
    depends_on:
      - temporal
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
      - TEMPORAL_CORS_ORIGINS=http://localhost:3000
    ports:
      - "127.0.0.1:8233:8080"   # D-08: Web UI on 8233

  redis:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

**Key decisions reflected:**
- Postgres hosts BOTH the app DB and Temporal's DB (separate databases on same instance in dev; D-07)
- Temporal bound to 127.0.0.1:7233 (D-07)
- Temporal Web UI on 127.0.0.1:8233, not 8080 (D-08, avoids conflict with API or Next.js)
- `DB=postgres12` -- this is the Temporal-internal DB driver name for Postgres [CITED: hub.docker.com/r/temporalio/auto-setup]
- `POSTGRES_SEEDS=postgresql` -- points to the compose service name

### Temporal Worker Architecture

```
Go API Binary
  ├── HTTP server (Echo)
  │   ├── /healthz
  │   ├── /api/dev/login
  │   └── /api/... (protected routes)
  ├── Temporal Client
  │   └── client.Dial(host:7233, namespace: "default")
  ├── Session Worker (task queue: "session")
  │   ├── PingPong workflow (trivial: ping -> pong, proves wiring)
  │   ├── SessionSpawn workflow (stub: logs "spawn not implemented")
  │   └── SessionDestroy workflow (stub: logs "destroy not implemented")
  ├── Billing Worker (task queue: "billing")
  │   └── ReconcileBilling workflow (stub)
  └── Reconciliation Worker (task queue: "reconciliation")
      └── ReconcileContainers workflow (stub)
```

### Namespace and Task Queue Registration

Task queues are implicit in Temporal -- they exist when a worker polls them. No pre-registration needed. [CITED: docs.temporal.io/develop/go/core-application]

The `default` namespace is auto-created by `temporalio/auto-setup`. For a custom namespace:
```bash
temporal operator namespace create --namespace agent-playground --retention 72h
```

Verification via `temporal` CLI (installed locally, version 1.6.2):
```bash
temporal operator namespace list
temporal workflow list --namespace default
# After PingPong runs:
temporal workflow show --workflow-id ping-pong-test --namespace default
```

## Baseline Migration Schema

```sql
-- 001_baseline.sql
-- Phase 1 baseline: users, sessions, agents

-- Users (OAuth-provider-agnostic for Phase 3)
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider    TEXT,          -- 'google', 'github', 'dev' (Phase 1)
    provider_sub TEXT,         -- Provider-specific user ID
    email       TEXT,
    display_name TEXT,
    avatar_url  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique per provider (one account per OAuth identity)
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_provider_sub
    ON users(provider, provider_sub) WHERE provider IS NOT NULL AND provider_sub IS NOT NULL;

-- Server-side sessions backing HTTP-only cookies
CREATE TABLE IF NOT EXISTS user_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,   -- SHA-256 of the session token
    expires_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

-- Multi-agent model (D-10, D-15..D-18)
-- Each user can create N agent instances; v1 enforces 1 active (running) at a time
CREATE TABLE IF NOT EXISTS agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    agent_type      TEXT NOT NULL,       -- 'openclaw', 'hermes', 'hiclaw', 'picoclaw', etc.
    model_provider  TEXT,                -- 'anthropic', 'openai', 'openrouter'
    model_id        TEXT,                -- 'claude-sonnet-4', 'gpt-4o', etc.
    key_source      TEXT,                -- 'byok', 'platform'
    status          TEXT NOT NULL DEFAULT 'stopped',  -- 'stopped','provisioning','ready','running','failed'
    webhook_url     TEXT,
    container_id    TEXT,
    ssh_port        INTEGER,
    config          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agents_user_id ON agents(user_id);
-- v1 enforcement: at most 1 active agent per user
-- Schema supports N-active; this partial index is the v1 limit
CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_one_active_per_user
    ON agents(user_id) WHERE status IN ('provisioning', 'ready', 'running');
```

## Hetzner Host Provisioning Scripts

### Script Patterns

All scripts in `deploy/hetzner/` must be:
- Idempotent (safe to re-run)
- Self-checking (verify state before acting)
- Logged (echo what they do)

### bootstrap.sh
```bash
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "=== Agent Playground Host Bootstrap ==="
"$SCRIPT_DIR/install-docker.sh"
"$SCRIPT_DIR/install-postgres.sh"
"$SCRIPT_DIR/install-redis.sh"
"$SCRIPT_DIR/install-temporal.sh"
"$SCRIPT_DIR/harden-ufw.sh"
echo "=== Bootstrap complete ==="
```

### install-docker.sh Key Points
- Install Docker CE 27.x from official apt repo
- Enable `userns-remap` in `/etc/docker/daemon.json`:
```json
{
    "userns-remap": "default",
    "log-driver": "json-file",
    "log-opts": { "max-size": "10m", "max-file": "3" }
}
```
- This creates the `dockremap` user and configures `/etc/subuid` + `/etc/subgid` [CITED: docs.docker.com/engine/security/userns-remap/]
- Verify: `docker info | grep -i "user namespace"` should show remapping active

### install-postgres.sh Key Points
- Install Postgres 17 from official PGDG apt repo
- Bind to 127.0.0.1 only (`listen_addresses = 'localhost'` in `postgresql.conf`)
- Create two databases: `agent_playground` (app) and `temporal` (Temporal persistence)
- Create user `ap_api` for the app, user `temporal` for Temporal
- Systemd-managed: `systemctl enable --now postgresql`

### install-redis.sh Key Points
- Install Redis 7 from official repo
- Bind to 127.0.0.1 (`bind 127.0.0.1 ::1`)
- Set `maxmemory 256mb` + `maxmemory-policy allkeys-lru`
- Systemd-managed: `systemctl enable --now redis-server`

### harden-ufw.sh Key Points
- `ufw default deny incoming`
- `ufw default allow outgoing`
- `ufw allow ssh` (port 22)
- `ufw allow 443/tcp` (HTTPS only -- SBX-07)
- `ufw --force enable`
- Postgres (5432), Redis (6379), Temporal (7233, 8233) are NOT exposed -- loopback only

## Mobile-First Frontend Patterns

### Tailwind v4 Configuration
```css
/* web/src/app/globals.css */
@import "tailwindcss";

@theme {
  --color-primary: oklch(0.7 0.15 250);
  --color-secondary: oklch(0.6 0.1 200);
  --font-sans: "Inter", system-ui, sans-serif;
  --breakpoint-sm: 640px;   /* Small tablets */
  --breakpoint-md: 768px;   /* Tablets */
  --breakpoint-lg: 1024px;  /* Desktop */
}
```
[CITED: ui.shadcn.com/docs/tailwind-v4]

### Mobile-First Principles for Phase 1
- Design at 375px viewport first (iPhone SE)
- Min touch target: 44x44px (D-13)
- Use shadcn/ui `Drawer` (Vaul-based) for mobile overlays [CITED: ui.shadcn.com/docs/components/radix/drawer]
- Bottom sheet pattern over modal dialogs on mobile
- `px-4` base padding; `sm:px-6 md:px-8` for larger screens
- Stack layout by default; grid/flex-row at `md:` breakpoint

### shadcn/ui Init
```bash
cd web
pnpm dlx shadcn@latest init
# Select: New York style, CSS variables, app/ directory
# Install starter components:
pnpm dlx shadcn@latest add button card input drawer sheet
```

### Login-Gated Landing Page (Next.js Middleware)
```typescript
// web/src/middleware.ts
import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const session = request.cookies.get('ap_session');
  if (!session) {
    return NextResponse.redirect(new URL('/login', request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!login|api|_next/static|_next/image|favicon.ico).*)'],
};
```

## Spike Report Methodology (FND-07)

### Spike 1: HTTPS_PROXY vs *_BASE_URL Per Agent
**Goal:** For each curated agent (OpenClaw, Hermes, HiClaw, PicoClaw, NanoClaw), determine which env var controls upstream model API routing.
**Method:**
1. Pull each agent's source (via clawclones catalog) 
2. Search for `HTTPS_PROXY`, `HTTP_PROXY`, `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, `OPENROUTER_BASE_URL` in source
3. Test with a local proxy that logs requests; set each env var and verify traffic routes
**Output:** Table: `| Agent | HTTPS_PROXY honored? | *_BASE_URL honored? | Both? | Notes |`

### Spike 2: chat_io.mode Per Agent  
**Goal:** Determine how each agent exposes chat I/O (stdin/stdout, named pipe, API endpoint, WebSocket, etc.)
**Method:**
1. Read agent documentation and entrypoint scripts
2. Run each agent in a container, probe I/O channels
**Output:** Table: `| Agent | chat_io.mode | stdin/stdout? | Named pipe? | API? | Notes |`

### Spike 3: tmux + Named Pipe Round-Trip Latency
**Goal:** Measure latency of writing to a named pipe -> tmux session -> reading from output pipe
**Method:**
1. Create a tmux session with `mkfifo` pipes: `/work/.ap/chat.in` and `/work/.ap/chat.out`
2. Write timestamped message to `chat.in`, read response from `chat.out`
3. Measure round-trip 100 times, report p50/p95/p99
**Output:** Latency histogram; pass if p99 < 50ms

### Spike 4: gVisor `runsc` Feasibility on Hetzner Kernel
**Goal:** Confirm gVisor `runsc` runs on the Hetzner host's kernel version
**Method:**
1. Check kernel version: `uname -r`
2. Install `runsc` from gVisor releases
3. Configure Docker: `"runtimes": {"runsc": {"path": "/usr/local/bin/runsc"}}`
4. Run `docker run --runtime=runsc alpine echo hello`
5. Document: kernel version, runsc version, success/failure, any warnings
**Output:** Pass/fail + kernel + runsc version; if fail, document the error and required kernel upgrade path
[CITED: gvisor.dev/docs/user_guide/faq/]

## Code Examples

### Health Handler (verified from MSV)
```go
// Source: MSV api/internal/handler/health.go [VERIFIED: local file read]
type HealthChecker interface {
    PingDB(ctx context.Context) error
    PingRedis(ctx context.Context) error
}

func (h *HealthHandler) Health(c echo.Context) error {
    ctx := c.Request().Context()
    checks := map[string]string{}
    allOK := true
    if err := h.checker.PingDB(ctx); err != nil {
        checks["database"] = "unhealthy: " + err.Error()
        allOK = false
    } else {
        checks["database"] = "healthy"
    }
    if err := h.checker.PingRedis(ctx); err != nil {
        checks["redis"] = "unhealthy: " + err.Error()
        allOK = false
    } else {
        checks["redis"] = "healthy"
    }
    status := "healthy"
    httpStatus := http.StatusOK
    if !allOK {
        status = "unhealthy"
        httpStatus = http.StatusServiceUnavailable
    }
    return c.JSON(httpStatus, HealthResponse{
        Status: status, Version: version.Info(),
        Checks: checks, Uptime: time.Since(startTime).Truncate(time.Second).String(),
    })
}
```

### Docker Runner - Run Method (new, validated pattern)
```go
// New method following MSV's validation pattern [VERIFIED: MSV runner.go pattern]
type RunOptions struct {
    Image     string
    Name      string            // container name (validated)
    Env       map[string]string // injected env vars
    Mounts    []string          // host:container paths
    Network   string
    Memory    string            // e.g. "512m"
    CPUs      string            // e.g. "0.5"
    PidsLimit string            // e.g. "100"
    Remove    bool              // --rm flag
    Labels    map[string]string
}

func (r *Runner) Run(ctx context.Context, opts RunOptions) (string, error) {
    if err := validateImageName(opts.Image); err != nil {
        return "", err
    }
    if opts.Name != "" {
        if err := validateContainerID(opts.Name); err != nil {
            return "", err
        }
    }
    args := []string{"run", "-d"}
    if opts.Remove { args = append(args, "--rm") }
    if opts.Name != "" { args = append(args, "--name", opts.Name) }
    // ... append validated env, mounts, network, resource limits, labels
    args = append(args, opts.Image)
    output, err := r.cmd.Run(ctx, "docker", args...)
    if err != nil {
        return "", fmt.Errorf("docker run: %w", err)
    }
    return strings.TrimSpace(string(output)), nil // returns container ID
}
```

### Temporal PingPong Workflow (trivial proof-of-wiring)
```go
// api/internal/temporal/workflows.go
func PingPong(ctx workflow.Context, input string) (string, error) {
    ao := workflow.ActivityOptions{
        StartToCloseTimeout: 10 * time.Second,
    }
    ctx = workflow.WithActivityOptions(ctx, ao)
    var result string
    err := workflow.ExecuteActivity(ctx, PingActivity, input).Get(ctx, &result)
    return result, err
}

// api/internal/temporal/activities.go
func PingActivity(ctx context.Context, message string) (string, error) {
    return fmt.Sprintf("pong: %s", message), nil
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tailwind v3 JS config | Tailwind v4 CSS-first (`@theme`) | Late 2025 | No `tailwind.config.js` needed; use `@import "tailwindcss"` in CSS |
| Next.js Pages Router | Next.js App Router (only path forward) | Next.js 13+ | Pages Router in maintenance; all new code uses `app/` directory |
| `nhooyr.io/websocket` | `coder/websocket` v1.8.14 | 2025 fork | Original deprecated; Coder maintains the active fork |
| `docker/docker/client` | `moby/moby/client` | 2026 redirect | Old import path redirects; use `moby/moby/client` canonical path |
| `temporalio/docker-compose` repo | `temporalio/samples-server/compose` | 2026-01-05 | Docker-compose repo archived; examples moved to samples-server |
| `tctl` CLI | `temporal` CLI (v1.6.2) | 2025+ | `tctl` deprecated in favor of unified `temporal` CLI |
| Echo v4 | Echo v5 available (2026-01-18) | 2026-01 | Maintainers recommend waiting until after 2026-03-31 for v5 in production |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `temporalio/auto-setup` image uses `DB=postgres12` env var name for Postgres driver | Temporal Setup | Temporal won't connect to DB; container will exit. Mitigated by testing in docker-compose first. |
| A2 | Temporal `default` namespace is auto-created by auto-setup image | Temporal Setup | Worker fails on startup; need to create namespace via CLI. Low risk -- well documented. |
| A3 | shadcn/ui `init` for Next.js 16.2 works with Tailwind v4 out of the box | Frontend | May need manual CSS config adjustments. Mitigated by checking `shadcn` CLI output. |
| A4 | gVisor `runsc` is compatible with Hetzner's default Ubuntu kernel | Spike 4 | Spike exists specifically to test this; failure means kernel upgrade. |
| A5 | MSV's custom migrator (not `golang-migrate` library) is the better choice for AP | Architecture | If `golang-migrate` is required by project convention, will need adapter. MSV's migrator is proven. |
| A6 | UUIDv7 is available via `uuid.NewV7()` in google/uuid v1.6.0 | Schema Design | May need v1.7+ or a separate library for v7. Can fall back to v4 with `created_at` ordering. |

## Open Questions

1. **Hetzner host OS and kernel version**
   - What we know: Hetzner dedicated servers typically ship Ubuntu 22.04 or 24.04 with standard kernels
   - What's unclear: Exact kernel version on the target host (needed for gVisor spike)
   - Recommendation: Run `uname -r` on the host as the first spike task; document in spike report

2. **Temporal version pin**
   - What we know: `temporalio/auto-setup:latest` works for dev; MSV pins Temporal SDK v1.40.0
   - What's unclear: Whether to pin `auto-setup` to a specific tag for reproducibility
   - Recommendation: Pin to a dated tag (e.g., `temporalio/auto-setup:1.25.2`) in docker-compose files; use `latest` only for initial testing

3. **Second Postgres database for Temporal in dev**
   - What we know: Dev docker-compose has one Postgres container; Temporal needs its own DB
   - What's unclear: Best way to create both `agent_playground` and `temporal` databases in one container
   - Recommendation: Use an init script volume-mounted into postgres container:
     ```sql
     -- deploy/init-dev-db.sql
     CREATE DATABASE agent_playground;
     CREATE DATABASE temporal;
     ```

4. **App database sharing with Temporal in production**
   - What we know: D-07 says Temporal uses a "separate temporal schema/database" on Postgres 17
   - What's unclear: Whether this means a separate Postgres instance or separate database on same instance
   - Recommendation: Same Postgres instance, separate database (simpler ops). The provisioning script creates both.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Go | Backend build | Yes | 1.25.3 | -- |
| Node.js | Frontend build | Yes | 24.10.0 | -- |
| pnpm | Frontend package manager | Yes | 10.22.0 | -- |
| Docker | Container runtime | Yes | 28.5.1 | -- |
| `temporal` CLI | Workflow observation/testing | Yes | 1.6.2 | -- |
| `tctl` | Legacy Temporal CLI | No | -- | Use `temporal` CLI instead (it's the replacement) |
| PostgreSQL (local) | Development DB | Via docker-compose | 17 (image) | embedded-postgres for tests |
| Redis (local) | Development cache | Via docker-compose | 7 (image) | miniredis for tests |

**Missing dependencies with no fallback:** None. All required tools are available.

**Missing dependencies with fallback:**
- `tctl` is not installed but `temporal` CLI (its replacement) is available and sufficient for all operations.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Go testing + testify v1.11.1 |
| Config file | None needed (Go built-in) |
| Quick run command | `cd api && go test ./... -short -count=1` |
| Full suite command | `cd api && go test ./... -count=1 -race` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FND-03 | `/healthz` returns 200 with DB+Redis healthy | unit | `go test ./internal/handler/ -run TestHealth -count=1` | Wave 0 |
| FND-05 | Migrations apply idempotently at boot | integration | `go test ./pkg/migrate/ -run TestMigrator -count=1` | Wave 0 |
| FND-06 | Runner can run/exec/inspect/stop/rm containers | unit | `go test ./pkg/docker/ -run TestRunner -count=1` | Wave 0 |
| FND-08 | PingPong workflow completes via Temporal | integration | `go test ./internal/temporal/ -run TestPingPong -count=1` (requires Temporal) | Wave 0 |
| FND-10 | Baseline migration creates agents table | integration | `go test ./pkg/migrate/ -run TestBaseline -count=1` | Wave 0 |
| FND-01 | Docker + userns-remap on host | manual | SSH to host, run `docker info` | Manual only |
| FND-02 | Postgres + Redis loopback services | manual | SSH to host, `pg_isready`, `redis-cli ping` | Manual only |
| FND-04 | Mobile-first landing page renders | e2e/manual | `cd web && pnpm build && pnpm start` + visual check | Manual in Phase 1 |
| FND-07 | Spike report committed | manual | File exists: `.planning/research/SPIKE-REPORT.md` | Manual only |
| FND-09 | Temporal namespace + queues observable | manual | `temporal operator namespace list` | Manual only |

### Sampling Rate
- **Per task commit:** `cd api && go test ./... -short -count=1`
- **Per wave merge:** `cd api && go test ./... -count=1 -race`
- **Phase gate:** Full suite green + manual verifications before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `api/internal/handler/health_test.go` -- covers FND-03
- [ ] `api/pkg/migrate/migrate_test.go` -- covers FND-05, FND-10
- [ ] `api/pkg/docker/runner_test.go` -- covers FND-06
- [ ] `api/internal/temporal/worker_test.go` -- covers FND-08 (may need Temporal testenv)
- [ ] `api/internal/middleware/auth_test.go` -- covers dev-cookie auth (D-09)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (dev stub) | HMAC-signed HTTP-only cookie, server-side session row |
| V3 Session Management | Yes | `user_sessions` table with `token_hash` (SHA-256) + `expires_at`; cookie: `HttpOnly; Secure; SameSite=Lax` |
| V4 Access Control | Yes (basic) | Auth middleware on all protected routes; dev-only endpoint gated by `AP_DEV_MODE=true` |
| V5 Input Validation | Yes | Docker runner arg validation (alphanumeric + safe chars only); migration file name validation |
| V6 Cryptography | Minimal | HMAC-SHA256 for cookie signing; SHA-256 for token hashing; no encryption in Phase 1 |

### Known Threat Patterns for Phase 1 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via Docker CLI args | Tampering | `validateContainerID()` strict allowlist [VERIFIED: MSV] |
| Cookie forgery | Spoofing | HMAC-SHA256 signing with server secret |
| Session fixation | Spoofing | Generate new session token on each login |
| Dev endpoint exposed in production | Elevation | Gate behind `AP_DEV_MODE=true` env var; disabled by default |
| Temporal binding on 0.0.0.0 | Information Disclosure | Bind to 127.0.0.1 only (D-07) |
| Postgres/Redis exposed to internet | Information Disclosure | UFW blocks all non-443 incoming; services bind to loopback |

## Sources

### Primary (HIGH confidence)
- MSV `api/` codebase at `/Users/fcavalcanti/dev/meusecretariovirtual/api/` -- direct source read of all ported files
- Go module proxy (`proxy.golang.org`) -- version verification for all Go dependencies
- npm registry -- version verification for all frontend dependencies
- Local tool versions (`go version`, `node --version`, `docker --version`, `temporal --version`)

### Secondary (MEDIUM confidence)
- [Temporal docker-compose-postgres.yml](https://github.com/temporalio/docker-compose/blob/main/docker-compose-postgres.yml) -- archived Jan 2026 but patterns still valid
- [temporalio/auto-setup Docker Hub](https://hub.docker.com/r/temporalio/auto-setup) -- env var documentation
- [Temporal Go SDK guide](https://www.glukhov.org/post/2026/03/workflow-applications-temporal-in-go/) -- worker/workflow/activity patterns
- [Docker userns-remap docs](https://docs.docker.com/engine/security/userns-remap/) -- daemon.json configuration
- [shadcn/ui installation](https://ui.shadcn.com/docs/installation/next) -- Next.js + Tailwind v4 setup
- [shadcn/ui Tailwind v4 guide](https://ui.shadcn.com/docs/tailwind-v4) -- CSS-first configuration
- [gVisor FAQ](https://gvisor.dev/docs/user_guide/faq/) -- kernel compatibility requirements
- [Alex Edwards: Working with Cookies in Go](https://www.alexedwards.net/blog/working-with-cookies-in-go) -- HMAC cookie signing pattern

### Tertiary (LOW confidence)
- Temporal docker-compose repo archived note (Jan 2026) -- verified via WebFetch but exact current replacement workflow not confirmed

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified against Go proxy and npm registry; MSV patterns verified from source
- Architecture: HIGH -- directly porting from a working MSV codebase with known patterns
- Temporal setup: MEDIUM-HIGH -- auto-setup image well-documented but specific Postgres dual-DB dev config needs testing
- Pitfalls: HIGH -- identified from real MSV experience and official documentation
- Spike methodology: MEDIUM -- methodology is sound but outcomes are by definition unknown (that's why they're spikes)
- Frontend (Next.js/Tailwind/shadcn): MEDIUM-HIGH -- versions verified, setup well-documented, but Tailwind v4 + shadcn integration is newer territory

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (30 days -- stack is stable, no breaking changes expected)
