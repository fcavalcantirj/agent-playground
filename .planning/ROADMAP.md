# Roadmap: Agent Playground

**Created:** 2026-04-11
**Granularity:** standard (8 phases)
**Core value:** Any agent x any model x any user, in one click -- agent-agnostic install pipeline is the differentiator.

## Phases

- [ ] **Phase 1: Foundations, Spikes & Temporal** - Provision Hetzner host, stand up Postgres/Redis/Docker/Temporal, land the Go+Next.js skeleton, and burn down the four Phase-0 unknowns.
- [ ] **Phase 2: Agent-in-a-Box + Minimal Substrate (reshaped 2026-04-13)** - Ship `ap-base` (tini + tmux + ttyd + MSV-ported entrypoint), wire sandbox knobs into runner.go, deterministic naming, two thin curated recipes (picoclaw + Hermes), minimal non-durable session API stubs. Prove API-driven agent start from curl for both agents -- the hypothesis proof. Full hardening spine moves to new Phase 7.5.
- [ ] **Phase 3: Auth, Secrets & BYOK Key Handling** - Google + GitHub OAuth, encrypted BYOK vault, safe key injection pipeline, and the BYOK settings UI with test/mask/delete flows.
- [ ] **Phase 4: Recipe System & Curated Catalog** - Ship `ap.recipe/v1` schema, the Go recipe loader, four curated recipes (OpenClaw, Hermes, HiClaw, PicoClaw), and the local + CI smoke-test rig.
- [ ] **Phase 5: Demoable MVP -- Session Lifecycle, Chat & Terminal** - Wire the orchestrator (Temporal-backed), one-active invariant, chat WS, terminal WSS, reconciliation, and idle reaper into the demoable "log in -> paste key -> chat with OpenClaw" milestone. Upgrades Phase 2's stub API to durable Temporal-backed workflows, same HTTP contract.
- [ ] **Phase 6: Metering, Billing & Credits** - LiteLLM proxy, per-session virtual keys, Stripe top-ups with idempotent webhooks, atomic ledger, circuit breakers, and the live credit-drain UI.
- [ ] **Phase 7: Persistent Tier & OSS Hardening** - Paid-tier volumes with backups/restore, disk pressure guards, audit log, rate limits, Apache-2.0 release, public CI, and ops runbooks.
- [ ] **Phase 7.5: Sandbox Hardening Spine (inserted 2026-04-13)** - Custom seccomp JSON, `ap-net` egress allowlist + iptables, Falco/Tetragon anomaly detection, escape-test CI harness, gVisor `runsc` install and per-recipe runtime selection. Fills in the sandbox knobs Phase 2 plumbed. Lands against a known-working substrate, right before Phase 8 introduces the first untrusted-code path.
- [ ] **Phase 8: Generic Claude-Code Bootstrap** - Ship the "paste any git repo" differentiator on the gVisor path with content-addressed recipe caching and a human-review promotion flow.

## Phase Details

### Phase 1: Foundations, Spikes & Temporal
**Goal**: A running Hetzner host with Docker, Postgres, Redis, Temporal, a Go API, a mobile-first Next.js shell, the multi-agent baseline schema, and the Phase-0 spike answers committed -- everything downstream phases consume.
**Depends on**: Nothing (first phase).
**Requirements**: FND-01, FND-02, FND-03, FND-04, FND-05, FND-06, FND-07, FND-08, FND-09, FND-10
**Success Criteria** (what must be TRUE):
  1. `curl https://<host>/healthz` from the internet returns 200 from the Go API behind UFW, proving the Hetzner box, Docker 27.x with `userns-remap`, Postgres 17, Redis 7, Echo v4, and pgx v5 are all up and `golang-migrate` has applied the baseline schema (including the `agents` table) at boot.
  2. A developer visits the Next.js 16 mobile-first login-gated landing page on a phone viewport and sees it served from the same host -- Next.js + React 19 + Tailwind v4 + shadcn/ui render correctly with touch-friendly targets and the route refuses unauthenticated access.
  3. A Go unit test can call `pkg/docker/runner.go` to `run`, `exec`, `inspect`, `stop`, `rm` an `alpine` container on the host with strict arg validation and succeed end-to-end -- the MSV-ported runner is live.
  4. A trivial Temporal workflow (`ping -> pong`) submitted to the `session` task queue via the Go API worker runs to completion and is observable in Temporal Web UI + `tctl`, proving worker identity, namespace, and all three task queues (`session`, `billing`, `reconciliation`) are wired.
  5. `.planning/research/SPIKE-REPORT.md` is committed documenting per-agent `HTTPS_PROXY` vs `*_BASE_URL` behavior, `chat_io.mode` for each curated agent, tmux+named-pipe round-trip latency, and gVisor `runsc` feasibility on the chosen Hetzner kernel.
