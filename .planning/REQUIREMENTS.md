# Requirements: Agent Playground

**Defined:** 2026-04-11
**Core Value:** Any agent × any model × any user, in one click — agent-agnostic install pipeline is the differentiator that must work.

## v1 Requirements

Requirements for the initial release. Each maps to exactly one roadmap phase.

### Platform Foundation (infrastructure substrate — addresses Phase-0 unknowns)

- [ ] **FND-01**: Hetzner dedicated host provisioned with Docker Engine 27.x + `userns-remap` enabled
- [ ] **FND-02**: PostgreSQL 17 + Redis 7 running as loopback-bound systemd services
- [ ] **FND-03**: Go 1.25 + Echo v4.15 + pgx v5.x (v5.8+) binary builds, starts, and serves `/healthz`
- [ ] **FND-04**: Next.js 16.2 + React 19.2 + Tailwind v4 + shadcn/ui frontend serves a mobile-first login-gated landing page (designed for phone viewport first, desktop enhances)
- [ ] **FND-05**: Embedded-FS custom migrator (MSV pattern, pgx-native) runs schema migrations on API start
- [ ] **FND-06**: `pkg/docker/runner.go` (ported from MSV, strict arg validation) can `run`, `exec`, `inspect`, `stop`, `rm` containers from Go
- [ ] **FND-07**: Phase-0 spike report documents per-target-agent `HTTPS_PROXY` vs `*_BASE_URL` honoring, `chat_io.mode` per agent, tmux+named-pipe round-trip latency, and gVisor runsc feasibility on the chosen Hetzner kernel
- [ ] **FND-08**: Temporal server runs on the host (single-node dev/prod profile, bound to loopback); Go API includes a Temporal worker that registers workflows and activities for session spawn, session destroy, recipe install, and reconciliation
- [ ] **FND-09**: Temporal namespace, task queues (`session`, `billing`, `reconciliation`), and worker identity are configured and observable via `tctl` / Temporal Web UI
- [ ] **FND-10**: Baseline migration includes an `agents` table (user_id FK, agent_type, model_provider, model_id, key_source, status, webhook_url, container_id, ssh_port, config jsonb) — multi-agent data model from day 1, ready for N-active in v2

### Authentication (AUTH)

- [ ] **AUTH-01**: User can sign in with Google via OAuth 2.0 (goth-backed)
- [ ] **AUTH-02**: User can sign in with GitHub via OAuth 2.0 (goth-backed)
- [ ] **AUTH-03**: User session persists across browser refresh via an HTTP-only signed cookie tied to a server-side Postgres session row
- [ ] **AUTH-04**: User can sign out from any page, invalidating the server-side session row
- [ ] **AUTH-05**: OAuth tokens refresh automatically at ≥80% of their TTL without interrupting an active session (MIN-3)
- [ ] **AUTH-06**: Unauthenticated requests to protected routes redirect to the provider picker

### Container Sandbox (SBX)

