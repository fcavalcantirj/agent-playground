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

**Reshaped on 2026-04-14** — this is an ARCHITECTURE phase, not a catalog phase. Its deliverable is the recipe manifest pattern (schema + loader + template registry + lifecycle runner + chat-bridge abstraction), not the recipes themselves. Phase 4 backfills the 8 deferred recipes against the locked pattern.

**Goal**: Lock the YAML-backed recipe substrate (`ap.recipe/v1` schema, loader, filesystem template registry, 6-hook lifecycle runner, ChatBridge interface, runtime base image build system, Praktor-shape secret vault resolver) and prove the architectural hypothesis that recipe N+1 is configuration, not code. Ship 2 reference recipes (aider + picoclaw) that exercise every component of the new substrate end-to-end. Pass both gates: Gate A (`make smoke-test-matrix` — plumbing proof, 4 cells max {aider, picoclaw} × {anthropic, openrouter}) and Gate B (`make test-architectural-drop-in` — acceptance gate where a third recipe is added to the running system as a pure directory drop with zero Go code changes). Gate B passing closes Phase 02.5.
**Depends on**: Phase 2 (substrate: `ap-base`, `pkg/docker/runner.go`, session handler stubs, Phase 2 bridge.go FIFO + exec modes that this phase lifts behind the `ChatBridge` interface)
**Context of record:** `.planning/phases/02.5-recipe-manifest-reshape/02.5-CONTEXT.md` (54 locked decisions D-01..D-54)
**Requirements**: REC-01, REC-02, REC-06, REC-07
**Success Criteria** (what must be TRUE):
  1. `agents/schemas/recipe.schema.json` exists as JSON Schema Draft 2019-09, enforces closed enums on every field (runtime.family / install.type / chat_io.mode / auth.mechanism / isolation.tier / policy_flags), rejects Dev Containers object-syntax parallel groups, rejects secret: refs inside onCreate/updateContent hooks, and requires 40-char hex SHA for install.git.rev.
  2. Go recipe loader at `api/internal/recipes/` walks `agents/`, validates + unmarshals + semantic-checks + flavor-resolves every recipe at API startup, refuses to start on any invalid recipe, supports SIGHUP atomic reload, and every Phase 2 hardcoded recipe struct (`recipes.Picoclaw`, `recipes.Hermes`, `recipes.AllRecipes`, `recipes.Render`, `recipes.AgentAuthFiles`) is REMOVED.
  3. Filesystem template registry at `agents/<id>/templates/*.tmpl` renders under a closed FuncMap ({default, quote, lower, upper, trim}) with path allowlist regex `^[a-z0-9][a-z0-9_-]*\.tmpl$`, symlink rejection, 5s timeout, 64 KiB output cap, and `missingkey=error` option. Zero Go recompile to add a new agent.
  4. `Runner.RunWithLifecycle` executes all 6 Dev Containers hooks in strict order (initializeCommand → onCreateCommand → updateContentCommand → postCreateCommand → postStartCommand → postAttachCommand) with `waitFor` gating (default postCreateCommand), array-of-arrays parallel groups via `errgroup.WithContext`, per-hook timeout (default 10 min), and teardown on any non-zero exit. No stubs, no TODOs.
  5. `ChatBridge` interface in `api/internal/session/bridge/` with `FIFOBridge` and `ExecBridge` implementations lifted verbatim from Phase 2 code (no rewrites). `BridgeRegistry.Dispatch` keys on closed `chat_io.mode` enum {fifo, exec_per_message}.
  6. 2 runtime base images built via `make build-runtimes`: `ap-runtime-python:v0.1.0-3.13` (Python 3.13 + uv 0.11.6 FROM ap-base) and `ap-runtime-node:v0.1.0-22` (Node 22 LTS Debian-slim FROM ap-base — NOT Alpine per D-20). 3 other families (go/rust/zig) deferred to Phase 4.
  7. 2 reference recipes pass L2 eager verification: `agents/aider/recipe.yaml` (python / pip / exec_per_message / env_var / anthropic+openrouter / standalone) and `agents/picoclaw/recipe.yaml` (node / git_build / fifo / secret_file_mount via template / anthropic / standalone — NOT config_flavor_of per D-40b). Both pin 40-char upstream SHAs per D-42.
  8. `GET /api/recipes` + `GET /api/recipes/:id` serve public-metadata views only (no lifecycle/install/auth/isolation leaks), support filter params (?family=, ?tier=, ?license=, ?provider=). `POST /api/sessions` accepts the new `provider` field and rejects invalid combinations with specific error codes (`recipe_not_found`, `provider_not_supported`, `model_not_supported`, `secret_missing`, `template_render_failed`, `lifecycle_hook_failed`, `chat_bridge_unsupported_mode`).
  9. **Gate A passes** (prerequisite): `make smoke-test-matrix` runs up to 4 cells {aider, picoclaw} × {anthropic, openrouter}, each sends literal `whoareyou` and asserts HTTP 200 + non-empty reply + no dangling `playground-*` container + no top-level error envelope. D-47 criteria: each recipe passes on ≥1 provider; ≥1 recipe passes on BOTH providers (OpenRouter wire proven); zero non-SKIP failures.
  10. **Gate B passes** (acceptance gate per D-01b): `make test-architectural-drop-in` — operator writes a third agent recipe (openclaw/plandex/synthetic null-echo fallback per D-50d) as a pure `agents/<target>/` directory drop, restarts the API server (SIGHUP reload), and the new cells pass the same `whoareyou` assertion as Gate A. `git diff api/ deploy/ Makefile agents/schemas/` is empty throughout the exercise per D-50c (only allowed substrate addition: a new `deploy/ap-runtime-<family>/Dockerfile` for an unbuilt runtime family). Passing Gate B closes Phase 02.5.
