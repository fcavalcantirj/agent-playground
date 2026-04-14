# Phase 2: Container Sandbox Spine - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

**Reshaped from the original ROADMAP scope.** The original Phase 2 bundled two unrelated jobs: (a) building the container substrate every recipe inherits from, and (b) landing the full host hardening spine (custom seccomp, egress allowlist, Falco/Tetragon, escape-test CI, gVisor install) against threats that don't enter the system until Phase 8.

This phase delivers **(a) only**, plus the **minimum viable API-driven agent-start loop** that proves the project hypothesis: *any agent × any model × any user, in one click*. The hardening spine (b) is deferred to a new phase landing immediately before Phase 8, against a known-working substrate.

**Concretely, this phase ships:**

1. **`ap-base` Docker image** — tini PID 1 + tmux (`chat` + `shell` windows) + ttyd on loopback + runtime deps (git, curl, jq, ca-certs, gosu) + entrypoint-shim privilege-drop pattern ported from MSV's proven `infra/picoclaw/`.
2. **Sandbox knobs wired into `pkg/docker/runner.go`** — `SeccompProfile`, `ReadOnlyRootfs`, `Tmpfs`, `CapDrop`, `NoNewPrivs`, `PidsLimit`, `Memory`, `CPUs`, `Runtime`, `NetworkMode` fields on `RunOptions` → Docker Engine SDK `HostConfig`. Safe defaults applied at call sites. **No custom seccomp JSON authored yet.**
3. **Deterministic naming** `playground-<user_uuid>-<session_uuid>` — validator + helper in runner.go so reconciliation (Phase 5) can derive container names from DB rows alone (SBX-09).
4. **Two curated agent recipes, thinly built on `ap-base`:**
   - **picoclaw** (Go CLI, `cli-stdio` → `stdin_fifo` chat path) — simplest agent, fastest demo, pinned to an immutable commit SHA.
   - **Hermes** (Python 3.11, Nous Research, MIT, TUI-first, six execution backends, multi-channel daemon) — the architecturally hardest agent. If it fits, the pattern generalizes. Pinned to a commit SHA.
