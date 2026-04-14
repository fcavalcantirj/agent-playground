---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 2 context gathered with a scope reshape. ROADMAP.md + REQUIREMENTS.md updated; Phase 7.5 (Sandbox Hardening Spine) inserted. Phase 2 is now the hypothesis-forward "agent-in-a-box + stub session API" slice. Ready for planning.
last_updated: "2026-04-14T18:59:51.964Z"
progress:
  total_phases: 9
  completed_phases: 2
  total_plans: 12
  completed_plans: 12
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-11)

**Core value:** Any agent × any model × any user, in one click — agent-agnostic install pipeline is the differentiator that must work.
**Current focus:** Phase 02 planning next — reshaped scope.

## Current Position

Phase: 3
Next:  02 (Agent-in-a-Box + Minimal Substrate, **reshaped 2026-04-14**) — needs `/gsd-plan-phase 2`
Plans complete: 6 of 6 (all Phase 1)
Status: Ready to execute

Progress: [█░░░░░░░░░] 11% (1/9 phases — Phase 7.5 inserted during reshape)

### ⚠️ Phase 02 Reshape (2026-04-14) — READ BEFORE PLANNING

The original Phase 02 in the roadmap bundled substrate + full hardening. After a discuss-phase session, the user challenged whether the hardening half actually moved the project hypothesis forward. Conclusion: it did not, and it should land against a known-working substrate rather than a speculative one.

**Phase 02 now ships:**

1. `ap-base` image (tini PID 1 + tmux chat/shell windows + ttyd on loopback + MSV entrypoint/gosu pattern ported from `meusecretariovirtual/infra/picoclaw/`)
2. Sandbox options wired into `pkg/docker/runner.go` `RunOptions` as fields (SeccompProfile, ReadOnlyRootfs, Tmpfs, CapDrop, NoNewPrivs, Runtime, NetworkMode, PidsLimit, Memory, CPUs) — safe defaults applied at call sites, no custom seccomp JSON yet
3. Deterministic container naming `playground-<user_uuid>-<session_uuid>` + validator + helper in runner.go
4. Two pre-built recipe images: **picoclaw** (Go CLI, pinned SHA from `/Users/fcavalcanti/dev/picoclaw`, `stdin_fifo` chat path) + **Hermes** (Python 3.11, pinned SHA from `github.com/NousResearch/hermes-agent`, MIT, TUI-first, multi-channel daemon disabled via pre-populated `~/.hermes/cli-config.yaml`, backend forced to `local`)
5. **Minimal non-durable session API stubs** pulled forward from Phase 5 scope: `POST /api/sessions`, `POST /api/sessions/:id/message` (synchronous FIFO bridge via `docker exec`), `DELETE /api/sessions/:id`. Direct runner.go calls — **no Temporal in Phase 2.** Phase 5 upgrades internals with SessionSpawn/SessionDestroy workflows, HTTP contract stays stable.
6. Dev BYOK via `AP_DEV_BYOK_KEY` env → tmpfs `/run/secrets/*_key` injection (file-based mechanism is Phase 2; Phase 3 replaces the source with the encrypted vault).
7. Hardcoded recipe structs in new `internal/recipes/` package (Phase 4 replaces with YAML schema + loader)
8. New migration `0002_sessions.sql` — `sessions` table (id, user_id, recipe_name, model_provider, model_id, container_id, status, created_at, updated_at). One-active-per-user enforced via Postgres partial unique index.
9. **Hypothesis proof smoke test:** `make smoke-test` or equivalent runs curl against the API, starts both agents, exchanges a real message with a real Anthropic model via BYOK, tears down cleanly, asserts no dangling `playground-*` containers. The curl output IS the demo — no browser UX until Phase 5.

**Phase 02 does NOT ship (deferred to new Phase 7.5):**

- Custom seccomp profile JSON
- `ap-net` Docker bridge + iptables DOCKER-USER egress allowlist
- Falco or Tetragon + rule set + alerting sink
- Escape-test CI harness (mount/unshare/setns/docker.sock/evil egress)
- gVisor `runsc` install + per-recipe runtime selection (Spike 4 still pending — not a Phase 2 blocker anymore, only gates Phase 7.5 + Phase 8)