**Plans:** 6 plans
Plans:
- [x] 01-01-PLAN.md -- Go API skeleton + migrations + dev-cookie auth
- [x] 01-02-PLAN.md -- Docker runner ported from MSV
- [x] 01-03-PLAN.md -- Next.js mobile-first frontend shell
- [x] 01-04-PLAN.md -- Infrastructure scripts + docker-compose
- [x] 01-05-PLAN.md -- Temporal worker + task queues + PingPong proof
- [x] 01-06-PLAN.md -- Spike report (4 unknowns)

### Phase 2: Agent-in-a-Box + Minimal Substrate
**Reshaped on 2026-04-13.** Original scope bundled substrate + full hardening; the hardening spine moved to Phase 7.5 so the substrate can be validated against real agents first.

**Goal**: Prove the hypothesis "any agent x any model, API-driven, no Telegram" for two architecturally different agents (picoclaw, Hermes), on top of an `ap-base` image forwards-compatible with the long-tail recipe catalog. **Context of record:** `.planning/phases/02-container-sandbox-spine/02-CONTEXT.md` (read before planning).
**Depends on**: Phase 1 (Docker + runner.go + auth middleware + migrations).
**Requirements (reshaped mapping)**:
  - **Landed in Phase 2:** SBX-01 (tini + tmux + ttyd in ap-base), SBX-03 (resource limits via runner.go options), SBX-05 (no docker socket, no privileged -- invariant), SBX-09 (deterministic naming `playground-<user>-<session>`), partial SBX-02 (cap-drop, no-new-privs, read-only rootfs, tmpfs via runner.go option fields -- custom seccomp JSON deferred to 7.5)
  - **Pulled forward from Phase 5 as stub scope:** partial SES-01 (session create with state transitions, direct runner.go call, no Temporal), partial SES-04 (session stop), partial CHT-01 (synchronous HTTP `POST /messages` via FIFO bridge -- no WS yet)
  - **Pulled forward from Phase 3 as dev-mode stub:** dev BYOK via `AP_DEV_BYOK_KEY` env + tmpfs `/run/secrets/*_key` injection mechanism (file-based injection is Phase 2; Phase 3 replaces the source with the encrypted vault)
  - **Pulled forward from Phase 4 as hardcoded:** two thin recipes (picoclaw Go CLI, Hermes Python TUI) as Go structs in `internal/recipes/` -- Phase 4 replaces with YAML schema + loader
  - **Deferred to Phase 7.5:** SBX-02 custom seccomp JSON, SBX-04 `ap-net` egress allowlist, SBX-06 gVisor runsc install, SBX-07 Falco/Tetragon, SBX-08 escape-test CI (SBX-07 UFW portion already active from Phase 1)