**Plans:** 11/11 plans complete
Plans:
- [x] 02.5-01-PLAN.md — Recipe YAML schema v0.1.0 + JSON Schema Draft 2019-09 + loader + validator + SIGHUP reload [Wave 1]
- [x] 02.5-02-PLAN.md — Filesystem template registry + renderer + security hardening (closed FuncMap, path allowlist, symlink rejection, timeout, size cap) [Wave 2]
- [x] 02.5-03-PLAN.md — `Runner.RunWithLifecycle` + all 6 Dev Containers hooks + `waitFor` gating + errgroup parallel groups + per-hook timeouts [Wave 2]
- [x] 02.5-04-PLAN.md — `ChatBridge` interface + `FIFOBridge` + `ExecBridge` (lifted verbatim from Phase 2) + `BridgeRegistry` [Wave 2]
- [x] 02.5-05-PLAN.md — `SecretSource` extended with `Resolve` + `DevEnvSecretSource` (Anthropic + OpenRouter + extras) + `Materialize` pipeline + log redaction + server options wiring [Wave 2]
- [x] 02.5-06-PLAN.md — Runtime base images `ap-runtime-python` (Python 3.13 + uv) + `ap-runtime-node` (Node 22 Debian-slim) + Makefile `build-runtimes` target [Wave 2]
- [x] 02.5-07-PLAN.md — `aider` reference recipe (python / pip / exec_per_message / env_var / anthropic+openrouter) with L2 eager verification resolving Assumption A3 [Wave 3]
- [x] 02.5-08-PLAN.md — `picoclaw` reference recipe (node / git_build / fifo / secret_file_mount) + `templates/security.yml.tmpl` + rebuilt `Dockerfile` FROM `ap-runtime-node` + L2 verification resolving Assumption A7 [Wave 3]
- [x] 02.5-09-PLAN.md — `GET /api/recipes` + `GET /api/recipes/:id` + `POST /api/sessions` provider-field extension + new error codes + legacy recipe struct removal + migration `0003_sessions_provider.sql` [Wave 3]
- [x] 02.5-10-PLAN.md — **Gate A**: `make smoke-test-matrix` (4 cells, `whoareyou` probe, D-47 enforcement) [Wave 4]
- [x] 02.5-11-PLAN.md — **Gate B**: `make test-architectural-drop-in` (architectural acceptance gate per D-01b; operator-driven drop-in of a third recipe with zero substrate edits; passing closes Phase 02.5) [Wave 5]
**UI hint**: no (API-only; Phase 5 consumes `GET /api/recipes` from the browser)
**Reshape note**: REC-01/02/06/07 moved from Phase 4 to Phase 02.5 as substrate. REC-03/04/05/08 (full)/09/10/11/12 remain in Phase 4. See `.planning/REQUIREMENTS.md` updated traceability.

### Phase 3: Auth, Secrets & BYOK Key Handling
**Goal**: A user can log in with Google or GitHub OAuth via goth, land on the dashboard, refresh the browser and stay signed in (HTTP-only signed cookie -> Postgres session row), click sign-out on any page and have the server-side session row invalidated; unauthenticated access to a protected route redirects to the provider picker.
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
| CRIT-2 (BYOK env leak) | Phase 3 | Secrets pipeline (SEC-*) lands with BYOK settings UI; no BYOK surface exposed before safe injection proven. **File-based injection mechanism** (`/run/secrets/*_key` tmpfs) is plumbed in Phase 2 via dev env var; Phase 3 replaces it with the encrypted vault -- same mechanism, different source. |
| CRIT-3 (runaway loop) | Phase 6 | Circuit breakers (MET-08, MET-09) ship with the metering layer -- never "later" |
| CRIT-4 (cross-tenant kernel escape) | Phase 1 (userns-remap active) + Phase 2 (cap-drop/read-only/no-new-privs defaults) + Phase 7.5 (custom seccomp + Falco) | Layered: the cheap defense-in-depth lands as Phase 2 runner.go defaults; the custom seccomp profile + anomaly detection land in 7.5 |
| CRIT-5 (Stripe webhook race) | Phase 6 | Idempotent ledger + BIL-02/03/04 land with the first Stripe call |
| CRIT-6 (dangling containers) | Phase 5 | Reconciliation loop (SES-05) + Temporal workflow (SES-07) + heartbeat (SES-08) land with the lifecycle manager. Phase 2's stub session API is explicitly non-durable -- Phase 5 upgrades it. |

