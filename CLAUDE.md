# ⚠️ Golden rules (permanent — apply every phase)

1. **No mocks, no stubs.** Tests hit real infra (live Postgres, real Docker daemon via testcontainers, real recipe runs). No in-memory fakes for core substrate. See `memory/feedback_no_mocks_no_stubs.md`.
2. **Dumb client, intelligence in the API.** The frontend is a thin terminal over the API. **No client-side catalogs** of anything the server owns — recipes come from `GET /v1/recipes`, models come from the API, no hardcoded `defaultClones`/model arrays in React state. If the page needs a list, it `fetch`es it. See `memory/feedback_dumb_client_no_mocks.md`.
3. **Ship when the stack works locally end-to-end.** Never deploy to a production host until the same Docker topology runs locally AND a real user workflow (click → see result, not `setState(isRunning: true)` theater) completes against it. Deploying an API with a mock UI is shipping a mock to prod.
4. **Root cause first, never fix-to-pass.** Investigate before removing code. See `memory/feedback_root_cause_first.md`.
5. **Test everything. Probe gray areas empirically BEFORE planning.** No PLAN may assume "pattern X in another module will work the same here" — every non-trivial mechanism (new file format, new subprocess lifecycle, new encryption path, new env-var injection, new health check, new container flag, new regex, new HTTP contract, new DB constraint) must be spiked against real infra and the spike result captured as evidence BEFORE the planner consumes it. If the spike fails or surfaces a gray area not considered, the plan goes back. Risk budget: zero untested mechanisms in a sealed PLAN. Rule-1 extended to planning: the plan's own assumptions hit real infra too. See `memory/feedback_test_everything_before_planning.md`.

# ⚠️ Current project state as of 2026-04-15

**READ THIS FIRST. The content below this banner is historical.**

On 2026-04-15 this project pivoted from the 9-phase GSD roadmap described below to a **recipe-first recon methodology**. Current state:

- **5 agent recipes are validated and committed** under `recipes/` — hermes, openclaw, picoclaw, nullclaw, nanobot. Each has a YAML recipe + a cell-verified PASS against OpenRouter.
- **2 agents are BLOCKED(format)** with documented reasons — nanoclaw (OneCLI Agent Vault dependency), openhands (trajectory-file responses + deprecated V0 headless + out of clawclones.com scope).
- **A minimal runner exists** at `tools/run_recipe.py` — ~300 lines of Python, consumes `ap.recipe/v0` YAML, does `docker build`/`docker pull` + sh-chained container invocation + `response_contains_name` pass_if check.
- **Backlog at `recipes/BACKLOG.md`** contains 35+ more clawclones.com candidates sorted by highest stars descending. **It is ON HOLD** — do not add new recipes until the consolidation phase below lands.

## The next phase (queued, not started)

`.planning/phases/03-recipe-format-v0.1/CONTEXT.md` is a standalone brief for the **format-v0.1 consolidation phase**. This phase must ship before any new agent is added. Scope:

1. `docs/RECIPE-SCHEMA.md` — canonical v0.1 spec formalizing every ad-hoc field that grew across the 5 recipes
2. Runner v0.1 — new `pass_if` verbs (`exit_zero`, `response_contains_string`, `response_regex`, `response_not_contains`), recipe-sourced smoke prompts, `--json` output, `--all-cells` sweep mode, disk budget guard
3. Retroactive re-validation — all 5 existing recipes must PASS against the new runner (regression gate)
4. `recipes/README.md` — user-facing how-to
5. BACKLOG banner update — "v0.1 canonical"

## Before doing ANY work, read in this order

1. `memory/MEMORY.md` (auto-memory index, likely already in context)
2. `memory/project_recipe_v0_state.md` — the 5-recipe matrix + every format innovation absorbed
3. `memory/feedback_recipe_runner_debt.md` — the 8 concrete debt items (this is the phase agenda)
4. `.planning/phases/03-recipe-format-v0.1/CONTEXT.md` — the phase brief with exit gate
5. `recipes/BACKLOG.md` — the ON HOLD banner + the post-phase queue (top: ZeroClaw, 30k ★ Rust)
6. `recipes/hermes.yaml` through `recipes/nanobot.yaml` — the five validated recipes showing every field in use
7. `tools/run_recipe.py` — the current runner state (2 build modes, 1 pass_if verb, sh-chain entrypoint override)