**Success Criteria** (what must be TRUE):
  1. `ap-base` image builds, starts with `tini` as PID 1 supervising `tmux` (two windows: `chat` + `shell`) and `ttyd` on loopback, has read-only rootfs + tmpfs `/tmp` + tmpfs `/run` + all caps dropped + `no-new-privileges`, drops to an unprivileged user via gosu entrypoint shim ported from MSV's `infra/picoclaw/`, and is reachable via `docker exec` for FIFO-based chat.
  2. `pkg/docker/runner.go` `RunOptions` has fields for `SeccompProfile`, `ReadOnlyRootfs`, `Tmpfs`, `CapDrop`, `CapAdd`, `NoNewPrivs`, `PidsLimit`, `Memory`, `CPUs`, `Runtime`, `NetworkMode`, all wired through to Docker Engine SDK `HostConfig`, all unit-tested. Defaults applied at call sites, not inside runner.go.
  3. A container spawned for user `u1` + session `s1` is named exactly `playground-u1-s1` via a validator/helper in runner.go. Name can be re-derived from DB row alone (SBX-09 satisfied for Phase 5 reconciliation).
  4. Two recipe images pre-built via `make build-recipes`: `ap-picoclaw` (Go binary pinned to commit SHA from `/Users/fcavalcanti/dev/picoclaw`, `stdin_fifo` chat path) and `ap-hermes` (Python 3.13 from `github.com/NousResearch/hermes-agent` pinned to commit SHA, with pre-populated `~/.hermes/cli-config.yaml` disabling built-in channel daemons and forcing `backend: local`).
  5. **Hypothesis proof via end-to-end curl smoke test**: `POST /api/sessions` (with `recipe`, `model_provider`, `model_id`) spawns the container via direct runner.go call (no Temporal in Phase 2, HTTP contract compatible with Phase 5's Temporal upgrade). `POST /api/sessions/:id/message {text}` exchanges a real message with a real Anthropic model via BYOK env injection, returns the response. `DELETE /api/sessions/:id` tears down cleanly. Test passes for **both picoclaw and Hermes** with no dangling `playground-*` containers afterwards. "API-driven agent start without Telegram" is demonstrated from curl.
**Plans:** 6 plans
Plans:
- [x] 02-01-PLAN.md -- ap-base image (Dockerfile + entrypoint + tmux + ttyd + gosu drop) [Wave 1]
- [x] 02-02-PLAN.md -- runner.go sandbox fields + container naming helper [Wave 1]
- [x] 02-03-PLAN.md -- Two recipe overlays (ap-picoclaw FIFO + ap-hermes single-query) [Wave 2]
- [x] 02-04-PLAN.md -- Sessions migration + recipes package + secrets writer + ExecWithStdin (foundations) [Wave 2]
- [x] 02-05-PLAN.md -- Session HTTP handlers + chat bridge + main.go wiring (API surface) [Wave 3]
- [x] 02-06-PLAN.md -- End-to-end smoke test + integration tests + human verification [Wave 4]
**UI hint**: no (API-only; Phase 5 adds the browser UX)
**Reshape rationale**: See `02-CONTEXT.md` `<domain>` section. Hardening deferred = zero work lost (runner.go hooks are plumbed; Phase 7.5 fills them in against a substrate known to work).

### Phase 02.5: Recipe Manifest Reshape (INSERTED)

**Goal:** [Urgent work - to be planned]
**Requirements**: TBD
**Depends on:** Phase 2
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 02.5 to break down)

### Phase 3: Auth, Secrets & BYOK Key Handling
**Goal**: A user can log in with Google or GitHub, manage BYOK keys safely, and the whole secret-handling pipeline (storage, injection, log scrubbing, audit) is hardened before the first BYOK-using session is ever spawned.
**Depends on**: Phase 1 (API + DB + Next.js) and Phase 2 (the sandbox that will later consume the injected secrets).
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08, SEC-09, SEC-10, SEC-11
**Success Criteria** (what must be TRUE):
  1. A user can sign in with Google or GitHub OAuth via goth, land on the dashboard, refresh the browser and stay signed in (HTTP-only signed cookie -> Postgres session row), click sign-out on any page and have the server-side session row invalidated; unauthenticated access to a protected route redirects to the provider picker.
  2. An authenticated user with an OAuth token that is about to expire has the token silently refreshed at >=80% of its TTL without any observable interruption, verified by an integration test that fast-forwards the clock.
  3. A user can add an Anthropic / OpenAI / OpenRouter BYOK key via the settings page, see it masked to the last 4 characters, click "Test key" and get a live valid/invalid verdict from the provider's `/models` endpoint within 5s, replace it, and delete it -- and at no point is the raw key returned in any API response or log line.
  4. A staged container run with a BYOK key injected via the tmpfs-backed `/run/secrets/<provider>_key` + entrypoint shim pattern (never a plain env var) is inspected with `docker inspect`, `ps eww`, `cat /proc/1/environ`, and the stdout/stderr pipeline -- the key never appears anywhere except inside the agent process, and the regex scrubber masks any known provider prefix that leaks.
  5. The nightly audit-log scanner, `gitleaks` pre-commit hook in `/work`, `ulimit -c 0`, and recipe CI lint banning `ENV`/`ARG` secret patterns are all active -- demonstrated by an end-to-end test that stages a leak via each vector and sees the alert/block fire.
**Plans**: TBD
**UI hint**: yes