- [ ] **SBX-01**: `ap-base` Docker image runs `tini` as PID 1 supervising `tmux` and `ttyd`
- [ ] **SBX-02**: Every user container runs with `--cap-drop ALL`, `--security-opt no-new-privileges`, a custom seccomp profile dropping mount/unshare/setns/keyctl/bpf/ptrace, and a read-only rootfs with `tmpfs /tmp`
- [ ] **SBX-03**: Every user container is resource-capped (`--cpus`, `--memory`, `--pids-limit`) with tier-specific values read from the recipe
- [ ] **SBX-04**: User containers are attached to a custom `ap-net` bridge with an egress allowlist (model providers + package registries + user's git remote) and nothing else
- [ ] **SBX-05**: The host Docker socket is never mounted into a user container; `--privileged` is never used
- [ ] **SBX-06**: gVisor `runsc` runtime is installed, validated, and selectable per-recipe via a `runtime: runsc` field (mandatory for the Phase-9 bootstrap path)
- [ ] **SBX-07**: UFW is active on the host with only the public HTTPS port exposed; Postgres/Redis/LiteLLM bind to 127.0.0.1
- [ ] **SBX-08**: A host-side syscall anomaly detector (Falco or Tetragon) logs and alerts on suspicious events from user containers
- [ ] **SBX-09**: Containers are named deterministically as `playground-<user_uuid>-<session_uuid>` so reconciliation is idempotent

### Secrets + BYOK Key Handling (SEC)

- [ ] **SEC-01**: BYOK keys are stored in Postgres with pgcrypto symmetric encryption; the master key is loaded from a systemd credential, never from a plaintext file on disk
- [ ] **SEC-02**: BYOK keys are never injected as plain environment variables into user containers; env holds only `PLAYGROUND_PROXY_URL` + `PLAYGROUND_SESSION_TOKEN`
- [ ] **SEC-03**: For agents that require a raw provider env var, the orchestrator writes the key to a tmpfs-backed `/run/secrets/<provider>_key` file and an entrypoint shim exports it only into the agent process, never PID 1
- [ ] **SEC-04**: Stdout/stderr from user containers passes through a regex scrubber that masks any string matching known provider key prefixes before logging
- [ ] **SEC-05**: `ulimit -c 0` is set inside every user container so crash dumps cannot capture secrets
- [ ] **SEC-06**: The `ap-base` image ships with `gitleaks` installed and a pre-commit hook inside `/work` that blocks committing files matching key patterns
- [ ] **SEC-07**: Recipe CI lint forbids `ENV`/`ARG` declarations whose name matches known secret patterns
- [ ] **SEC-08**: An audit-log scanner job scans API logs nightly for known key prefixes and alerts on matches
- [ ] **SEC-09**: User can add, replace, test, and delete a BYOK key per provider (Anthropic, OpenAI, OpenRouter) via a settings page; keys are displayed masked (last-4 only) and never returned in API responses
- [ ] **SEC-10**: The BYOK "test key" button hits the provider's `/models` endpoint and returns valid / invalid without storing the response
- [ ] **SEC-11**: BYOK key validity status is cached for at most 5 minutes (MIN-9)

### Recipe System (REC)

- [ ] **REC-01**: The recipe schema `ap.recipe/v1` is defined as a JSON-Schema document committed to `agents/_schema/recipe.schema.json`
- [ ] **REC-02**: A Go recipe loader reads `agents/<name>/recipe.yaml`, validates against the schema, and returns a typed `Recipe` struct; invalid recipes fail loudly at API startup
- [ ] **REC-03**: `agents/openclaw/recipe.yaml` + `agents/openclaw/Dockerfile` exist, pass schema validation, and build a working image
- [ ] **REC-04**: `agents/hermes/recipe.yaml` + Dockerfile exist and pass validation
- [ ] **REC-05**: `agents/hiclaw/recipe.yaml` + Dockerfile exist and pass validation
- [ ] **REC-06**: `agents/picoclaw/recipe.yaml` + Dockerfile exist and pass validation
- [ ] **REC-07**: Every recipe pins upstream source to an immutable ref (commit SHA or tag), never `main` or `:latest`
- [ ] **REC-08**: `make test-recipe AGENT=<name>` spawns the recipe's container, runs a hello-world prompt against it, and asserts a non-error response
- [ ] **REC-09**: A nightly CI job re-runs `test-recipe` against every recipe and auto-opens a GitHub issue on failure (recipe drift detection)
- [ ] **REC-10**: An upstream-watch cron polls each recipe's source GitHub release feed and opens a PR when a new release is found
- [ ] **REC-11**: Recipe cache entries (bootstrap-discovered) are content-addressed by `(repo_url, commit_sha, bootstrap_output_hash)`; cached recipes cannot silently inherit a different commit's permissions
- [ ] **REC-12**: Recipes declare `models.supported_providers` and `models.base_url_env`; the API picker scopes model options to the intersection of the selected agent's supported providers and the user's available keys

### Session Lifecycle (SES)

- [ ] **SES-01**: User can create a new session by selecting `(agent, model_provider, model_id, key_source, tier)`; session goes from `pending → provisioning → ready → running` with observable state transitions
- [ ] **SES-02**: v1 enforces max 1 active (running) agent per user at two layers: a Postgres partial-unique index on `(user_id) WHERE status IN ('provisioning','ready','running')` and a Redis `SETNX agent:activate:{user_id}` lock with 60s TTL. Schema and API support N-active — flipping the limit is a config change (v2), not a migration.
- [ ] **SES-03**: Container creation installs the recipe and launches the agent inside a tmux window named `chat` attached to named pipes `/work/.ap/chat.in` and `/work/.ap/chat.out`; TTY ready in ≤10s from click
- [ ] **SES-04**: User can stop a session; orchestrator tears down the container, releases the invariant, and destroys the ephemeral volume if free tier
- [ ] **SES-05**: A reconciliation loop runs every 30s, lists all `playground-*` containers + all DB sessions, and fixes divergence (kills orphaned containers, marks zombie DB rows `failed`)
- [ ] **SES-06**: An idle reaper goroutine kills sessions whose `last_activity_at` exceeds the tier's idle TTL (free = 15min, paid = 4h); activity is defined as any chat message, any terminal keystroke, or any `/work` mtime change — not just WS frames
- [ ] **SES-07**: Session create/destroy is implemented as a **Temporal workflow** (not pg-boss) so an API crash mid-spawn does not leave dangling state; activities wrap `pkg/docker/runner.go` calls with retry + timeout policies
- [ ] **SES-08**: Container heartbeat pings the host every 30s; missing 3 heartbeats marks the session `stale` and triggers reconciliation
- [ ] **SES-09**: Two concurrent `POST /api/sessions` from the same user race cleanly — exactly one succeeds, the other returns 409 Conflict (MIN-7)

### Chat Surface (CHT)

- [ ] **CHT-01**: A single WSS endpoint `/api/sessions/:id/stream` streams chat bidirectionally between browser and the agent via `docker exec` reads/writes on the named pipes
- [ ] **CHT-02**: The chat WS authenticates via the session cookie on upgrade; origin is allowlisted; unauthenticated or cross-origin upgrades are rejected (MOD-6)
- [ ] **CHT-03**: Redis pubsub (`session:{id}:chat:out`) decouples WS connection lifetime from container lifetime — browser reconnect replays the last N messages without losing state
- [ ] **CHT-04**: Next.js session page renders a chat textarea, message history, and session state badge (`provisioning`/`ready`/`running`/`stopped`/`failed`) bound to the WS stream
- [ ] **CHT-05**: Only one chat WS per session is permitted; a new WS upgrade kicks the previous one

### Web Terminal Surface (TRM)

- [ ] **TRM-01**: `ttyd` inside the container binds to `127.0.0.1:<allocated_port>` attached to a second tmux window named `shell` with a plain bash session in the SAME `/work` filesystem
- [ ] **TRM-02**: The Go API reverse-proxies `wss /api/sessions/:id/tty` to the container's ttyd port via `coder/websocket` and terminates user-facing WS auth (session cookie validation + origin allowlist)
- [ ] **TRM-03**: The Next.js terminal page renders `@xterm/xterm` 5.5 with `@xterm/addon-fit` and `@xterm/addon-attach` and auto-fits on window resize
- [ ] **TRM-04**: Only one terminal WS per session is permitted; a new connection kicks the previous one
- [ ] **TRM-05**: Both chat and terminal views can be open simultaneously on the same container without PTY contention (chat uses named pipes, terminal uses the tmux shell window)
- [ ] **TRM-06**: Terminal upgrade is WSS-only; plain `ws://` is refused

### Model Metering + Credits (MET)

- [ ] **MET-01**: LiteLLM Proxy runs as a systemd unit bound to `127.0.0.1:8088`, logging to the main Postgres (separate schema)
- [ ] **MET-02**: On session spawn for a platform-billed user, the orchestrator calls LiteLLM admin API to mint a per-session virtual key with `max_budget = remaining_credits` and metadata `{user_id, session_id}`
- [ ] **MET-03**: The orchestrator injects `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` / `OPENROUTER_BASE_URL` into the container pointing at `host.docker.internal:8088` and the virtual key as the provider API key env var
- [ ] **MET-04**: BYOK sessions bypass LiteLLM entirely — no virtual key, no base URL override, no billing row written
- [ ] **MET-05**: Billing mode (BYOK vs platform) is locked at session spawn; there is no silent fallback mid-session (MOD-2)
- [ ] **MET-06**: Credit balance is computed as `SUM(amount) FROM credit_ledger WHERE user_id = $1` — never a cached scalar (MSV's `poken_balances` anti-pattern)
- [ ] **MET-07**: A pre-authorized token budget is deducted *before* each model call (estimate × rate) and refunded on completion for unused tokens
- [ ] **MET-08**: Hard circuit breakers independent of billing apply to every session regardless of key source: ≤60 model calls/min, token ceiling, wall-clock ceiling
- [ ] **MET-09**: A loop-detection heuristic kills sessions that make N calls in M seconds with no `/work` mtime change and emails the user (CRIT-3)
- [ ] **MET-10**: Live credit drain is displayed in the header during platform-billed sessions with a ±5% disclaimer; header hides the drain entirely during BYOK sessions
- [ ] **MET-11**: Low-balance warning fires at 20% remaining; at 0, LiteLLM returns 429 and the orchestrator pauses the session and prompts the user to top up
- [ ] **MET-12**: A nightly reconciliation job diffs the local ledger against Stripe events and provider invoices and alerts on drift
- [ ] **MET-13**: Credits are stored in cents (integer) in Postgres and rendered as `$X.YY` in the UI (MIN-8)
- [ ] **MET-14**: A refund policy handles provider responses that omit `usage` (MIN-10)
- [ ] **MET-15**: All timestamps are stored UTC and rendered in the user's timezone (MIN-2)

### Billing (BIL)

- [ ] **BIL-01**: User can top up their credit balance via Stripe Checkout (one-time payment); completed checkouts credit the user's ledger atomically
- [ ] **BIL-02**: `webhook_events` table has `UNIQUE (stripe_event_id)`; the webhook handler INSERTs idempotency rows as the first action inside the same transaction as the credit-ledger update (CRIT-5)
- [ ] **BIL-03**: Stripe webhook signatures are verified on every webhook; events older than 5 minutes are rejected as replay attempts
- [ ] **BIL-04**: Webhooks for the same user are queued and processed serially to prevent double-credit races
- [ ] **BIL-05**: User can view a paginated transaction history (credit ledger) for dispute resolution
- [ ] **BIL-06**: User can see their current balance, lifetime spend, and most recent transaction on the dashboard

### Persistent Tier (PER)

- [ ] **PER-01**: Free tier uses `--rm` containers with a tmpfs `/work`; state is destroyed on stop
- [ ] **PER-02**: Paid tier uses a per-user named Docker volume `ap-vol-{user_id}` mounted at `/work` that survives container recreation
- [ ] **PER-03**: Paid-tier volumes are quota-enforced (XFS project quotas or a `du`-supervisor sidecar) per the tier limit
- [ ] **PER-04**: Paid-tier volumes are snapshotted nightly to an S3-compatible target (MinIO on-host or Hetzner Storage Box) via `restic` with retention policy
- [ ] **PER-05**: A paid-tier user can disconnect, reconnect within the idle TTL, and resume the same container with the same `/work` state
- [ ] **PER-06**: Host disk pressure monitoring alerts at 70 / 80 / 90% utilization and blocks new session creation at 90%
- [ ] **PER-07**: Per-session egress bandwidth is capped (`tc` or app-layer) and the bootstrap allowlist excludes large-file CDNs (MIN-4)
- [ ] **PER-08**: OOM-kill events on paid-tier containers auto-restore the latest snapshot after the next session spawn
- [ ] **PER-09**: A quarterly restore drill is documented and verified

### Generic Claude-Code Bootstrap (BST) — headline differentiator, highest-risk, Phase 9

- [ ] **BST-01**: `ap-base:bootstrap` image ships with `git`, `node`, `python`, `tini`, `ttyd`, and Claude Code preinstalled
- [ ] **BST-02**: User can start a session by pasting a git repo URL (regex: `^https://(github|gitlab|codeberg|bitbucket)\.com/[\w.-]+/[\w.-]+$`) instead of picking a curated agent
- [ ] **BST-03**: Bootstrap sessions run under `runsc` (gVisor) by default, never vanilla `runc`
- [ ] **BST-04**: The bootstrap prompt at `/prompt.md` instructs Claude Code to emit a valid `/work/.ap/recipe.yaml` conforming to `ap.recipe/v1` or exit with a documented failure mode
- [ ] **BST-05**: Extracted recipes are validated against the JSON-Schema before being trusted; invalid recipes surface a "bootstrap failed — here's the log" UX
- [ ] **BST-06**: Bootstrap-discovered recipes are cached content-addressed and flagged `unverified` until human or CI review (no silent catalog promotion)
- [ ] **BST-07**: Claude Code inside the bootstrap container runs with its own scoped key only — never a central fallback key (limits CRIT-3 blast radius)
- [ ] **BST-08**: All shell invocations in the bootstrap path use `exec.Command` with zero shell interpolation (defends against YAML/shell injection via the repo URL)
- [ ] **BST-09**: An optional "PR this recipe to `agents/community/`" flow lets a successful bootstrap submit back to the catalog with a PR template

### Open-Source Release (OSS)

- [ ] **OSS-01**: The repository ships under the Apache-2.0 license with headers applied to every source file
- [ ] **OSS-02**: `README.md` documents the quickstart, architecture overview, and "try any git repo" demo
- [ ] **OSS-03**: `CONTRIBUTING.md` documents the recipe submission workflow with the CI smoke-test gate as the merge requirement
- [ ] **OSS-04**: `SECURITY.md` documents the responsible disclosure process and the sandbox guarantees for curated vs bootstrap paths
- [ ] **OSS-05**: GitHub Actions CI runs on every PR: `go test`, `go vet`, frontend type-check, every recipe smoke test
- [ ] **OSS-06**: A self-hosted deployment guide documents the Hetzner + Docker + systemd path (`ansible`/`terraform` optional, shell scripts acceptable)
- [ ] **OSS-07**: Per-user and per-IP rate limits are enforced in Echo middleware
- [ ] **OSS-08**: An append-only audit log records every session spawn, stop, billing event, BYOK key change, and admin action with a retention policy
- [ ] **OSS-09**: `unattended-upgrades` is configured on the host for kernel and Docker patches (CRIT-4 ongoing mitigation)
- [ ] **OSS-10**: Published Falco/Tetragon rules and a reconciliation/restore runbook ship in `docs/ops/`

## v2 Requirements

Deferred to future release. Tracked but not in the current roadmap.

### Parallel Sessions

- **PAR-01**: Tier-gated parallel sessions (free = 1, paid = N) with tab-based UI
- **PAR-02**: Per-session resource accounting across parallel sessions

### Subscriptions

- **SUB-01**: Monthly subscription tiers with included usage quotas
- **SUB-02**: Overage billing via credits
- **SUB-03**: Annual billing discount

### Advanced Model Providers

- **MPR-01**: Local / Ollama provider for a free-tier compute path
- **MPR-02**: AWS Bedrock, Google Vertex AI providers via LiteLLM
- **MPR-03**: Per-model cost preview before expensive operations

### Recipe Catalog UX

- **CAT-01**: Recipe catalog browser UI with search, filter, and ratings
- **CAT-02**: In-app recipe contribution flow (vs GitHub PR)
- **CAT-03**: Recipe version pinning per-user

### Collaboration

- **COL-01**: Real-time collaborative sessions (multiple users on one container)
- **COL-02**: Session sharing via signed URL (read-only spectate)
- **COL-03**: Session export / replay

### Mobile

- **MOB-01**: Responsive mobile layout for chat + terminal
- **MOB-02**: Progressive web app installable on iOS/Android

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Telegram bot / Telegram-as-UI | MSV's biggest constraint; the explicit product pivot is to remove this. Browser-only. |
| Locked to single agent | Defeats the core differentiator. Agent picker is top-level from day 1. |
| Locked to single provider | Same. Model picker with BYOK + platform-billed on day 1. |
| BYOK punishment (à la Cursor) | BYOK is first-class. No feature gating, no asterisks. |
| In-product file editor / IDE | This is an agent runner, not Replit. Files happen via the agent's commands. |
| Email/password authentication | Google + GitHub OAuth only. Reduces auth surface and credential risk. |
| Cloud-managed hosting (AWS/GCP/Fly) | Hetzner dedicated is the cost model. Cloud-managed containers break the predictable-per-container economics. |
| Closed-source core | Open source is a core positioning requirement. Monetization is the hosted service, not the code. |
| Curated-only catalog | Defeats "agent-agnostic." Generic Claude-Code bootstrap is mandatory for the long tail. |
| Shared global terminal | Every session is isolated per user. No shared state across users. |
| Parallel sessions in v1 | Tier-gated v2 upgrade lever. Keeps v1 invariant simple. |
| Monthly subscription billing in v1 | Credit balance only. Subscriptions can come later if users ask. |
| Kubernetes / K3s / Nomad | One Hetzner box, Docker on host. K8s is overkill and defeats the cost model. |
| Storing OAuth tokens in cookies | Server-side Postgres session row; cookie holds only an opaque signed session ID. |
| Mounting the host Docker socket | Security non-starter. Never. |
| Running agent as PID 1 | `tini` is always PID 1; agent is a supervised child. |
| Real-time collaboration | v2 feature — deferred to prove the single-user experience first. |
| IPFS checkpoint pattern from MSV | Defer to v2 per MSV's own docs; v1 uses heartbeat + DB state only. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01 | Phase 1 | Pending |
| FND-02 | Phase 1 | Pending |
| FND-03 | Phase 1 | Pending |
| FND-04 | Phase 1 | Pending |
| FND-05 | Phase 1 | Pending |
| FND-06 | Phase 1 | Pending |
| FND-07 | Phase 1 | Pending |
| FND-08 | Phase 1 | Pending |
| FND-09 | Phase 1 | Pending |
| FND-10 | Phase 1 | Pending |
| SBX-01 | Phase 2 | Pending |
| SBX-02 | Phase 2 | Pending |
| SBX-03 | Phase 2 | Pending |
| SBX-04 | Phase 2 | Pending |
| SBX-05 | Phase 2 | Pending |
| SBX-06 | Phase 2 | Pending |
| SBX-07 | Phase 2 | Pending |
| SBX-08 | Phase 2 | Pending |
| SBX-09 | Phase 2 | Pending |
| AUTH-01 | Phase 3 | Pending |
| AUTH-02 | Phase 3 | Pending |
| AUTH-03 | Phase 3 | Pending |
| AUTH-04 | Phase 3 | Pending |
| AUTH-05 | Phase 3 | Pending |
| AUTH-06 | Phase 3 | Pending |
| SEC-01 | Phase 3 | Pending |
| SEC-02 | Phase 3 | Pending |
| SEC-03 | Phase 3 | Pending |
| SEC-04 | Phase 3 | Pending |
| SEC-05 | Phase 3 | Pending |
| SEC-06 | Phase 3 | Pending |
| SEC-07 | Phase 3 | Pending |
| SEC-08 | Phase 3 | Pending |
| SEC-09 | Phase 3 | Pending |
| SEC-10 | Phase 3 | Pending |
| SEC-11 | Phase 3 | Pending |
| REC-01 | Phase 4 | Pending |
| REC-02 | Phase 4 | Pending |
| REC-03 | Phase 4 | Pending |
| REC-04 | Phase 4 | Pending |
| REC-05 | Phase 4 | Pending |
| REC-06 | Phase 4 | Pending |
| REC-07 | Phase 4 | Pending |
| REC-08 | Phase 4 | Pending |
| REC-09 | Phase 4 | Pending |
| REC-10 | Phase 4 | Pending |
| REC-11 | Phase 4 | Pending |
| REC-12 | Phase 4 | Pending |
| SES-01 | Phase 5 | Pending |
| SES-02 | Phase 5 | Pending |
| SES-03 | Phase 5 | Pending |
| SES-04 | Phase 5 | Pending |
| SES-05 | Phase 5 | Pending |
| SES-06 | Phase 5 | Pending |
| SES-07 | Phase 5 | Pending |
| SES-08 | Phase 5 | Pending |
| SES-09 | Phase 5 | Pending |
| CHT-01 | Phase 5 | Pending |
| CHT-02 | Phase 5 | Pending |
| CHT-03 | Phase 5 | Pending |
| CHT-04 | Phase 5 | Pending |
| CHT-05 | Phase 5 | Pending |
| TRM-01 | Phase 5 | Pending |
| TRM-02 | Phase 5 | Pending |
| TRM-03 | Phase 5 | Pending |
| TRM-04 | Phase 5 | Pending |
| TRM-05 | Phase 5 | Pending |
| TRM-06 | Phase 5 | Pending |
| MET-01 | Phase 6 | Pending |
| MET-02 | Phase 6 | Pending |
| MET-03 | Phase 6 | Pending |
| MET-04 | Phase 6 | Pending |
| MET-05 | Phase 6 | Pending |
| MET-06 | Phase 6 | Pending |
| MET-07 | Phase 6 | Pending |
| MET-08 | Phase 6 | Pending |
| MET-09 | Phase 6 | Pending |
| MET-10 | Phase 6 | Pending |
| MET-11 | Phase 6 | Pending |
| MET-12 | Phase 6 | Pending |
| MET-13 | Phase 6 | Pending |
| MET-14 | Phase 6 | Pending |
| MET-15 | Phase 6 | Pending |
| BIL-01 | Phase 6 | Pending |
| BIL-02 | Phase 6 | Pending |
| BIL-03 | Phase 6 | Pending |
| BIL-04 | Phase 6 | Pending |
| BIL-05 | Phase 6 | Pending |
| BIL-06 | Phase 6 | Pending |
| PER-01 | Phase 7 | Pending |
| PER-02 | Phase 7 | Pending |
| PER-03 | Phase 7 | Pending |
| PER-04 | Phase 7 | Pending |
| PER-05 | Phase 7 | Pending |
| PER-06 | Phase 7 | Pending |
| PER-07 | Phase 7 | Pending |
| PER-08 | Phase 7 | Pending |
| PER-09 | Phase 7 | Pending |
| OSS-01 | Phase 7 | Pending |
| OSS-02 | Phase 7 | Pending |
| OSS-03 | Phase 7 | Pending |
| OSS-04 | Phase 7 | Pending |
| OSS-05 | Phase 7 | Pending |
| OSS-06 | Phase 7 | Pending |
| OSS-07 | Phase 7 | Pending |
| OSS-08 | Phase 7 | Pending |
| OSS-09 | Phase 7 | Pending |
| OSS-10 | Phase 7 | Pending |
| BST-01 | Phase 8 | Pending |
| BST-02 | Phase 8 | Pending |
| BST-03 | Phase 8 | Pending |
| BST-04 | Phase 8 | Pending |
| BST-05 | Phase 8 | Pending |
| BST-06 | Phase 8 | Pending |
| BST-07 | Phase 8 | Pending |
| BST-08 | Phase 8 | Pending |
| BST-09 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 117
- Mapped to phases: 117
- Unmapped: 0

---
*Requirements defined: 2026-04-11*
*Last updated: 2026-04-13 — added FND-10 (multi-agent schema), updated FND-04 (mobile-first), updated SES-02 (N-agent model)*