5. **Minimal non-durable session API stubs** (pulled forward from Phase 5's scope, explicitly smoke-test scope):
   - `POST /api/sessions` → validate, create session row, direct runner.go call, return id. **No Temporal workflow.** Phase 5 replaces internals with Temporal; HTTP contract stays stable.
   - `POST /api/sessions/:id/message` → docker exec write to chat FIFO, read from output FIFO, return response. Synchronous for v1.
   - `DELETE /api/sessions/:id` → runner.Stop + Remove + DB state update.
6. **Dev-mode BYOK** from a server env var (`AP_DEV_BYOK_KEY`). Phase 3 replaces with the encrypted pgcrypto vault + tmpfs `/run/secrets/*_key` injection pattern. The file-based injection path is what Phase 2 wires in — it's Phase 3's job to populate the file from encrypted storage instead of a dev env var.
7. **End-to-end smoke test** via real curl invocations: start picoclaw → exchange one message with a real Anthropic model → stop. Repeat for Hermes. Proves API-driven start without Telegram — the hypothesis proof.

**Explicitly deferred** to a new hardening phase (call it Phase 7.5 or 2.5 landing right before Phase 8):
- Custom seccomp profile JSON authoring
- `ap-net` bridge + iptables / DOCKER-USER egress allowlist
- Falco or Tetragon deployment + rule set
- Escape-test CI harness (mount, unshare, docker.sock probe, evil egress)
- gVisor `runsc` install + per-recipe runtime selection (Spike 4 still pending)
- Anomaly alerting sink + dashboards

**Why deferral doesn't lose work:** the sandbox knobs wired into runner.go in step 2 are exactly what the deferred hardening phase populates. Seccomp profile path, network name, runtime name — all plumbed through from Phase 2; the deferred phase fills in the JSON files, iptables rules, and Falco configs that the knobs reference. Zero rewrites.

**Mission context:** Every later phase depends on this substrate. Phase 4's recipe loader FROMs `ap-base`. Phase 5's durable session lifecycle replaces the stub API internals. Phase 8's generic Claude-Code bootstrap extends the entrypoint-shim pattern with gVisor. None of those are possible until a real agent runs in a box and the API proves it.

**Roadmap impact:** `.planning/ROADMAP.md` Phase 2 description + success criteria should be updated to reflect this reshape before `/gsd-plan-phase 2` runs. The deferred-hardening phase needs to be inserted (probably after Phase 7 or as a new Phase 7.5). Flag for the user to run `/gsd-add-phase` or edit the roadmap directly after this context is committed.

</domain>

<decisions>
## Implementation Decisions

### Scope reshape (hypothesis-forward)
- **D-01:** Phase 2 is a vertical slice proving API-driven agent start, not a pure sandbox-hardening phase. It legitimately crosses into Phase 3 (dev BYOK), Phase 4 (first two recipes), and Phase 5 (minimal session API) territory because the hypothesis proof requires all of them together.
- **D-02:** The full hardening spine (custom seccomp, egress allowlist, Falco/Tetragon, escape-test CI, gVisor install) moves to a new phase landing right before Phase 8. Rationale: no untrusted code enters the system until Phase 8; hardening against a known-working substrate is cheaper than hardening against speculation.
- **D-03:** ROADMAP.md Phase 2 description + success criteria + phase list must be updated to reflect this reshape before planning runs. Done via `/gsd-add-phase` or direct edit after this CONTEXT commits.

### `ap-base` image architecture
- **D-04:** **Base OS:** Debian slim (`debian:trixie-slim` or `bookworm-slim`), not Alpine. Reason: Hermes is Python 3.11 with `uv pip install -e ".[all,dev]"` — Alpine's musl breaks many Python wheels and drags compilation pain. MSV's `infra/picoclaw/Dockerfile` already uses `node:22-slim` (Debian-based) for the same reason. Pick one base OS to minimize image-layer churn across recipes.
- **D-05:** **PID 1 = tini**, always. Agent is a supervised child. Matches CLAUDE.md's "What NOT to Use" table.
- **D-06:** **tmux in `ap-base` from day 1** with two windows: `chat` (FIFO-attached agent) and `shell` (plain bash for ttyd). Cannot defer — Hermes TUI needs a real PTY, and the `shell` window is the ttyd surface both curated and bootstrap agents need.
- **D-07:** **ttyd in `ap-base` from day 1**, bound to `127.0.0.1:<allocated>`. Phase 5 adds the Go WS reverse proxy in front of it; Phase 2 verifies ttyd is spawnable and responds on loopback.
- **D-08:** **Non-root user + gosu privilege-drop entrypoint**, ported from MSV's `infra/picoclaw/entrypoint.sh` pattern. Container stays root only long enough for the entrypoint to fix permissions, then drops to an unprivileged UID. User namespace remapping (already enabled in Phase 1's `install-docker.sh`) remaps that UID further at the kernel level.
- **D-09:** **Entrypoint-shim pattern for config + secrets:** the entrypoint reads `/run/secrets/*_key` tmpfs files (Phase 3's injection target), writes any per-agent config files the recipe needs (e.g., Hermes's `~/.hermes/cli-config.yaml` to disable channel daemons), exports keys into the agent process environment only (never PID 1), and execs the recipe's `LAUNCH_CMD` inside the tmux `chat` window. This one pattern has to serve picoclaw, Hermes, and the unknown N-next agents — the user's "this list will grow" signal.
- **D-10:** **Runtime deps in `ap-base`:** `tini`, `tmux`, `ttyd`, `git`, `curl`, `jq`, `ca-certificates`, `gosu`, `bash`. Recipe overlays add language runtimes (Node.js for OpenClaw, Python 3.11 + uv for Hermes, pinned-SHA Go binary for picoclaw).
- **D-11:** **Image tagging:** semver tags `ap-base:v0.1.0` in Phase 2, with git SHA as secondary tag. Recipe overlays tag `ap-picoclaw:v0.1.0-<sha>`, `ap-hermes:v0.1.0-<sha>`. No `:latest`, ever (REC-07 will enforce in Phase 4; we pre-enforce here).

