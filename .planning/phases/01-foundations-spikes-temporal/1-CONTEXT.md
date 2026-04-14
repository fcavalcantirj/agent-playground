# Phase 1: Foundations, Spikes & Temporal - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Stand up the shared substrate every later phase consumes: Hetzner host with Docker/Postgres/Redis/Temporal, a Go API skeleton (Echo v4 + pgx v5), a mobile-first Next.js 16 shell, `pkg/docker/runner.go` ported from MSV, and a committed spike report answering four Phase-0 unknowns. The baseline DB schema plants the multi-agent-per-user data model from day 1.

**Mission context:** Democratize agent deployment — the easiest way to deploy any agent x any model combination, in one click.

</domain>

<decisions>
## Implementation Decisions

### Repo layout + local dev workflow
- **D-01:** Mirror MSV shape — `api/` (Go) + `web/` (Next.js) + `deploy/` (provisioning scripts + compose files) at repo root
- **D-02:** Ship `docker-compose.dev.yml` that brings up Postgres 17 + Redis 7 + Temporal (auto-setup) locally — contributors can hack without a Hetzner box from day 1
- **D-03:** Tests use `embedded-postgres` per MSV pattern; docker-compose.dev is for running the full stack locally, not for test isolation

### Host provisioning
- **D-04:** Idempotent shell scripts in `deploy/hetzner/` — `bootstrap.sh`, `install-docker.sh`, `install-postgres.sh`, `install-redis.sh`, `install-temporal.sh`, `harden-ufw.sh` — all committed, all re-runnable
- **D-05:** OSS-06 self-hosted deployment guide (Phase 7) will reference these scripts directly — they are the production runbook

### Temporal deployment
- **D-06:** `temporalio/auto-setup` as a docker-compose service, same image in dev and prod — one deployment artifact
- **D-07:** Temporal persists to Postgres 17 (separate `temporal` schema/database), bound to `127.0.0.1:7233`
- **D-08:** Temporal Web UI as a companion compose service on `127.0.0.1:8233`

### Auth stub + baseline DB schema
- **D-09:** Dev-cookie auth stub: `POST /api/dev/login` (enabled only when `AP_DEV_MODE=true`) sets a signed HTTP-only session cookie; auth middleware reads it on every protected route. Phase 3 swaps `goth` behind the same middleware interface — zero frontend churn.
- **D-10:** Migration `0001_baseline.sql` creates:
  - `users` (id uuid PK, provider text, provider_sub text, email text, display_name text, avatar_url text, created_at timestamptz, updated_at timestamptz)
  - `user_sessions` (id uuid PK, user_id FK, token_hash text UNIQUE, expires_at timestamptz, created_at timestamptz) — server-side session backing the cookie
  - `agents` (id uuid PK, user_id FK, name text, agent_type text, model_provider text, model_id text, key_source text, status text DEFAULT 'stopped', webhook_url text, container_id text, ssh_port int, config jsonb, created_at timestamptz, updated_at timestamptz) — multi-agent model from day 1
- **D-11:** Phase 1 does NOT populate or exercise the `agents` table beyond schema creation — Phase 4-5 bring it to life. The table exists so downstream migrations extend it, not create it from scratch.

### Mobile-first design
- **D-12:** All frontend work is mobile-first — design for mobile viewport, scale up to desktop. Not "responsive desktop that degrades," but "mobile that enhances."
- **D-13:** Touch-friendly targets (min 44px), responsive breakpoints, standard shadcn/ui mobile patterns
- **D-14:** Phase 1 landing page must look and feel good on a phone — this is the first impression

### Multi-agent data model (groundwork)
- **D-15:** Each user can create N agent instances — each is its own dockerized container with a webhook URL, SSH access, and a chat channel
- **D-16:** On the mobile UI, agents appear as tabs for quick-switch chat (Phase 5 builds this; Phase 1 ships the schema)
- **D-17:** v1 enforces 1 active (running) agent at a time — but schema, API types, and UI components are designed for N-active. Flipping the limit to N is a config change, not a migration or rewrite.
- **D-18:** "Active" means a running container the user can chat with via a tab. Creating / configuring an agent doesn't count as "active" — only launching it does.