### Phase 9: Spec lint + test harness foundations
**Goal:** JSON Schema-based `--lint` gate (`ap.recipe.schema.json`) + `pytest` suite with mocked-docker fixtures for every `pass_if` verb, lint negative tests, ruamel write-back round-trip. Lint runs as mandatory pre-step (`--no-lint` to bypass). Gates all subsequent framework phases.
**Depends on:** Phase 3 (v0.1 consolidation)
**Plans:** 4 plans
Plans:
- [x] 09-01-PLAN.md — JSON Schema + pyproject.toml + recipe v0->v0.1 bump + function extraction [Wave 1]
- [x] 09-02-PLAN.md — --lint / --lint-all / --no-lint CLI integration + colored output + exit code 2 [Wave 2]
- [x] 09-03-PLAN.md — pytest suite: pass_if verbs + lint negatives (12 fragments) + YAML round-trip + regression [Wave 2]
- [x] 09-04-PLAN.md — Makefile targets (install-tools, test, lint-recipes, check) + GitHub Actions CI [Wave 3]

### Phase 10: Error taxonomy + timeout enforcement
**Goal:** Replace single `PASS|FAIL` verdict with category-aware verdicts (`PASS`, `ASSERT_FAIL`, `INVOKE_FAIL`, `BUILD_FAIL`, `PULL_FAIL`, `CLONE_FAIL`, `TIMEOUT`, `LINT_FAIL`, `INFRA_FAIL`) + 2 reserved (`STOCHASTIC`, `SKIP`). Wire `smoke.timeout_s` to `--cidfile` + `docker kill` for true container reaping. Add `build.timeout_s`, `build.clone_timeout_s`, `--global-timeout`. Migrate 5 committed recipes to new shape. Steal from Inspect AI (5-layer timeout) and SWE-bench (`ResolvedStatus` enum).
**Depends on:** Phase 9
**Plans:** 5/5 plans complete
Plans:
- [x] 10-01-PLAN.md — Loosen schema: add category/detail as OPTIONAL + 11-value enum + build.timeout_s/clone_timeout_s [Wave 1]
- [x] 10-02-PLAN.md — Migrate 5 committed recipes (ruamel round-trip) adding category+detail per D-04 [Wave 2]
- [x] 10-03-PLAN.md — Tighten schema: category/detail REQUIRED on verified_cells + known_incompatible_cells [Wave 3]
- [x] 10-04-PLAN.md — Runner: Category enum + Verdict dataclass + preflight_docker + cidfile timeout + main() refactor [Wave 3]
- [x] 10-05-PLAN.md — tools/tests/test_categories.py: 9 live-category fixtures + cidfile lifecycle + emit format [Wave 4]

### Phase 11: Linux host owner_uid correctness
**Goal:** All 5 recipes run cleanly on a Linux host. Pick approach: chown tmpdir to `volumes[].owner_uid` before mount, OR `docker cp` instead of bind mount (SWE-bench pattern), OR `docker run --user`. Hard fail on permission mismatch. CI fixture against distinct UIDs (0, 1000, 10000, 65534).
**Depends on:** Phase 9
**Plans:** 0 plans
- [ ] TBD (run /gsd-plan-phase 11 to break down)

### Phase 12: Provenance + output bounds
**Goal:** Verdict JSON carries `recipe_sha256`, `resolved_upstream_ref`, `image_digest`, `runner_version`, `run_started_at`, `host_os`. Add `smoke.stdout_max_bytes` (default 1 MiB) with stream-and-truncate + `TRUNCATED` verdict. Steal from Cog (Docker labels with git SHA) and Inspect AI (`MAX_EXEC_OUTPUT_SIZE`).
**Depends on:** Phase 10 (`TRUNCATED` is a category)
**Plans:** 0 plans
- [ ] TBD (run /gsd-plan-phase 12 to break down)

### Phase 13: Determinism — SHA pinning + ap.recipe v0.2
**Goal:** Introduce `apiVersion: ap.recipe/v0.2` requiring full SHA in `source.ref`. Migration script for existing recipes. Clone dir keyed by SHA. Runner records `resolved_upstream_ref` for v0.1 compat. Steal from METR (`standard_version` semver) and SWE-bench (tag-pinned-not-digest-pinned gap).
**Depends on:** Phase 12 (uses provenance field)
**Plans:** 0 plans
- [ ] TBD (run /gsd-plan-phase 13 to break down)