### Sandbox options in `runner.go`
- **D-12:** Add fields to `RunOptions`: `SeccompProfile string` (path to JSON; empty = Docker default), `ReadOnlyRootfs bool`, `Tmpfs map[string]string` (target → options), `CapDrop []string`, `CapAdd []string`, `NoNewPrivs bool`, `Runtime string` (empty = runc), `NetworkMode string`. Plumb all the way through to `container.HostConfig`. Safe defaults applied by the session-start code path (not by runner.go itself — runner stays transport-layer).
- **D-13:** Default sandbox posture applied by the session-start handler (not hardcoded in runner.go): `CapDrop = ["ALL"]`, `NoNewPrivs = true`, `ReadOnlyRootfs = true`, `Tmpfs = {"/tmp": "rw,noexec,nosuid,size=128m", "/run": "rw,noexec,nosuid,size=16m"}`, `PidsLimit = 256`, `Memory = 1GB`, `CPUs = 1e9`, `Runtime = ""` (runc), `NetworkMode = "bridge"` (default Docker bridge; Phase 7.5 swaps for `ap-net`). These defaults apply to both picoclaw and Hermes for the smoke test.
- **D-14:** **No `ap-net` custom bridge in Phase 2.** Use the default Docker bridge with a wide-open egress. Phase 7.5 replaces with a locked-down `ap-net` + iptables allowlist. The `NetworkMode` field in RunOptions is the hook that phase populates.
- **D-15:** **No custom seccomp JSON in Phase 2.** Use Docker's default seccomp profile (it already blocks most of the dangerous syscalls). Phase 7.5 authors the custom profile that additionally drops `mount/unshare/setns/keyctl/bpf/ptrace`. The `SeccompProfile` field is the hook.

### Recipe handling (minimal, no schema yet)
- **D-16:** **No `ap.recipe/v1` YAML schema in Phase 2** — that's Phase 4. Phase 2 ships two hardcoded Go structs `recipes.Picoclaw` and `recipes.Hermes` in `internal/recipes/` with the fields the session-start handler needs: image ref, launch command, env overrides, chat_io mode, required secret slots. Phase 4 replaces the hardcoded map with a YAML-backed loader — the struct shape is the schema.
- **D-17:** **Recipe images are pre-built**, not built at session-start time. `make build-recipes` builds `ap-base`, `ap-picoclaw`, `ap-hermes` into the local Docker image cache. `POST /api/sessions` does `docker run`, never `docker build`. First-start latency stays under the SES-01 10s budget.
- **D-18:** **Upstream pinning:** picoclaw pinned to a specific commit SHA from `/Users/fcavalcanti/dev/picoclaw` (Phase 2 planning picks it); Hermes pinned to a specific commit SHA from `github.com/NousResearch/hermes-agent`. Both Dockerfiles use `git clone ... && git checkout <sha>`, never `main` or release channels.