### Phase 4: Recipe System & Curated Catalog
**Goal**: A validated `ap.recipe/v1` schema, a Go recipe loader that refuses to start on invalid recipes, four curated agent recipes (OpenClaw, Hermes, HiClaw, PicoClaw) with pinned immutable refs, and the local + nightly CI smoke-test rig that keeps them honest.
**Depends on**: Phase 2 (recipes build on `ap-base`) and Phase 3 (recipe CI lint uses the SEC-07 secret-pattern rules).
**Requirements**: REC-01, REC-02, REC-03, REC-04, REC-05, REC-06, REC-07, REC-08, REC-09, REC-10, REC-11, REC-12
**Success Criteria** (what must be TRUE):
  1. `agents/_schema/recipe.schema.json` is committed, the Go recipe loader parses every `agents/<name>/recipe.yaml` at API startup, validates against the schema, and the API refuses to start if any recipe is invalid (tested by a CI job that stages a malformed recipe).
  2. Running `make test-recipe AGENT=openclaw` (and for `hermes`, `hiclaw`, `picoclaw`) spawns the recipe's container, sends a hello-world prompt, and asserts a non-error response from the agent -- every curated recipe passes this smoke test locally and in CI.
  3. Every curated recipe pins its upstream source to an immutable git SHA or tag (never `main`, never `:latest`), verified by a CI linter that greps recipe YAML and fails on floating refs.
  4. The nightly CI workflow re-runs `test-recipe` against all four recipes and, on any failure, auto-opens a GitHub issue tagged `recipe-drift`; the upstream-watch cron polls each recipe's GitHub release feed and opens a PR when a new release is detected -- both are exercised by injecting a staged drift/release in a test.
  5. Given a user with an Anthropic BYOK key and no OpenAI key, the API's model-picker endpoint for `openclaw` returns only Anthropic models (intersection of `models.supported_providers` and the user's available keys), and bootstrap-discovered recipe cache entries are keyed by `(repo_url, commit_sha, bootstrap_output_hash)` so no cached recipe can silently inherit a different commit's permissions.
**Plans**: TBD

### Phase 5: Demoable MVP -- Session Lifecycle, Chat & Terminal
**Goal**: The headline demoable milestone. A logged-in user picks OpenClaw + Anthropic + BYOK, gets a running container in <=10s, chats with the agent in the browser, opens the web terminal on the same container, stops the session -- and every lifecycle path is durable, reconciled, and leak-free.
**Depends on**: Phase 2 (sandbox), Phase 3 (auth + BYOK injection), Phase 4 (recipe loader + OpenClaw recipe), Phase 1 (Temporal worker).
**Requirements**: SES-01, SES-02, SES-03, SES-04, SES-05, SES-06, SES-07, SES-08, SES-09, CHT-01, CHT-02, CHT-03, CHT-04, CHT-05, TRM-01, TRM-02, TRM-03, TRM-04, TRM-05, TRM-06
**Success Criteria** (what must be TRUE):
  1. A logged-in user clicks "New session", picks `(openclaw, anthropic, claude-sonnet-X, BYOK, free)`, and within 10 seconds sees the session badge go `pending -> provisioning -> ready -> running` and a chat textarea that accepts input and streams the agent's response back -- the full demoable milestone.
  2. Session create/destroy runs as a Temporal workflow on the `session` task queue (not pg-boss, not in-process only): killing the Go API mid-spawn and restarting it results in the workflow resuming or compensating, with no dangling container and no `provisioning` zombie row -- verified by a chaos test.
  3. Two concurrent `POST /api/sessions` from the same user race cleanly -- exactly one succeeds, the other returns `409 Conflict` -- because the Postgres `UNIQUE (user_id) WHERE status IN ('provisioning','ready','running')` partial index AND the Redis `SETNX session:create:{user_id}` lock both fire, and the reconciliation loop every 30s kills any `playground-*` container that has no matching DB row (and vice versa).
  4. With the chat WS open on `/api/sessions/:id/stream`, the user simultaneously opens `/api/sessions/:id/tty` on the xterm.js terminal page, runs `ls /work` in the shell, and sees the same filesystem the agent is editing -- both surfaces work on the same container with no PTY contention because chat uses named pipes and terminal uses the tmux `shell` window. A second WS on either endpoint kicks the first; plain `ws://` on the terminal is refused; cross-origin upgrades are rejected.
  5. An idle session whose free-tier TTL (15 min) elapses with no chat message, terminal keystroke, or `/work` mtime change is reaped by the idle reaper; a container that stops heartbeating for 90s is marked `stale` and reconciled; stopping a free-tier session tears down the container and destroys the ephemeral volume -- all tested end-to-end.