### Phase 14: Isolation limits + default-deny
**Goal:** Schema adds `runtime.limits.{memory_mb, cpus, pids, network}` + `runtime.isolation.{cap_drop, read_only_rootfs, no_new_privileges}` — mandatory for v0.2, default-deny. Runner applies all via Docker flags. All 5 recipes audited + given explicit limits. Escape-attempt fixture. Steal from METR (`manifest.yaml` resource declarations + iptables network control).
**Depends on:** Phase 9, Phase 11
**Plans:** 0 plans
- [ ] TBD (run /gsd-plan-phase 14 to break down)

### Phase 15: Stochasticity — multi-run determinism
**Goal:** Schema adds `smoke.determinism: {runs: N, require: unanimous|majority|at_least(K)|pass_at(K)}`. Runner retries cells N times with aggregation. New `STOCHASTIC` category. Retrofit hermes × gemini as multi-run probe. Steal from Inspect AI (`multi_scorer` with `at_least(k)` / `pass_at(k)` reducers).
**Depends on:** Phase 10 (`STOCHASTIC` is a category)
**Plans:** 0 plans
- [ ] TBD (run /gsd-plan-phase 15 to break down)

### Phase 16: Dead verb coverage — fake-agent fixture
**Goal:** `recipes/_fake-agent.yaml` (busybox/alpine, controlled output) exercises every `pass_if` verb with ≥1 PASS + ≥1 FAIL fixture each. Runs in `pytest` in <10s, no LLM. Consider promptfoo's `not-` prefix pattern for v0.3. Steal from promptfoo (`assert-set` with fractional threshold for composition).
**Depends on:** Phase 9, Phase 10
**Plans:** 0 plans
- [ ] TBD (run /gsd-plan-phase 16 to break down)

### Phase 17: Doc-runner sync check
**Goal:** `tests/test_schema_sync.py` parses `ap.recipe.schema.json` (from P09) and asserts `pass_if` enum, `build.mode` enum, required fields, and CLI flags match the runner's argparse + `evaluate_pass_if` branches. Deliberate desync = pytest failure. Steal from Cog (schema IS the single source of truth).
**Depends on:** Phase 9
**Plans:** 0 plans
- [ ] TBD (run /gsd-plan-phase 17 to break down)

### Phase 18: Schema Maturity v0.1.1

**Goal:** Close concrete gaps in `tools/ap.recipe.schema.json` + `docs/RECIPE-SCHEMA.md` to make the recipe spec mature enough to serve as the API contract for Phase 19. No wire-format break — all 5 committed recipes continue to lint-pass unchanged. v0.1.1 is additive over v0.1: `$defs.v0_1` discriminator seam (D-01), `$defs.category` extraction (D-02), `known_incompatible_cells.verdict` enum tightening per WR-05 (D-03), `source.ref` allowlist pattern (D-04), `name` maxLength 64 (D-05), differentiated timeout bounds (D-06), `owner_uid` full-uid_t range (D-07), `annotations` escape valve on 7 subschemas (D-08), optional `metadata.license`/`metadata.maintainer` (D-09), self-validation gate in pytest (D-10), markdown spec kept in sync (D-11).
**Requirements**: D-01, D-02, D-03, D-04, D-05, D-06, D-07, D-08, D-09, D-10, D-11
**Depends on:** Phase 17
**Plans:** 3/3 plans complete

Plans:
- [x] 18-01-PLAN.md — Self-validation gate (D-10): TDD RED test scaffolding [Wave 1]
- [x] 18-02-PLAN.md — Schema refactor (D-01..D-09): $defs, bounds, annotations, license/maintainer [Wave 2]
- [x] 18-03-PLAN.md — Narrative spec update (D-11): RECIPE-SCHEMA.md v0.1.1 [Wave 3]

### Phase 19: API Foundation (FastAPI)