### Hermes architecture accommodation
- **D-19:** **Hermes is dockerized in Phase 2 despite its complexity** because it is the architecturally hardest agent and validates the substrate against TUI, multi-backend, and multi-channel daemon patterns. Source of truth: `github.com/NousResearch/hermes-agent`, MIT license, Python 3.11 baseline, `uv pip install -e ".[all,dev]"`, config dir `~/.hermes/`, `cli-config.yaml.example` in repo root as a template.
- **D-20:** **Non-interactive bootstrap:** Hermes normally expects an interactive `hermes setup` wizard. Recipe Dockerfile pre-populates `~/.hermes/cli-config.yaml` during build from a committed template in `agents/hermes/cli-config.yaml`. First boot must not prompt.
- **D-21:** **Disable multi-channel daemons:** Hermes's built-in Telegram/Discord/Slack/WhatsApp/Signal/Email/Matrix/Mattermost gateway daemons are disabled via the pre-populated `cli-config.yaml` (the exact YAML key to set is a Phase 2 planning research item — study `hermes-agent/cli-config.yaml.example` to find it). Credentials for those channels are never injected; without credentials the daemons wouldn't start anyway, but explicit disable is belt-and-suspenders.
- **D-22:** **Force local execution backend:** Hermes supports `local / Docker / SSH / Daytona / Singularity / Modal` backends. The non-`local` options would try to spawn containers-in-containers from inside our container — CRIT-1 territory. Recipe `cli-config.yaml` forces `backend: local`. Planning must verify the exact YAML key.
- **D-23:** **Chat bridge mechanism — planning research item.** Hermes is TUI-first, which the `stdin_fifo` bridge that works for picoclaw cannot drive (readline + slash-command autocomplete + streaming tool output need a real PTY). Three candidate bridges for Hermes, decision deferred to Phase 2 planning research (spawn `gsd-phase-researcher`):
  - **(a) PTY via tmux `chat` window** — send keystrokes, scrape screen buffer, state-machine the prompt detection. Most general, hardest to build.
  - **(b) MCP stdio/HTTP** — Hermes ships `mcp_serve.py`, meaning it can expose itself over Model Context Protocol. If the MCP interface supports "send a message, get a response" semantics, this is the cleanest bridge. Verify in planning.
  - **(c) `hermes` CLI invoked per-message in non-interactive mode** — `docker exec hermes --message "hello"` style if such a flag exists. Simplest if supported. Verify in planning.
  - Recommended fallback if research is inconclusive: **(c) if the CLI has a `--message` flag, else (a).** Do NOT ship (b) until MCP semantics are verified.
- **D-24:** **Persistent memory path:** Hermes stores memory under `~/.hermes/` (FTS5 SQLite). Phase 2 runs Hermes with a tmpfs `~/.hermes/` — memory is ephemeral, destroyed on session stop. Paid-tier persistent memory is Phase 7 (`ap-vol-<user>` volume mounted at `~/.hermes/`).
- **D-25:** **"This list will grow":** the recipe struct + entrypoint-shim + runner.go sandbox-knob design must accept a new agent as "add a Dockerfile + add a struct literal" — no code changes to `ap-base`, `runner.go`, or the session API handlers. Validated by the fact that adding Hermes to Phase 2 alongside picoclaw works the same way.