**Plans**: TBD
**UI hint**: yes

### Phase 6: Metering, Billing & Credits
**Goal**: A user can top up credits via Stripe, spawn a platform-billed session, see their balance drain live, hit a hard ceiling if the agent loops, and never get double-charged -- with the BYOK path still completely bypassing the billing surface.
**Depends on**: Phase 5 (session spawn is where virtual keys get minted and billing mode is locked).
**Requirements**: MET-01, MET-02, MET-03, MET-04, MET-05, MET-06, MET-07, MET-08, MET-09, MET-10, MET-11, MET-12, MET-13, MET-14, MET-15, BIL-01, BIL-02, BIL-03, BIL-04, BIL-05, BIL-06
**Success Criteria** (what must be TRUE):
  1. A user can click "Top up $10" in the header, complete Stripe Checkout, and see their credit balance (computed as `SUM(amount) FROM credit_ledger`, never a cached scalar, stored in cents, rendered as `$X.YY` in their timezone) increase by exactly $10 -- even if Stripe delivers the webhook twice, the `UNIQUE (stripe_event_id)` constraint + same-transaction ledger insert guarantee idempotency, and replay attacks with events >5 min old are rejected via signature + timestamp check.
  2. Spawning a platform-billed OpenClaw session mints a LiteLLM virtual key with `max_budget = remaining_credits`, injects `ANTHROPIC_BASE_URL=http://host.docker.internal:8088` into the container, and routes every model call through LiteLLM on `127.0.0.1:8088` where it is logged to Postgres and decremented from the ledger; spawning a BYOK session for the same user writes zero billing rows and never overrides any base URL.
  3. Billing mode is locked at session spawn -- mid-session there is no silent fallback from BYOK to platform (or vice versa), verified by an integration test that tries to swap keys and observes the session refuse.
  4. A staged runaway agent that makes >60 model calls per minute with no `/work` mtime change is killed by the loop-detection heuristic and the user receives a notification email; the hard circuit breakers (call-rate, token ceiling, wall-clock ceiling) fire independently of credit balance on every session regardless of key source; at 20% remaining balance the user sees a low-balance warning and at 0 the session is paused with a top-up prompt.
  5. A pre-authorized token budget is deducted before each model call and the unused delta refunded on completion; calls that return without a `usage` field are handled by the documented refund policy; the nightly reconciliation job diffs the local ledger against Stripe events and provider invoices and alerts on any drift; the header drains the balance live during platform-billed sessions (with a +-5% disclaimer) and hides it entirely during BYOK sessions.
**Plans**: TBD
**UI hint**: yes

### Phase 7: Persistent Tier & OSS Hardening
**Goal**: Paid-tier users get a persistent `/work` volume with backups and restore, the host is guarded against disk pressure and egress blowouts, and the whole platform is ready for an Apache-2.0 public release with audit logs, rate limits, CI, and ops runbooks.
**Depends on**: Phase 5 (session lifecycle is where the volume mount happens) and Phase 6 (tier gating is driven by billing state).
**Requirements**: PER-01, PER-02, PER-03, PER-04, PER-05, PER-06, PER-07, PER-08, PER-09, OSS-01, OSS-02, OSS-03, OSS-04, OSS-05, OSS-06, OSS-07, OSS-08, OSS-09, OSS-10
**Success Criteria** (what must be TRUE):
  1. A paid-tier user spawns a session, writes files into `/work`, stops the session, reconnects within the 4h idle TTL, and finds the same files in the same container-equivalent -- their `ap-vol-{user_id}` volume is mounted, quota-enforced (XFS project quota or `du`-supervisor), and survives container recreation; free-tier users still get `--rm` + tmpfs with state destroyed on stop.
  2. The nightly `restic` snapshot job writes paid-tier volumes to the S3-compatible target (MinIO or Hetzner Storage Box) with the documented retention policy; the quarterly restore drill runbook has been executed at least once and passes; an OOM-killed paid-tier container auto-restores the latest snapshot on the next spawn.
  3. Host disk usage alerts fire at 70 / 80 / 90% and the 90% threshold blocks new session creation; per-session egress bandwidth is capped via `tc` or app-layer and the bootstrap allowlist excludes large-file CDNs -- verified by a load test that staged a bandwidth blowout.
  4. The repository is live on GitHub under Apache-2.0 with headers on every source file, `README.md` with the quickstart + "try any git repo" demo, `CONTRIBUTING.md` documenting the recipe submission workflow with CI smoke-test as the merge gate, `SECURITY.md` with the disclosure process and curated-vs-bootstrap sandbox guarantees, and a self-hosted deployment guide for the Hetzner + Docker + systemd path.
  5. Every session spawn / stop, billing event, BYOK key change, and admin action is recorded in the append-only `audit_log` with a retention policy; per-user + per-IP rate limits are enforced in Echo middleware; GitHub Actions CI runs `go test`, `go vet`, frontend type-check, and every recipe smoke test on every PR; `unattended-upgrades` is patching the host kernel + Docker; Falco/Tetragon rules and the reconciliation/restore runbook ship in `docs/ops/`.