**Goal:** Ship `api_server/` — a FastAPI service wrapping `tools/run_recipe.py` as the public HTTP API. Postgres-backed runs + agent_instances + idempotency_keys + rate_limit_counters + users from day 1 (per the "no mocks, no stubs" directive). Endpoints: `GET /healthz` (thin) + `GET /readyz` (rich) + `GET /v1/schemas` + `GET /v1/schemas/{version}` + `GET /v1/recipes` + `GET /v1/recipes/{name}` + `POST /v1/lint` (256 KiB cap) + `POST /v1/runs` (load-bearing; per-image-tag asyncio.Lock + global Semaphore concurrency primitives) + `GET /v1/runs/{id}`. BYOK via `Authorization: Bearer <provider-key>` — never persisted, never logged. Stripe-shape error envelope + ULID run_id + allowlist-based log redaction + `_redact_api_key` widening. Full Hetzner deployment with Caddy-managed TLS at `api.agentplayground.dev`.
**Requirements**: Bound to CONTEXT.md §Success Criteria SC-01..SC-13 (REQUIREMENTS.md has no phase_req_ids for Phase 19 — the CONTEXT.md list is the effective requirement set).
**Depends on:** Phase 18 (schema v0.1.1 maturity)
**Plans:** 7/7 plans complete
Plans:
- [x] 19-01-PLAN.md — Alembic baseline migration + api_server/ package skeleton + pyproject.toml + migration test [Wave 1]
- [x] 19-02-PLAN.md — FastAPI skeleton + lifespan + /healthz + /readyz + conftest fixtures + docs gating [Wave 2]
- [x] 19-03-PLAN.md — Recipe + schema + lint endpoints + per-call YAML + Pydantic models + error envelope [Wave 3]
- [x] 19-04-PLAN.md — POST /v1/runs + GET /v1/runs/{id} + runner_bridge (Pattern 2) + run_store (asyncpg) [Wave 3]
- [x] 19-05-PLAN.md — Rate limit middleware (advisory lock) + idempotency middleware (body-hash) [Wave 3]
- [x] 19-06-PLAN.md — Log redaction middleware + correlation-id + widen tools/run_recipe.py::_redact_api_key [Wave 1]
- [x] 19-07-PLAN.md — Hetzner deployment: Dockerfile + docker-compose.prod + Caddyfile + deploy.sh + smoke-api.sh [Wave 4]

### Phase 20: Frontend Alicerce

**Goal:** Replace the v0 mock `/playground` page with a real API-driven conversational form that round-trips a run end-to-end (pick recipe from `GET /v1/recipes`, type model + BYOK + prompt, click Deploy, see verdict card from `POST /v1/runs`). Delete `<AgentConfigurator>` and all mock client-side catalogs. Desktop-first; mobile polish deferred. No auth, no dashboard, no streaming — those are later phases. **Gates the Phase 19 Hetzner deploy**: deploy is BLOCKED until Phase 20 SC-11 passes.
**Requirements**: Bound to `20-CONTEXT.md` §Success Criteria SC-01..SC-11 + D-01..D-14 decisions.
**Depends on:** Phase 19
**Plans:** 5 plans

Plans:
- [x] 20-01-PLAN.md — Extend frontend/lib/api.ts (ApiError.headers + apiPost headers param) + new frontend/lib/api-types.ts (TS mirrors + UiError union + parseApiError + useRetryCountdown) [Wave 1]
- [x] 20-02-PLAN.md — Delete mock tree (agent-configurator + 4 import-only peers + playground-section) and neutralize /playground + homepage references [Wave 1]
- [x] 20-03-PLAN.md — New <PlaygroundForm> client component: recipe fetch, 4 fields, BYOK hardening, 6 error states [Wave 2]
- [x] 20-04-PLAN.md — New <RunResultCard> pure display: verdict badge map (11 categories), metadata grid, stderr accordion [Wave 2]
- [ ] 20-05-PLAN.md — Mount <PlaygroundForm> on /playground + manual SC-11 smoke gate + STATE.md update (unblocks Hetzner deploy) [Wave 3]

### Phase 21: SSE Streaming Upgrade

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 20
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 21 to break down)

### Phase 22c: OAuth (Google + GitHub) — Multi-tenant auth substrate

**Inserted 2026-04-19** as the unblocker for every `/dashboard/*` page + ~8 backend endpoints (per `.planning/audit/ACTION-LIST.md` line 108). SPEC locks 8 requirements + CONTEXT adds 7 amendments + 21+ locked implementation decisions.

**Goal:** Replace the `setTimeout`-theater login + the `ANONYMOUS_USER_ID` placeholder with a real Google AND GitHub (AMD-01) OAuth flow that mints a server-side session and resolves a real `user_id` on every API request. Scope: backend auth routes + session middleware + `/v1/users/me` + `/v1/auth/logout` + `sessions` table + `users` column expansion, full data purge migration (alembic 006 TRUNCATEs all 8 tables per AMD-04), frontend login rewrite + dashboard layout rewrite + sign-out wire-up + dead-theater cleanup (/signup + /forgot-password redirects). Refresh-token storage DROPPED (AMD-02); identity-only flow.
**Requirements**: Bound to `22c-SPEC.md` R1..R8 + `22c-CONTEXT.md` AMD-01..AMD-07.
**Depends on:** Phase 19 (FastAPI substrate); does NOT depend on Phase 20 / 21 — parallel track.
**Plans:** 9 plans across 5 waves