## Rules for this session (do not break these)

- **Do NOT add a new agent recipe** before format-v0.1 lands. The backlog waits.
- **Do NOT touch `api/`, `deploy/`, `test/`, or the old substrate** described below — that work was abandoned during the pivot.
- **Do NOT act on the 9-phase roadmap below as if it were authoritative.** It reflects a direction that was paused on 2026-04-15.
- **Do NOT delete or rewrite the 5 existing recipes** unless the retroactive re-validation specifically requires a minimal retrofit.
- When the phase exit gate passes (5 recipes return `"verdict": "PASS"` via `--all-cells --json`), the stars-desc queue in BACKLOG resumes with ZeroClaw.

---

<!-- GSD:project-start source:PROJECT.md -->
## Project

**Agent Playground**

A web platform where logged-in users pick any combination of coding agent (OpenClaw, Hermes, HiClaw, PicoClaw, NanoClaw, and others from the clawclones catalog) and any model (OpenRouter, Anthropic, OpenAI) and get a dockerized session to drive it — via a browser chat UI or a web terminal into the same container. Inspired by `/Users/fcavalcanti/dev/meusecretariovirtual` (MSV) but without its constraints: no Telegram dependency, not locked to PicoClaw, not locked to Anthropic models.

**Core Value:** **Any agent × any model × any user, in one click.** If everything else fails, the agent-agnostic install pipeline (deterministic recipes for known agents, Claude-Code bootstrap for unknown ones) must work — that's the differentiator.

### Constraints