**Phase 7.5 (new, inserted 2026-04-14): Sandbox Hardening Spine.** Fills in every sandbox knob Phase 2 plumbed, against a known-working substrate, right before Phase 8 introduces the first untrusted-code path. Requirements moved there: SBX-02 (custom seccomp portion), SBX-04, SBX-06, SBX-07 (Falco portion), SBX-08.

**Critical forward-compatibility signals from discuss-phase (user verbatim):**

- *"API-driven start without Telegram is the hypothesis proof"* — Phase 2 completion gate is curl → real model response for both agents
- *"this list will grow"* — recipe abstraction must accept new agents as recipe YAML + Dockerfile, no code changes to `ap-base`, `runner.go`, or session handlers. Hermes being the architecturally hardest agent validates the pattern.
- *"Hermes is totally different from OpenClaw"* — OpenClaw (gateway-WebSocket, Node, pairing) vs Hermes (PTY TUI, Python 3.11, multi-channel daemon, six execution backends). Both must fit `ap-base` without special-casing. Hermes's chat bridge mechanism (PTY screen-scrape vs MCP via `mcp_serve.py` vs hypothetical CLI `--message` flag) is a Phase 2 **planning research** item.

**Full reshape rationale + every decision + canonical refs:** `.planning/phases/02-container-sandbox-spine/02-CONTEXT.md`

**Discussion audit trail:** `.planning/phases/02-container-sandbox-spine/02-DISCUSSION-LOG.md`

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: ~25 min/plan (parallel waves; wall clock ~3h45m total)
- Total execution time: ~4 hours wall clock for Phase 01 end-to-end

**By Phase:**

| Phase | Plans | Wall Time | Notes |
|-------|-------|-----------|-------|
| 01    | 6     | ~4h       | 5-plan parallel Wave 1 + 1-plan Wave 2; opus executors in worktrees |

## Accumulated Context

### Decisions (locked)

From PROJECT.md Key Decisions:

- **Temporal is required** (overrides research's "drop Temporal" recommendation). Session create/destroy, recipe install, reconciliation = Temporal workflows. Workers must be running. **PROVEN in Phase 01:** PingPong workflow ran live against the cluster, 50ms, completed.
- **Go API + Next.js** mirrors MSV. `pkg/docker/runner.go` ported from MSV pattern but rewritten for the **Docker Engine SDK** (`github.com/moby/moby/client`) — explicitly NOT `os/exec` shelling. Verified clean.
- **Hetzner dedicated single host.** No K8s, no cloud-managed containers. docker-compose stack on host.
- **BYOK first-class.** Platform-billed mode via LiteLLM + Stripe credit ledger (Phase 6/7).
- **gVisor (`runsc`) mandatory for Phase 8** bootstrap path. Curated recipes may use plain `runc`.
- **Apache-2.0 OSS.** Monetization = hosted service.

### Phase 01 Outcomes (what now exists in the repo)

**Go API (`api/`):**

- Echo v4.15.1 + pgx v5.9.1 + Redis v9.18 + zerolog
- `cmd/server/main.go` boot: config → DB → Redis → migrations → server.New(...opts) → graceful shutdown
- `pkg/database/postgres.go` — pgxpool wrapper
- `pkg/redis/client.go` — Redis wrapper
- `pkg/migrate/` — embedded `//go:embed sql/*.sql` migrator with `pg_advisory_lock(8675309)` + per-migration tx (CR-04 fix). Baseline schema = users / user_sessions / agents (with partial unique index `idx_agents_one_active_per_user`).
- `pkg/docker/runner.go` — 396 lines, Docker Engine SDK (NOT os/exec). Run / Exec / Inspect / Stop / Remove + strict input validation (validateContainerID/validateImageName/validateEnvVar/validateMountPath). 49 unit tests + integration test (real Docker, alpine:3.19) all green.
- `internal/server/server.go` — `server.New(cfg, logger, checker, opts ...Option)` with **functional options pattern**. `WithDevAuth(...)` and `WithWorkers(WorkerManager)` are the two options. Plan 01-01 pre-declared the pattern so Plan 01-05 added Temporal without touching the New signature.
- `internal/handler/` — health (`/healthz` returning DB+Redis status), checker, devauth (POST /api/dev/login, POST /api/dev/logout, GET /api/me).
- `internal/middleware/auth.go` — `SessionProvider` interface (Phase 3 will swap goth in), HMAC-SHA256 signed `ap_session` cookie (HttpOnly, SameSite=Lax), `VerifyCookie` constant-time compare (CR-01 fix). Session secret length validated unconditionally (CR-02 fix).
- `internal/temporal/` — 3 workers (session/billing/reconciliation queues), 5 stub workflows (SessionSpawn, SessionDestroy, RecipeInstall, ReconcileContainers, ReconcileBilling) + PingPong proof. Workers.Start() rolls back partial startups (CR-03 fix). Empty TEMPORAL_HOST short-circuits to skip Temporal entirely (WR-01 fix).

**Next.js frontend (`web/`):**

- Next 16.2 + React 19.2 + Tailwind v4 + shadcn/ui + Inter font + dark mode default + emerald accent
- `src/app/page.tsx` — auth-gated landing. **Uses versioned auth re-fetch pattern**: `authVersion` state bumped by `refreshAuth` callback re-runs the /api/me effect. (Was using `router.refresh()` which only re-runs server components — fixed in `eecbef4`.)
- `src/components/dev-login-form.tsx` — emerald 44px touch-target button, calls `onLoginSuccess` callback prop after POST /api/dev/login
- `src/components/top-bar.tsx` — sticky top bar, sign-out icon, calls `onSignOut` callback prop
- `src/lib/api.ts` — `apiGet/apiPost` with `credentials: 'include'` and typed `ApiError`/`SessionUser`
- `src/middleware.ts` — Next middleware (no-op for Phase 01, set up for Phase 02+)
- `next.config.ts` — rewrites `/api/*` → `http://localhost:8080/api/*` for local dev
- **CRITICAL:** `web/AGENTS.md` says "This is NOT the Next.js you know" — Next 16 has breaking changes; future agents must read `node_modules/next/dist/docs/` before touching Next-specific code. Already burned by NODE_ENV=development causing build failure during 01-03.

**Infrastructure:**

- `docker-compose.dev.yml` — Postgres 17 + Redis 7 + **Temporal 1.29.3** + **Temporal UI 2.34.0** (CR-05 fix: pinned versions). All ports `127.0.0.1`-bound. `condition: service_healthy` on temporal→postgresql. **Removed `DYNAMIC_CONFIG_FILE_PATH`** env var (compose fix `480d5b4`) — image doesn't ship the file and we don't mount it.
- `docker-compose.yml` — production Temporal + UI, `network_mode: host`, same pinned versions
- `deploy/dev/init-db.sh` — creates `agent_playground` DB after first compose up
- `deploy/hetzner/` — 6 idempotent provisioning scripts: bootstrap.sh, install-docker.sh (with userns-remap), install-postgres.sh, install-redis.sh, install-temporal.sh, harden-ufw.sh (default-deny, 22 + 443 only)
- `.env.example` — all env vars documented

**Spike report (`.planning/research/SPIKE-REPORT.md`):**

- **Spike 1** (per-agent HTTPS_PROXY vs *_BASE_URL): OpenClaw + PicoClaw both honor BOTH; HTTPS_PROXY env wins for v1 transparent metering proxy. Hermes/HiClaw/NanoClaw deferred to Phase 4 recipe authoring (sources not local).
- **Spike 2** (chat_io.mode per agent): OpenClaw = `gateway-websocket`; PicoClaw = `cli-stdio` + per-channel adapters. Drives `chat_io.mode` enum addition to Phase 4 recipe schema.
- **Spike 3** (tmux + named-pipe RTT): **min 69µs / p50 85µs / p95 138µs / p99 0.19ms / max 238µs** measured locally in alpine:3.20 Docker. PASS — 262× headroom under 50ms budget.
- **Spike 4** (gVisor runsc on Hetzner): NOT EXECUTED. Needs SSH to prod box (gVisor is Linux-only, can't run from macOS). Exact commands documented in §"Spike 4 — Exact commands to run on the Hetzner host". Result template at end of report — fill kernel version, runsc version, PASS/FAIL.

### Code Review Outcomes

`01-REVIEW.md` (initial): 5 critical / 6 warnings / 5 info
`01-REVIEW-FIX.md`: 11/11 critical+warning fixed in single pass, 0 skipped. Info findings deferred (run `/gsd-code-review-fix 01 --all` to address).

Notable info-severity items deferred:

- INF-01: HMAC compare logic duplicated in 2 places (now uses shared VerifyCookie after CR-01, but constant could be extracted)
- INF-02: Related — VerifyCookie naming
- INF-03: docker-compose missing temporal healthcheck (currently relies on restart: on-failure)
- INF-04: API_BASE empty string in `web/src/lib/api.ts` could be more defensive
- INF-05: SQL injection risk in install-postgres.sh if operator passes hostile password (low-prio; operator controls input)

### Verification Outcomes

`01-VERIFICATION.md`: status `human_needed`, score 9/10 must-haves verified.
`01-HUMAN-UAT.md`: 2 items

1. ✅ **CLEARED** — Visual mobile-first frontend verification (375px viewport) — passed live test after `eecbef4` fix to login/logout reload bug
2. ⏳ **PENDING** — Spike 4: gVisor runsc on Hetzner — needs human SSH

### Bugs Found and Fixed During Phase 01 Execution

1. **`480d5b4 fix(01-04): drop unmountable DYNAMIC_CONFIG_FILE_PATH from compose files`** — Temporal compose env referenced a config file not shipped in image. Found while testing.
2. **`eecbef4 fix(01-03): re-check auth on login/logout via callback instead of router.refresh`** — Frontend used router.refresh() but page is a client component. Caught by visual UAT.
3. The 11 code-review fixes (CR-01..05, WR-01..06) — see `01-REVIEW-FIX.md`.

### Phase 01 Git Log Summary (newest first)

```
eecbef4 fix(01-03): re-check auth on login/logout via callback instead of router.refresh
66295fb docs(01): add code review fix report
3250a47 fix(01): WR-06 ...
444e821 fix(01): WR-05 ...
9402fe6 fix(01): WR-04 ...
81dc055 fix(01): WR-03 ...
dc4a258 fix(01): WR-02 ...
479be7c fix(01): WR-01 ...
05e5fde fix(01): CR-05 ...
f642408 fix(01): CR-04 ...
cbd16d5 fix(01): CR-03 ...
391f7f4 fix(01): CR-02 ...
43c6499 fix(01): CR-01 ...
98224c1 test(01): persist human verification items as UAT
c1f144a docs(01): add phase verification report
174ad63 docs(01): add code review report
80b5abb docs(01-05): complete temporal workers plan
9bf3fc6 feat(01-05): wire temporal workers into main.go via WithWorkers option
1c0560e feat(01-05): add temporal workers + stub workflows + PingPong proof
480d5b4 fix(01-04): drop unmountable DYNAMIC_CONFIG_FILE_PATH from compose files
387c685 docs(01-03): add plan summary
c9e53d6 chore: merge 01-03 worktree (next.js frontend shell)
5afaa8c chore: merge 01-06 worktree (spike report 1-3)
e16a71f chore: merge 01-04 worktree (hetzner provisioning + dev compose)
6d742ba chore: merge 01-02 worktree (docker SDK runner)
fec45dd feat(01-03): auth-gated landing page + dev login + dashboard shell
9e1364c feat(01-03): scaffold Next.js 16 + shadcn/ui + emerald design system
... (Plan 01-01 + 01-02 + 01-04 + 01-06 commits before merges)
```

### Pending Todos

- **Spike 4 (gVisor on Hetzner)** — human action required. SSH to Hetzner host, run `runsc install` + `docker run --runtime=runsc alpine:3.20 echo hello`. Update `.planning/research/SPIKE-REPORT.md` §"Spike 4 — Result template" with kernel version, runsc version, PASS/FAIL. Result gates Phase 8 sandbox tier: if FAIL, Phase 8 must pivot from gVisor to Sysbox-only or microVMs.
- **5 info-severity code review items** deferred — run `/gsd-code-review-fix 01 --all` if/when desired (low priority).

### Blockers/Concerns

- **None blocking Phase 02.** Spike 4 result is needed for Phase 8 architecture decision but does NOT block Phase 02 (Recipes & Sandbox). Phase 02 can proceed assuming gVisor works; if it later fails, Phase 8 plans get adjusted.

## Local Dev Stack — How to Bring It Back Up

```bash

# Compose stack (currently running — postgres + redis + temporal + temporal UI)

docker compose -f docker-compose.dev.yml up -d
./deploy/dev/init-db.sh   # only on first start

# Go API

cd api && \
  AP_DEV_MODE=true \
  AP_SESSION_SECRET=test-secret-that-is-at-least-32-characters-long \
  DATABASE_URL="postgres://temporal:temporal@localhost:5432/agent_playground?sslmode=disable" \
  REDIS_URL=redis://localhost:6379 \
  TEMPORAL_HOST=localhost:7233 \
  TEMPORAL_NAMESPACE=default \
  API_PORT=8080 \
  go run ./cmd/server/

# Next.js

cd web && pnpm dev

# Trigger PingPong workflow (proves Temporal end-to-end)

docker exec agent-playground-temporal-1 sh -c 'temporal --address $(hostname -i):7233 workflow execute --type PingPong --task-queue session --workflow-id ping-pong-test --input "\"hello\""'
```

URLs:

- http://localhost:8080/healthz — Go API health
- http://localhost:3000 — Frontend
- http://localhost:8233 — Temporal Web UI

## Session Continuity

Last session: 2026-04-14 — Phase 2 discuss-phase + roadmap reshape
Stopped at: Phase 2 context gathered with a scope reshape. ROADMAP.md + REQUIREMENTS.md updated; Phase 7.5 (Sandbox Hardening Spine) inserted. Phase 2 is now the hypothesis-forward "agent-in-a-box + stub session API" slice. Ready for planning.

**Next command:** `/gsd-plan-phase 2`

### Reading order for a fresh session after /clear

1. `.planning/STATE.md` (this file) — top-level situational awareness + Phase 2 reshape summary above
2. `.planning/phases/02-container-sandbox-spine/02-CONTEXT.md` — **source of truth for Phase 2 decisions**. Every decision from the discuss-phase is in `<decisions>`; every doc downstream agents need is in `<canonical_refs>`; every deferred idea is in `<deferred>`.
3. `.planning/phases/02-container-sandbox-spine/02-DISCUSSION-LOG.md` — full Q&A audit trail (optional; use if you need to understand WHY a decision was made, not just WHAT was decided)
4. `.planning/ROADMAP.md` §Phase 2 — reshaped success criteria + requirement mapping (points at 02-CONTEXT.md)
5. `.planning/ROADMAP.md` §Phase 7.5 — new phase inserted during reshape; holds the deferred hardening work
6. `.planning/REQUIREMENTS.md` — SBX-02 partial, SBX-04/06/07/08 moved to Phase 7.5
7. `.planning/research/SPIKE-REPORT.md` — Phase 1 spike findings (Hermes gap; Phase 2 planning must extend Spike 1+2 for Hermes)
8. `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/Dockerfile` + `entrypoint.sh` — MSV's battle-tested dockerized-agent pattern to port into `ap-base` (entry point, privilege drop via gosu, pre-populated config baked at build)

### Planning research items Phase 2 must resolve (flagged in 02-CONTEXT.md D-23)

- Hermes chat bridge mechanism: PTY screen-scrape vs MCP (via `mcp_serve.py`) vs hypothetical `hermes --message` non-interactive CLI flag. Fetch the `cli-config.yaml.example` from `github.com/NousResearch/hermes-agent` to pin exact keys.
- Exact YAML keys in Hermes `cli-config.yaml` for (a) disabling Telegram/Discord/Slack/WhatsApp/Signal/SMS/Email/Matrix/Mattermost gateway daemons and (b) forcing `backend: local`.
- Commit SHAs to pin picoclaw and Hermes to (pick the latest stable at plan-writing time).
- Extend Spike 1 + Spike 2 for Hermes (currently picoclaw + OpenClaw only covered).

Resume file: .planning/phases/02-container-sandbox-spine/02-CONTEXT.md