Plans:
- [x] 22c-01-PLAN.md — Wave 0 spikes (respx × authlib interop + TRUNCATE CASCADE 7-table FK graph; Mode B since 005 ships in 22c-02) + deps + test dir scaffolds [Wave 0 GATE CLEARED 2026-04-19; see 22c-01-SUMMARY.md]
- [x] 22c-02-PLAN.md — Alembic migration 005: sessions table + users.{sub,avatar_url,last_login_at} + UNIQUE(provider,sub) partial index [Wave 1 COMPLETE 2026-04-19; applied live to deploy-postgres-1; see 22c-02-SUMMARY.md]
- [x] 22c-03-PLAN.md — config.py Pydantic fields + auth/oauth.py authlib registry (google + github) + upsert_user + mint_session + deploy/.env.prod.example update [Wave 1 COMPLETE 2026-04-19; see 22c-03-SUMMARY.md]
- [x] 22c-04-PLAN.md — SessionMiddleware (ap_session cookie → request.state.user_id) + last_seen throttle + log_redact docstring + 10 middleware tests (6 R3 + 2 throttle + 2 cookie-redact) [Wave 2 COMPLETE 2026-04-20; see 22c-04-SUMMARY.md]
- [x] 22c-05-PLAN.md — auth/deps.py require_user + routes/auth.py (5 endpoints) + routes/users.py + main.py middleware stack + 20 integration tests (13+ plan-mandated + 7 extras covering WARNING-3 regression trap) [Wave 3 COMPLETE 2026-04-20; see 22c-05-SUMMARY.md]
- [x] 22c-06-PLAN.md — Alembic migration 006 destructive purge + ANONYMOUS_USER_ID deletion + 4 route files migrated + idempotency/rate_limit user_id wiring [Wave 4 backend-half COMPLETE 2026-04-20; applied live to deploy-postgres-1 (alembic_version=006_purge_anonymous, all 8 tables COUNT=0); agent_status PATTERNS gap closed per D-22c-AUTH-03; 9 test files migrated to TEST_USER_ID + 8 regression fixes absorbed; see 22c-06-SUMMARY.md]
- [x] 22c-07-PLAN.md — Frontend useUser hook + rewrite login/page.tsx + dashboard/layout.tsx + navbar.tsx real logout button [Wave 4 frontend-half COMPLETE 2026-04-20; setTimeout + Alex Chen hardcode deleted; Google/GitHub buttons do top-level nav to /api/v1/auth/{google,github}; ?error=<code> → sonner toast (access_denied/state_mismatch/oauth_failed exact-string switch per T-22c-25); email/password form disabled w/ caption; logout calls POST /v1/auth/logout then router.push; zero deviations from plan; see 22c-07-SUMMARY.md]
- [x] 22c-08-PLAN.md — Frontend proxy.ts (Next 16 rename per AMD-06) + next.config.mjs redirects(/signup → /login, /forgot-password → /login) + delete stale middleware.ts [Wave 4 COMPLETE 2026-04-20; proxy.ts matcher=/dashboard/:path* + ap_session cookie-presence gate verified live (307→/login no-cookie, 200 with-cookie, subpath matcher working); stale middleware.ts + orphaned x-ap-has-session header retired; next.config.mjs redirects() entries verified live (/signup + /forgot-password = HTTP 307 loc:/login); zero deviations from plan; see 22c-08-SUMMARY.md]
- [x] 22c-09-PLAN.md — Cross-user isolation integration test + test/22c-manual-smoke.md + manual smoke gate (D-22c-TEST-02) + STATE.md close-out [Wave 5 COMPLETE 2026-04-28; cross-user isolation 1/1 PASS in 4.60s with R8 8-table COUNT=0 pre-assertion; 4 browser OAuth scenarios PASS confirmed by human operator (Google happy path, GitHub happy path, access_denied, logout invalidation); 3 plan gaps surfaced + fixed inline (4f7d8b0 Dockerfile authlib+itsdangerous, fdf3924 httpx runtime promotion, f9a7df9 OAuth callback frontend host); 3 UX findings deferred to 22c.1 per AMD-02 scope discipline; see 22c-09-SUMMARY.md]

---
*Roadmap created: 2026-04-11*
*Phase 1 planned: 2026-04-13*
*Phase 1 complete: 2026-04-14*
*Phase 2 reshaped + Phase 7.5 inserted: 2026-04-14 (see `.planning/phases/02-container-sandbox-spine/02-CONTEXT.md` `<domain>` for rationale)*
*Phase 2 plans split (W1 fix): Plan 04 split into 04 (foundations) + 05 (API surface); existing Plan 05 renumbered to 06 — 2026-04-14*
*Phase 20 planned: 2026-04-17 — 5 plans in 3 waves; D-14 testing decision DEFERRED to Phase 20.1*
*Phase 22c planned: 2026-04-19 — 9 plans in 5 waves (Wave 0 mandatory spike gate); inserted post-pivot, not in 1–8 numbered list*

### Phase 22c.3: In-App Chat Channel — `inapp` transport (Flutter foundation)