- **Tech stack**: Go API + Next.js frontend — mirror MSV, transfer patterns and code directly.
- **Workflow engine**: **Temporal** — used for all durable workflows (session create/destroy, recipe install, reconciliation, billing reconciliation). Mirrors MSV's executor pattern. Explicitly overrides the research recommendation to "drop Temporal" — user decision.
- **Infra**: Hetzner dedicated box — same as MSV; one beefy host, Docker on host for per-user containers.
- **Auth**: Google + GitHub OAuth only in v1 — no email/password.
- **Billing**: Credit balance via Stripe for platform-billed mode; BYOK path has zero billing touchpoints.
- **Models**: Must support OpenRouter, Anthropic direct, and OpenAI direct on day 1. Local/Ollama is a later tier.
- **Open source**: Whole platform ships OSS under a permissive license (MIT or Apache-2.0) — decision deferred to planning.
- **Session concurrency**: One active session per user; multi-session is tier-gated v2 work.
- **Security**: Per-user isolated Docker container on a shared host; recipe execution inside containers must not trust user-supplied repo URLs blindly (sandbox hardening is a hard requirement for the generic bootstrap path).
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## TL;DR
## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **Go** | **1.25.x** | Backend API + container orchestrator | Mirror MSV (`go 1.25.6`); transfer patterns directly. Strong stdlib HTTP, native concurrency, good Docker SDK story. |
| **Echo** | **v4.15.x** (NOT v5) | HTTP framework | MSV already uses `labstack/echo/v4 v4.15.1`. Echo v5 only stabilized 2026-01-18 and the maintainers explicitly recommend waiting until after 2026-03-31 before upgrading production. v4 is supported through 2026-12-31. **Pin to v4 in v1, plan v5 migration as a v2 chore.** |
| **pgx** | **v5.8.x** | PostgreSQL driver + query layer | MSV uses `jackc/pgx/v5 v5.8.0`. Fastest Postgres driver in Go, native types, no ORM tax. **No GORM, no sqlc-only stack** — use raw pgx with hand-rolled queries like MSV. |
| **PostgreSQL** | **17.x** | Primary datastore | Users, sessions, recipes, credit ledger, audit log. `embedded-postgres` (already in MSV go.mod) makes local dev painless. **Not SQLite** — multi-process Docker orchestrator + Stripe webhooks + concurrent session writes need a real concurrent DB. |
| **Next.js** | **16.2.x** (App Router) | Frontend | Latest stable as of March 2026. Turbopack is stable in 16, React Compiler 1.0 enabled by default. App Router is the only path forward — Pages Router is in maintenance mode. Mirrors BasicPay/MSV stack muscle memory. |
| **React** | **19.2** | UI runtime | Bundled with Next 16.2; nothing to decide. |
| **TypeScript** | **5.7+** | Frontend type safety | Standard. |
| **Docker Engine** | **27.x+** | Per-user container runtime | Already on the Hetzner box. One container per active user session. |
| **Docker Engine SDK (Go)** | `github.com/moby/moby/client` (latest, March 2026) | Container lifecycle from Go | The canonical import path is now `moby/moby/client`; `docker/docker/client` redirects there in 2026. **Use this directly** — don't shell out to `docker` CLI, don't use `fsouza/go-dockerclient` (third-party, lags features), don't use the higher-level `docker/go-sdk` (less control over exec streams which we need for the terminal). |
### Supporting Libraries (Go backend)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `github.com/labstack/echo/v4` | v4.15.1 | HTTP router/middleware | Every HTTP route. Mirror MSV middleware stack (recover, logger, CORS). |
| `github.com/jackc/pgx/v5` + `pgxpool` | v5.8.0 | Postgres | All DB access. |
| `github.com/jackc/pgx/v5/stdlib` | (bundled) | `database/sql` adapter | Only if a library demands `*sql.DB` (e.g. `golang-migrate`). |
| `github.com/golang-migrate/migrate/v4` | v4.18+ | Schema migrations | Versioned SQL files in `api/migrations/`. Standard Go choice. |
| `github.com/redis/go-redis/v9` | v9.18.0 | Session cache, rate limiting, ephemeral state | Mirror MSV. Use for: per-user rate limits, OAuth state nonces, ephemeral session metadata, websocket presence. |
| `github.com/rs/zerolog` | v1.34.0 | Structured logging | Mirror MSV. JSON to stdout, scraped by Loki/Promtail. |
| `github.com/moby/moby/client` | (latest) | Docker Engine SDK | Container create / start / exec / wait / remove / volumes / image pull. |
| `github.com/markbates/goth` + `gothic` | latest | OAuth (Google + GitHub) | Has both providers built-in, has new active maintainers (post-Buffalo handoff), idiomatic with Echo. **Wrap goth in our own session layer** (HTTP-only signed cookies → server-side session in Postgres). |
| `golang.org/x/oauth2` | latest | Lower-level OAuth primitives | Used transitively by goth; pin explicitly so you can refresh tokens manually if needed. |
| `github.com/stripe/stripe-go/v82` | v82.x (API `2025-03-31.basil`) | Stripe SDK | v82 has first-class **Billing Credit Balance** and **Billing Meter Events** APIs — exactly what the platform-billed credit model needs. Pin major; bump minors freely. |
| `github.com/anthropics/anthropic-sdk-go` | latest (updated 2026-04-10) | Anthropic direct provider | Official SDK; well-maintained. Use for the platform-billed Anthropic path. BYOK Anthropic users bypass this. |
| `github.com/openai/openai-go` | latest (official) | OpenAI direct **and** OpenRouter | OpenRouter is fully OpenAI-compatible — same SDK, just override `BaseURL` to `https://openrouter.ai/api/v1`. **One client, two providers.** |
| `github.com/google/uuid` | v1.6.0 | IDs | Already a transitive dep. Use UUIDv7 for time-ordered keys. |
| `github.com/coder/websocket` | v1.8+ | WebSocket server | Successor to `nhooyr.io/websocket` (Coder forked + maintains it). Cleaner API than `gorilla/websocket`, context-aware, single-frame helpers. **Use this, not gorilla.** |
| `github.com/stretchr/testify` | v1.11+ | Test assertions | Mirror MSV. |
| `github.com/pashagolub/pgxmock/v4` | v4.9+ | Postgres mocking | Mirror MSV. |
| `github.com/alicebob/miniredis/v2` | v2.37+ | Redis mocking | Mirror MSV. |
### Supporting Libraries (Next.js frontend)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `next` | 16.2.x | Framework | App Router only. |
| `react`, `react-dom` | 19.2.x | UI | Bundled with Next 16. |
| `@xterm/xterm` | 5.5.x | Terminal emulator | The browser-side web terminal. **Use the new `@xterm/xterm` scoped package**, not the legacy `xterm` package. |
| `@xterm/addon-fit` | 0.11.x | Resize terminal to container | Standard. |
| `@xterm/addon-attach` | 0.12.x | Wire xterm to a WebSocket | Connects directly to the Go-side terminal proxy → ttyd inside container. |
| `@xterm/addon-web-links` | latest | Clickable URLs in the terminal | Nice-to-have. |
| `tailwindcss` | v4.x | Styling | Tailwind v4 is stable, fast, and the dev UX matches BasicPay. |
| `shadcn/ui` (via CLI, copy-in components) | latest | Component library | No runtime dep — components live in your repo. Best DX for a small frontend. |
| `next-auth` / Auth.js | **NOT USED** | — | Auth lives in the Go backend (goth) so the API is the source of truth. The frontend just reads a session cookie set by Go. |
| `@stripe/stripe-js` + `@stripe/react-stripe-js` | latest | Stripe Checkout / Elements on the client | For credit top-up flow. |
| `swr` *or* `@tanstack/react-query` v5 | latest | Data fetching against the Go API | Pick one — **react-query** is the more capable choice and matches BasicPay if it's already there. |
| `zod` | v3.x | Runtime validation of API responses | Pair with the OpenAPI types if you generate them. |
### Web Terminal Stack (the load-bearing decision)
| Component | Choice | Why |
|-----------|--------|-----|
| **In-container TTY server** | **`ttyd`** (binary, run as PID 1 or under tini in the user container) | C port of GoTTY, smaller, actively maintained, has first-class Alpine Docker images, uses xterm.js on the wire, websocket-based, supports auth tokens via query string. **Picked over GoTTY** because GoTTY is unmaintained since 2017. |
| **Wire protocol** | ttyd's native binary websocket protocol | xterm.js can speak it via a tiny client; or you front it with `addon-attach` and a Go proxy that translates. |
| **Backend bridge** | **Go WebSocket reverse proxy** using `coder/websocket`, fronted by Echo at `/api/sessions/:id/terminal` | Terminates the user-facing WS, validates the auth cookie, looks up the session → container ID → internal ttyd port, then proxies bidirectionally. **Critical:** never expose ttyd directly — the Go proxy is the auth boundary. |
| **Chat ↔ container bridge** | **Go-side stdio bridge** that runs `docker exec -i <container> <agent-cli>` via the SDK and pipes the agent's stdin/stdout over a separate WebSocket | The chat UI is a *second* view of the same container. It does **not** spawn a second container. The bridge holds the agent process; chat messages → stdin, agent output → SSE/WS → React. |
| **Why not run ttyd outside the container?** | Each user gets a fresh agent install with its own home dir, env vars, recipe-specific tools — ttyd has to live *inside* so the shell sees that environment. |
| **Why not just `docker exec` for the terminal too?** | You can, but you lose tty resize, ANSI mouse events, and you're reinventing PTY plumbing in Go. ttyd already solved it. |
### Container Isolation Tiers
| Tier | When | Tech |
|------|------|------|
| **v1 (launch)** | First 100 users, you trust the agent recipes you wrote | Plain Docker, dropped capabilities, `--read-only` rootfs where possible, `--pids-limit`, `--memory`, `--cpus`, `--network` on a per-tenant bridge, no `--privileged`, user namespace remapping (`userns-remap`) on the daemon. |
| **v1.5 (hardening)** | Before opening the generic Claude-Code-bootstrap path to arbitrary git repos | **Sysbox** as the runtime (`--runtime=sysbox-runc`). Drop-in, no app changes, gives you nested-Docker-safe + much stronger user namespace isolation. The Coder team uses exactly this pattern for the same reason. |
| **v2** | Multi-tenant scale, untrusted code at volume | Add **gVisor** (`--runtime=runsc`) as a *second* runtime tier you can opt sessions into; or move highest-risk sessions to firecracker microVMs. Out of scope for v1. |
### Job/Worker Layer
| Need | v1 Solution | When to Reconsider |
|------|-------------|-------------------|
| Container lifecycle (create → wait → reap) | Goroutines + Postgres-backed `sessions` table with state column; reaper goroutine polls expired/idle sessions every 30s | When you need >1 host or cross-host workflow durability |
| Recipe build cache invalidation | Postgres + a single `recipes` table | — |
| Stripe webhook processing | Synchronous in the webhook handler, idempotent via `webhook_events` table | When webhook volume > 100/s |
| Async work (e.g. backup persistent volumes) | A simple Postgres queue (`SELECT … FOR UPDATE SKIP LOCKED`) + a Go worker pool | Real workflow needs (retries, sagas, signals) → Temporal |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| `air` | Live-reload Go API in dev | Standard. |
| `golangci-lint` | Lint | Mirror MSV config. |
| `golang-migrate` CLI | Run migrations locally + in prod | Versioned, reversible. |
| `pnpm` | Frontend package manager | Faster installs than npm, works fine with Next 16. |
| `docker compose` | Local dev: postgres + redis + the API + a fake "user container" | Single `docker compose up`. |
| `ko` (`github.com/ko-build/ko`) | Build the Go API into a tiny container with no Dockerfile | Optional but slick for CI. |
| `goreleaser` | Release the Go API binary if you want fat-binary deploys instead of containers | Optional. |
| `playwright` | E2E tests of the auth + session-launch flow | Standard. |
## Installation
### Backend (Go API)
# Initialize
# Test deps
### Frontend (Next.js)
### Host (Hetzner)
# Daemon hardening for v1
# v1.5: install sysbox (Nestybox / Docker)
# https://github.com/nestybox/sysbox  → adds runtime=sysbox-runc
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **Echo v4** | Gin, Fiber, chi, stdlib `net/http` + `ServeMux` | Use Gin only if you already know it. **Use chi or stdlib** if a future maintainer wants minimal magic. Echo is picked here strictly because MSV uses it. |
| **Echo v4** | **Echo v5** | After 2026-04-01 once v5 settles; v5 has cleaner middleware semantics. Defer the migration. |
| **pgx v5** | GORM, ent, sqlc | sqlc is the only credible alternative — type-safe queries from SQL files. **Reconsider for v2** if hand-rolled queries become a chore. GORM and ent are anti-recommendations for this kind of small high-control service. |
| **Postgres** | SQLite (`modernc.org/sqlite`) | Pure single-process embedded apps. Not us — we have webhooks + multiple goroutines + a long-running orchestrator. |
| **`moby/moby/client`** | `fsouza/go-dockerclient`, shelling out to `docker` CLI, `docker/go-sdk` higher-level | Shell out only for one-off operations a human would run. `go-sdk` if you discover the low-level API is too verbose for 90% of your code (you can mix). |
| **`coder/websocket`** | `gorilla/websocket`, `nhooyr.io/websocket` (deprecated; coder/websocket is the fork) | Gorilla if you need the very long tail of WS extensions; you don't. |
| **`ttyd` inside container** | `gotty` (unmaintained since 2017), Wetty (Node.js, heavier), pure Go PTY via `creack/pty` + custom protocol | Pure-Go PTY only if you cannot install ttyd in the base image. It's more code to own. |
| **`goth` for OAuth** | Hand-rolled with `golang.org/x/oauth2`, Ory Hydra, Authentik, Clerk, Supabase Auth | Hand-roll if you only need 2 providers and want zero deps (~200 lines). External IdP only if compliance requires it — overkill here. |
| **Hetzner dedicated** | Hetzner Cloud, Fly.io, Railway, AWS ECS | Cloud only if Hetzner dedicated suffers a hardware incident and you need failover. Stick with dedicated for cost predictability per the project decision. |
| **Plain Docker → Sysbox in v1.5** | gVisor (`runsc`) from day 1, Firecracker microVMs, Kata Containers | gVisor day-1 if your threat model says so *now* and you have the ops bandwidth. Most teams correctly defer this. |
| **No Temporal** | Temporal (MSV uses it), River, Asynq, Faktory | Temporal when you have multi-step workflows that must survive restarts and span hours. Our session loop is short-lived; an in-process supervisor is enough. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **Echo v5 in v1** | Released 2026-01-18, maintainers explicitly recommend waiting until after 2026-03-31 for production. v4 ships through end of 2026. | Echo v4.15.x; revisit v5 in v2. |
| **GORM** | Reflection-heavy, hides SQL, breaks under unusual queries, slows down code review. | pgx + raw SQL or sqlc. |
| **`docker/docker/client` import path** | Redirects in 2026; not the canonical path anymore. | `github.com/moby/moby/client`. |
| **`gotty`** | Unmaintained since 2017, no security patches, no Alpine images. | `ttyd`. |
| **`nhooyr.io/websocket`** | Original repo deprecated; the maintainer joined Coder and the active fork is `coder/websocket`. | `github.com/coder/websocket`. |
| **`gorilla/websocket`** | Works fine, but the API is older, not context-aware, requires more boilerplate, and the project went into archival/community-maintenance. | `coder/websocket`. |
| **`fsouza/go-dockerclient`** | Third-party, perpetually 1–2 API versions behind upstream Moby. | `moby/moby/client`. |
| **Running `docker run` via `os/exec`** | Loses structured errors, no event subscription, no exec streams, hard to test. | Docker SDK. |
| **K3s / Kubernetes / Nomad** | One-host fleet of short-lived sandbox containers does not justify a control plane. MSV explicitly chose Docker on host for the same reason. | Plain `dockerd` + Go orchestrator. |
| **NextAuth/Auth.js for the canonical session** | Splits auth state between Next and Go; the Go API needs to be the source of truth for billing and session ownership anyway. | `goth` server-side, Go sets a signed cookie, Next reads it as opaque. |
| **GORM-style "migrations from struct tags"** | Diverges from prod state, hides DDL. | `golang-migrate` with hand-written SQL files. |
| **Storing OAuth tokens in cookies** | XSS-leak surface, rotation pain. | Server-side session row in Postgres keyed by HTTP-only cookie. |
| **Running the agent CLI as PID 1 in the container** | If the CLI crashes the container dies and you lose logs. | Run `tini` or `dumb-init` as PID 1, supervise both ttyd and the agent process. |
| **Mounting the host Docker socket into user containers** | Container escape on a silver platter. | Don't. If a recipe needs Docker-in-Docker, use Sysbox (v1.5). |
| **`--privileged` containers** | Defeats the entire isolation story. | Drop caps, add only what the recipe needs. |
| **Long-lived OpenAI / Anthropic API keys baked into images** | Users would inherit them. | Inject per-session env at container start; never bake. |
## Stack Patterns by Variant
- The Go API never sees tokens count or makes upstream LLM calls itself
- The user's API key is injected as `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY` env into their container at start time
- Stored encrypted at rest (libsodium / age via `filippo.io/age`) keyed by a per-user KEK derived from a server master key + user ID
- **Never logged, never returned via API**
- No metering tables touched
- The Go API runs an **HTTP egress proxy** (a Go reverse proxy on a dedicated unix socket inside each container) that the agent CLI is configured to use as `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL`
- The proxy authenticates via a per-session token, forwards upstream with the platform's master key, parses the response for `usage` block, deducts from the user's credit balance in Postgres atomically
- **Metering at the proxy layer, not at the SDK layer.** The agent CLI doesn't know it's metered.
- For OpenRouter you also call `/api/v1/generation?id=…` post-hoc to confirm cost (OpenRouter returns cost in USD directly — much simpler than computing it from token counts)
- Stripe webhook tops up the credit balance row; the proxy decrements it; if balance ≤ 0, the proxy starts returning 402
- Container runs with `--rm` (ephemeral), no persistent volume
- Memory cap stricter (512MB), CPU cap stricter (0.5 vCPU)
- Idle timeout 15min
- One concurrent session enforced via Postgres unique index on `(user_id, status='active')`
- Container has a per-user named volume mounted at `/workspace`
- Volume is backed up nightly via `restic` to a Hetzner Storage Box
- Idle timeout 4h, hard cap 24h per session
- Memory 2GB, CPU 2 vCPU
- Pre-built container image lives in a private registry on the box (or `ghcr.io`)
- Recipe defines `BASE_IMAGE`, `INSTALL_CMD`, `LAUNCH_CMD`, `ENV`
- Pull time on session start: ~0 (cached locally)
- Start from a `base-bootstrap` image (Debian slim + git + node + python + tini + ttyd + Claude Code preinstalled)
- Mount the target git repo, run the bootstrap prompt as a child process, capture the resulting recipe, **persist it back to the user's volume AND offer to PR it to `agents/community/`**
- Subsequent sessions for the same repo skip the bootstrap
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Go 1.25.6 | Echo v4.15, pgx v5.8, moby/moby/client (latest) | All set in MSV. |
| Echo v4.15.1 | `coder/websocket` v1.8 | Use Echo handler that hijacks the response writer; coder/websocket has helpers. |
| `moby/moby/client` (latest) | Docker daemon 24.x → 27.x | Use API version negotiation: `client.New(client.FromEnv, client.WithAPIVersionNegotiation())`. |
| `stripe-go/v82` | Stripe API `2025-03-31.basil` | Pin in code via `stripe.APIVersion`. |
| Next 16.2 | React 19.2 | Bundled. Don't downgrade React. |
| `@xterm/xterm` 5.5 | `@xterm/addon-fit` 0.11, `@xterm/addon-attach` 0.12 | All require xterm.js v4+. |
| `ttyd` (latest) | `@xterm/xterm` 5.x | ttyd ships its own bundled client; if you use addon-attach you reimplement the protocol. Easiest path: serve ttyd's HTML directly inside an iframe and let it manage xterm. **Decision flag for design phase:** iframe vs direct attach. Iframe is simpler, direct attach is prettier. |
| `goth` | Echo v4 | Wire via `gothic.GetProviderName` injection; goth is router-agnostic. |
## Concrete Architecture Choices the Roadmap Should Encode
## Where Mirroring MSV is the Right Call
| Mirror MSV | Reason |
|-----------|--------|
| Go 1.25 + Echo v4 + pgx v5 + Redis + zerolog | Direct code transfer, same testing harness, same observability shape. |
| Embedded postgres for tests (`fergusstrange/embedded-postgres`) | Already in MSV go.mod, painless local test DB. |
| `pgxmock`, `miniredis` test deps | Same. |
| Hetzner dedicated, Docker on host, no K8s | Same operational model, proven at MSV's scale. |
| Project layout: `api/` for Go, `web/` for Next | Same monorepo shape. |
## Where Mirroring MSV is WRONG
| Don't Mirror | Reason | Do Instead |
|--------------|--------|-----------|
| **Temporal SDK (`go.temporal.io/sdk`)** | MSV uses it for long-running Telegram bot orchestration. We have one short-lived session per user. Temporal is heavy, needs its own server, and adds 30+ transitive deps. | In-process supervisor + Postgres queue. Add River later if needed. |
| **Telegram-bot-shaped session model** | MSV's session = a Telegram chat. Ours = a browser WebSocket. The state machine is simpler. | Model sessions as `(user_id, container_id, status, started_at, expires_at)` with a simple state machine. |
| **MSV's bot creation flow** | Doesn't apply. | Skip entirely. |
| **PicoClaw-specific assumptions in container base images** | MSV assumes one agent. We must be agent-agnostic. | Generic base image + recipe overlay. |
| **MSV's auth (if it's email-based)** | We need OAuth-only. | goth + Google/GitHub. |
## Open Questions for the Design Phase
## Confidence Notes
| Area | Confidence | Why |
|------|------------|-----|
| Go core (Echo v4 / pgx / zerolog / Redis) | **HIGH** | Mirrors MSV's already-running stack, all libraries verified current as of April 2026. |
| Stripe v82 + credit balance + meters | **HIGH** | Verified against the v82 migration guide and live API. |
| `moby/moby/client` as canonical Docker SDK path | **HIGH** | Verified against pkg.go.dev and moby/moby releases. |
| Next.js 16.2 + React 19.2 | **HIGH** | Verified against the Next.js 16 release notes. |
| `goth` for OAuth | **MEDIUM-HIGH** | Confirmed maintainer handoff; new maintainers active. Lower confidence than golang.org/x/oauth2 for long-term stability. |
| `ttyd` as terminal backend | **MEDIUM-HIGH** | Project is active, widely used (Coder, Selenoid UI). The risk is the integration choice (iframe vs attach), not the tool. |
| `coder/websocket` over `gorilla/websocket` | **MEDIUM-HIGH** | Coder uses it in production at scale; API is cleaner; gorilla still works. |
| Sysbox as the v1.5 isolation tier | **MEDIUM** | Coder uses Sysbox exactly for this case, which is strong validation. Caveat: Sysbox requires kernel features that are present on every modern Hetzner box but should be verified on the actual host before committing. |
| LLM egress proxy as the metering layer | **MEDIUM** | Architecturally clean and proven elsewhere. The risk is the agent CLIs that don't honor `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` env — needs per-recipe verification. **Flag for the recipe phase.** |
| "No Temporal" decision | **MEDIUM-HIGH** | Correct for v1 scale. Will likely flip in v2 if cross-host or backup workflows arrive. |
| Hetzner dedicated as the long-term home | **HIGH** | Same as MSV, proven cost model. |
## Sources
- [Echo v4 / v5 release status](https://github.com/labstack/echo/releases) — confirmed v4.15 latest, v5 stabilized 2026-01-18 with maintainer recommendation to wait until after 2026-03-31 for production
- [Echo v4 docs](https://echo.labstack.com/docs) — v4 supported through 2026-12-31
- [`moby/moby/client` package](https://pkg.go.dev/github.com/moby/moby/client) — confirmed canonical path; `docker/docker/client` redirects here in 2026; updated 2026-03-05
- [Docker Engine SDK guide](https://docs.docker.com/reference/api/engine/sdk/) — verified API negotiation and security best practices
- [`stripe-go` v82 migration guide](https://github.com/stripe/stripe-go/wiki/Migration-guide-for-v82) — confirmed Billing Credit Balance + Meter Events APIs
- [Stripe API changelog](https://docs.stripe.com/changelog) — current API version `2026-03-25.dahlia`, v82 SDK is on `2025-03-31.basil`
- [Stripe Billing Meter API](https://docs.stripe.com/api/billing/meter) — verified the metering primitives exist
- [Next.js 16 release post](https://nextjs.org/blog/next-16) — Turbopack stable, React Compiler 1.0 default
- [Next.js 16.2](https://nextjs.org/blog/next-16-2) — latest stable as of March 2026
- [`@xterm/addon-fit` 0.11](https://www.npmjs.com/package/@xterm/addon-fit) — verified current version
- [`@xterm/addon-attach` 0.12](https://www.npmjs.com/package/@xterm/addon-attach) — verified current version
- [ttyd project](https://tsl0922.github.io/ttyd/) — verified active, Alpine Docker images, websocket protocol
- [GoTTY repo](https://github.com/yudai/gotty) — confirmed unmaintained
- [`anthropics/anthropic-sdk-go`](https://github.com/anthropics/anthropic-sdk-go) — official, updated 2026-04-10
- [Anthropic Client SDKs](https://platform.claude.com/docs/en/api/client-sdks) — Go listed as official
- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) — confirmed OpenAI-compatible base URL `https://openrouter.ai/api/v1`
- [OpenRouter API reference](https://openrouter.ai/docs/api/reference/overview) — confirmed `/api/v1/generation` returns cost in USD
- [`markbates/goth`](https://github.com/markbates/goth) — confirmed Google + GitHub providers, new maintainers post-Buffalo handoff
- [`golang.org/x/oauth2`](https://pkg.go.dev/golang.org/x/oauth2) — official Go OAuth2 client primitives
- [Coder architecture docs](https://coder.com/docs/admin/infrastructure/architecture) — `coderd` API + `provisionerd` worker model; validates a Go-orchestrator-on-one-host pattern
- [Coder + Sysbox](https://coder.com/docs/admin/templates/extending-templates/docker-in-workspaces) — Sysbox runtime for secure per-user docker workspaces
- [Sysbox project (Nestybox)](https://github.com/nestybox/sysbox) — drop-in OCI runtime
- [gVisor](https://gvisor.dev/) — alternative isolation tier; flagged for v2
- [Northflank: How to sandbox AI agents in 2026](https://northflank.com/blog/how-to-sandbox-ai-agents) — validation of microVM/gVisor/Sysbox tradeoffs for AI agent sandboxes
- [MSV `api/go.mod`](file:///Users/fcavalcanti/dev/meusecretariovirtual/api/go.mod) — direct read; pinned versions for Echo, pgx, Redis, zerolog, miniredis, pgxmock, embedded-postgres, Temporal
- [MSV `README.md`](file:///Users/fcavalcanti/dev/meusecretariovirtual/README.md) — confirms Hetzner dedicated + Docker on host operational pattern
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
