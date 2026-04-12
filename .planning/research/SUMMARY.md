# Project Research Summary

**Project:** Agent Playground
**Domain:** Multi-tenant per-user dockerized AI coding-agent runner (agent × model agnostic, browser-only, Hetzner single-host)
**Researched:** 2026-04-11
**Confidence:** MEDIUM-HIGH

## Executive Summary

Agent Playground is a hosted, open-source web platform that lets a logged-in user pick *any* CLI coding agent from the clawclones ecosystem (OpenClaw, Hermes, HiClaw, PicoClaw, and growing) combined with *any* model provider (OpenRouter, Anthropic, OpenAI — BYOK or platform-billed) and get a dockerized per-user session driven through both a browser chat UI and a web terminal attached to the **same** container. The architecture is a near-direct mirror of MSV (Go + Echo v4 + pgx v5 + Next.js 16 + Docker on a Hetzner dedicated host) with three deliberate divergences: **drop Telegram entirely**, **drop Temporal in favor of a Postgres-backed in-process orchestrator**, and **generalize the agent dimension** via a recipe catalog (`agents/<name>/recipe.yaml` + JSON-Schema + CI smoke tests) plus a generic Claude-Code bootstrap fallback for unknown git repos.

The expert-consensus build approach is a single Go binary (`api/` + in-process orchestrator + `pkg/docker/runner.go` shell-out like MSV), one tmux-muxed container per active user session, **ttyd** inside the container exposing the terminal on a loopback port that the Go API reverse-proxies, and **named pipes in tmux** (not a second PTY) connecting the chat UI to the agent's stdio. Metering for platform-billed sessions flows through a single host-wide **LiteLLM Proxy** with per-session virtual keys; BYOK bypasses the proxy entirely and never touches a billing table. Stripe v82's Billing Credit Balance + Meter Events APIs are the right primitives for the credit ledger, but must be wired through an **atomic idempotent ledger** (not MSV's cached `poken_balances`) with pre-authorized token budgets.

The dominant risks cluster in three areas and must set the shape of the early phases: **(1) security of the untrusted-code path** — the bootstrap differentiator executes arbitrary repo install scripts and is a container-escape / BYOK-exfiltration vector by default, so sandbox hardening (drop caps, user-namespace remap, read-only rootfs, egress allowlist, gVisor/Sysbox runtime) is a Phase-2 non-negotiable; **(2) billing correctness** — Stripe webhook races, token-usage drift, and runaway agent loops can each quietly drain real money, so idempotent webhooks + atomic ledger + circuit breakers must ship *with* the credit system, never "later"; **(3) MSV-inherited operational pain** — dangling containers, `poken_balances` races, plaintext env-var key injection, UFW-off, 40GB disk, agent OOMs. Every one of these is already a documented pain point in MSV's own docs; inheriting them uncritically would repeat known failures. The research is high-signal precisely because MSV serves as an honest post-mortem of the exact pattern.

## Key Findings

### Recommended Stack

Mirror MSV's Go core verbatim where it works, diverge surgically where the product requirements force it. All versions are current as of April 2026 and the stack is biased toward "boring, verified, transferable from BasicPay/MSV muscle memory" over novelty.

**Core technologies:**
- **Go 1.25.x + Echo v4.15.x** — single-binary API + in-process orchestrator. **Pin v4; do NOT use Echo v5 until after 2026-04-01** per the maintainer's own guidance. v4 is supported through 2026-12-31.
- **pgx v5.8.x + PostgreSQL 17** — raw SQL, no ORM, no sqlc. Single source of truth for users, sessions, recipes, credit ledger, webhook idempotency, audit log. **Not SQLite** — orchestrator + webhooks + concurrent writes need real concurrency.
- **Redis (go-redis v9.18.x)** — locks (SETNX for session create), pubsub (`session:{id}:chat:out`), rate limits, WS presence. Cache only; losing Redis is a brownout, not an outage.
- **Next.js 16.2 (App Router) + React 19.2 + TypeScript 5.7 + Tailwind v4 + shadcn/ui** — mirrors BasicPay. Use Turbopack (stable in 16), React Compiler 1.0 on by default.
- **Docker Engine 27.x + `github.com/moby/moby/client`** — canonical SDK import path (NOT `docker/docker/client`, NOT `fsouza/go-dockerclient`). MSV uses a `pkg/docker/runner.go` shell-out pattern with strict arg validation; **prefer that for v1** (audit-friendly, zero vendored deps, MSV-proven). Embed the SDK only if the shell-out becomes a bottleneck.
- **`coder/websocket` v1.8+** — NOT `gorilla/websocket`, NOT `nhooyr.io/websocket` (deprecated; `coder/websocket` is the active fork).
- **`ttyd` (inside each user container)** + **`@xterm/xterm` 5.5 + addon-fit/attach** on the browser. ttyd runs on a loopback-bound port; Go API reverse-proxies + enforces auth. Picked over GoTTY (unmaintained since 2017) and Wetty (Node, heavier).
- **`tmux` inside the container with named pipes** — the chat UI writes to `/work/.ap/chat.in` and reads `/work/.ap/chat.out` (not a PTY), the terminal UI attaches to a *separate* tmux window. This is the **load-bearing decision** that avoids PTY-contention between the two surfaces while keeping both views on the same container and the same `/work` filesystem.
- **`markbates/goth`** — Google + GitHub OAuth, server-side session in Postgres, HTTP-only signed cookie. **NOT NextAuth/Auth.js** — the Go API must be the canonical source of session and billing truth.
- **Stripe SDK v82** (`stripe-go/v82`, API `2025-03-31.basil`) — first-class Billing Credit Balance + Meter Events APIs, exactly the right primitives for the credit model.
- **`anthropics/anthropic-sdk-go`** (for direct Anthropic platform-billed path) and **`openai/openai-go`** (used for both OpenAI direct *and* OpenRouter by overriding `BaseURL` — OpenRouter is OpenAI-compatible; one client, two providers).
- **LiteLLM Proxy (Python, host-wide on `127.0.0.1:8088`)** — single instance, per-session virtual keys, built-in Postgres logging, maintained provider price table. Picked over custom Go proxy (cost-table drift, per-provider shape parity is a forever tax) and per-container sidecar (50MB × N users = RAM blowout).
- **Hetzner dedicated host + Docker on host + `userns-remap` from day 1 + Sysbox (`sysbox-runc`) by v1.5 + gVisor (`runsc`) for the bootstrap path** — explicit tiered isolation. Vanilla `runc` is insufficient for untrusted-code paths.
- **No Temporal, no K8s, no Kafka, no Vault.** In-process orchestrator + Postgres queue + systemd + pgcrypto-encrypted BYOK key storage.

**Explicit don't-use list (load-bearing):** Echo v5 in v1, GORM, `docker/docker/client` import path, `gotty`, `nhooyr.io/websocket`, `fsouza/go-dockerclient`, `os/exec`-shelling-`docker run` without arg validation, K3s/Nomad/Kubernetes, NextAuth as canonical session, GORM struct-tag migrations, storing OAuth tokens in cookies, running the agent CLI as PID 1 (use `tini` + supervise ttyd + agent), **mounting the host Docker socket into user containers**, `--privileged`, plain env-var injection of BYOK keys (see CRIT-2).

Full detail: `.planning/research/STACK.md`.

### Expected Features

**Must have (v1 table stakes):**
- Google + GitHub OAuth (`goth`, no email/password)
- Agent picker UI with 3–4 hardcoded recipes (OpenClaw, Hermes, HiClaw, PicoClaw)
- Model picker scoped to the selected agent's `recipe.models.supported_providers` (turns multi-agent complexity into a guard rail, not a footgun)
- BYOK key management: one row per provider, "test key" button, encrypted at rest (pgcrypto), masked display, **never logged, never returned**
- Session start → Docker container → recipe install → launch → TTY ready in <10s (pre-warmed base image pool)
- **Web terminal surface (xterm.js + ttyd proxy)** — the simpler of the two surfaces; ship first
- Stop / destroy session button + visible state machine (`provisioning`/`ready`/`running`/`stopped`/`failed`)
- One active session per user (enforced via Postgres `UNIQUE (user_id) WHERE status IN (…)` partial index + Redis SETNX)
- Free tier = ephemeral `--rm` container, tmpfs volume, 15min idle timeout, stricter resource caps

**Should have (v1.0 first marketable release):**
- **Chat surface alongside terminal (hybrid view on the same container, same tmux)** — the wedge vs Warp (desktop-only), Replit (chat-only), aider (terminal-only)
- Stripe credit top-up (Checkout) + USD balance displayed in header draining live during platform-billed sessions
- Session timeout with countdown UI + idle warning
- Paid tier = per-user named volume (`ap-vol-{user_id}`), reconnect-after-disconnect, backup via restic to Hetzner Storage Box or MinIO
- "Test key" validation, last-4 masked display
- Transaction history / append-only credit ledger for dispute resolution
- Low-balance warning at 20%, hard cutoff at 0 (via LiteLLM budget enforcement)

**Differentiators (what makes it win):**
1. **Agent-agnostic recipe system** — `agents/<name>/recipe.yaml` + `Dockerfile` + CI smoke test, PR-driven contribution flow (devcontainer features as the direct model). **No competitor treats the agent itself as a swappable resource.** This is the moat.
2. **Hybrid chat + terminal on the same container** via tmux + named pipes.
3. **BYOK is first-class, not punished.** Every feature works with BYOK, no asterisks. Directly contra Cursor ("Agent and Edit cannot be billed to an API key") and Replit (no BYOK at all).
4. **Whole platform open source** (Apache-2.0 recommended for the patent grant) — monetize the hosted service, not the code; OSS drives long-term recipe catalog contributions.
5. **"Try any git repo as an agent"** — paste a GitHub URL on the homepage, 30 seconds later working session. The demoable differentiator. Backed by the generic Claude-Code bootstrap path.
6. **Predictable per-container cost** on Hetzner dedicated — MSV proved $0.044/user/month at 10k users. Enables free credits other platforms can't match.

**Defer to v1.5 or v2:**
- Generic Claude-Code bootstrap (highest-risk, highest-differentiator — ship curated path first, then bootstrap)
- Recipe catalog browser UI (vs hardcoded list), recipe contribution flow with CI
- Cost preview before expensive operations (Replit can only do this because they own agent+model; we don't)
- Local/Ollama provider (different resource model — GPU/CPU vs API call)
- Multiple parallel sessions per user (tier-gated v2 upgrade lever)
- Monthly subscription billing (credits only in v1)
- Recipe version pinning, self-hosted deployment docs, real-time collaboration

**Anti-features (explicitly NOT building, even when asked):**
- **Telegram bot / Telegram-as-UI** — MSV's biggest constraint, explicitly removed. Browser-only. Period.
- **Locked-to-one-agent** or **locked-to-one-provider** — defeats the product premise. Agent picker and 3-provider model picker are top-level from day 1.
- **BYOK punishment** à la Cursor — the whole point of BYOK is no asterisks.
- **In-product file editor / IDE** — we are an *agent runner*, not Replit. Files happen via the agent's own commands.
- **Email/password auth, cloud-managed hosting (AWS/GCP/Fly), closed-source core, curated-only catalog, shared global terminal, parallel sessions in v1, cost preview prediction.**

Full detail: `.planning/research/FEATURES.md`.

### Architecture Approach

Single Go binary hosts the Echo v4 HTTP API, the in-process Session Orchestrator, and the Recipe Runner. Postgres is the source of truth; Docker is a cache that a reconciliation loop reconciles every 30s. Redis provides locks + pubsub. Each active user session maps to one Docker container running `tini` → `tmux` with two windows: `chat` (agent attached via named pipes) and `shell` (plain bash). `ttyd` runs inside the container bound to a loopback port; the Go API reverse-proxies `wss /api/sessions/:id/tty` to it. The chat surface (`wss /api/sessions/:id/stream`) uses `docker exec` to read/write the named pipes and republishes via Redis pubsub, decoupling WS connection lifetime from container lifetime so browser reconnects do not lose state. For platform-billed sessions, the orchestrator injects `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` / `OPENROUTER_BASE_URL` pointing at `host.docker.internal:8088` (LiteLLM) plus a per-session virtual key; BYOK bypasses the proxy entirely and injects the raw key via a tmpfs-backed secret file at `/run/secrets/<provider>_key` (never plain env var — see CRIT-2).

**Major components:**
1. **Next.js 16 Web UI** — SSR/CSR, shadcn/ui, xterm.js terminal, React Query data layer, Stripe Elements for top-ups. Talks to the Go API over HTTPS + two WSS endpoints per session.
2. **Go API (Echo v4)** — OAuth (goth), JWT-over-cookie session, session CRUD, WS hub, Stripe webhook handler, rate limiter. Same binary as #3.
3. **Session Orchestrator (in-process Go package)** — `Spawn/Get/Stop/Pause/AttachChat/ProxyTTY/ListByUser`. Uses `pkg/docker/runner.go` (ported from MSV, shell-out with strict arg validation) for all container lifecycle. Enforces the one-active invariant at two layers (Postgres partial unique index + Redis SETNX). Idle reaper + reconciliation loop goroutines.
4. **Recipe Runner (Go package)** — Deterministic mode (reads `agents/<name>/recipe.yaml`, validates against `agents/_schema/recipe.schema.json`, executes install + launch via `docker exec` into tmux) and Bootstrap mode (spins `ap-base:bootstrap` with Claude Code preinstalled, runs templated prompt at `/prompt.md`, captures emitted `recipe.yaml`, validates, caches).
5. **Model Proxy (LiteLLM, host systemd unit on 127.0.0.1:8088)** — Per-session virtual keys with budget caps, built-in Postgres `LiteLLM_SpendLogs`, automatic 429 on budget exhaustion, cost calculation via maintained price table. Shared across all containers. Bypassed on BYOK.
6. **Postgres 17** — `users`, `oauth_identities`, `sessions`, `containers`, `volumes`, `recipes`, `credit_ledger`, `usage_events`, `stripe_events` (idempotency), `byok_keys` (encrypted), `audit_log`. One instance, 127.0.0.1-bound.
7. **Redis 7** — Locks, pubsub, ephemeral state. One instance, 127.0.0.1-bound.
8. **MinIO (optional v1.0, required by Phase 6 persistence tier)** — Volume snapshots, bootstrap recipe cache.
9. **In-container PTY mux** — `tini` → `tmux` (two windows) + `ttyd` + named pipes for chat. Ships in the `ap-base` image; each agent recipe layers on top.

**Two WebSocket endpoints per session** (not one) — `/api/sessions/:id/stream` (chat, reads/writes named pipes) and `/api/sessions/:id/tty` (terminal, proxies ttyd). Multiplex over one WS is a v1.5 nicety.

**Build order from ARCHITECTURE.md §9 (the minimum cut):** Postgres + migrations → Go API skeleton + OAuth → `pkg/docker/runner.go` port → Recipe loader + schema validator → `agents/openclaw/recipe.yaml` + `agents/_base/Dockerfile` (node22 + tmux + ttyd + tini) → `Orchestrator.Spawn` (deterministic mode) → tmux+named-pipe init → Chat WS handler → Next.js shell with login + "New session" + chat textarea → one-active-session invariant. **That cut is the demoable MVP.** Terminal, LiteLLM, Stripe, persistent volumes, bootstrap all layer on top.

Full detail: `.planning/research/ARCHITECTURE.md`.

### Critical Pitfalls

Six critical pitfalls shape phase design. Every one of them must be addressed *with* the phase it belongs to, not "later." Most are MSV-inherited pain — this project starts with an honest post-mortem of the exact pattern it's mirroring.

1. **CRIT-1: Bootstrap executing arbitrary install scripts as root in a weak sandbox (container escape, cross-tenant key exfiltration).** The differentiator is also the biggest attack surface. Prevention: gVisor (`runsc`) runtime for the bootstrap path, never Docker socket inside the container, read-only rootfs + tmpfs `/tmp` + dedicated `/workspace`, drop all caps + `no-new-privileges` + tight seccomp, network egress allowlist (model providers + package registries + user's git remote — nothing else), user-namespace remap, recipe content addressing so cached recipes never silently inherit permissions from a different repo. **Phase 2 non-negotiable.**
2. **CRIT-2: BYOK keys leaking via env var → `/proc/<pid>/environ`, logs, crash dumps, git history.** MSV's `INFRASTRUCTURE.md` already documents the env-var injection pattern that would cause exactly this leak. **Do not inherit.** Prevention: never inject BYOK as plain env var. Container env holds only `PLAYGROUND_PROXY_URL` + `PLAYGROUND_SESSION_TOKEN`; the host-side proxy injects the real key into outbound HTTPS. For agents that genuinely require the raw env var, use a tmpfs-backed `/run/secrets/<provider>_key` and an entrypoint shim that exports it only into the agent process, never PID 1. Plus stdout/stderr regex scrubber, pre-commit gitleaks in workspace base, recipe CI lint forbidding `ENV`/`ARG` with secrets, `ulimit -c 0`. **Phase 3 non-negotiable, must ship before BYOK input UI is live.**
3. **CRIT-3: Runaway agent loop draining credits (or BYOK bill) — check-before, deduct-after race + concurrent in-flight calls.** Prevention: **pre-authorize** token budget (estimate `max_tokens` × rate, deduct optimistically, refund unused delta). Hard circuit breakers independent of billing (≤60 calls/min per session, token cap, wall-clock cap). Loop-detection heuristic (N calls in M seconds with no file diff → kill + email user). Atomic ledger (`SUM(transactions)`, **not** a cached `poken_balances` scalar — MSV's pattern is race-prone). OpenRouter per-session sub-keys with hard caps where possible. BYOK gets the same circuit breakers. **Phase 5 must include the rate limiter from day one.**
4. **CRIT-4: Cross-tenant kernel escape.** Vanilla `runc` on a shared kernel is one kernel CVE (`overlayfs`, `io_uring`, `eBPF`, Dirty Pipe, or a 2026 equivalent of CVE-2025-9074) away from a cross-tenant root. Prevention: gVisor `runsc` as default runtime for user containers, Kata Containers for a Pro tier, userns-remap on the host, tight seccomp + AppArmor, drop all caps, `unattended-upgrades` for kernel patches, Falco/Tetragon for syscall anomaly alerts. **Phase 2 — switching runtimes later is technically easy but invalidates every recipe's validation.**
5. **CRIT-5: Stripe webhook race double-crediting or losing credits.** At-least-once delivery + "check then write" non-atomic handler = over-credit or ghost receipts. Prevention: **UNIQUE constraint on `stripe_event_id`** in `webhook_events`, INSERT as first action *inside the same transaction* as the credit update. Verify Stripe signatures on every webhook, reject events > 5 min old (replay window). Balance is `SUM(amount) FROM transactions`, never a stored scalar. Queue webhooks per-user-id key for serial processing. Nightly reconciliation against Stripe's event list. **Phase 5, wired in before the first real Stripe call.**
6. **CRIT-6: Dangling containers + orphaned state after API crashes.** Two systems of record (Postgres + Docker daemon) diverge without a reconciliation loop. Prevention: **Postgres is the source of truth, Docker is the cache**; reconciliation loop every 30s lists all `playground-*` containers + all DB sessions and fixes the diff. Idempotent container names (`playground-<user_uuid>-<session_uuid>`). Explicit state machine (`pending → starting → running → stopping → stopped → reaped`). pg-boss / DBOS-style durable workflows for session create/destroy (MSV's converged decision per `RELIABLE-AGENT-EXECUTION.md` — inherit). Heartbeat-out from the container + host-side liveness probe. Volume GC owned by a separate slower loop. **Phase 4 — build the reconciliation loop with the lifecycle manager, not after.**

Moderate and minor pitfalls (MOD-1..8, MIN-1..10) cover token-counting drift between providers, BYOK-vs-platform mode confusion, recipe drift from upstream agents, YAML/shell injection via user-supplied repo URLs, disk-filling from persistent volumes (MSV's 40GB box is **not** sufficient — spec ≥500GB NVMe), PTY contention + WS auth bypass on the web terminal, idle reaper false-kills during long builds, persistent volume corruption on OOM, debug-log disk blowout, time-zone bugs, OAuth refresh mid-session, egress bandwidth blowouts, image bloat, recipe cache lookup scaling, create-race on the one-active invariant, credit-display unit inconsistency, stale BYOK validity cache, refund on failed model calls.

**MSV "do-not-inherit" list:** plain env-var BYOK injection, `poken_balances` cached-scalar balance, `UFW INACTIVE`, `:latest` image tags in prod, gateway crons for scheduled tasks, 40GB disk, no swap. **MSV "inherit" list:** per-user named container + bind-mount pattern (with userns fix), `/opt/<user>/data` layout, `.env` at `-rw-r----- root:<group>`, Postgres + Redis loopback-bound, pg-boss durable workflows, heartbeat + stale-alert pattern, `pkg/docker/runner.go` shell-out with arg validation, embedded-postgres for tests.

Full detail: `.planning/research/PITFALLS.md` §Phase-Specific Warning Map + §MSV Inheritances.

## Implications for Roadmap

The research converges on a **10-phase build order** (Phase 0 spikes through Phase 10 OSS release) that maps cleanly to the critical pitfalls — each phase is scoped so its pitfalls are addressable *within* it, not deferred. Phases 0–4 produce a demoable MVP (log in, paste Anthropic key, chat with OpenClaw in a container). Phases 5–7 produce the first marketable release. Phase 9 is the headline differentiator but is correctly placed late because it is the highest-risk component.

### Phase 0: Foundations & Spikes (1 week)
**Rationale:** Four unknowns block every downstream decision; resolve them before scaffold lands.
**Delivers:** Hetzner provisioned; Docker 27.x + `userns-remap` configured; Postgres 17 + Redis 7 loopback-bound; `ap-base` Dockerfile draft (node22 + tini + tmux + ttyd); hand-launched OpenClaw in a container with tmux + named pipes proven; HTTPS_PROXY vs `*_BASE_URL` behavior documented per target agent; gVisor `runsc` installability on Hetzner kernel verified; Apache-2.0 license chosen; `ghcr.io` registry decided; Phase-0 spike report committed.
**Addresses:** Foundational unknowns from ARCHITECTURE §13.
**Avoids:** Building the wrong proxy wiring in Phase 7.
**Research flag:** **HIGH — spike is the phase.**

### Phase 1: Auth + Skeleton (1 week)
**Rationale:** Cheap to land, unblocks every subsequent phase, direct MSV transfer.
**Delivers:** Go API (Echo v4) skeleton; `users` + `oauth_identities` + `sessions` tables via `golang-migrate`; goth-based Google + GitHub OAuth with server-side session in Postgres; Next.js 16 shell with login + empty dashboard; `pkg/docker/runner.go` ported from MSV; zerolog; embedded-postgres test harness; repo conventions for recipe layout, secret handling, env-var policy.
**Uses:** Go 1.25 + Echo v4.15 + pgx v5.8 + goth + Next.js 16.2.
**Avoids:** MIN-3 via proactive refresh at 80% TTL.
**Research flag:** None — standard patterns.

### Phase 2: Container Sandbox Foundations (1.5 weeks)
**Rationale:** The security spine. Sandbox decisions made here are inherited by every recipe in the catalog and cannot be retrofitted.
**Delivers:** `ap-base` image finalized (tini PID 1 supervising tmux + ttyd); Docker daemon hardened (`userns-remap: default`, `log-opts`, `live-restore`); default `runc` for curated recipes + `runsc` (gVisor) runtime installed and validated for bootstrap path; drop-all-caps + `no-new-privileges` + custom seccomp profile (dropping mount/unshare/setns/keyctl/bpf/ptrace); read-only rootfs + `tmpfs /tmp`; resource caps (`--cpus`, `--memory`, `--pids-limit`); custom bridge network `ap-net` with egress allowlist; UFW **active**; per-agent slim base images (MIN-5); Falco/Tetragon syscall anomaly alerting.
**Addresses:** CRIT-1, CRIT-4, MIN-1, MIN-5, MOD-4 argv discipline.
**Research flag:** **MEDIUM** — gVisor/Sysbox kernel-feature validation on the actual Hetzner host.

### Phase 3: Secrets + BYOK Input + Provider Wiring (1.5 weeks)
**Rationale:** BYOK input UI cannot ship until the key-handling path is safe end-to-end. MSV's plain env-var injection is the explicit anti-pattern.
**Delivers:** `byok_keys` table with pgcrypto symmetric encryption (key from systemd credential or SOPS); BYOK settings page (one row per provider, "test key" button, masked display); "test key" validator hitting provider models-list endpoints; host-side outbound HTTP proxy skeleton (Go pass-through for BYOK, to become LiteLLM in Phase 7); per-session tmpfs `/run/secrets/<provider>_key` entrypoint shim for agents needing raw env; stdout/stderr regex scrubber in supervisor; pre-commit gitleaks in `ap-base` workspace; `ulimit -c 0`; audit-log scan job for known key prefixes; OAuth refresh at 80% TTL (MIN-3); BYOK validity cache ≤5min (MIN-9).
**Addresses:** CRIT-2 **before** BYOK is user-facing. MIN-3, MIN-9.
**Research flag:** **MEDIUM** — per-agent BASE_URL behavior may force per-recipe shims; driven by Phase 0 spike.

### Phase 4: Single-Agent BYOK MVP — Session Lifecycle + Chat (2 weeks)
**Rationale:** The demoable milestone. Proves orchestrator, recipe runner, tmux+pipes chat wiring, and one-active invariant with a single trusted recipe.
**Delivers:** Recipe schema (`ap.recipe/v1`) + JSON-Schema validator at `agents/_schema/recipe.schema.json`; `agents/openclaw/recipe.yaml` + `agents/openclaw/Dockerfile` + smoke test; `internal/orchestrator/` implementing `Spawn/Get/Stop/Pause/AttachChat/ProxyTTY/ListByUser`; one-active invariant at two layers (Postgres partial unique index + Redis SETNX); explicit session state machine with reconciliation loop every 30s; Chat WS handler `/api/sessions/:id/stream` reading/writing named pipes via `docker exec` + Redis pubsub; idempotent container names (`playground-<user>-<session>`); idle reaper with multi-signal definition (chat + terminal + workspace mtime + WS frame); pg-boss-style durable workflow for session create/destroy (inherit from MSV); Next.js session page with chat textarea + state badges.
**Demoable:** *Log in → click "New session" → OpenClaw + Anthropic + paste BYOK → 10s later chat with OpenClaw in a fresh container → Stop → invariant released.*
**Addresses:** CRIT-6, MOD-6 (WS auth for chat), MOD-7 (idle false-kill), MIN-7 (create race).
**Research flag:** **LOW-MEDIUM** — tmux+named-pipe latency depends on Phase-0 spike.

### Phase 5: Web Terminal Surface (3–5 days)
**Rationale:** Second tmux window already exists from Phase 2. Separate phase because single-WS-per-session discipline (MOD-6) is worth landing deliberately.
**Delivers:** ttyd bound to `127.0.0.1:<allocated_port>` inside container, port in sessions row; Go API WSS reverse-proxy at `/api/sessions/:id/tty` terminating user-facing WS, validating session cookie, proxying bidirectionally via `coder/websocket`; xterm.js Next.js terminal page with `@xterm/addon-fit` + `@xterm/addon-attach`; single-WS-per-session enforcement (new connection kicks old); `Origin` allowlist on WS upgrade; WSS-only; terminal-as-iframe (v1 recommendation).
**Addresses:** MOD-6.
**Research flag:** **LOW**.

### Phase 6: Recipe Catalog Expansion + Local Test Rig (1 week)
**Rationale:** Prove the recipe pipeline with 3 more agents before wiring metering.
**Delivers:** `agents/hermes/`, `agents/hiclaw/`, `agents/picoclaw/` recipes with pinned versions (no `:latest`); frozen `agents/_schema/recipe.schema.json`; `make test-recipe AGENT=<name>` local rig running container + hello-world prompt + response verification; nightly CI re-running every recipe, auto-opens issues on failure; upstream-watch cron polling agent GitHub releases for PR bumps; recipe age in UI; agent picker filtering model picker by `recipe.models.supported_providers`; recipe content addressing.
**Addresses:** MOD-3, MOD-4, MIN-6.
**Research flag:** **LOW** — devcontainer features is a direct template.

### Phase 7: Metering + Stripe + Credits (2 weeks)
**Rationale:** Unlocks platform-billed tier. Every pitfall here is money-losing. Atomic ledger + idempotent webhooks + circuit breakers MUST land together.
**Delivers:** LiteLLM Proxy as host systemd unit on `127.0.0.1:8088` backed by main Postgres (separate schema); per-session virtual key minting on `Spawn` with `max_budget = remaining_credits`; `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` / `OPENROUTER_BASE_URL` injection via recipe `models.base_url_env` map; `stripe_events` table with `UNIQUE (stripe_event_id)`; webhook handler INSERTs idempotency row *first* inside the same transaction as credit-ledger update; Stripe signature verification + 5-min replay window; ledger-only balance (`SUM(transactions)`, no cached scalar); **pre-authorized token budgets**; **hard circuit breakers independent of billing** (≤60 calls/min/session, token cap, wall-clock cap); loop-detection heuristic; OpenRouter per-session sub-keys where supported; session-immutable billing mode (BYOK vs platform locked at spawn, **no silent fallback**); different proxy endpoints per mode; nightly reconciliation against Stripe events + provider invoices; Stripe Checkout + Elements for top-ups; live credit drain in header with ±5% disclaimer; cents-in-DB / "$X.YY" in UI (MIN-8); UTC storage + user-TZ render (MIN-2); refund policy for calls without `usage` (MIN-10).
**Addresses:** CRIT-3, CRIT-5, MOD-1, MOD-2, MIN-2, MIN-8, MIN-10.
**Research flag:** **HIGH** — LiteLLM operational fit at >1K users is MEDIUM confidence; Stripe Billing Credit Balance API vs local ledger boundary needs a spike.

### Phase 8: Persistent Tier + Volume Backups (1 week)
**Rationale:** Paid tier monetization; infra-only phase.
**Delivers:** Per-user named volume `ap-vol-{user_id}` mounted at `/work` for paid tier; free tier `--rm` + tmpfs unchanged; XFS project quotas or `du`-supervisor per-volume quota; MinIO or Hetzner Storage Box via restic nightly snapshots `ap-volumes/{user_id}/{date}.tar.zst`; ZFS/btrfs hourly snapshots for paid tier on host; restore drill documented + tested quarterly; tiered storage (workspace SSD, build caches separate/pruned); disk-pressure monitoring with alerts at 70/80/90% + "refuse new sessions" at 90%; per-session egress cap (`tc` or app-layer) + bootstrap allowlist excluding large-file CDNs (MIN-4); mount `data=ordered`; OOM-kill detection with auto-restore-latest-snapshot for paid tier; reconnect-after-disconnect flow; tier badge in session header; **host disk spec'd to ≥500GB NVMe before this phase ships**.
**Addresses:** MOD-5, MOD-8, MIN-4.
**Research flag:** **MEDIUM** — MinIO vs Hetzner Storage Box + restic vs tar-zst tradeoffs.

### Phase 9: Generic Claude-Code Bootstrap (2 weeks — HIGH RISK)
**Rationale:** Headline differentiator and highest-risk component. Placed LAST so it never blocks shipping. Requires every sandbox decision from Phase 2.
**Delivers:** `ap-base:bootstrap` image (Debian slim + git + node + python + tini + ttyd + Claude Code preinstalled); templated prompt at `/prompt.md` pointing at target git repo with instructions to emit `/work/.ap/recipe.yaml` conforming to `ap.recipe/v1`; Claude Code runs with only its own scoped key (never a central fallback — reduces CRIT-3 blast radius); recipe extraction + JSON-Schema validation + content-addressed caching keyed on `(repo_url, commit_sha, bootstrap_output_hash)`; recipe review gate (cached recipes flagged "unverified" until human/CI approval); "bootstrap failed, here's the log" UX (~30% failure rate expected); tightened network egress allowlist; **runs under `runsc` (gVisor) by default**; repo URL validator regex (`^https://(github|gitlab|codeberg|bitbucket)\.com/[\w.-]+/[\w.-]+$`); `exec.Command`-only (zero shell interpolation); optional "PR this recipe to `agents/community/`" flow.
**Addresses:** CRIT-1 (all mitigations applied), MOD-4.
**Research flag:** **HIGH** — Claude Code reliability on unknown repos is LOW-MEDIUM; plan for the failure UX from day one.

### Phase 10: OSS Release Hardening (1 week)
**Rationale:** Open-source is a core positioning requirement, not a post-hoc chore.
**Delivers:** Audit log schema + retention; per-user + per-IP rate limits in Echo middleware; abuse-handling runbook; public README with quickstart; Apache-2.0 license headers; CONTRIBUTING.md for recipe submissions with CI smoke-test gate; public GitHub Actions CI; SECURITY.md; self-hosted deployment docs (document the path, defer full support); kernel patching policy (`unattended-upgrades`); Falco/Tetragon rules published; reconciliation + restore drill documentation.
**Addresses:** CRIT-4 ongoing patching, long-term ops hygiene.
**Research flag:** **LOW**.

### Phase Ordering Rationale

- **Sandbox before features.** Phase 2 lands the security spine before any user-visible surface that could be abused. Switching runtimes post-launch invalidates every recipe's validation.
- **Secrets before BYOK UI.** Phase 3's outbound-proxy + secret shim land *before* Phase 4 exposes BYOK input.
- **Demo before metering.** Phase 4's BYOK MVP proves the orchestrator + recipe pipeline + chat surface without billing complexity.
- **Terminal after chat.** Chat is the demoable surface. Terminal (Phase 5) is 3–5 days once tmux + ttyd from Phase 2 are in place.
- **Catalog before metering.** Phase 6 proves the recipe pipeline with 3 more agents before wiring money through it.
- **Metering before persistence.** Credits are the monetization; persistent volumes (Phase 8) are the feature credits unlock.
- **Bootstrap last.** Phase 9 is highest differentiator AND highest risk. If it slips, Phases 0–8 still constitute a marketable product.
- **Critical pitfalls map 1:1 to phases.** CRIT-1→P2+P9, CRIT-2→P3, CRIT-3→P7, CRIT-4→P2, CRIT-5→P7, CRIT-6→P4. No pitfall is homeless.

### Research Flags

Phases likely needing deeper research during planning (`/gsd-research-phase` candidates):
- **Phase 0 (Spikes):** The entire phase is research — per-agent BASE_URL, `chat_io.mode` per agent, tmux+pipe latency, gVisor feasibility, LiteLLM shape.
- **Phase 2 (Sandbox):** gVisor/Sysbox kernel validation on actual Hetzner hardware; seccomp profile tuning per agent class; Falco vs Tetragon.
- **Phase 7 (Metering):** Stripe Billing Credit Balance API vs local ledger; LiteLLM virtual-key + budget primitives deep dive; provider-specific `usage` quirks (reasoning tokens, 200K-tier, OpenRouter markup).
- **Phase 9 (Bootstrap):** Claude Code reliability patterns on unknown repos; prompt template iteration; failure UX.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Auth + Skeleton):** Direct MSV transfer.
- **Phase 4 (Lifecycle):** MSV already ships this; port + fix known pitfalls.
- **Phase 5 (Terminal):** ttyd + xterm.js is standard.
- **Phase 6 (Catalog):** devcontainer features is a direct template.
- **Phase 8 (Persistence):** Standard restic/tar + named volume patterns.
- **Phase 10 (OSS):** Standard release hygiene.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | Go/Echo v4/pgx v5/Next.js 16/Stripe v82/moby-client verified against official docs current to March-April 2026. MSV runs most of this in production. MEDIUM on ttyd integration mode, Sysbox kernel fit, and LiteLLM operational fit at >1K users. |
| Features | **MEDIUM-HIGH** | Reference products (e2b, Daytona, Replit, Cursor, Warp, Workspace, aider) well-documented and current. MEDIUM on hybrid chat+terminal tmux pattern (no hosted competitor does exactly this). MEDIUM on generic Claude-Code-bootstrap differentiator (no prior art). LOW on precise token/cost-meter accuracy (provider `usage` quirks). |
| Architecture | **MEDIUM-HIGH** | Single-binary Go + in-process orchestrator + `pkg/docker/runner.go` shell-out is MSV-verified. Tmux + pipes + ttyd is HIGH per piece, MEDIUM combined — needs Phase-0 spike. LiteLLM as metering is HIGH-capability, MEDIUM-operational. `HTTPS_PROXY` vs `BASE_URL` is MEDIUM agent-specific. Bootstrap mode is LOW-MEDIUM. |
| Pitfalls | **HIGH** | Six CRIT pitfalls are overwhelmingly MSV-inherited and documented in MSV's production pain-point table — not theoretical. Container escape confirmed by CVE-2025-9074 and 2025–2026 sandbox guides. Stripe webhook race has authoritative post-mortems. Token drift MEDIUM (heuristic). WS/PTY issues HIGH (xterm.js docs explicitly enumerate). |

**Overall confidence:** **MEDIUM-HIGH.** Product shape, stack, and failure modes are well-understood. The two genuinely uncertain areas (bootstrap reliability, LiteLLM at scale) are isolated to late phases where failure is recoverable.

### Gaps to Address

- **Phase-0 spike is load-bearing.** Determines recipe schema `chat_io.mode`, metering wiring (`HTTPS_PROXY` vs `BASE_URL`), tmux+pipe latency, gVisor feasibility. Do not skip.
- **Per-agent BASE_URL honoring** — some CLI agents may not respect `ANTHROPIC_BASE_URL`; per-recipe entrypoint shims may be needed. Scope unknown until each target agent is verified.
- **Claude-Code bootstrap failure rate** — expected ~30% on real-world unknown repos; no prior art. Dedicated prompt-iteration sprint inside Phase 9 + honest failure UX.
- **Stripe Billing Credit Balance API vs custom ledger** — almost certainly need a local ledger on top; boundary needs a Phase-7 spike.
- **LiteLLM operational fit at >1K users** — single host correct for v1; HA path is 2 instances behind nginx with shared Postgres but not validated.
- **Host hardware spec** — MSV's 40GB disk is insufficient; spec ≥500GB NVMe *before* Phase 8 ships. Backup footprint scales accordingly.
- **Provider-specific `usage` reporting quirks** — reasoning tokens, 200K-tier pricing, OpenRouter markup, optional `usage.include: true`. Document rate-table SKU format in Phase 7.
- **Per-tier isolation escalation** — Sysbox as v1.5 hardening and Kata for Pro tier are MEDIUM confidence until kernel-validated.
- **Recipe review gate workflow** — bootstrap-cached recipes need human-or-CI approval; exact gate (GitHub PR? in-app admin review?) deferred to Phase 9 design.
- **OAuth refresh strategy** — MIN-3 noted but exact refresh timing + UX needs Phase-3 design call.

---
*Research completed: 2026-04-11*
*Ready for roadmap: yes*