**Inserted 2026-04-29; planning complete 2026-04-30 (after 7 plan-checker iterations).** Adds an `inapp` channel transport so logged-in users can send chat messages to a running agent + receive replies via the API. Foundation for the Flutter native app (Phase 23) and a future web `/dashboard/agents/:id` chat surface.

**Goal (Round-3 final, 2026-04-30):** Ship the inapp channel: new `inapp_messages` table (D-27), new background dispatcher + reaper + outbox-pump asyncio tasks attached at lifespan, SSE outbound stream via sse-starlette with Last-Event-Id replay (D-25/D-26), Redis Pub/Sub fan-out (D-08/D-09), 3 HTTP routes (POST /v1/agents/:id/messages D-07/D-29 fast-ack 202; GET /v1/agents/:id/messages/stream; DELETE /v1/agents/:id/messages D-43/D-44), and `channels.inapp` blocks added to **5 recipes via NATIVE chat HTTP — no sidecars, no MSV deviation**: hermes/nanobot/openclaw native /v1/chat/completions (contract `openai_compat`); nullclaw native /a2a Google A2A JSON-RPC 2.0 (contract `a2a_jsonrpc`); zeroclaw native /webhook (contract `zeroclaw_native` — NEW recipe substituting picoclaw per user direction). **picoclaw DEFERRED** out of this phase's scope; `recipes/picoclaw.yaml` UNTOUCHED. Single transport verb `http_localhost` with three contract adapters in dispatcher (~50 LOC each) per user directive "5/5 must work" (RESEARCH Rounds 1/2/3). Per-message size cap none (D-41). Rate limit 4/min per (user, agent) (D-42). Bot timeout 600s (D-40, no auto-retry — terminal failures direct to `'failed'`). Persist-before-action discipline (D-28) honors no-mocks/no-stubs across crash recovery.

**Requirements**: Bound to `22c.3-CONTEXT.md` D-01..D-46 (the 46 D-decisions ARE the phase requirements per CONTEXT.md line 1133; no separate REQ-XX IDs).
**Depends on:** Phase 22c (OAuth — `ap_session` cookie + `require_user` are the auth boundary for D-18/D-19).
**Plans:** 15 plans across 6 waves