### Session API stubs (non-durable, Phase 5 upgrades)
- **D-26:** `sessions` table schema (add in a new migration `0002_sessions.sql`): `id uuid PK, user_id uuid FK, recipe_name text, model_provider text, model_id text, container_id text NULLABLE, status text DEFAULT 'pending', created_at timestamptz, updated_at timestamptz`. No `expires_at`, no `billing_mode`, no `tier` yet — Phase 5/6/7 add those. Schema-forwards-compatible.
- **D-27:** **No Temporal workflow in Phase 2.** Session spawn/destroy are direct runner.go calls from the HTTP handler. Phase 5 wraps them in `SessionSpawn` / `SessionDestroy` workflows on the `session` task queue (workflows already stubbed in Phase 1's `internal/temporal/`). HTTP contract stays the same.
- **D-28:** **No reconciliation loop, no idle reaper, no heartbeat, no chat WS reconnect, no WS at all in Phase 2.** All deferred to Phase 5. Chat is synchronous `POST /api/sessions/:id/message` that blocks until the agent responds (or times out).
- **D-29:** **Two-chat-surfaces invariant (CHT-05 / TRM-04)** not enforced in Phase 2. Phase 5 enforces via Redis key ownership. Phase 2's synchronous API doesn't need it because there's no persistent connection to kick.
- **D-30:** **One-active-session invariant (SES-02)** enforced in Phase 2 via the Postgres partial unique index on `(user_id) WHERE status IN ('provisioning','ready','running')` — already-shaped in Phase 1's schema. The Redis `SETNX` second layer is Phase 5. Phase 2 gets the DB layer for free.
- **D-31:** **Dev BYOK injection:** server reads `AP_DEV_BYOK_KEY` from its own env and writes it to a tmpfs file at `/run/secrets/anthropic_key` inside the container before start. Phase 3 replaces with the encrypted vault + per-provider key lookup. The file-based injection mechanism is what Phase 2 wires; Phase 3 populates it from a different source.

### Smoke test — the hypothesis proof
- **D-32:** `make smoke-test` (or equivalent Go test + shell runner) performs:
  1. `docker pull` or `make build-recipes` — ensure images exist
  2. Start Go API with `AP_DEV_BYOK_KEY=sk-ant-...`
  3. `curl -X POST /api/sessions -d '{"recipe":"picoclaw","model_provider":"anthropic","model_id":"claude-sonnet-..."}'` → assert 201 + session id
  4. `curl -X POST /api/sessions/<id>/message -d '{"text":"say hi in 5 words"}'` → assert 200 + response contains text from a real model call
  5. `curl -X DELETE /api/sessions/<id>` → assert 200
  6. Repeat steps 3-5 for `recipe:"hermes"`
  7. Assert no dangling `playground-*` containers remain after the test
- **D-33:** Smoke test uses real Anthropic BYOK via `AP_DEV_BYOK_KEY` env. Test is gated on `AP_DEV_BYOK_KEY` being set — skips cleanly in CI if absent. Local dev workflow: set env, `make smoke-test`, see green.
- **D-34:** **Hypothesis signoff:** the phase is complete when the smoke test passes for both agents AND a human manually sees a response appear in the terminal from each one. No UI yet — the curl output is the demo. Phase 5 adds the browser UX.

### Claude's Discretion
- Exact Dockerfile layering (single-stage vs multi-stage, which base pins)
- Naming of internal Go packages (`internal/recipes/`, `internal/sessions/`, etc.)
- Default resource limits (1GB / 1 vCPU / 256 PIDs) can be revised by planning if Hermes is provably starving
- Error response shapes for the new HTTP endpoints (match Phase 1's existing JSON envelope)
- Whether `make build-recipes` lives at repo root or in `agents/`
- Log lines, test scaffolding, helper function names
- Exact commit SHAs to pin picoclaw and Hermes to (planning picks latest stable at time of plan writing)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project + process
- `.planning/PROJECT.md` — Core value, constraints, key decisions
- `.planning/REQUIREMENTS.md` §Container Sandbox (SBX) — SBX-01..SBX-09 are the source of truth; reshape in this CONTEXT.md redistributes which SBX land in Phase 2 vs the deferred hardening phase
- `.planning/ROADMAP.md` §Phase 2 — Original success criteria (being reshaped)
- `.planning/STATE.md` — Phase 1 outcomes, what's live in the repo today

### Phase 1 carry-forward
- `.planning/phases/01-foundations-spikes-temporal/1-CONTEXT.md` — Phase 1 decisions that still apply (repo layout, compose stack, dev-cookie auth stub)
- `.planning/phases/01-foundations-spikes-temporal/01-05-SUMMARY.md` — Temporal workers are live but Phase 2 does NOT use them (stub API is direct runner.go); Phase 5 picks them up
- `api/pkg/docker/runner.go` — the runner this phase extends with sandbox option fields
- `api/internal/middleware/auth.go` — dev-cookie auth that the new session endpoints sit behind
- `api/pkg/migrate/sql/` — location for the new `0002_sessions.sql` migration

### Spike results (Phase 1)
- `.planning/research/SPIKE-REPORT.md` §Spike 1 — OpenClaw + PicoClaw both honor `HTTPS_PROXY`; transparent proxy metering works (relevant to Phase 6, not Phase 2)
- `.planning/research/SPIKE-REPORT.md` §Spike 2 — `chat_io.mode` per agent: OpenClaw = `gateway-websocket`, PicoClaw = `cli-stdio` + per-channel adapters. Hermes NOT covered — Phase 2 planning must extend the spike
- `.planning/research/SPIKE-REPORT.md` §Spike 3 — tmux + named-pipe RTT p99 = 0.19 ms, 262× headroom. Chat FIFO path validated for picoclaw.
- `.planning/research/SPIKE-REPORT.md` §Spike 4 — gVisor feasibility **PENDING** — not a Phase 2 blocker under the reshape (gVisor moves to the deferred hardening phase); still a Phase 8 blocker

### Upstream proven pattern (MSV)
- `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/Dockerfile` — the battle-tested entrypoint + privilege-drop + OAuth-injection pattern to port into `ap-base`
- `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/entrypoint.sh` — the shim that runs as root, fixes perms, drops via gosu — port this
- `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/openclaw.json` — example of a pre-populated config file baked at build time — template for Hermes's `cli-config.yaml`
- `/Users/fcavalcanti/dev/meusecretariovirtual/infra/test-picoclaw-local.sh` — MSV's local smoke test; pattern to mirror for our `make smoke-test`
- `/Users/fcavalcanti/dev/meusecretariovirtual/infra/verify-picoclaw.sh` — MSV's post-start verification; pattern for our Phase 2 healthcheck

### Agent sources
- `/Users/fcavalcanti/dev/picoclaw/` — local copy of the picoclaw Go CLI; `cmd/picoclaw/internal/agent/command.go` has the cobra command definitions (Spike 2 cited lines 7-30); `pkg/utils/http_client.go` and `pkg/config/config.go` for proxy/base-URL behavior
- `github.com/NousResearch/hermes-agent` — Hermes source; `pyproject.toml` for Python 3.11 + `uv` install path; `cli-config.yaml.example` for the template to pre-populate; `scripts/install.sh` for the install recipe; `mcp_serve.py` worth investigating for the chat bridge decision
- `https://hermes-agent.nousresearch.com/` — marketing page with supported-platform list
- MSV's `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/Dockerfile` is NOT a picoclaw-Go CLI reference — it actually dockerizes the `openclaw@latest` npm package. Don't let the name collision mislead the Hermes/picoclaw authoring.

### Stack decisions
- `CLAUDE.md` §Technology Stack — version pins, library choices, anti-recommendations
- `CLAUDE.md` §Container Isolation Tiers — v1 = plain Docker with dropped caps + read-only + cgroup limits; Sysbox v1.5; gVisor v2. Phase 2 stays at v1.
- `CLAUDE.md` §Stack Patterns by Variant — BYOK vs platform-billed injection patterns
- `CLAUDE.md` §Web Terminal Stack — ttyd inside container + Go WS proxy pattern

### Pitfalls (direct relevance to this phase)
- `.planning/research/PITFALLS.md` §CRIT-1 — untrusted bootstrap execution; primary reason hardening is deferred but tmux/ttyd must still land now
- `.planning/research/PITFALLS.md` §CRIT-2 — BYOK env leak; justifies the tmpfs `/run/secrets/*_key` + entrypoint-shim injection pattern even in dev mode
- `.planning/research/PITFALLS.md` §CRIT-4 — cross-tenant kernel escape; userns-remap already active from Phase 1

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`api/pkg/docker/runner.go`** — 396 lines, Docker Engine SDK, already has `RunOptions` struct, input validation helpers (`validateContainerID`, `validateImageName`, `validateEnvVar`, `validateMountPath`). Phase 2 extends `RunOptions` with sandbox fields; validation helpers get new siblings for mount paths and network names.
- **`api/pkg/docker/runner_test.go`** — 49 unit tests + integration test using real Docker + `alpine:3.19`. Pattern to extend for new sandbox options and the new recipe images.
- **`api/internal/middleware/auth.go`** — `SessionProvider` interface + HMAC-SHA256 signed `ap_session` cookie. New `/api/sessions/*` endpoints sit behind this middleware.
- **`api/internal/server/server.go`** — `server.New(cfg, logger, checker, opts ...Option)` functional options pattern. Phase 2 likely adds a `WithSessionStore(...)` option (follow the same shape as `WithDevAuth` / `WithWorkers`).
- **`api/pkg/migrate/` + `api/pkg/migrate/sql/`** — embedded migrator with `pg_advisory_lock` + per-migration tx. New `0002_sessions.sql` migration lives in `sql/`. Baseline `0001_baseline.sql` already has `users`, `user_sessions`, `agents` — the `agents` table partial unique index is a pattern to copy.
- **`api/internal/temporal/`** — 3 workers + 5 stub workflows (`SessionSpawn`, `SessionDestroy`, `RecipeInstall`, `ReconcileContainers`, `ReconcileBilling`). **Phase 2 does NOT use these** — stub API is direct runner.go calls. Phase 5 wires these up.
- **`web/`** — Next.js 16 shell. Phase 2 is API-only; no frontend work. Phase 5 adds the session creation UI.

### Established Patterns
- **Functional options on `server.New`** — add any new store/provider via `WithX(...)` options
- **`SessionProvider` interface with Phase 3 swap path** — new recipe/session dependencies should follow the same "declare an interface, inject an implementation, let later phases swap" pattern
- **Per-migration transactions + advisory lock** — new migrations go in `sql/`, numbered sequentially
- **Dev-mode feature flags** (`AP_DEV_MODE=true` gates dev-cookie auth) — `AP_DEV_BYOK_KEY` follows the same pattern
- **MSV-port-first, rewrite-second** — porting MSV patterns is the default; deviate only where Agent Playground's constraints force it (e.g., MSV's plain-env OAuth vs our tmpfs secrets)

### Integration Points
- `api/cmd/server/main.go` — wires new session handlers via `server.New(...opts)` options
- `api/internal/handler/` — new `sessions.go` file for the three HTTP handlers
- `api/internal/recipes/` — NEW package for the hardcoded recipe structs (Phase 4 replaces with a YAML loader)
- `api/internal/session/` — NEW package for the session-start code path (validation, default sandbox posture, runner.go invocation, FIFO bridge)
- `deploy/ap-base/` — NEW directory for the `ap-base` Dockerfile and entrypoint shim
- `agents/picoclaw/` — NEW directory for the picoclaw recipe Dockerfile and any baked config
- `agents/hermes/` — NEW directory for the Hermes recipe Dockerfile, `cli-config.yaml` template, install steps
- `Makefile` — NEW targets `build-recipes`, `smoke-test`, `build-ap-base`

</code_context>

<specifics>
## Specific Ideas

- **"API-driven start without Telegram is the hypothesis proof"** — the user's explicit framing. Phase 2 is complete when `curl POST /api/sessions` followed by `curl POST /api/sessions/:id/message` returns a real model response from both picoclaw and Hermes. The curl output is the demo. No browser UX until Phase 5.
- **"MSV already proved dockerizing these agents works"** — don't re-spike what MSV runs in production. Port `infra/picoclaw/Dockerfile`'s entrypoint + privilege-drop + OAuth-injection pattern directly; the delta is (a) adding tmux + ttyd because our UX is browser chat + web terminal, (b) replacing plain-env secret injection with tmpfs `/run/secrets/*_key`, (c) swapping the one-hardcoded-agent model for a per-recipe overlay model.
- **"This list will grow"** — recipe system must accept new agents as recipe YAML + Dockerfile, no code changes. Hermes validates the pattern by being the hardest case. If picoclaw and Hermes both work end-to-end, the next N agents are a template fill-in.
- **"Hermes is totally different from OpenClaw"** — the user's explicit flag. Hermes is Python 3.11 + TUI-first + six execution backends + multi-channel daemon with built-in Telegram/Discord/Slack/WhatsApp/Signal/SMS/Email/Matrix/Mattermost; OpenClaw is Node.js + gateway-WebSocket + pairs devices into the gateway. They are opposites. `ap-base` must be forward-compatible with both plus picoclaw's Go CLI without special-casing any of them.
- **Hermes MCP angle worth investigating** — Hermes ships `mcp_serve.py`. If MCP supports message-exchange semantics, it may be a cleaner bridge for TUI agents than PTY screen-scraping. Planning spawns research to verify.
- **"Test the combination before making it web-allowed"** — the user's explicit concern about exposing tmux+ttyd via the web before validating the agent it fronts works at all. Phase 2 runs the smoke test from curl against the API (not from a browser over WSS), explicitly to validate the agent path before Phase 5 wires the WS endpoints.

</specifics>

<deferred>
## Deferred Ideas

- **Custom seccomp JSON authoring** (`mount/unshare/setns/keyctl/bpf/ptrace` drops) — new hardening phase before Phase 8
- **`ap-net` custom bridge + iptables DOCKER-USER egress allowlist** — new hardening phase before Phase 8
- **Falco or Tetragon deployment + rule set + alerting sink** — new hardening phase before Phase 8
- **Escape-test CI harness** (mount attempts, unshare, docker.sock probe, evil egress curl) — new hardening phase before Phase 8
- **gVisor `runsc` installation + per-recipe runtime selection** — new hardening phase before Phase 8. Spike 4 is still pending a human SSH session to Hetzner; neither Phase 2 nor the hardening phase can finalize gVisor until Spike 4 lands
- **OpenClaw recipe** — MSV proves its Dockerfile, but the chat_io path is `gateway-websocket` (a native WS adapter we don't have yet). Defer to Phase 4's recipe expansion (and a follow-up plan that builds the gateway-WS adapter)
- **`ap.recipe/v1` YAML schema** (REC-01) — Phase 4. Phase 2 uses hardcoded Go structs; Phase 4 replaces with a YAML loader
- **Temporal-backed session lifecycle** (SES-07) — Phase 5. Phase 2 is direct runner.go calls; HTTP contract stays stable
- **Chat WebSocket + reconnect + Redis pubsub replay** (CHT-01..05) — Phase 5. Phase 2 is synchronous HTTP message exchange
- **ttyd reverse-proxy terminal WS + xterm.js frontend** (TRM-01..06) — Phase 5. Phase 2 spawns ttyd inside the container and verifies it binds to loopback; doesn't expose it
- **Idle reaper, reconciliation loop, heartbeat** (SES-05, SES-06, SES-08) — Phase 5
- **Two-concurrent-sessions race resolution via Redis SETNX** (SES-09) — Phase 5. Phase 2 gets the Postgres partial-unique-index layer for free (schema already there from Phase 1)
- **BYOK encrypted vault + `/models` test button + settings UI** (SEC-01..11, AUTH-\*) — Phase 3. Phase 2 uses dev env var injection
- **Paid-tier persistent Hermes memory** (`ap-vol-<user>` mounted at `~/.hermes/`) — Phase 7
- **ROADMAP.md update** — reflect this reshape (Phase 2 scope shrinks; new hardening phase inserts before Phase 8; success criteria for Phase 2 rewrite to match). User should run `/gsd-add-phase` or edit directly after this context commits

</deferred>

---

*Phase: 02-container-sandbox-spine*
*Context gathered: 2026-04-13*