**Plans**: TBD
**UI hint**: yes

### Phase 7.5: Sandbox Hardening Spine
**Inserted 2026-04-13** as part of the Phase 2 reshape. Holds the host-hardening work originally in Phase 2 that no longer blocks the hypothesis proof.

**Goal**: Against a known-working substrate (Phase 2's `ap-base` + runner.go sandbox knobs + pre-built recipes), fill in the full host hardening posture required before Phase 8 introduces the first untrusted-code path. Populate every sandbox knob Phase 2 plumbed.
**Depends on**: Phase 2 (runner.go fields to fill in, ap-base to harden), Phase 4 (curated recipes to test against), Phase 7 (OSS hardening + audit log share ops surface).
**Requirements (moved from Phase 2)**:
  - **SBX-02** (custom seccomp JSON blocking `mount/unshare/setns/keyctl/bpf/ptrace`)
  - **SBX-04** (`ap-net` bridge + egress allowlist: model providers + package registries + user git remote only)
  - **SBX-06** (gVisor `runsc` install + selectable per-recipe via `runtime: runsc` -- mandatory for Phase 8)
  - **SBX-07** (Falco or Tetragon, confirmed -- the UFW + loopback-bind portion of SBX-07 is already done in Phase 1)
  - **SBX-08** (host-side syscall anomaly detector alerting on staged escape events)

**Success Criteria** (what must be TRUE):
  1. A custom seccomp profile JSON is committed and applied by default to every recipe container via `RunOptions.SeccompProfile`; an escape-attempt test harness in CI stages `mount`, `unshare`, `setns`, `keyctl`, `bpf`, `ptrace` calls from inside each recipe image and asserts they fail with `EPERM`/`EACCES`.
  2. `ap-net` Docker bridge is created with an iptables DOCKER-USER allowlist (model provider CIDRs + npm/pypi/cargo + user's git remote host); integration test proves `curl https://api.anthropic.com` succeeds and `curl https://evil.example.com` fails from inside a recipe container.
  3. gVisor `runsc` is installed on the Hetzner host (Spike 4 cleared), registered as a Docker runtime, and selectable via `RunOptions.Runtime = "runsc"`. A recipe flagged `runtime: runsc` starts, passes the same escape-attempt test, and the bootstrap path scheduled for Phase 8 can use it.
  4. Falco or Tetragon runs as a systemd unit on the host with a published rule set in `docs/ops/`; a staged `mount`-from-container test fires an alert to the configured sink within 5s.
  5. Host Docker socket is never visible inside any recipe container under any code path (existing Phase 2 invariant re-verified as part of the hardening audit); `--privileged` does not appear anywhere in the codebase (grep gate in CI).
**Plans**: TBD
**UI hint**: no

### Phase 8: Generic Claude-Code Bootstrap
**Goal**: The headline differentiator. A user pastes any GitHub / GitLab / Codeberg / Bitbucket URL and gets a working dockerized session 30 seconds later via Claude Code driving the install -- running under gVisor with a content-addressed recipe cache and a human-review promotion flow.
**Depends on**: Phase 2 (the gVisor runtime it requires), Phase 4 (the recipe schema it emits into), Phase 6 (scoped billing for Claude Code), Phase 5 (session lifecycle).
**Requirements**: BST-01, BST-02, BST-03, BST-04, BST-05, BST-06, BST-07, BST-08, BST-09
**Success Criteria** (what must be TRUE):
  1. A user pastes `https://github.com/<owner>/<repo>` into the session creator (URL validated by the allowlist regex `^https://(github|gitlab|codeberg|bitbucket)\.com/[\w.-]+/[\w.-]+$`), and the bootstrap session spins the `ap-base:bootstrap` image (shipping `git`, `node`, `python`, `tini`, `ttyd`, Claude Code) under `runsc` (gVisor) by default -- never vanilla `runc`.
  2. Claude Code inside the container reads `/prompt.md`, drives the install, and emits `/work/.ap/recipe.yaml`; the recipe is validated against `ap.recipe/v1` before it is trusted, and on validation failure the user sees a "bootstrap failed -- here's the log" UX instead of a silent error.
  3. A successful bootstrap caches the extracted recipe content-addressed by `(repo_url, commit_sha, bootstrap_output_hash)` and flags it `unverified` until a human or CI approves -- no cached recipe silently gets promoted to the curated catalog, verified by a test that confirms a fresh bootstrap re-runs until approval.
  4. Claude Code in the bootstrap container runs with its own scoped API key only (never a shared platform fallback), hard circuit breakers from Phase 6 apply, and an audit shows that no shell invocation in the bootstrap path uses string interpolation -- every call goes through `exec.Command` with arg arrays.
  5. A user whose bootstrap succeeded can optionally click "PR this recipe to `agents/community/`" and have the tool open a PR with the filled-in template against the public GitHub repo, closing the loop from bootstrap -> community catalog.
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundations, Spikes & Temporal | 6/6 | Complete | 2026-04-14 |
| 2. Agent-in-a-Box + Minimal Substrate | 0/? | Context gathered | - |
| 3. Auth, Secrets & BYOK Key Handling | 0/? | Not started | - |
| 4. Recipe System & Curated Catalog | 0/? | Not started | - |
| 5. Demoable MVP -- Session Lifecycle, Chat & Terminal | 0/? | Not started | - |
| 6. Metering, Billing & Credits | 0/? | Not started | - |
| 7. Persistent Tier & OSS Hardening | 0/? | Not started | - |
| 7.5. Sandbox Hardening Spine | 0/? | Not started | - |
| 8. Generic Claude-Code Bootstrap | 0/? | Not started | - |

## Coverage

- **v1 requirements**: 117
- **Mapped**: 117 (100%)
- **Unmapped**: 0
- **Orphaned**: 0

### Pitfall -> Phase Mapping

| Pitfall | Phase | Rationale |
|---------|-------|-----------|
| CRIT-1 (bootstrap sandbox escape) | Phase 7.5 + Phase 8 | gVisor + custom seccomp + egress allowlist land in 7.5 against a known-working substrate; Phase 8 is the first phase that actually introduces untrusted code, so 7.5 lands immediately before it |
| CRIT-2 (BYOK env leak) | Phase 3 | Secrets pipeline (SEC-*) lands with BYOK settings UI; no BYOK surface exposed before safe injection proven. **File-based injection mechanism** (`/run/secrets/*_key` tmpfs) is plumbed in Phase 2 via dev env var; Phase 3 populates it from the encrypted vault -- same mechanism, different source. |
| CRIT-3 (runaway loop) | Phase 6 | Circuit breakers (MET-08, MET-09) ship with the metering layer -- never "later" |
| CRIT-4 (cross-tenant kernel escape) | Phase 1 (userns-remap active) + Phase 2 (cap-drop/read-only/no-new-privs defaults) + Phase 7.5 (custom seccomp + Falco) | Layered: the cheap defense-in-depth lands as Phase 2 runner.go defaults; the custom seccomp profile + anomaly detection land in 7.5 |
| CRIT-5 (Stripe webhook race) | Phase 6 | Idempotent ledger + BIL-02/03/04 land with the first Stripe call |
| CRIT-6 (dangling containers) | Phase 5 | Reconciliation loop (SES-05) + Temporal workflow (SES-07) + heartbeat (SES-08) land with the lifecycle manager. Phase 2's stub session API is explicitly non-durable -- Phase 5 upgrades it. |

---
*Roadmap created: 2026-04-11*
*Phase 1 planned: 2026-04-13*
*Phase 1 complete: 2026-04-14*
*Phase 2 reshaped + Phase 7.5 inserted: 2026-04-14 (see `.planning/phases/02-container-sandbox-spine/02-CONTEXT.md` `<domain>` for rationale)*
*Phase 2 plans split (W1 fix): Plan 04 split into 04 (foundations) + 05 (API surface); existing Plan 05 renumbered to 06 — 2026-04-14*