Plans:
- [x] 22c.3-01-PLAN.md — Wave 0 spike re-validation against current main + A5 nanobot-auth resolution [Wave 0 GATE] — SHIPPED 2026-04-30 (commits f32df66, 55138e7, f0341e7); 5/5 PASS (hermes/nanobot/openclaw via openai_compat; nullclaw via native a2a_jsonrpc; zeroclaw via zeroclaw_native — Round-3 substitution for picoclaw); WAVE-0-CLOSED gate emitted in spikes/wave-0-summary.md
- [x] 22c.3-02-PLAN.md — Alembic migration 007: `inapp_messages` table + `agent_events.published` + `agent_containers.inapp_auth_token` + extend `ck_agent_events_kind` (3 new kinds); applied live to deploy-postgres-1 [Wave 1] — SHIPPED 2026-04-30 (commits b4bef12, b9b5004); 2/2 testcontainers integration tests PASS; deploy-postgres-1 alembic_version transitioned 006 → 007; full-DDL + reversible-round-trip coverage
- [x] 22c.3-03-PLAN.md — `sse-starlette>=3.4,<4` + `redis>=5.2,<7` deps; `redis:7-alpine` service in docker-compose; `AP_REDIS_URL` env + Settings.redis_url field [Wave 1] — SHIPPED 2026-04-30 (commits 9e85e64, ede14f5, 8721e98, e57cac7); deps baked into deploy-api_server image sha 4675c28f55b5; live deploy-redis-1 healthy on compose bridge net; pubsub round-trip verified end-to-end from inside api_server container; one Rule 1 fix inline (--protected-mode no — compose bridge IS the security boundary per D-08, not the per-process redis flag)
- [x] 22c.3-04-PLAN.md — Extend `models/events.py` (3 new payloads + VALID_KINDS); new `services/inapp_messages_store.py` (10 CRUD functions; FOR UPDATE SKIP LOCKED) [Wave 2] — SHIPPED 2026-04-30 (commits be839c6, ba1e0bd, baab35c, c2ff352); 35 tests PASS (20 unit + 15 integration testcontainer PG); SKIP LOCKED concurrency proven via asyncio.gather of 2 independent connections; 2 Rule deviations auto-fixed (Rule-1 test_valid_kinds_exact subset relaxation; Rule-2 fetch_by_id added per truths block)
- [x] 22c.3-05-PLAN.md — `services/inapp_dispatcher.py` (3-way contract switch openai_compat / a2a_jsonrpc / zeroclaw_native; persist-before-action; D-40 no-auto-retry; readiness gate D-37/D-38) + `services/inapp_recipe_index.py` (lazy LRU + 60s container-IP cache) [Wave 2] — SHIPPED 2026-04-30 (commits a9a68bb, 00bb1ca); 20 tests PASS (10 unit InappRecipeIndex + 10 integration testcontainer PG dispatcher with respx-mocked bot endpoints — 3 contract happy paths + 5 failure paths + D-40 no-retry invariant); zeroclaw test asserts X-Session-Id sent on the wire; consumes Plan 04 store API verbatim (zero inlined SQL); 2 Rule-1 deviations auto-fixed inline (LISTEN/NOTIFY tokens removed from docstring; test monkey-patch switched from cache-dict to method override)
- [x] 22c.3-06-PLAN.md — `services/inapp_reaper.py` (15s tick; D-40 stuck-row sweep direct to failed) [Wave 2] — SHIPPED 2026-04-30 (commits d9444dc, 79279e4); 6 testcontainer-PG integration tests PASS in 3.00s (happy-path 12min stuck → failed + agent_events INSERT, fresh 5min skip, pending/done skip, D-40 no-auto-retry across 5 stuck rows attempts=1..5, SKIP LOCKED multi-replica safety, stop_event responsive cancel); consumes Plan 04 store API verbatim (ims.fetch_stuck_forwarded + ims.mark_failed); atomic mark_failed + insert_agent_event in same tx; agent_events.published=false (column default); 2 Rule-1 deviations auto-fixed inline (insert_agent_event published-kwarg removed since signature has no such param; type annotations dropped on module constants to satisfy plan's literal grep gate)
- [x] 22c.3-07-PLAN.md — `services/inapp_outbox.py` (100ms tick; Pitfall 3 strategy 2 batch-rollback; D-35 abandon-after-1h) [Wave 2] — SHIPPED 2026-04-30 (commits d00e459, 59445ce, 65a4989); 8 testcontainer-PG + testcontainer-Redis integration tests PASS in 9.77s (happy path, skip-published, D-35 abandon-after-1h, Pitfall 3 strategy 2 Redis-error rollback, D-32 SKIP LOCKED via asyncio.gather, D-09 per-agent fan-out, stop_event cancel <1s, D-34 envelope shape); first transactional-outbox pattern in api_server (PATTERNS.md GREENFIELD); JOIN agent_containers ON c.id = e.agent_container_id derives channel name; 1 Rule-3 deviation auto-fixed inline (testcontainers[redis] requires redis>=7; runtime pin bumped <7 → <8 — redis 7.x asyncio API source-compatible with 5.x); Wave 2 COMPLETE
- [ ] 22c.3-08-PLAN.md — `routes/agent_messages.py` (POST + DELETE + SSE GET); idempotency middleware extension; rate-limit `chat:{user}:{agent}` 4/min [Wave 3]
- [ ] 22c.3-09-PLAN.md — `main.py` lifespan: 3 background tasks attached + Redis client + httpx.AsyncClient + restart sweep (D-31); image rebuild + live deploy [Wave 3]
- [ ] 22c.3-10-PLAN.md — hermes recipe channels.inapp (native env-flag activation, port 8642) [Wave 4]
- [ ] 22c.3-11-PLAN.md — nanobot recipe channels.inapp (`nanobot serve` mode, port 8900, --timeout 600) [Wave 4]
- [ ] 22c.3-12-PLAN.md — openclaw recipe channels.inapp (config-flag chatCompletions.enabled=true on gateway port 18789; MSV pattern) [Wave 4]
- [ ] 22c.3-13-PLAN.md — **NEW recipes/zeroclaw.yaml** (substitutes picoclaw per user direction 2026-04-30; image_pull `ghcr.io/zeroclaw-labs/zeroclaw:latest` distroless ~50 MB Rust 30,845 ★; channels.inapp contract=zeroclaw_native, native /webhook on :42617; built-in X-Idempotency-Key + X-Session-Id) [Wave 4]
- [ ] 22c.3-14-PLAN.md — nullclaw recipe channels.inapp **via native Google A2A** (contract=a2a_jsonrpc, endpoint=/a2a; persistent_argv writes config.json with `a2a.enabled=true` + `gateway.require_pairing=false` then `nullclaw gateway`; NO sidecar — Round-3 supersession) [Wave 4]
- [ ] 22c.3-15-PLAN.md — Wave 5 e2e gate: 5/5 recipes round-trip a real chat message via SSE + 3 cross-cutting D-criteria checks; agent_lifecycle.start_persistent extension to mint inapp_auth_token; human-verify checkpoint [Wave 5 GATE]

**UI hint:** no (API-only; Flutter Phase 23 + future web chat consume the new endpoints).

*Phase 22c.3 planned: 2026-04-29 — 15 plans in 6 waves (Wave 0 mandatory spike re-validation gate; Wave 5 mandatory e2e gate); inserted post-pivot.*