### Claude's Discretion
- Mobile navigation pattern (bottom tabs, drawer, etc.)
- Exact breakpoints, spacing, and typography
- Loading states, skeleton design, error states
- Dev login page styling and layout
- docker-compose.dev.yml exact service configuration
- Spike report format and structure

</decisions>

<specifics>
## Specific Ideas

- "Think of each agent like MSV's bot instances — persistent things with their own identity, not transient sessions"
- "Tab on the mobile website where I can send comments to it" — the mobile chat UX is the primary interaction surface
- Agents have webhook URLs and SSH access — multiple integration surfaces beyond browser (web, SSH, webhook, potentially a future native app)
- "The user can create as many as their credit card allows" — no artificial cap on agent count, credits are the natural limiter
- Mission: **democratize agent deployment — the easiest way to deploy any agent x any model**

</specifics>

<canonical_refs>
## Canonical References

### Stack decisions
- `CLAUDE.md` §Technology Stack — All version pins, library choices, and anti-recommendations for the Go + Next.js stack
- `CLAUDE.md` §Stack Patterns by Variant — BYOK vs platform-billed injection patterns, tier-specific container behavior
- `CLAUDE.md` §Web Terminal Stack — ttyd, Go WS proxy, chat↔container bridge architecture

### Research
- `.planning/research/STACK.md` — Technology evaluation and version compatibility
- `.planning/research/ARCHITECTURE.md` — System architecture and component interaction
- `.planning/research/FEATURES.md` — Feature breakdown and implementation approach
- `.planning/research/PITFALLS.md` — Risk areas and mitigation strategies
- `.planning/research/SUMMARY.md` — Research synthesis

### Project
- `.planning/PROJECT.md` — Core value, constraints, key decisions (needs update for multi-agent + mobile-first)
- `.planning/REQUIREMENTS.md` — FND-01..FND-09 are Phase 1 requirements
- `.planning/ROADMAP.md` §Phase 1 — Success criteria and requirement mapping

### Upstream patterns (MSV)
- `/Users/fcavalcanti/dev/meusecretariovirtual/api/` — Go API patterns to mirror (Echo, pgx, zerolog, Docker runner)
- `/Users/fcavalcanti/dev/meusecretariovirtual/api/go.mod` — Pinned dependency versions to match

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- No existing code in the repo yet — Phase 1 is the first code phase
- MSV's `api/` directory is the primary code source for Go patterns (Docker runner, middleware, logging)

### Established Patterns
- None yet — Phase 1 establishes them. Mirror MSV's patterns for Echo middleware, pgx queries, zerolog structured logging.

### Integration Points
- `deploy/` directory will be created by Phase 1 provisioning scripts
- `api/` and `web/` directories will be created as the Go and Next.js skeletons
- `docker-compose.dev.yml` at repo root for local dev stack
- `docker-compose.yml` for prod services (Temporal, optionally PG/Redis if containerized)

</code_context>

<deferred>
## Deferred Ideas

- **SSH access to agent containers** — Each agent gets SSH access; implementation details belong in Phase 5 (session lifecycle surfaces)
- **Webhook URL per agent** — Each agent gets a webhook endpoint for external integrations; Phase 5 scope
- **"Our own app" as access channel** — Native app or installable PWA beyond basic mobile-first web; v2
- **PROJECT.md + REQUIREMENTS.md update needed** — "One active session per user" constraint text needs revision to "N agents per user, 1 active in v1, N-active ready" + mobile-first as a project constraint + mission statement addition. Capture before Phase 1 planning.
- **Multi-agent concurrent billing** — When N-active lands in v2, metering needs per-agent tracking; Phase 6 will need awareness

</deferred>

---

*Phase: 01-foundations-spikes-temporal*
*Context gathered: 2026-04-13*
