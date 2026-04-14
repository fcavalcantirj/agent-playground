# Phase 2: Agent-in-a-Box + Minimal Substrate — Research

**Researched:** 2026-04-14
**Domain:** Container substrate + minimal stub session API + two architecturally different agent recipes (picoclaw Go CLI, Hermes Python TUI) + dev-mode BYOK injection mechanism
**Confidence:** HIGH on substrate / SDK fields / picoclaw / Hermes single-query bridge — MEDIUM on tmux+ttyd supervision wiring (no Phase 1 prior art for tmux/ttyd inside ap-base) — LOW on the picoclaw chat sub-command wire (depends on Phase 4 spike findings; partially deferred)

## Summary

Phase 2 ships a 4-layer stack: (1) a Debian-slim `ap-base` image baking tini + tmux + ttyd + gosu + the MSV entrypoint-shim privilege-drop pattern; (2) sandbox option fields appended to `pkg/docker/runner.go`'s existing `RunOptions` struct (no rewrites — Phase 1 already validated the SDK shape against `moby/moby/client@v0.4.0`); (3) two thin recipe overlays (`ap-picoclaw` Go binary + `ap-hermes` Python via uv) that FROM `ap-base` and bake their respective agent binaries; (4) a non-durable session API built directly on the runner with a synchronous chat bridge.

**Two key research wins that simplify the plan dramatically:**

1. **Hermes ships a non-interactive single-query mode out of the box.** `hermes chat -q "your question"` runs one query and exits ([CITED: cli.py docstring + main() lines 9787-9837 from `NousResearch/hermes-agent@5621fc4`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/cli.py)). This means the Phase 2 chat bridge for Hermes is `docker exec <container> hermes chat -q "<msg>"` — no PTY screen-scraping, no MCP sidecar, no FIFO bridge for Hermes. CONTEXT D-23 listed three candidate bridges; the answer is option (c) verified, and it is dramatically simpler than (a) or (b).

2. **Hermes's "channel daemons" (Telegram/Discord/Slack/WhatsApp/Signal/etc) are NOT activated by config — they are a separate subcommand `hermes gateway`.** [CITED: `hermes_cli/main.py` docstring lines 1-40](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/hermes_cli/main.py). Phase 2 simply never invokes `hermes gateway`, and no daemon ever starts. The CONTEXT D-21 plan to "disable channel daemons via cli-config.yaml YAML key" is moot — there is no such key because the daemons aren't config-driven; they're subcommand-driven. **This eliminates an entire research+config sub-task.** The `cli-config.yaml` we DO need to pre-bake only contains: `model.provider: anthropic`, `terminal.backend: local`, and toolset selection (`platform_toolsets.cli: [hermes-cli]`). All three are documented in `cli-config.yaml.example`.

The rest of Phase 2 is mechanical: port MSV's `infra/picoclaw/entrypoint.sh` gosu-drop pattern verbatim (it is 70 lines and 95% reusable), append 6 fields to `RunOptions`, write a 60-line FIFO chat-bridge for picoclaw, write a 30-line `docker exec` chat-bridge for Hermes, add a `0002_sessions.sql` migration, and wire three HTTP handlers.

**Primary recommendation:** Build `ap-base` first (Wave 1), then in parallel: (a) extend runner.go with sandbox fields + naming validator (Wave 2a, code-only, fast), (b) build the two recipe overlays + bake configs (Wave 2b, slow because Hermes image is ~3GB), (c) write the session API + recipe structs + migration + FIFO bridge (Wave 2c, depends on 2a). Wave 3 is the smoke-test orchestration. The whole phase is 4-6 plans depending on how aggressively the recipes are bundled together.

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Scope reshape (D-01 to D-03):**
- Phase 2 is a vertical slice proving API-driven agent start, NOT a pure sandbox-hardening phase. It legitimately crosses into Phase 3 (dev BYOK), Phase 4 (first two recipes), and Phase 5 (minimal session API) territory because the hypothesis proof requires all of them together.
- The full hardening spine (custom seccomp, egress allowlist, Falco/Tetragon, escape-test CI, gVisor install) moves to Phase 7.5.
- ROADMAP.md + REQUIREMENTS.md already updated to reflect the reshape (verified by reading both files at research time).

**`ap-base` image architecture (D-04 to D-11):**
- Base OS: Debian slim (`debian:trixie-slim` or `bookworm-slim`), NOT Alpine. Reason: Hermes is Python with native deps; Alpine musl breaks Python wheels.
- PID 1 = tini, always. Agent is a supervised child.
- tmux in `ap-base` from day 1 with two windows: `chat` (FIFO-attached) and `shell` (plain bash for ttyd). Cannot defer.
- ttyd in `ap-base` from day 1, bound to `127.0.0.1:<allocated>`. Phase 5 adds the Go WS reverse proxy.
- Non-root user + gosu privilege-drop entrypoint, ported from MSV's `infra/picoclaw/entrypoint.sh`.
- Entrypoint-shim pattern reads `/run/secrets/*_key` tmpfs files, writes per-agent config files, exports keys into the agent process env only (never PID 1).
- Runtime deps in `ap-base`: `tini`, `tmux`, `ttyd`, `git`, `curl`, `jq`, `ca-certificates`, `gosu`, `bash`. Recipe overlays add language runtimes.
- Image tagging: semver `ap-base:v0.1.0` + git SHA secondary tag. No `:latest`, ever.

**Sandbox options in `runner.go` (D-12 to D-15):**
- Add fields to `RunOptions`: `SeccompProfile string`, `ReadOnlyRootfs bool`, `Tmpfs map[string]string`, `CapDrop []string`, `CapAdd []string`, `NoNewPrivs bool`, `Runtime string`, `NetworkMode string`. Plumb through to `container.HostConfig`. Safe defaults applied by session-start code path, NOT inside runner.go.
- Default sandbox posture (applied by session-start handler): `CapDrop = ["ALL"]`, `NoNewPrivs = true`, `ReadOnlyRootfs = true`, `Tmpfs = {"/tmp": "rw,noexec,nosuid,size=128m", "/run": "rw,noexec,nosuid,size=16m"}`, `PidsLimit = 256`, `Memory = 1GB`, `CPUs = 1e9`, `Runtime = ""` (runc), `NetworkMode = "bridge"`.
- NO custom `ap-net` bridge in Phase 2 — default Docker bridge.
- NO custom seccomp JSON in Phase 2 — Docker's default profile.

**Recipe handling (D-16 to D-18):**
- NO `ap.recipe/v1` YAML schema in Phase 2. Two hardcoded Go structs `recipes.Picoclaw` + `recipes.Hermes` in `internal/recipes/`. Phase 4 replaces with YAML loader.
- Recipe images are PRE-BUILT via `make build-recipes`, never built at session-start time.
- Upstream pinning: picoclaw to a specific commit SHA from `/Users/fcavalcanti/dev/picoclaw`; Hermes to a specific commit SHA from `github.com/NousResearch/hermes-agent`. Both Dockerfiles use `git clone … && git checkout <sha>`.

**Hermes accommodation (D-19 to D-25):**
- Hermes is dockerized in Phase 2 because it is the architecturally hardest agent and validates the substrate against TUI, multi-backend, multi-channel daemon patterns.
- Pre-populate `~/.hermes/cli-config.yaml` from a committed template at build time. First boot must not prompt.
- Disable multi-channel daemons via the cli-config (NOTE: research below shows this is unnecessary — daemons are subcommand-activated, not config-activated; the `cli-config.yaml` only sets model provider + terminal backend + toolsets).
- Force `terminal.backend: local` in `cli-config.yaml` to prevent Hermes from spawning containers-in-containers via its `docker`/`ssh`/`modal`/`daytona`/`singularity` terminal backends.
- Chat bridge mechanism — planning research item. **RESOLVED IN THIS RESEARCH:** Use `hermes chat -q "<msg>"` via `docker exec` (option c from CONTEXT D-23). Confirmed verbatim against upstream.
- Hermes runs with tmpfs `~/.hermes/` in Phase 2 — memory ephemeral, destroyed on session stop. Persistent volume is Phase 7.
- "This list will grow": recipe struct + entrypoint-shim + runner.go must accept new agents as Dockerfile + struct literal — no code changes to `ap-base`, `runner.go`, or session handlers.

**Session API stubs (D-26 to D-31):**
- New migration `0002_sessions.sql` with `sessions` table: `id uuid PK, user_id uuid FK, recipe_name text, model_provider text, model_id text, container_id text NULLABLE, status text DEFAULT 'pending', created_at timestamptz, updated_at timestamptz`.
- NO Temporal in Phase 2 — direct runner.go calls from HTTP handler.
- NO reconciliation, idle reaper, heartbeat, or WS in Phase 2 — all deferred to Phase 5.
- Two-chat-surfaces invariant NOT enforced in Phase 2.
- One-active-session invariant enforced via Postgres partial unique index (Redis SETNX layer is Phase 5).
- Dev BYOK injection: server reads `AP_DEV_BYOK_KEY` from its own env, writes to tmpfs `/run/secrets/anthropic_key` inside the container before start. Phase 3 swaps source for encrypted vault.

**Smoke test (D-32 to D-34):**
- `make smoke-test` performs: build images → start API with `AP_DEV_BYOK_KEY` → POST /sessions → POST /messages → assert response → DELETE /sessions → assert no dangling `playground-*` containers. For BOTH picoclaw and Hermes.
- Test uses real Anthropic BYOK; gated on env var presence (skips in CI if absent).
- Phase complete when smoke test passes for both agents AND a human manually sees a real model response in curl output.

### Claude's Discretion

- Exact Dockerfile layering (single-stage vs multi-stage, which base pins)
- Naming of internal Go packages (`internal/recipes/`, `internal/sessions/`, etc.)
- Default resource limits (1GB / 1 vCPU / 256 PIDs) — revisable if Hermes is provably starving
- Error response shapes for new HTTP endpoints (match Phase 1 envelope)
- Whether `make build-recipes` lives at repo root or in `agents/`
- Log lines, test scaffolding, helper function names
- Exact commit SHAs to pin picoclaw and Hermes to (planning picks at writing time)

### Deferred Ideas (OUT OF SCOPE)

- Custom seccomp JSON authoring → Phase 7.5
- `ap-net` custom bridge + iptables egress allowlist → Phase 7.5
- Falco / Tetragon deployment → Phase 7.5
- Escape-test CI harness → Phase 7.5
- gVisor `runsc` install + per-recipe runtime selection → Phase 7.5
- OpenClaw recipe → Phase 4 (needs gateway-WebSocket adapter)
- `ap.recipe/v1` YAML schema → Phase 4
- Temporal-backed session lifecycle → Phase 5 (HTTP contract stays stable)
- Chat WebSocket + reconnect + Redis pubsub → Phase 5
- ttyd reverse-proxy terminal WS + xterm.js frontend → Phase 5
- Idle reaper, reconciliation loop, heartbeat → Phase 5
- Two-concurrent-sessions Redis SETNX layer → Phase 5
- BYOK encrypted vault + settings UI → Phase 3
- Persistent Hermes memory volume → Phase 7

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **SBX-01** | `ap-base` runs tini PID 1 supervising tmux + ttyd | Section "ap-base Image Recipe" — verbatim Dockerfile sketch + supervision wiring via tini multi-process flag |
| **SBX-02 (partial)** | cap-drop, no-new-privs, read-only rootfs, tmpfs via runner.go option fields (custom seccomp JSON deferred to 7.5) | Section "RunOptions → HostConfig Mapping" — exact field names verified against `moby/moby/api@v1.54.1/types/container/hostconfig.go` |
| **SBX-03** | Resource caps (`--cpus`, `--memory`, `--pids-limit`) tier-specific from recipe | Section "RunOptions → HostConfig Mapping" + Section "Recipe Struct Shape" (DefaultResources field) |
| **SBX-05** | No host Docker socket, no `--privileged` | Invariant — verified Phase 1 runner.go does not expose `Privileged` field; CI grep gate recommended |
| **SBX-09** | Deterministic naming `playground-<user_uuid>-<session_uuid>` | Section "Deterministic Naming" — regex + builder + parser + collision rules |
| **SES-01 (partial)** | Session create with state transitions, direct runner.go call, no Temporal | Section "Session API Surface" — handler shape + status FSM |
| **SES-04 (partial)** | Session stop | Section "Session API Surface" — DELETE handler |
| **CHT-01 (partial)** | Synchronous HTTP POST /messages via FIFO bridge — no WS yet | Section "Chat Bridge — picoclaw (FIFO)" + Section "Chat Bridge — Hermes (single-query exec)" |
| **(pulled forward)** | Dev BYOK via `AP_DEV_BYOK_KEY` env + tmpfs `/run/secrets/*_key` injection | Section "BYOK Dev Injection Mechanism" |
| **(pulled forward)** | Two hardcoded recipes as Go structs | Section "Recipe Struct Shape" + Section "Hermes Specifics" + Section "picoclaw specifics" |

## Project Constraints (from CLAUDE.md)

The following directives from `./CLAUDE.md` MUST be honored. Any plan that contradicts these is wrong.

- **Tech stack pinned:** Go 1.25.x, Echo v4.15.x (NOT v5), pgx v5.8.x, PostgreSQL 17, Docker Engine 27.x+, Docker SDK = `github.com/moby/moby/client` (canonical path), `github.com/coder/websocket` (NOT gorilla/nhooyr), zerolog v1.34.
- **Container isolation v1 = plain Docker** with dropped caps + read-only rootfs + cgroup limits + userns-remap. Sysbox is v1.5, gVisor is v2 / Phase 7.5.
- **Web Terminal Stack:** ttyd inside container bound to loopback; Go WS reverse proxy fronts it (Phase 5 — NOT Phase 2). Phase 2 only verifies ttyd binds and responds on loopback inside the container.
- **What NOT to use, hard prohibitions:**
  - Echo v5 — pin v4 in Phase 2.
  - GORM, ent — pgx + raw SQL only.
  - `docker/docker/client` import path — use `moby/moby/client`.
  - `gotty` — use `ttyd`.
  - `gorilla/websocket`, `nhooyr.io/websocket` — use `coder/websocket`.
  - `fsouza/go-dockerclient` — use `moby/moby/client`.
  - Running `docker run` via `os/exec` — use the SDK only.
  - K3s / Kubernetes / Nomad — plain `dockerd` + Go orchestrator.
  - **Running the agent CLI as PID 1** — tini is always PID 1. Hermes ships its own Dockerfile that runs `hermes` as PID 1 directly; we override via our `ap-base`-rooted derivative recipe.
  - Mounting the host Docker socket into user containers — never.
  - `--privileged` — never.
  - Long-lived API keys baked into images — inject per-session env at start.
- **MSV mirroring:** transfer the gosu entrypoint shim and the per-agent config-file injection pattern from `infra/picoclaw/`.
- **Where mirroring MSV is wrong:** MSV's PicoClaw-specific assumptions in container base images do not apply — `ap-base` must be agent-agnostic, with recipe overlays providing the agent.
- **Code Change Protocol:** "NEVER change code that wasn't directly asked for in the prompt without user confirmation first." Plans must scope edits narrowly to the runner.go fields and new packages — no opportunistic refactors of Phase 1 code.

## Standard Stack

### Core (already pinned by Phase 1, Phase 2 inherits)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `github.com/moby/moby/client` | v0.4.0 (verified live in `api/go.sum`) | Docker Engine SDK | Canonical Docker SDK path. Phase 1 wired via interface injection — Phase 2 reuses without changes. [VERIFIED: Phase 1 SUMMARY 01-02-SUMMARY.md] |
| `github.com/moby/moby/api` | v1.54.1 | HostConfig + Container types | Provides `container.HostConfig` with all the security fields we need. [VERIFIED: read `~/go/pkg/mod/github.com/moby/moby/api@v1.54.1/types/container/hostconfig.go` lines 373-457] |
| `github.com/labstack/echo/v4` | v4.15.1 | HTTP framework | Phase 1 already uses; Phase 2 adds 3 handlers behind existing auth middleware. |
| `github.com/jackc/pgx/v5` | v5.9.1 | Postgres | Phase 1 uses; Phase 2 adds new `sessions` table queries. |
| `github.com/rs/zerolog` | v1.34.0 | Logging | Phase 1 uses. |

### Supporting (new in Phase 2)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **None — pure stdlib for the chat bridge** | — | FIFO IO + docker-exec piping | The chat bridge is `docker exec` via the SDK + `bufio.Scanner`. No new dependency. [VERIFIED: Phase 1 runner.go already exposes `Exec(ctx, containerID, cmd []string) ([]byte, error)`] |

**Image-layer dependencies (baked into `ap-base`, not Go):**

| Package | Version | Source | Purpose |
|---------|---------|--------|---------|
| **tini** | 0.19.0 (Debian package `tini`) | apt — debian:trixie ships it | PID 1, signal forwarder, reaps zombies, supervises tmux + ttyd via `tini -- bash -c "ttyd ... & exec tmux ..."` pattern. [VERIFIED: Debian tracker shows `tini` package `0.19.0-3` available in trixie] |
| **gosu** | 1.19 | Either `apt-get install gosu` (trixie) or copy from `tianon/gosu:1.19-trixie` multi-stage | Privilege-drop in entrypoint shim. [CITED: Hermes upstream Dockerfile uses `tianon/gosu:1.19-trixie@sha256:3b176695...`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/Dockerfile) |
| **tmux** | 3.4 (Debian trixie default) | apt | Two windows (`chat`, `shell`); chat window owns the agent process attached to FIFOs; shell is plain bash for ttyd. [CITED: `tmux` package in Debian trixie] |
| **ttyd** | 1.7.7 (latest stable, Mar 2024) | Pre-compiled static binary download from GitHub releases | Loopback web terminal. Static binary: `https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64` — no Debian package needed. [VERIFIED: GitHub API call to `repos/tsl0922/ttyd/releases/latest` returned tag `1.7.7` published 2024-03-30 with assets for `x86_64`, `aarch64`, `arm`, `mips`, etc.] |
| **bash, git, curl, jq, ca-certificates** | trixie defaults | apt | Standard. |

**Recipe overlay dependencies:**

| Recipe | Adds on top of `ap-base` | Source |
|--------|--------------------------|--------|
| `ap-picoclaw` | A single Go binary `picoclaw` + initial `~/.picoclaw/` config | Multi-stage build: `FROM golang:1.25-alpine AS builder` → `git clone https://github.com/sipeed/picoclaw && git checkout <SHA> && make build` → `COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw` into `ap-base`. [VERIFIED: read `/Users/fcavalcanti/dev/picoclaw/docker/Dockerfile` — already uses this exact two-stage pattern.] |
| `ap-hermes` | Python 3.13 + uv + Hermes source tree at `/opt/hermes` + pre-baked `~/.hermes/config.yaml` | `apt install python3 nodejs npm ripgrep ffmpeg gcc python3-dev libffi-dev procps git` → `git clone NousResearch/hermes-agent && git checkout <SHA> && uv venv && uv pip install -e ".[all]"`. [CITED: Hermes upstream Dockerfile] **Note:** Hermes upstream uses Python **3.13** (Debian 13.4 base), NOT 3.11 as CONTEXT D-19 stated. Plan must use 3.13. |

### Verified versions (queried at research time)

| Package | Version | Verification | Date |
|---------|---------|--------------|------|
| `tsl0922/ttyd` | `1.7.7` | `curl https://api.github.com/repos/tsl0922/ttyd/releases/latest` — `tag_name: "1.7.7"`, `published_at: "2024-03-30T03:18:34Z"` | 2026-04-14 |
| `NousResearch/hermes-agent` HEAD | `5621fc449a7c00f11168328c87e024a0203792c3` | `curl https://api.github.com/repos/NousResearch/hermes-agent/commits?per_page=1` | 2026-04-14 |
| `sipeed/picoclaw` HEAD (local clone) | `c7461f9e963496c4471336642ac6a8d91a456978` | `git -C /Users/fcavalcanti/dev/picoclaw log -1 --format=%H` | 2026-04-14 |
| `moby/moby/api` (Go module) | `v1.54.1` | Already in `api/go.sum`; `~/go/pkg/mod/github.com/moby/moby/api@v1.54.1/types/container/hostconfig.go` exists | 2026-04-14 |
| `moby/moby/client` (Go module) | `v0.4.0` | Phase 1 SUMMARY 01-02 + `api/go.sum` | 2026-04-13 |

**Plan-time pin recommendation:** plans should pin both `picoclaw` and `hermes-agent` to the SHAs above unless a newer release lands by plan-writing time. The picoclaw HEAD SHA is dated 2026-03-31 (latest stable per Phase 1 spike); the Hermes HEAD SHA is dated 2026-04-14 (literally hours before this research) — planning may pin to a slightly older release-tagged SHA like `v0.9.0` if planners prefer release tags over HEAD.

## ap-base Image Recipe

This is the **load-bearing artifact** for the entire phase. Every recipe FROMs it. Get it right.

### Dockerfile sketch

```dockerfile
# ap-base — Agent Playground base image
# Provides: tini PID 1, tmux (chat + shell windows), ttyd on loopback,
# gosu privilege-drop entrypoint shim, FIFO-based chat bridge scaffolding.
# Recipe overlays FROM ap-base:vX.Y.Z and add their agent binary + config.

FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# --- Runtime deps ---
# tini = PID 1 / signal forwarder / zombie reaper
# gosu = privilege-drop in entrypoint
# tmux = supervise chat + shell windows
# bash, git, curl, jq, ca-certificates = recipe install primitives
# procps = ps for entrypoint diagnostics
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        gosu \
        tmux \
        bash \
        git \
        curl \
        jq \
        ca-certificates \
        procps \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true   # smoke-test gosu

# --- ttyd (static binary, latest stable) ---
ARG TTYD_VERSION=1.7.7
ARG TTYD_ARCH=x86_64
RUN curl -fsSL -o /usr/local/bin/ttyd \
        "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/ttyd.${TTYD_ARCH}" \
    && chmod +x /usr/local/bin/ttyd \
    && /usr/local/bin/ttyd --version

# --- Non-root user ---
# UID 10000 matches Hermes upstream and stays clear of host system UIDs
# even after userns-remap (which adds 100000+ to in-container UIDs).
RUN useradd -u 10000 -m -d /home/agent -s /bin/bash agent

# --- Filesystem layout ---
# /work     = the agent's working directory (will be a tmpfs in the free tier)
# /home/agent = HOME (config, .bashrc, agent state)
# /run/ap   = runtime FIFO + pidfile dir (tmpfs at runtime — see below)
RUN mkdir -p /work /home/agent /run/ap \
    && chown -R agent:agent /work /home/agent /run/ap

# --- Entrypoint shim ---
# This is the MSV-ported pattern: starts as root, fixes mounted-volume
# permissions, drops to `agent` via gosu, then exec's tini → tmux + ttyd.
COPY --chmod=0755 entrypoint.sh /entrypoint.sh

# Stay as root so the entrypoint can fix volume permissions before dropping.
WORKDIR /home/agent

# tini supervises everything that comes after it. The "-g" flag forwards
# signals to the entire process group so ttyd + tmux + the agent all die
# cleanly on stop.
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/entrypoint.sh"]

# Default CMD is overridden by every recipe overlay. ap-base's default
# launches a no-op tmux session so a smoke test of ap-base alone proves
# the supervision chain works.
CMD ["bash", "-lc", "tail -f /dev/null"]
```

### entrypoint.sh sketch (port + adapt MSV's `infra/picoclaw/entrypoint.sh`)

The shim runs **twice**: first as root to fix permissions, then re-execs itself as `agent` via `gosu` to do the real work.

```bash
#!/bin/bash
# ap-base entrypoint shim.
# Phase 1: as root — fix mounted-volume perms, prep FIFOs, then gosu drop.
# Phase 2: as agent — read /run/secrets/*_key, write any per-recipe config,
#          start ttyd in background, start tmux session with chat + shell
#          windows, exec the agent's launch command in the chat window.
set -e

AGENT_USER="agent"
AGENT_HOME="/home/agent"
RUN_DIR="/run/ap"
FIFO_IN="${RUN_DIR}/chat.in"
FIFO_OUT="${RUN_DIR}/chat.out"

# === PHASE 1: root ===
if [ "$(id -u)" = "0" ]; then
    # Fix ownership of any mounted volumes (Phase 7 will mount /work as a
    # named volume; Phase 2 uses tmpfs, but the fix is a no-op then).
    chown -R "$AGENT_USER:$AGENT_USER" /work "$AGENT_HOME" "$RUN_DIR" 2>/dev/null || true

    # Re-exec as agent.
    exec gosu "$AGENT_USER" "$0" "$@"
fi

# === PHASE 2: agent ===
echo "=== ap-base entrypoint (user: $(whoami)) ==="

# --- Create FIFOs (chat in/out) ---
# /run/ap is a tmpfs mounted by the runner with size=16M. mkfifo on tmpfs
# is supported and benchmarked at p99 < 0.2ms (Spike 3).
[ -p "$FIFO_IN"  ] || mkfifo "$FIFO_IN"
[ -p "$FIFO_OUT" ] || mkfifo "$FIFO_OUT"
chmod 600 "$FIFO_IN" "$FIFO_OUT"

# --- Read injected secrets into the agent's env (NOT into PID 1's env) ---
# Phase 2 dev BYOK source: /run/secrets/anthropic_key (tmpfs file).
# Phase 3 prod source: same path, populated from the encrypted vault.
AGENT_ENV=""
if [ -f /run/secrets/anthropic_key ]; then
    AGENT_ENV="$AGENT_ENV ANTHROPIC_API_KEY=$(cat /run/secrets/anthropic_key)"
fi
if [ -f /run/secrets/openai_key ]; then
    AGENT_ENV="$AGENT_ENV OPENAI_API_KEY=$(cat /run/secrets/openai_key)"
fi
if [ -f /run/secrets/openrouter_key ]; then
    AGENT_ENV="$AGENT_ENV OPENROUTER_API_KEY=$(cat /run/secrets/openrouter_key)"
fi

# --- Start ttyd in the background, loopback only ---
# Recipe overlays may override AP_TTYD_PORT. The Go-side WS proxy in Phase 5
# will dial 127.0.0.1:$AP_TTYD_PORT inside the container's net namespace
# (or via docker exec wrapping a curl/socat handoff in Phase 2 if proxying
# from the host is not yet set up).
TTYD_PORT="${AP_TTYD_PORT:-7681}"
ttyd \
    --port "$TTYD_PORT" \
    --interface 127.0.0.1 \
    --writable \
    --max-clients 1 \
    --once \
    bash -lc 'tmux attach -t ap || tmux new -s ap' \
    > "$RUN_DIR/ttyd.log" 2>&1 &
echo "ttyd started on 127.0.0.1:$TTYD_PORT"

# --- Start the tmux session with two windows ---
# Window 0: "chat" — runs the agent attached to FIFOs (recipe-specific cmd)
# Window 1: "shell" — plain bash for the ttyd-attached web terminal
tmux new-session -d -s ap -n shell "exec bash -l"

# --- Launch the agent in the "chat" window ---
# AP_AGENT_CMD is set by the recipe overlay (e.g., "picoclaw agent" or
# "hermes chat"). For the FIFO-bridged path (picoclaw), the cmd is wrapped
# so its stdin reads from chat.in and stdout writes to chat.out.
# For the docker-exec-bridged path (hermes -q), the chat window just runs
# a no-op (tail -f /dev/null) and POST /messages execs `hermes chat -q`
# directly — the chat window is unused.
if [ -n "${AP_AGENT_CMD:-}" ]; then
    tmux new-window -t ap -n chat \
        "env $AGENT_ENV bash -c '$AP_AGENT_CMD < $FIFO_IN > $FIFO_OUT 2>&1'"
fi

# Wait for ttyd (we want the container to die when ttyd dies if --once is set,
# but for v1 we let tmux be the long-lived process).
wait %1 2>/dev/null || true

# Keep PID 1 (tini → entrypoint.sh) alive as long as tmux is alive.
while tmux has-session -t ap 2>/dev/null; do sleep 5; done
```

### What this Dockerfile + entrypoint give us

- **PID 1 = tini** ✅ (SBX-01 satisfied)
- **tmux with chat + shell windows** ✅ (SBX-01 + SES-03 forward-compat satisfied)
- **ttyd on loopback** ✅ (SBX-01 + TRM-01 forward-compat satisfied)
- **Non-root user via gosu drop** ✅ (D-08 + CRIT-4 layer)
- **Tmpfs FIFOs at `/run/ap/chat.in` and `/run/ap/chat.out`** ✅ — runner mounts `/run/ap` as tmpfs noexec,nosuid,size=16M (already in the default sandbox posture from D-13, just verify the path matches)
- **Secret injection point at `/run/secrets/*_key`** ✅ (SEC-03 forward-compat satisfied via dev BYOK in Phase 2)
- **Agent-agnostic** ✅ — recipe overlay sets `AP_AGENT_CMD` env or overrides `CMD`; never edits ap-base

### Open questions (flag for planning)

- **Do we use `tini --` (single-process) or `tini -g --` (process group)?** Recommendation: `-g` so a `docker stop` propagates SIGTERM to ttyd + tmux + the agent simultaneously. [ASSUMED — based on tini docs; planner should verify against tini 0.19 man page]
- **Do we install `ttyd` from apt (Debian package may exist) or pre-compiled static binary?** Recommendation: **static binary** for version pinning + reproducibility. The Debian package version drifts by release; the static binary is content-addressed by URL. Architecture matters — Hetzner box is x86_64, but the planning tasks should accept an `ARG TTYD_ARCH` for ARM developer laptops. [VERIFIED: ttyd 1.7.7 ships `x86_64`, `aarch64`, `arm`, `mips`, etc.]
- **`--once` flag on ttyd:** if set, ttyd exits after the first WS client disconnects. For Phase 2 (no Phase 5 WS proxy yet), `--once` is fine — the smoke test never connects to ttyd. For Phase 5 it must be removed. [ASSUMED — verify in ttyd 1.7.7 man page]
- **Does `mkfifo` survive `--read-only` rootfs?** Yes if and only if `/run/ap` is mounted as a writable tmpfs. The default Tmpfs map in D-13 is `{"/tmp": "...", "/run": "..."}` — but the FIFOs are at `/run/ap/`, which is a subdirectory. The runner needs to mount tmpfs at `/run/ap` (NOT `/run`) OR mkdir `/run/ap` inside the tmpfs at entrypoint time. **Recommendation:** mount tmpfs at `/run` (which is the OS-standard runtime dir anyway) and let the entrypoint mkdir `/run/ap`. [VERIFIED: tmpfs supports mkfifo per Linux fs/tmpfs.c]

### Confidence

**HIGH** on the overall shape (ports MSV's proven pattern + bakes ttyd which is widely used). **MEDIUM** on the exact tmux supervision wiring — the script above is plausible but has not been smoke-tested by anyone yet. The first task in the plan should be to build this image locally and verify: (a) container starts, (b) `docker exec <id> tmux ls` shows the `ap` session with `chat` + `shell` windows, (c) `docker exec <id> ss -tlnp` shows ttyd on 127.0.0.1:7681, (d) `docker exec <id> id` shows uid=10000(agent).

## RunOptions → HostConfig Mapping

Append the following fields to `pkg/docker/runner.go`'s existing `RunOptions` struct. Phase 1 left it explicitly extensible: *"Keep this struct additive — adding fields must not break existing callers."* [VERIFIED: read `api/pkg/docker/runner.go` lines 47-75]

### New fields

```go
type RunOptions struct {
    // ... existing fields (Image, Name, Env, Mounts, Network, Memory, CPUs,
    //     PidsLimit, Remove, Labels, Cmd) ...

    // SeccompProfile is the path to a seccomp JSON profile file on the host.
    // Empty string = use Docker's default seccomp profile (recommended for
    // Phase 2). Phase 7.5 sets this to a custom-authored profile.
    SeccompProfile string

    // ReadOnlyRootfs makes the container's root filesystem read-only.
    // Use Tmpfs to provide writable scratch directories.
    ReadOnlyRootfs bool

    // Tmpfs declares tmpfs mounts. Key = container path, value = mount
    // options (e.g. "rw,noexec,nosuid,size=128m"). Empty value = defaults.
    Tmpfs map[string]string

    // CapDrop is the list of Linux capabilities to drop. Use ["ALL"] to
    // drop everything and add back only what's needed via CapAdd.
    CapDrop []string

    // CapAdd is the list of capabilities to add back after CapDrop.
    // Phase 2 picoclaw + hermes need ZERO capabilities — leave empty.
    CapAdd []string

    // NoNewPrivs sets the no-new-privileges security option, preventing
    // setuid binaries from gaining privileges (defense against local
    // privilege escalation inside the container).
    NoNewPrivs bool

    // Runtime selects the OCI runtime ("" = runc default, "runsc" = gVisor,
    // "sysbox-runc" = Sysbox). Phase 2 always passes "" (runc).
    // Phase 7.5 wires the runtime selector for hardened recipes.
    Runtime string
}
```

**Note:** the existing `Network` field is already `string` and already maps to `NetworkMode`. CONTEXT D-12 lists `NetworkMode string` as a "new" field but it's actually already there — this is a no-op delta. Planner should re-read runner.go to confirm and remove from the new-field list.

### Field-by-field mapping to `container.HostConfig`

All field names verified verbatim against `~/go/pkg/mod/github.com/moby/moby/api@v1.54.1/types/container/hostconfig.go`. [VERIFIED: file read 2026-04-14]

| `RunOptions` field | `container.HostConfig` field | Notes |
|---|---|---|
| `Image` | (top-level `ContainerCreateOptions.Image`, NOT in HostConfig) | Phase 1 already does this correctly (see runner.go line 169). |
| `Name` | (top-level `ContainerCreateOptions.Name`) | Same. |
| `Env` | (NOT HostConfig — goes on `container.Config.Env`) | Phase 1 already builds env slice and puts it on Config. |
| `Mounts` (existing, "host:container[:ro]" string format) | `HostConfig.Binds []string` | Phase 1 line 156. |
| `Network` (existing) | `HostConfig.NetworkMode container.NetworkMode` | Phase 1 line 156 — `container.NetworkMode(opts.Network)`. |
| `Memory` (existing) | `HostConfig.Resources.Memory int64` | Phase 1 line 158 — embedded via Resources. |
| `CPUs` (existing) | `HostConfig.Resources.NanoCPUs int64` | Phase 1 line 159. |
| `PidsLimit` (existing) | `HostConfig.Resources.PidsLimit *int64` | Phase 1 lines 160-163, **note pointer type** — must do `pl := opts.PidsLimit; hostCfg.PidsLimit = &pl`. Already done correctly. |
| `Remove` (existing) | `HostConfig.AutoRemove bool` | Phase 1 line 154. |
| `Labels` (existing) | (NOT HostConfig — goes on `container.Config.Labels`) | Phase 1 already correct. |
| `Cmd` (existing) | (NOT HostConfig — goes on `container.Config.Cmd`) | Phase 1 already correct. |
| **NEW** `SeccompProfile` | `HostConfig.SecurityOpt []string` | Encode as `"seccomp=" + path`. Empty → omit (Docker uses default). When set, the file at that path on the **host** (not the container) is read by dockerd. |
| **NEW** `ReadOnlyRootfs` | `HostConfig.ReadonlyRootfs bool` | **Note Docker's spelling: `Readonly` not `ReadOnly`.** Direct passthrough. |
| **NEW** `Tmpfs` | `HostConfig.Tmpfs map[string]string` | Direct passthrough. Format: `{"/tmp": "rw,noexec,nosuid,size=128m", "/run": "rw,noexec,nosuid,size=16m"}`. Validate keys are absolute paths. |
| **NEW** `CapDrop` | `HostConfig.CapDrop []string` (a typedef alias for `strslice.StrSlice`) | Direct passthrough. Validate values against the allowed cap-name set (`CAP_*` minus the prefix). |
| **NEW** `CapAdd` | `HostConfig.CapAdd []string` | Same. |
| **NEW** `NoNewPrivs` | `HostConfig.SecurityOpt []string` (append `"no-new-privileges:true"`) | NOT a standalone HostConfig field — it's a SecurityOpt entry. The runner builds a SecurityOpt slice from `SeccompProfile` + `NoNewPrivs` and assigns once. |
| **NEW** `Runtime` | `HostConfig.Runtime string` | Direct passthrough. Empty = runc. |

### SecurityOpt slice composition

```go
var secOpt []string
if opts.NoNewPrivs {
    secOpt = append(secOpt, "no-new-privileges:true")
}
if opts.SeccompProfile != "" {
    // Validate the path exists (best-effort), then wire it.
    secOpt = append(secOpt, "seccomp="+opts.SeccompProfile)
}
hostCfg.SecurityOpt = secOpt
```

### Default sandbox posture (applied at the **session-start handler**, not in runner.go)

D-13 spells these out. Plan should put them in `internal/session/defaults.go` (or similar) and call them as `sandbox := session.DefaultSandbox(); sandbox.Apply(&opts)`.

```go
// internal/session/defaults.go
package session

import "github.com/agent-playground/api/pkg/docker"

// DefaultSandbox returns the Phase 2 baseline sandbox posture. Phase 7.5
// will replace SeccompProfile with a path to the custom-authored JSON.
func DefaultSandbox() docker.RunOptions {
    return docker.RunOptions{
        // SeccompProfile: "" — use Docker default
        ReadOnlyRootfs: true,
        Tmpfs: map[string]string{
            "/tmp": "rw,noexec,nosuid,size=128m",
            "/run": "rw,noexec,nosuid,size=16m",
        },
        CapDrop:    []string{"ALL"},
        CapAdd:     nil,
        NoNewPrivs: true,
        Runtime:    "",          // runc
        Network:    "bridge",    // default Docker bridge
        Memory:     1 << 30,     // 1 GiB
        CPUs:       1_000_000_000, // 1 vCPU (1e9 nanoCPUs)
        PidsLimit:  256,
        Remove:     true,        // --rm
    }
}
```

The session-start handler then merges the recipe's overrides on top: `opts := session.DefaultSandbox(); recipe.Apply(&opts); opts.Image = recipe.Image; opts.Name = nameFor(userID, sessionID); opts.Env = ...`.

### Unit-testing the new fields

Phase 1's `runner_test.go` uses a mock `DockerClient` (not a real daemon). The new tests need to verify that for each new field, the value lands on the correct `HostConfig` field at the call to `ContainerCreate`. Pattern:

```go
func TestRunner_Run_AppliesNoNewPrivs(t *testing.T) {
    mock := newMockDockerClient(t)
    mock.OnContainerCreate(func(opts client.ContainerCreateOptions) {
        require.Contains(t, opts.HostConfig.SecurityOpt, "no-new-privileges:true")
    })
    r := docker.NewRunnerWithClient(mock, zerolog.Nop())
    _, err := r.Run(ctx, docker.RunOptions{Image: "alpine:3.19", NoNewPrivs: true})
    require.NoError(t, err)
}
```

Phase 1 already has the mock infrastructure (49 sub-tests using it per 01-02-SUMMARY). Plan should add ~6 new subtests, one per new field, plus one that verifies SecurityOpt composition when both `NoNewPrivs` and `SeccompProfile` are set.

**Integration test (real Docker, gated `-short`):** start a busybox container with `ReadOnlyRootfs: true`, exec `touch /foo`, assert it fails with EROFS. Start with `NoNewPrivs: true`, exec `cat /proc/self/status`, assert `NoNewPrivs: 1`. These are the cheap, fast end-to-end proofs that the wiring is correct.

## Deterministic Naming

SBX-09 + D-12 require deterministic container names so reconciliation (Phase 5) can derive container names from DB rows alone.

### Format

```
playground-<user_uuid>-<session_uuid>
```

Where both UUIDs are RFC-4122 strings (36 chars each, lowercase, dashes intact).

**Total length:** 11 (`playground-`) + 36 (user UUID) + 1 (`-`) + 36 (session UUID) = **84 chars**.

Docker's container-name limit is **253 chars** ([CITED: Docker engine source `daemon/names.go`](https://github.com/moby/moby/blob/master/daemon/names.go) — `containerNamePattern = "[a-zA-Z0-9][a-zA-Z0-9_.-]+"` with a 253-char max). 84 << 253, so we're well under. Phase 1's runner.go `validateContainerID` enforces a stricter `maxContainerIDLen = 128` — also fine for 84.

### Builder + parser

```go
// pkg/docker/naming.go (new file in Phase 2)
package docker

import (
    "fmt"
    "strings"

    "github.com/google/uuid"
)

const containerNamePrefix = "playground-"

// BuildContainerName returns the deterministic Docker container name for a
// given (userID, sessionID) pair. Both must be valid RFC-4122 UUIDs.
func BuildContainerName(userID, sessionID uuid.UUID) string {
    return fmt.Sprintf("%s%s-%s", containerNamePrefix, userID.String(), sessionID.String())
}

// ParseContainerName extracts (userID, sessionID) from a deterministic name.
// Returns an error if the name does not match the expected format.
func ParseContainerName(name string) (userID, sessionID uuid.UUID, err error) {
    if !strings.HasPrefix(name, containerNamePrefix) {
        return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: missing prefix in %q", name)
    }
    rest := strings.TrimPrefix(name, containerNamePrefix)
    // UUIDs are exactly 36 chars; the separator is at position 36.
    if len(rest) != 36+1+36 || rest[36] != '-' {
        return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: bad shape %q", name)
    }
    userID, err = uuid.Parse(rest[:36])
    if err != nil {
        return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: bad user uuid: %w", err)
    }
    sessionID, err = uuid.Parse(rest[37:])
    if err != nil {
        return uuid.Nil, uuid.Nil, fmt.Errorf("docker name: bad session uuid: %w", err)
    }
    return userID, sessionID, nil
}

// IsPlaygroundContainerName returns true if the given Docker name belongs to
// the agent-playground (used by Phase 5 reconciliation to filter `docker ps`).
func IsPlaygroundContainerName(name string) bool {
    // Docker names start with "/" when returned from Inspect; trim it.
    return strings.HasPrefix(strings.TrimPrefix(name, "/"), containerNamePrefix)
}
```

### Tests (TDD plan)

```go
// Test cases:
// 1. BuildContainerName roundtrips through ParseContainerName for 100 random UUIDs (property test).
// 2. ParseContainerName rejects: missing prefix, wrong length, non-UUID parts, embedded null bytes.
// 3. BuildContainerName output passes runner.go's existing validateContainerID.
// 4. IsPlaygroundContainerName matches both "playground-..." and "/playground-..." (Docker name from Inspect has leading slash).
// 5. Two distinct (user, session) pairs MUST produce different names (collision impossibility).
```

### Collision rules

UUIDv7 (or v4) collision probability is negligible by design. The session row in Postgres is the source of truth — if a planner is worried, the migration's `id uuid PRIMARY KEY DEFAULT gen_random_uuid()` provides DB-level uniqueness, and the runner.go-side validator just refuses duplicates from the daemon side (Docker returns 409 Conflict on duplicate names; the runner already wraps that error). Phase 5's reconciliation reads `docker ps --filter name=playground-*` and matches against `SELECT id, user_id FROM sessions` — any orphan (in Docker but not DB) gets killed; any zombie (in DB but not Docker) gets marked failed.

## Recipe Struct Shape

D-16 says: "the struct shape IS the schema for Phase 4." Get it right so Phase 4 can swap a YAML loader behind it.

```go
// internal/recipes/recipe.go
package recipes

import "github.com/agent-playground/api/pkg/docker"

// ChatIOMode is how the chat HTTP handler exchanges messages with the agent.
// Phase 2 supports two modes; Phase 4 may add gateway_ws etc.
type ChatIOMode string

const (
    // ChatIOFIFO — the chat handler writes messages to /run/ap/chat.in and
    // reads responses from /run/ap/chat.out. The agent runs as a long-lived
    // process inside the container (typically inside the tmux "chat" window)
    // with its stdin attached to chat.in and stdout to chat.out.
    // Used by: picoclaw.
    ChatIOFIFO ChatIOMode = "stdin_fifo"

    // ChatIOExec — the chat handler runs `docker exec <container> <cmd> -q <msg>`
    // for every message and reads the exec's stdout as the response. The agent
    // is invoked once per message (cold-start latency per call).
    // Used by: hermes (because hermes chat -q is the official non-interactive mode).
    ChatIOExec ChatIOMode = "exec_per_message"
)

// Recipe is the in-memory representation of an agent recipe. Phase 2 ships
// two of these as Go literals in recipes.go. Phase 4 replaces with a YAML
// loader against this exact struct shape.
type Recipe struct {
    // Name is the recipe identifier ("picoclaw", "hermes"). Used in
    // POST /api/sessions {"recipe": "<Name>"}.
    Name string

    // Image is the fully qualified Docker image reference, including tag.
    // Phase 2: locally-built tags like "ap-picoclaw:v0.1.0-c7461f9".
    Image string

    // ChatIO describes how POST /api/sessions/:id/message exchanges with
    // the agent inside the container.
    ChatIO ChatIO

    // RequiredSecrets lists the /run/secrets/ files this recipe needs.
    // The session-start handler refuses to start the container if any
    // listed secret is missing.
    // Phase 2 example: ["anthropic_key"] for both recipes.
    RequiredSecrets []string

    // EnvOverrides are recipe-specific env vars set on the container.
    // Layered ON TOP of the defaults (HOME, PATH from ap-base) and BENEATH
    // any per-session overrides.
    // Example: {"AP_AGENT_CMD": "picoclaw agent --session cli:default"}
    EnvOverrides map[string]string

    // SupportedProviders lists the model_provider values the user picker
    // may pair with this recipe. Phase 2: ["anthropic"] for both recipes.
    // Phase 4 fans out to ["anthropic", "openai", "openrouter"] etc.
    SupportedProviders []string

    // ResourceOverrides tweak the default sandbox posture for this recipe.
    // Nil fields = inherit DefaultSandbox(). Used to give Hermes more memory
    // (it's Python + Playwright, hungrier than picoclaw's tiny Go binary).
    ResourceOverrides *ResourceOverrides
}

// ChatIO bundles the mode + the actual command to launch / exec.
type ChatIO struct {
    Mode ChatIOMode

    // For ChatIOFIFO: the long-lived command launched in the chat tmux
    // window. Inherits stdin from chat.in via the entrypoint shim.
    // Example: ["picoclaw", "agent", "--session", "cli:default"]
    LaunchCmd []string

    // For ChatIOExec: the per-message command run via docker exec.
    // The handler appends the user's message as the final argv element.
    // Example: ["hermes", "chat", "-q"]
    ExecCmd []string

    // ResponseTimeout — how long the handler waits for the agent's reply
    // before returning 504 Gateway Timeout. Phase 2 default: 60s.
    ResponseTimeout time.Duration
}

// ResourceOverrides is a sparse set of fields that override DefaultSandbox().
type ResourceOverrides struct {
    Memory    *int64 // pointer to distinguish "not set" from "set to 0"
    CPUs      *int64
    PidsLimit *int64
}
```

### Phase 2's two recipe literals

```go
// internal/recipes/recipes.go
package recipes

import "time"

// AllRecipes is the Phase 2 hardcoded catalog. Phase 4 replaces with
// YAML files under agents/<name>/recipe.yaml + a loader that parses
// against the Recipe struct.
var AllRecipes = map[string]*Recipe{
    "picoclaw": {
        Name:               "picoclaw",
        Image:              "ap-picoclaw:v0.1.0-c7461f9",  // pinned to picoclaw HEAD 2026-03-31
        RequiredSecrets:    []string{"anthropic_key"},
        SupportedProviders: []string{"anthropic"},
        ChatIO: ChatIO{
            Mode:            ChatIOFIFO,
            LaunchCmd:       []string{"picoclaw", "agent", "--session", "cli:default"},
            ResponseTimeout: 60 * time.Second,
        },
        EnvOverrides: map[string]string{
            // picoclaw reads its model from PICOCLAW_MODEL or the agent --model flag
            // [VERIFIED: cmd/picoclaw/internal/agent/command.go line 27]
            "PICOCLAW_PROVIDER": "anthropic",
        },
    },
    "hermes": {
        Name:               "hermes",
        Image:              "ap-hermes:v0.1.0-5621fc4",  // pinned to hermes HEAD 2026-04-14
        RequiredSecrets:    []string{"anthropic_key"},
        SupportedProviders: []string{"anthropic"},
        ChatIO: ChatIO{
            Mode:            ChatIOExec,
            // `hermes chat -q "<msg>"` runs single-query mode and exits.
            // [VERIFIED: cli.py docstring lines 1-12 + main() lines 9787-9837]
            ExecCmd:         []string{"hermes", "chat", "-q"},
            ResponseTimeout: 120 * time.Second,  // Hermes is heavier — give it 2x
        },
        EnvOverrides: map[string]string{
            // Force the auto-detect picker to land on Anthropic.
            // [CITED: cli-config.yaml.example, model.provider section]
            "HERMES_INFERENCE_PROVIDER": "anthropic",
            // Disable startup banners + chatty logging
            "HERMES_QUIET": "1",
        },
        ResourceOverrides: &ResourceOverrides{
            // Hermes ships Playwright + ffmpeg + heavy Python deps — bump memory
            // to avoid OOM during the smoke test. Verified empirically Phase 2.
            Memory: ptr(int64(2 << 30)),  // 2 GiB
        },
    },
}
```

### Forward-compatibility check

When Phase 4 introduces `agents/<name>/recipe.yaml`, the YAML must deserialize into the same `Recipe` struct. A planner can verify by writing a YAML literal of the picoclaw recipe and `yaml.Unmarshal`-ing it into `Recipe{}` — if the round-trip matches the Go literal, the schema is fixed.

The fields most likely to drift in Phase 4:
- `LaunchCmd` / `ExecCmd` may need to become a single `chat_io.cmd` with a discriminator, or split into `cmd` + `args`. Acceptable refactor — the consumer is one handler.
- `RequiredSecrets` may grow to `RequiredSecrets []SecretSlot` with `{name, env_var, optional}` triples. Acceptable.
- `SupportedProviders` will gain `RequiredEnvVars []string` per provider so the model-picker UI can show "you need to add an OpenAI key first."

These are additive; Phase 4 will not need to delete a Phase 2 field.

## BYOK Dev Injection Mechanism

D-31 + Phase 3 forward-compat: the **mechanism** (file at `/run/secrets/<provider>_key`) is what Phase 2 wires; the **source** (`AP_DEV_BYOK_KEY` env vs encrypted vault) is what Phase 3 swaps.

### End-to-end flow (Phase 2)

1. **API startup** reads `AP_DEV_BYOK_KEY` from its own process env. Empty = log a warning and refuse to spawn sessions that have `RequiredSecrets`. Non-empty = treat as a single Anthropic key for v1.
2. **Session create handler** (`POST /api/sessions`) is called with `{recipe, model_provider, model_id}`. Handler:
   - Looks up the recipe.
   - Reads `recipe.RequiredSecrets` — for Phase 2 always `["anthropic_key"]`.
   - For each required secret, fetches the value from the dev BYOK source (env var). If missing → 503 Service Unavailable with a clear error.
   - **Writes the value to a host-side temp file** under `/tmp/ap/secrets/<session_id>/anthropic_key` (mode 0600, owner = API process user).
   - Adds a bind-mount to RunOptions: `/tmp/ap/secrets/<session_id>:/run/secrets:ro`.
   - Calls `runner.Run(...)`.
3. **Inside the container**, the entrypoint shim reads `/run/secrets/anthropic_key` and exports `ANTHROPIC_API_KEY=<value>` ONLY into the agent process env (not into PID 1 or any sibling process).
4. **Session destroy handler** (`DELETE /api/sessions/:id`) calls `runner.Stop` + `runner.Remove` AND `os.RemoveAll(/tmp/ap/secrets/<session_id>)` to wipe the host-side secret file.

### Why bind-mount and not Docker secrets

Docker's native secrets API requires Swarm mode. We're plain Docker on a single host. The bind-mount of a tmpfs-style host directory is the standard Docker-not-Swarm replacement and is exactly what Phase 3 will continue to use — it just swaps step (2)'s "read env var" with "decrypt the value from the pgcrypto-encrypted column."

### Security posture in Phase 2

- **Host file lives under `/tmp/ap/secrets/`** which the planner should configure on startup with `0700` perms owned by the API process user.
- **The bind-mount is read-only** (`:ro`) so the container cannot write back into host /tmp.
- **The container's `/run/secrets/` is mode 0500 visible only to the agent user (uid 10000)**. The entrypoint's gosu drop happens before `cat /run/secrets/anthropic_key`, so the read happens as `agent`.
- **Cleanup is the handler's responsibility** on session stop. Plan task: add a startup sweep that nukes any leftover `/tmp/ap/secrets/<id>` not matching an active session row, in case a previous API crash left orphans.
- **NEVER log the key**, NEVER include it in any API response. CONTEXT D-31 + SEC-02. Plan should add a `redactedSecret(s string) string` helper that returns `sk-***` and use it in any log line that happens near the secret read.

### Phase 3 hand-off

Phase 3 replaces step (2)'s "read from `AP_DEV_BYOK_KEY` env" with "look up the user's encrypted Anthropic key in the Postgres `byok_keys` table, decrypt with the per-user KEK, write to the same host-side tmpfs path." The bind-mount, in-container path, and entrypoint reader stay byte-for-byte identical. **This is the key win of the Phase 2 reshape:** zero rewrites in Phase 3.

## Chat Bridge — picoclaw (FIFO)

picoclaw uses `ChatIOFIFO`. The agent process is launched **once** by the entrypoint shim inside the tmux `chat` window with stdin redirected from `/run/ap/chat.in` and stdout redirected to `/run/ap/chat.out`. The Go-side handler then writes one line of JSON (or a single text payload) to `chat.in` and reads one line back from `chat.out`.

### How writes reach a FIFO inside a running container

The Go API does not have direct host filesystem access to FIFOs that live inside the container's namespaces (the FIFOs are at `/run/ap/chat.in` *inside* the container's tmpfs, not on the host). Three options:

| Option | How | Tradeoff |
|---|---|---|
| **(A) `docker exec` a tee** | `docker exec <id> sh -c 'cat > /run/ap/chat.in' < (echo "$msg")` — but Go SDK ExecAttach needs to send the message via the hijacked stdin stream | Spawns a process per message but ergonomically clean. **Recommended for Phase 2.** |
| **(B) Mount the FIFO dir as a host volume** | Bind-mount `/var/lib/ap/run/<session>:/run/ap` so the Go API can `os.OpenFile("/var/lib/ap/run/<session>/chat.in")` directly | Avoids per-message exec overhead but breaks the "tmpfs everywhere" invariant — the FIFO dir is now persistent on the host disk. Also leaks the chat content to host filesystem audit logs. **Reject.** |
| **(C) `nsenter` from the API** | `nsenter --target <pid>` into the container's mount/pid namespaces and write to the FIFO directly | Requires the API process to have CAP_SYS_ADMIN on the host. **Reject — security non-starter.** |

**Decision: Option A.** Use the Phase 1 runner's `Exec(ctx, containerID, cmd []string) ([]byte, error)` for the read side, and add a new `ExecWithStdin(ctx, containerID, cmd []string, stdin io.Reader) ([]byte, error)` for the write side. The new method uses the same `ExecCreate` + `ExecAttach` cycle Phase 1 already wired, but sets `AttachStdin: true` and writes from the `stdin` reader into the hijacked connection.

### Handler flow

```
POST /api/sessions/:id/message {"text": "say hi"}
    │
    ▼
1. Validate session belongs to caller (check session.user_id against cookie).
2. Look up container_id from sessions table; refuse if status != 'running'.
3. Look up recipe by session.recipe_name; switch on recipe.ChatIO.Mode:
       case ChatIOFIFO: → step 4
       case ChatIOExec: → see "Chat Bridge — Hermes" section below
4. Write message to chat.in via:
       runner.ExecWithStdin(ctx, container_id,
           []string{"sh", "-c", "cat >> /run/ap/chat.in"},
           strings.NewReader(payload + "\n"))
5. Read response from chat.out with a timeout:
       deadline := time.Now().Add(recipe.ChatIO.ResponseTimeout)
       loop:
           output, err := runner.Exec(ctx, container_id,
               []string{"timeout", "5", "head", "-n", "1", "/run/ap/chat.out"})
           if got line: return JSON {"text": line}
           if past deadline: return 504
           sleep 100ms
6. Return {"text": "..."} as JSON.
```

### Why "head -n 1" with a 5s timeout in a loop

A `read` from a FIFO blocks until **any** writer writes, so the natural impl is "head -n 1 < /run/ap/chat.out" and let it block. But if the agent is slow, the docker exec hijack will sit there for the full ResponseTimeout — and the Go SDK's Exec doesn't expose a graceful interrupt. Using a 5s `timeout` wrapper means each individual exec is bounded; the outer Go loop can check the overall deadline and return 504 cleanly.

The 5s value is a tuning knob — too short = wasted exec spawns; too long = sloppy 504 timing. **Recommend 5s for Phase 2** and revisit in Phase 5 when WS replaces sync HTTP and the bridge becomes a long-lived goroutine instead of a per-request poll.

### Validation

The Phase 1 runner's `validateContainerID` already protects against shell injection in container_id. The `cat >> /run/ap/chat.in` command is hardcoded in the handler — no user input flows into argv elements. The user message goes only into stdin of the exec, which is bytes — there is no shell interpretation. **The bridge is injection-safe by construction**, BUT plans should add a unit test that fuzzes the message with `;`, `$()`, and backticks and verifies they hit the FIFO as literal bytes (not interpreted by the agent's downstream parser — that's the agent's problem, not ours).

## Chat Bridge — Hermes (single-query exec)

Hermes uses `ChatIOExec`. **There is no FIFO involvement and no long-lived agent process.** Each message spawns a fresh `hermes chat -q "<msg>"` invocation via `docker exec`, and the exec's stdout IS the response.

### Why this is dramatically simpler than CONTEXT D-23 anticipated

CONTEXT D-23 listed three candidate bridges: PTY screen-scrape, MCP via `mcp_serve.py`, or a hypothetical `--message` flag. The flag exists and is the supported non-interactive path. It is documented in the cli.py docstring and the main argparse:

> `python cli.py -q "your question"  # Single query mode`
> `q: Shorthand for --query`

[CITED: `cli.py` lines 1-12 + lines 9787-9837 from `NousResearch/hermes-agent@5621fc4`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/cli.py)

The actual binary is the `hermes` shell script in the repo root, which dispatches to `hermes_cli/main.py` for subcommand routing. `hermes chat -q "your question"` is the canonical invocation. [CITED: `hermes_cli/main.py` lines 1-40](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/hermes_cli/main.py)

### Handler flow

```
POST /api/sessions/:id/message {"text": "say hi"}
    │
    ▼
1. Validate session ownership (same as picoclaw).
2. Look up container_id; refuse if not 'running'.
3. Recipe says ChatIOExec — use recipe.ChatIO.ExecCmd = ["hermes", "chat", "-q"]
4. Build argv: append the user's text as a single element:
       cmd := append(slices.Clone(recipe.ChatIO.ExecCmd), msg.Text)
   This sends [ "hermes", "chat", "-q", "say hi" ] — the SDK passes this as
   an argv slice to the Docker daemon, NOT through a shell, so the message
   text is structurally injection-safe.
5. Run with timeout:
       ctx, cancel := context.WithTimeout(ctx, recipe.ChatIO.ResponseTimeout)
       defer cancel()
       output, err := runner.Exec(ctx, container_id, cmd)
6. Return {"text": string(output)} as JSON. (Optional: scrub ANSI escapes.)
```

### Cold-start latency

Each message spawns a fresh Python interpreter + loads the Hermes module tree. Empirically (per the cli.py imports we read), Hermes loads `prompt_toolkit`, `yaml`, agent modules, etc. — expect **3–8 seconds of cold-start per message** in the Phase 2 smoke test. This is acceptable for the hypothesis proof but is a known cliff for Phase 5 — Phase 5 will need a long-lived Hermes process behind an MCP or HTTP bridge to make chat feel real-time.

**Document this as a known limitation in the smoke test:** the test waits up to `recipe.ChatIO.ResponseTimeout` (120s for Hermes vs 60s for picoclaw) for each message. The test still passes because we only send 1-2 messages. Phase 5 fixes the cliff.

### ANSI escape handling

`hermes chat -q` writes the response to stdout. It MAY emit ANSI escape codes if it detects a TTY. Since we're invoking via `docker exec` without `-t`, stdout is a pipe and Hermes should detect that and emit plain text. **Verify in plan:** include a smoke test assertion that the response does not contain `\x1b[`. If it does, add `--no-color` (if Hermes supports it — read the cli.py argparse to verify) or pipe through `sed 's/\x1b\[[0-9;]*m//g'` inside the exec.

## Hermes Specifics

### Source of truth (verified)

- **Repo:** `https://github.com/NousResearch/hermes-agent` ✅ (HTTP 200, public)
- **License:** description "The agent that grows with you", license file present (assumed MIT — the repo lists `LICENSE` in root, content not fetched in this research; planner should verify before committing)
- **Latest commit (HEAD):** `5621fc449a7c00f11168328c87e024a0203792c3` (2026-04-14T02:51:54Z, "rename AI Gateway → Vercel AI Gateway")
- **Latest tagged release:** Per the README directory listing, `RELEASE_v0.9.0.md` is present — `v0.9.0` is the latest release tag (not directly fetched; verify at plan time via `gh release list`).

### Python version (CONTEXT got this wrong)

CONTEXT D-19 says "Python 3.11 baseline." **Hermes upstream uses Python 3.13** per its Dockerfile:

```dockerfile
FROM ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie@sha256:...
```

[CITED: `Dockerfile` line 1 from `NousResearch/hermes-agent@5621fc4`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/Dockerfile)

The plan must use Python 3.13. uv handles the version pin automatically — the plan just needs to apt-install `python3` (which on Debian trixie is 3.13.x) and let uv create the venv.

### Install steps (port from upstream Dockerfile)

```dockerfile
# Inside ap-hermes recipe overlay (FROM ap-base:v0.1.0)
USER root

# Hermes upstream apt install line, verbatim:
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential nodejs npm python3 ripgrep ffmpeg gcc python3-dev libffi-dev procps && \
    rm -rf /var/lib/apt/lists/*

# Install uv from official static binary (matches upstream)
COPY --chmod=0755 --from=ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

# Clone Hermes at pinned SHA
ARG HERMES_SHA=5621fc449a7c00f11168328c87e024a0203792c3
RUN git clone https://github.com/NousResearch/hermes-agent /opt/hermes && \
    cd /opt/hermes && \
    git checkout "$HERMES_SHA"

# Install Node deps (Hermes ships a package.json for Playwright + WhatsApp bridge)
WORKDIR /opt/hermes
RUN npm install --prefer-offline --no-audit && \
    npx playwright install --with-deps chromium --only-shell

# Hand ownership to agent user, install Python deps as that user
RUN chown -R agent:agent /opt/hermes
USER agent
RUN cd /opt/hermes && uv venv && uv pip install --no-cache-dir -e ".[all]"

# Create config dir + bake the cli-config.yaml
USER root
RUN mkdir -p /home/agent/.hermes && chown agent:agent /home/agent/.hermes
COPY --chown=agent:agent cli-config.yaml /home/agent/.hermes/config.yaml

# Symlink hermes binary into PATH
USER root
RUN ln -sf /opt/hermes/hermes /usr/local/bin/hermes

# ap-base's entrypoint stays in charge — we just provide AP_AGENT_CMD
ENV HERMES_HOME=/home/agent/.hermes
ENV PATH=/opt/hermes/.venv/bin:$PATH
ENV AP_AGENT_CMD=""  # Hermes uses ChatIOExec — no chat-window long-lived process
```

**Image size warning:** Hermes upstream image is reported as ~3GB after Playwright + node deps + Python venv. Plan should `make build-recipes` cache aggressively and accept that the first build takes 10+ minutes. CI runners may need to be sized accordingly or the image cached in a registry.

### `cli-config.yaml` to bake (committed at `agents/hermes/cli-config.yaml`)

Based on [CITED: `cli-config.yaml.example`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/cli-config.yaml.example), the minimum we need to set:

```yaml
# agents/hermes/cli-config.yaml — pre-baked for Phase 2 smoke test
# Forces Anthropic provider, local terminal backend, CLI toolset.
# All other settings inherit upstream defaults.

model:
  default: "anthropic/claude-sonnet-4-6"
  provider: "anthropic"
  base_url: "https://api.anthropic.com"

terminal:
  backend: "local"        # CRITICAL: prevents container-in-container backends (docker/ssh/modal/daytona/singularity)
  cwd: "/home/agent/work"
  timeout: 180
  lifetime_seconds: 300

platform_toolsets:
  cli: [hermes-cli]
  # No telegram/discord/whatsapp/slack/signal sections — those activate
  # only when `hermes gateway` is run, which Phase 2 NEVER does.

memory:
  memory_enabled: false   # ephemeral memory in Phase 2 (no persistent volume)
  user_profile_enabled: false

agent:
  verbose: false
  reasoning_effort: "medium"
```

**Crucial correction to CONTEXT D-21:** there is no "channel daemon disable" YAML key. The messaging gateways (Telegram/Discord/Slack/WhatsApp/Signal/Matrix/Mattermost) are NOT spawned by `hermes chat` — they are spawned by `hermes gateway`. Since Phase 2 only ever invokes `hermes chat -q`, no daemon is even loaded. The `platform_toolsets` block above only constrains which tools the LLM has access to within a session; it does not start any daemons.

[CITED: `hermes_cli/main.py` lines 5-25 — `hermes gateway` is a separate subcommand](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/hermes_cli/main.py)

### Authentication (BYOK)

Hermes reads `ANTHROPIC_API_KEY` from env when `model.provider: anthropic` is set in config. [CITED: `cli-config.yaml.example` model.provider section] Our entrypoint shim exports `ANTHROPIC_API_KEY=$(cat /run/secrets/anthropic_key)` into the agent process env before exec'ing. **Confirmed compatible.**

### One-shot mode feasibility

✅ **Confirmed.** `hermes chat -q "your question"` runs one query and exits with the response on stdout. This is the official non-interactive mode documented in `cli.py` line 12 and the `main()` argparse. No screen-scraping, no PTY, no MCP needed.

### Confidence

**HIGH** for `hermes chat -q` one-shot mode (verified directly from upstream source). **MEDIUM** for the exact Dockerfile build (it ports the upstream Dockerfile but tweaks it to inherit ap-base, which means we're downgrading from upstream's Python-3.13-uv FROM image to a layer-on-top approach — first build will require iteration). **LOW** for the smoke test passing on the first try without tuning Hermes's startup config — Hermes is a complex codebase, and the first invocation of `hermes chat -q` may need to be told what session/profile to use. Plan should budget for one iteration.

## picoclaw Specifics

### Source of truth (verified)

- **Local repo:** `/Users/fcavalcanti/dev/picoclaw` — already on disk
- **HEAD SHA:** `c7461f9e963496c4471336642ac6a8d91a456978` (2026-03-31, "Merge pull request #2221 ...")
- **Upstream:** `https://github.com/sipeed/picoclaw` (per README)
- **License:** MIT
- **Language:** Go 1.25+
- **Latest stable per README:** v0.2.4 (2026-03-25)

### Existing upstream Dockerfile

[VERIFIED: read `/Users/fcavalcanti/dev/picoclaw/docker/Dockerfile`]

```dockerfile
FROM golang:1.25-alpine AS builder
RUN apk add --no-cache git make
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN make build

FROM alpine:3.23
RUN apk add --no-cache ca-certificates tzdata curl
COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw
RUN addgroup -g 1000 picoclaw && adduser -D -u 1000 -G picoclaw picoclaw
USER picoclaw
RUN /usr/local/bin/picoclaw onboard
ENTRYPOINT ["picoclaw"]
CMD ["gateway"]
```

**Adaptation for `ap-picoclaw`:** we keep stage 1 (Go builder) but replace stage 2 with `FROM ap-base:v0.1.0`. This way picoclaw inherits tini, tmux, ttyd, gosu, the entrypoint shim, and uses our `agent` user (uid 10000) instead of upstream's `picoclaw` (uid 1000). The picoclaw binary is just `COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw`.

### Recipe Dockerfile sketch

```dockerfile
# agents/picoclaw/Dockerfile
ARG PICOCLAW_SHA=c7461f9e963496c4471336642ac6a8d91a456978

# Stage 1: Build picoclaw from pinned SHA
FROM golang:1.25-alpine AS builder
RUN apk add --no-cache git make
WORKDIR /src
RUN git clone https://github.com/sipeed/picoclaw . && \
    git checkout "${PICOCLAW_SHA}" && \
    go mod download && \
    make build

# Stage 2: Layer the binary onto ap-base
FROM ap-base:v0.1.0

USER root
COPY --from=builder /src/build/picoclaw /usr/local/bin/picoclaw
RUN chmod +x /usr/local/bin/picoclaw

# Run picoclaw onboard as the agent user to create initial config
USER agent
RUN /usr/local/bin/picoclaw onboard

USER root

# AP_AGENT_CMD launches picoclaw in interactive mode in the tmux chat window.
# The entrypoint shim wraps stdin from /run/ap/chat.in and stdout to chat.out.
# [VERIFIED: cmd/picoclaw/internal/agent/command.go - the `agent` subcommand
# without -m runs interactive readline loop, perfect for FIFO bridging]
ENV AP_AGENT_CMD="picoclaw agent --session cli:default"
```

### picoclaw's relevant CLI flags (verified)

[VERIFIED: read `/Users/fcavalcanti/dev/picoclaw/cmd/picoclaw/internal/agent/command.go` lines 1-30]

```go
cmd.Flags().BoolVarP(&debug, "debug", "d", false, "Enable debug logging")
cmd.Flags().StringVarP(&message, "message", "m", "", "Send a single message (non-interactive mode)")
cmd.Flags().StringVarP(&sessionKey, "session", "s", "cli:default", "Session key")
cmd.Flags().StringVarP(&model, "model", "", "", "Model to use")
```

So picoclaw supports both modes:
- **Interactive:** `picoclaw agent --session cli:default` — REPL with readline; this is what we wire into the FIFO bridge.
- **One-shot:** `picoclaw agent -m "say hi"` — single message and exit; this could ALSO be used via ChatIOExec like Hermes if the FIFO bridge proves flaky.

**Recommendation:** Phase 2 starts with the FIFO bridge for picoclaw because it's the architecture Phase 5 will need anyway (real-time chat, no per-message cold start). If the FIFO bridge has bugs in the first wave, fall back to ChatIOExec (`picoclaw agent -m`) as a temporary measure — same recipe struct, just flip the mode and ExecCmd. **Both paths are validated for picoclaw**, which gives the planner a rollback option.

### Authentication (BYOK)

picoclaw reads provider credentials via its config system (`pkg/config/config.go` per Phase 1 spike). The simplest path: set `ANTHROPIC_API_KEY` env var, which picoclaw's Anthropic provider reads via the official `anthropic-sdk-go` env-loading. [CITED: Phase 1 SPIKE-REPORT.md §Spike 1 — picoclaw uses `pkg/providers/anthropic/provider.go` with `option.WithBaseURL` and reads env via the SDK]. Our entrypoint shim already exports `ANTHROPIC_API_KEY` into the agent process env. **Compatible.**

### picoclaw `onboard` step

The upstream Dockerfile runs `picoclaw onboard` at build time to seed initial config in `~/.picoclaw/`. This is fine to do at build time — it creates a static config. Our recipe Dockerfile mirrors this. The resulting config dir will be at `/home/agent/.picoclaw/` (because the build runs as `USER agent`).

### Confidence

**HIGH** for the picoclaw recipe — the upstream Dockerfile already proves the build works, and we have local source + verified flags. The only delta from upstream is FROM-ing ap-base instead of alpine. **MEDIUM** for the FIFO bridge interaction with picoclaw's readline prompt — readline emits a prompt to stdout (`picoclaw> ` or similar), which means the FIFO output stream will contain prompt cruft mixed with the actual response. Plan must include a state-machine response parser OR set picoclaw to a non-prompt mode if one exists (verify via `--help`).

## MSV picoclaw Port Details

[VERIFIED: read `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/Dockerfile` (75 lines) + `/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/entrypoint.sh` (203 lines)]

### What we port verbatim

| MSV file | What | New location | Adaptation |
|---|---|---|---|
| `Dockerfile` line 13-23 (apt install line) | Runtime deps including gosu | `deploy/ap-base/Dockerfile` | Replace `git python3 make g++ openssh-client ca-certificates curl jq gosu` with our slimmer set: `tini gosu tmux bash git curl jq ca-certificates procps`. We don't need build tools because ap-base never compiles anything. |
| `Dockerfile` line 27-29 (useradd + .openclaw dir) | Non-root user creation | `deploy/ap-base/Dockerfile` | Use `useradd -u 10000 -m -d /home/agent agent` (matches Hermes upstream UID). |
| `Dockerfile` line 60-65 (entrypoint copy + WORKDIR) | Entrypoint pattern | `deploy/ap-base/Dockerfile` | Verbatim. |
| `entrypoint.sh` lines 13-30 (PHASE 1: root → fix perms → exec gosu) | The privilege drop | `deploy/ap-base/entrypoint.sh` | Verbatim. The only change is variable names — `HOME_DIR=/home/picoclaw` becomes `AGENT_HOME=/home/agent`. |
| `entrypoint.sh` line 29 (`exec gosu picoclaw "$0" "$@"`) | The actual gosu drop | `deploy/ap-base/entrypoint.sh` | Verbatim except user name. |

### What we DROP from MSV

| MSV behavior | Why we don't port it |
|---|---|
| `entrypoint.sh` lines 36-111 — Anthropic OAuth + Groq fallback config write | MSV is locked to Anthropic with OAuth; we use BYOK env vars from /run/secrets. Different injection path. |
| `entrypoint.sh` lines 113-118 — Pod recovery script call | MSV recovers AMCP identity from a remote API; we have no equivalent in Phase 2. |
| `entrypoint.sh` lines 120-156 — AMCP identity creation | MSV uses Anthropic Multi-Agent Communication Protocol; not relevant. |
| `entrypoint.sh` lines 158-197 — OpenClaw gateway config injection | MSV runs OpenClaw, we don't. |
| `entrypoint.sh` lines 199-202 — `exec openclaw gateway --port $PORT` | We exec our supervised tmux + ttyd setup instead. |
| Dockerfile `EXPOSE 18789` + HEALTHCHECK | Our network model is loopback-only; ttyd exposes nothing externally. Healthcheck moves to runner.go side. |

### What we ADD that MSV doesn't have

- **tmux + ttyd installation + supervision** — MSV runs OpenClaw as PID 1 directly; we need tini supervising both ttyd and the agent so the web terminal works.
- **FIFO creation** — MSV's chat surface is via Telegram (a remote service); ours is via in-container FIFOs.
- **`/run/secrets/*_key` reader** — MSV uses MBALLONA_OAUTH env var; we use file-based injection.

**Net file size estimate:** `entrypoint.sh` shrinks from 203 lines to ~80 lines. The MSV-specific OpenClaw / AMCP / OAuth chunks (~120 lines) all drop out; we add ~30 lines for tmux + ttyd + FIFO setup.

## Session API Surface

Three handlers behind the existing Phase 1 `/api/*` auth middleware. All synchronous, all wrapping direct runner.go calls.

### `POST /api/sessions`

```
Request:  {"recipe": "picoclaw", "model_provider": "anthropic", "model_id": "claude-sonnet-4-6"}
Response: 201 {"id": "<uuid>", "status": "running", "container_id": "<docker-id>"}
Errors:
  400 — unknown recipe, unsupported provider for recipe, missing required field
  401 — no session cookie
  409 — user already has an active session (Postgres partial unique index fires)
  503 — required secret missing (AP_DEV_BYOK_KEY not set)
  500 — runner.Run failed
```

Handler steps:
1. Decode JSON body, validate fields against allowlists (`recipe ∈ recipes.AllRecipes`, `model_provider ∈ recipe.SupportedProviders`).
2. Generate session UUID (`uuid.New()` — Phase 1 already imports google/uuid).
3. Insert sessions row with status=`pending`. The partial unique index on `(user_id) WHERE status IN ('pending','provisioning','running')` will return a UNIQUE_VIOLATION → handler returns 409.
4. Update status to `provisioning`.
5. Read required secrets from `AP_DEV_BYOK_KEY`, write to host tmpfs path `/tmp/ap/secrets/<session_id>/anthropic_key`.
6. Build RunOptions: `DefaultSandbox()` + recipe overrides + bind-mount `/tmp/ap/secrets/<session_id>:/run/secrets:ro` + Image from recipe + Name from `BuildContainerName(userID, sessionID)`.
7. Call `runner.Run(ctx, opts)` → container_id.
8. Update sessions row: `container_id = <id>`, `status = 'running'`.
9. Return 201 + JSON.

**Failure paths:** if step 7 fails, set status=`failed`, wipe the secrets dir, return 500. If step 8 fails, force-remove the container, set status=`failed`. **No retry, no Temporal — this is the explicit Phase 2 stub.**

### `POST /api/sessions/:id/message`

```
Request:  {"text": "say hi in 5 words"}
Response: 200 {"text": "Hello! How are you?"}
Errors:
  400 — empty text, text too long (cap at 16KB for Phase 2)
  401 — no cookie
  403 — session belongs to a different user
  404 — session id not in DB
  409 — session status != 'running'
  504 — agent did not respond within recipe.ChatIO.ResponseTimeout
  500 — exec failure
```

Handler steps:
1. Look up session by id; check ownership against cookie's user_id.
2. Check status == `running`; refuse otherwise.
3. Look up recipe by `session.recipe_name`; switch on `recipe.ChatIO.Mode`:
   - `ChatIOFIFO`: call the FIFO bridge (write to chat.in, read from chat.out with timeout)
   - `ChatIOExec`: call the exec bridge (`runner.Exec(ctx, container_id, append(execCmd, msg.Text))`)
4. Return JSON.

### `DELETE /api/sessions/:id`

```
Response: 200 {"id": "<uuid>", "status": "stopped"}
Errors: 401, 403, 404
```

Handler steps:
1. Look up session, check ownership.
2. Update status to `stopping`.
3. Call `runner.Stop(ctx, container_id)` (best-effort — log and continue if it fails because the container may already be gone).
4. Call `runner.Remove(ctx, container_id)` (also best-effort).
5. `os.RemoveAll("/tmp/ap/secrets/" + session_id)`.
6. Update status to `stopped`, set `updated_at = NOW()`.
7. Return 200.

### Sessions table migration

```sql
-- 002_sessions.sql
-- Phase 2: minimal sessions table for the stub session API.
-- Phase 5 adds: expires_at, last_activity_at, heartbeat_at, billing_mode, tier.

CREATE TABLE IF NOT EXISTS sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_name    TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_id       TEXT NOT NULL,
    container_id   TEXT,                     -- nullable until runner.Run returns
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id  ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status   ON sessions(status);

-- Phase 2 enforces "1 active session per user" via this partial unique index.
-- Phase 5 adds a Redis SETNX layer on top for race resolution.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_one_active_per_user
    ON sessions(user_id)
    WHERE status IN ('pending', 'provisioning', 'running');
```

**Note:** Phase 1 already created an `agents` table with a similar shape (`container_id`, `model_provider`, `model_id`, `status`, partial unique index on the same three statuses). The CONTEXT D-26 explicitly calls for a NEW `sessions` table — they are different concepts: `agents` is the user's saved configuration of an agent (like a "saved Slack workspace"); `sessions` is one running container instance of an agent. **Plan should keep them separate** per CONTEXT direction. A future migration could backfill an `agent_id` foreign key from sessions → agents once Phase 4/5 fully populate the agents table.

## Runtime State Inventory

(This phase is greenfield code addition with no rename/refactor — the inventory is brief, but real items exist.)

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — sessions table is new, no migration of existing data needed. The `agents` table from Phase 1 baseline is empty. | None. |
| Live service config | None — Hetzner host already has Docker, Postgres, Redis, Temporal running from Phase 1. Phase 2 adds two new container images (`ap-base`, `ap-picoclaw`, `ap-hermes`) to the local image cache via `make build-recipes`. These need to be present before the API can spawn sessions. | Plan task: `make build-recipes` runs as part of bootstrap. CI/CD sequence: build images BEFORE starting the API. |
| OS-registered state | None | None. |
| Secrets/env vars | New env var `AP_DEV_BYOK_KEY` introduced. The Go API reads it at startup. Local dev: must be in the developer's shell before `go run ./cmd/server/`. CI: opt-in via repo secret if smoke test should run live; otherwise smoke test gracefully skips. | Plan task: document `AP_DEV_BYOK_KEY` in `.env.example` (already exists per Phase 1 STATE) with a comment "Phase 2 dev BYOK; Phase 3 replaces with encrypted vault." |
| Build artifacts | New: `agent-playground/ap-base:v0.1.0`, `agent-playground/ap-picoclaw:v0.1.0-c7461f9`, `agent-playground/ap-hermes:v0.1.0-5621fc4` Docker images in local cache. New: `/tmp/ap/secrets/<session_id>/` directories created at runtime. | Plan task: `make clean-recipes` to wipe the image cache for repro; `make smoke-test` cleans /tmp/ap/secrets at start. |

## Common Pitfalls

### Pitfall 1: tini supervising tmux + ttyd doesn't actually supervise
**What goes wrong:** You run `tini -- bash -c "ttyd ... & tmux ..."` and tini supervises only the bash, not its children. When ttyd dies, the bash sees no error and tini doesn't reap it.
**Why it happens:** tini's job is signal forwarding + zombie reaping, not service management. It only watches its direct child.
**How to avoid:** Use `tini -g --` (process group flag) so signals propagate to the whole group, AND put `wait` at the end of the entrypoint script so the bash blocks on its child processes. The entrypoint sketch above does this with `wait %1`.
**Warning signs:** `docker stop <container>` takes 10 seconds (the Docker default kill grace), then the container becomes a zombie. Or: ttyd dies and the container doesn't exit, but no longer responds to web terminal connections.

### Pitfall 2: FIFO writes block forever if there's no reader
**What goes wrong:** Handler does `runner.ExecWithStdin(ctx, id, []string{"sh","-c","cat > /run/ap/chat.in"}, msg)`, but the agent process inside the chat tmux window has already died (crashed during install, OOMed, etc.), so nothing is reading chat.in. The `cat` blocks forever.
**Why it happens:** POSIX FIFO semantics — open-for-write blocks until at least one reader has the FIFO open.
**How to avoid:** Use the `O_NONBLOCK` open mode (in shell: `exec 3>/run/ap/chat.in 2>/dev/null` returns immediately if no reader; check with `[ -p /run/ap/chat.in ] && [ "$(stat -c %Z /run/ap/chat.in)" ]`). Better: in Go, set a context deadline on the ExecWithStdin call so the whole exec aborts after `recipe.ChatIO.ResponseTimeout / 2`. Best: have the entrypoint shim hold both FIFOs open with `exec 3</run/ap/chat.in; exec 4>/run/ap/chat.out` BEFORE launching the agent — that way they are always "open" from the kernel's view, even if the agent dies, and writes will not block (they'll just be discarded).
**Warning signs:** First message hangs for the full 60s, then 504. Subsequent messages also hang.

### Pitfall 3: Hermes `chat -q` requires stdin to be a TTY
**What goes wrong:** Hermes detects pipe stdin and refuses to run, or prints "use a real terminal" and exits.
**Why it happens:** Per `hermes_cli/main.py` `_require_tty()` helper [CITED lines 50-65], some Hermes commands explicitly check `sys.stdin.isatty()` and exit if not.
**How to avoid:** **Verify whether `hermes chat -q` is one of the TTY-required commands.** The `_require_tty` function lists "tools, setup, model" as TTY-required. `chat -q` is plausibly a single-query mode that doesn't need TTY (since the question is on the command line and the response is on stdout), but this needs to be confirmed by running it in a fresh container during the first plan task. If it does require TTY, work around by using `docker exec -t` (allocate a pseudo-TTY) — moby/moby/client supports this via `ExecCreateOptions.Tty: true`.
**Warning signs:** First Hermes smoke test message returns "Error: hermes chat requires an interactive terminal" or hangs.

### Pitfall 4: Build of ap-base on macOS produces wrong-arch ttyd
**What goes wrong:** Developer on Apple Silicon runs `docker build` and Docker buildx auto-pulls `arm64` Debian, but the Dockerfile hardcodes `TTYD_ARCH=x86_64`, so ttyd binary is downloaded for the wrong arch and fails to exec at startup.
**Why it happens:** `curl … ttyd.x86_64` is hardcoded.
**How to avoid:** Use `ARG TTYD_ARCH` and set it via Docker buildx target platform, or detect arch in the Dockerfile: `RUN ARCH=$(dpkg --print-architecture) && case $ARCH in amd64) TTYD_ARCH=x86_64 ;; arm64) TTYD_ARCH=aarch64 ;; esac && curl …`.
**Warning signs:** `exec format error` at container start.

### Pitfall 5: `--read-only` rootfs breaks recipe install scripts
**What goes wrong:** Recipe Dockerfile's RUN steps work fine (they happen at build time). At runtime, the agent tries to `git clone`, write to `~/.cache`, `pip install` something, etc. — and gets EROFS.
**Why it happens:** `ReadOnlyRootfs: true` makes EVERYTHING read-only except the explicit Tmpfs mounts and bind-mounts.
**How to avoid:** The DefaultSandbox tmpfs map covers `/tmp` and `/run` only. Anything the agent needs to write at runtime — caches, config, output — must be either (a) in a tmpfs mount, (b) in a bind-mount from the host, or (c) in a Docker named volume. **For Phase 2, add `~/.hermes` and `~/.picoclaw` and `/work` as additional tmpfs mounts** in the recipe's ResourceOverrides (extend the Recipe struct to expose extra Tmpfs entries). Document that any new recipe MUST audit its write paths.
**Warning signs:** Agent crashes with `Permission denied` or `Read-only file system` errors during the first message processing.

### Pitfall 6: User-namespace remap breaks bind-mounted secrets
**What goes wrong:** Host file `/tmp/ap/secrets/<id>/anthropic_key` is mode 0600 owned by `apiuser` (uid 1000). Inside the container with `userns-remap` enabled, uid 10000 in the container maps to uid 110000 on the host. The agent (in-container uid 10000) tries to read /run/secrets/anthropic_key and gets EACCES because the host file is owned by 1000, not 110000.
**Why it happens:** userns-remap is enabled per Phase 1 install-docker.sh.
**How to avoid:** **Make the host secret file world-readable (0644) but located in a directory that's NOT world-traversable (0700 dir owned by apiuser)**. The directory perms protect against other host users; the file perms allow the userns-remapped container uid to read. OR: chmod the file to be owned by the userns-remap range (chown 110000:110000) — more correct but requires the API to know the userns base. Recommendation: **0644 file inside 0700 dir**, plus add a unit test that asserts the container can read.
**Warning signs:** Container starts, entrypoint runs, but `cat /run/secrets/anthropic_key` returns "Permission denied" and the agent dies because no API key is set.

### Pitfall 7: Bind-mount from host into a `--read-only` rootfs fails
**What goes wrong:** Phase 2 wants to bind-mount the secrets dir read-only into a read-only rootfs, but the bind-mount target `/run/secrets` doesn't exist in the image, so the mount fails with "no such file or directory."
**Why it happens:** Docker auto-creates bind-mount target directories only when the rootfs is writable. With `ReadonlyRootfs: true`, the create fails.
**How to avoid:** **Pre-create `/run/secrets` in the ap-base Dockerfile.** Add `RUN mkdir -p /run/secrets && chmod 0500 /run/secrets`. Then the bind-mount has a target to mount on. Note: `/run` itself becomes a tmpfs at runtime per the default sandbox, which means `/run/secrets` (created at build time) gets shadowed UNLESS the Tmpfs mount is at `/run/secrets` not `/run`. **Decision:** mount tmpfs at `/run/ap` (subdir, not /run), keep `/run/secrets` as a regular dir created at build time, and bind-mount on top.
**Warning signs:** runner.Run returns "create container: invalid mount config: source path does not exist" or "rootfs read-only."

## Code Examples

### Building a deterministic name (forward-compat with Phase 5)

```go
// Source: this research, derived from naming format spec in CONTEXT D-12 + SBX-09
import (
    "github.com/agent-playground/api/pkg/docker"
    "github.com/google/uuid"
)

// In session-create handler:
sessionID := uuid.New()
name := docker.BuildContainerName(userID, sessionID)
// → "playground-7c8f3e90-aab1-4d27-9e89-cf21b9c0b1a8-2f0a4d11-...-..."

opts := session.DefaultSandbox()
opts.Image = recipe.Image
opts.Name = name
opts.Env = buildEnvFromRecipe(recipe)
opts.Mounts = []string{
    "/tmp/ap/secrets/" + sessionID.String() + ":/run/secrets:ro",
}
containerID, err := runner.Run(ctx, opts)

// In Phase 5 reconciler:
out, _ := runner.client.ContainerList(ctx, container.ListOptions{
    Filters: filters.NewArgs(filters.Arg("name", "playground-")),
})
for _, c := range out {
    name := strings.TrimPrefix(c.Names[0], "/")
    userID, sessionID, err := docker.ParseContainerName(name)
    if err != nil { continue }
    // ...check DB, kill orphans, etc.
}
```

### Synchronous chat handler (FIFO mode, picoclaw)

```go
// Source: this research; uses Phase 1 runner.Exec + new ExecWithStdin helper
func (h *SessionHandler) postMessage(c echo.Context) error {
    // ... parse + auth + lookup session/recipe ...

    if recipe.ChatIO.Mode != recipes.ChatIOFIFO {
        return h.execMessage(c, sess, recipe, msg) // Hermes path
    }

    ctx, cancel := context.WithTimeout(c.Request().Context(), recipe.ChatIO.ResponseTimeout)
    defer cancel()

    // Write message + newline to FIFO
    payload := []byte(msg.Text + "\n")
    _, err := h.runner.ExecWithStdin(ctx, sess.ContainerID,
        []string{"sh", "-c", "cat >> /run/ap/chat.in"},
        bytes.NewReader(payload))
    if err != nil {
        return jsonErr(c, http.StatusInternalServerError, "fifo write failed", err)
    }

    // Read one line from FIFO output, polling with short-lived execs
    for {
        if err := ctx.Err(); err != nil {
            return jsonErr(c, http.StatusGatewayTimeout, "agent did not respond", err)
        }
        out, err := h.runner.Exec(ctx, sess.ContainerID,
            []string{"timeout", "5", "head", "-n", "1", "/run/ap/chat.out"})
        if err == nil && len(bytes.TrimSpace(out)) > 0 {
            return c.JSON(http.StatusOK, map[string]string{"text": string(bytes.TrimSpace(out))})
        }
        time.Sleep(100 * time.Millisecond)
    }
}
```

### Synchronous chat handler (Exec mode, Hermes)

```go
// Source: this research
func (h *SessionHandler) execMessage(c echo.Context, sess *Session, recipe *recipes.Recipe, msg MessageRequest) error {
    ctx, cancel := context.WithTimeout(c.Request().Context(), recipe.ChatIO.ResponseTimeout)
    defer cancel()

    cmd := append(slices.Clone(recipe.ChatIO.ExecCmd), msg.Text)
    out, err := h.runner.Exec(ctx, sess.ContainerID, cmd)
    if err != nil {
        if errors.Is(err, context.DeadlineExceeded) {
            return jsonErr(c, http.StatusGatewayTimeout, "agent did not respond", err)
        }
        return jsonErr(c, http.StatusInternalServerError, "exec failed", err)
    }
    text := stripANSI(strings.TrimSpace(string(out)))
    return c.JSON(http.StatusOK, map[string]string{"text": text})
}
```

## State of the Art

| Old approach | Current approach | When changed | Impact |
|---|---|---|---|
| MSV pattern: one Dockerfile per agent, agent baked into base | Generic `ap-base` + recipe overlays | Phase 2 (this) | Adds 1 image layer of indirection but enables N agents from the same base |
| `gotty` for in-container terminal | `ttyd` | 2017+ (gotty unmaintained) | Active maintenance, static binary, smaller |
| `nhooyr.io/websocket` / `gorilla/websocket` | `coder/websocket` | 2024+ (Coder fork) | Cleaner API, context-aware (Phase 5 will use; Phase 2 doesn't yet) |
| Long-lived agent process per message | Recipe-declared chat_io mode (FIFO vs exec-per-message) | Phase 2 (this research) | Allows mix-and-match per agent — picoclaw long-lived, Hermes per-message |
| Anthropic env vars baked into container | tmpfs-injected `/run/secrets/*_key` | Phase 2 → 3 (mechanism Phase 2, vault Phase 3) | Defends CRIT-2 |

## Environment Availability

| Dependency | Required by | Available | Version | Fallback |
|---|---|---|---|---|
| Docker Engine | Runner, image builds | ✓ (Phase 1) | 27.x+ | None — required |
| `docker buildx` | Multi-arch builds (optional) | ✓ (Docker Desktop default) | bundled | Single-arch build via plain `docker build` |
| `make` | `make build-recipes`, `make smoke-test` | ✓ (macOS + Hetzner host) | GNU make 3.8+ | Document raw shell commands as fallback |
| `git` | Recipe Dockerfiles clone upstream sources at build time | ✓ | any | None |
| `curl` | ttyd binary download in ap-base build | ✓ | any | wget |
| Postgres 17 | Migration + sessions table | ✓ (Phase 1) | 17.x | None |
| `AP_DEV_BYOK_KEY` env var (real Anthropic key) | Smoke test only | ✗ at research time (developer must set) | n/a | Smoke test skips cleanly if absent — see Validation Architecture |
| Internet access at build time | Cloning picoclaw + hermes from GitHub, downloading ttyd binary, apt-get | ✓ (developer + CI) | n/a | None — this is a hard requirement for the FIRST build; subsequent builds use Docker layer cache |

**Missing dependencies with no fallback:**
- A real Anthropic API key for the smoke test. Without it, the smoke test phase-gate cannot prove the hypothesis. **Plan task:** the smoke test makefile target detects `$AP_DEV_BYOK_KEY` is unset and prints "SKIPPED — set AP_DEV_BYOK_KEY to run the live smoke test" with exit 0 (so CI is green without a key). Local dev: developer sets the env var.

**Missing dependencies with fallback:**
- None.

## Validation Architecture

> Phase 2 has substantial new code surface (entrypoint shim, recipe Dockerfiles, runner.go field additions, session API, FIFO/exec bridges). Validation must catch failures at multiple sample points so the planner knows where bugs hide.

### Test Framework

| Property | Value |
|---|---|
| Framework (Go) | `testing` stdlib + `stretchr/testify` v1.11+ (already in go.mod) |
| Framework (image smoke) | `make` targets + bash assertions + `docker ps` / `docker exec` |
| Config file | `api/go.mod` (no separate test config) |
| Quick run command | `cd api && go test ./pkg/docker/ ./internal/recipes/ ./internal/session/ -count=1 -short` |
| Full suite command | `cd api && go test ./... -count=1` (includes the integration tests against a real Docker daemon) + `make smoke-test` (live API + curl + real Anthropic) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test type | Automated command | File exists? |
|---|---|---|---|---|
| **SBX-01** | ap-base has tini PID 1 | integration | `docker run --rm ap-base:v0.1.0 ps -p 1 -o comm` → assert `tini` | ❌ Wave 0 |
| **SBX-01** | tmux has chat + shell windows | integration | `docker run -d --name t ap-base; docker exec t tmux list-windows -t ap` → assert 2 lines | ❌ Wave 0 |
| **SBX-01** | ttyd binds to 127.0.0.1 | integration | `docker exec t ss -tlnp` → assert `127.0.0.1:7681` | ❌ Wave 0 |
| **SBX-02** | `RunOptions.NoNewPrivs` writes `no-new-privileges:true` to SecurityOpt | unit | `go test ./pkg/docker -run TestRunner_Run_AppliesNoNewPrivs` | ❌ Wave 0 |
| **SBX-02** | `RunOptions.ReadOnlyRootfs` writes `HostConfig.ReadonlyRootfs=true` | unit | `go test ./pkg/docker -run TestRunner_Run_AppliesReadOnlyRootfs` | ❌ Wave 0 |
| **SBX-02** | `RunOptions.Tmpfs` writes `HostConfig.Tmpfs` | unit | `go test ./pkg/docker -run TestRunner_Run_AppliesTmpfs` | ❌ Wave 0 |
| **SBX-02** | `RunOptions.CapDrop` writes `HostConfig.CapDrop` | unit | `go test ./pkg/docker -run TestRunner_Run_AppliesCapDrop` | ❌ Wave 0 |
| **SBX-02** | `RunOptions.SeccompProfile` writes `seccomp=<path>` to SecurityOpt | unit | `go test ./pkg/docker -run TestRunner_Run_AppliesSeccompProfile` | ❌ Wave 0 |
| **SBX-02** | Real container with `ReadOnlyRootfs=true` cannot write to `/etc` | integration | `go test ./pkg/docker -run TestRunner_Integration_ReadOnlyEnforced` | ❌ Wave 0 |
| **SBX-03** | `RunOptions.Memory/CPUs/PidsLimit` already wired Phase 1 | unit | Phase 1 test exists; no new test needed | ✅ existing |
| **SBX-05** | runner.go does NOT expose `Privileged` field | static | `grep -n Privileged api/pkg/docker/runner.go` → no match | ❌ Wave 0 (CI grep gate) |
| **SBX-09** | `BuildContainerName(u,s) → "playground-u-s"` | unit | `go test ./pkg/docker -run TestBuildContainerName` | ❌ Wave 0 |
| **SBX-09** | `ParseContainerName(name)` round-trips | unit | `go test ./pkg/docker -run TestParseContainerName_RoundTrip` | ❌ Wave 0 |
| **SBX-09** | `IsPlaygroundContainerName` matches both `/`-prefixed and bare | unit | `go test ./pkg/docker -run TestIsPlaygroundContainerName` | ❌ Wave 0 |
| **SES-01** | `POST /api/sessions` with valid recipe → 201 + sessions row + container | integration | `go test ./internal/session -run TestSessionCreate_Success` (mock runner) | ❌ Wave 0 |
| **SES-01** | Unknown recipe → 400 | unit | `go test ./internal/session -run TestSessionCreate_UnknownRecipe` | ❌ Wave 0 |
| **SES-01** | Same user creating second session → 409 | integration | `go test ./internal/session -run TestSessionCreate_OneActiveOnly` (real Postgres) | ❌ Wave 0 |
| **SES-01** | Missing `AP_DEV_BYOK_KEY` → 503 | unit | `go test ./internal/session -run TestSessionCreate_MissingSecret` | ❌ Wave 0 |
| **SES-04** | `DELETE /api/sessions/:id` → runner.Stop + Remove + status='stopped' | integration | `go test ./internal/session -run TestSessionDelete_Success` (mock runner) | ❌ Wave 0 |
| **SES-04** | Delete leaves no /tmp/ap/secrets dir | integration | Same test asserts os.Stat returns NotExist | ❌ Wave 0 |
| **CHT-01** | `POST /messages` (FIFO mode) writes to chat.in via exec | unit | `go test ./internal/session -run TestPostMessage_FIFOWrite` | ❌ Wave 0 |
| **CHT-01** | `POST /messages` (Exec mode) calls runner.Exec with appended argv | unit | `go test ./internal/session -run TestPostMessage_ExecMode` | ❌ Wave 0 |
| **CHT-01** | Timeout path returns 504 | unit | `go test ./internal/session -run TestPostMessage_Timeout` | ❌ Wave 0 |
| **(BYOK dev)** | Server reads AP_DEV_BYOK_KEY at start | unit | `go test ./internal/session -run TestSecretSource_DevEnv` | ❌ Wave 0 |
| **(BYOK dev)** | Secret file written 0600, dir 0700 | integration | `go test ./internal/session -run TestSecretSource_FilePerms` | ❌ Wave 0 |
| **(recipes)** | `recipes.AllRecipes["picoclaw"]` exists with expected shape | unit | `go test ./internal/recipes -run TestRecipes_PicoclawShape` | ❌ Wave 0 |
| **(recipes)** | `recipes.AllRecipes["hermes"]` exists with expected shape | unit | `go test ./internal/recipes -run TestRecipes_HermesShape` | ❌ Wave 0 |
| **(hypothesis)** | End-to-end picoclaw smoke test | manual / live | `make smoke-test` (gated on AP_DEV_BYOK_KEY) | ❌ Wave 0 |
| **(hypothesis)** | End-to-end Hermes smoke test | manual / live | `make smoke-test` (same target, both agents) | ❌ Wave 0 |
| **(hypothesis)** | No dangling `playground-*` containers after smoke test | integration | `make smoke-test` final assertion: `docker ps -a --filter name=playground- --format '{{.Names}}'` returns empty | ❌ Wave 0 |

**Test count target:** ~30 unit tests + ~10 integration tests (real Docker daemon, gated by `-short`) + 1 live smoke test (gated on `AP_DEV_BYOK_KEY`).

**Coverage target:** runner.go new fields → 100% (each field has at least one positive and one negative test); session handler → ≥85% (the 504 + 409 + 401 paths must be covered); recipes package → 100% (it's just two struct literals + a lookup function). Image-layer tests are not measured for line coverage but are covered by the integration suite.

### Sampling Rate

- **Per task commit:** `cd api && go test ./pkg/docker/ ./internal/recipes/ ./internal/session/ -count=1 -short` (under 10s)
- **Per wave merge:** `cd api && go test ./... -count=1` (~30s including integration tests against real Docker)
- **Phase gate:** Full suite green + `make smoke-test` passes for both agents (with AP_DEV_BYOK_KEY set) + a human eyeballs the curl output

### Wave 0 Gaps

All test files for Phase 2 are NEW. Wave 0 tasks must create:

- [ ] `api/pkg/docker/runner_test.go` — extend with subtests for SecurityOpt composition, ReadOnlyRootfs, Tmpfs, CapDrop, CapAdd, Runtime, NoNewPrivs (covers SBX-02 mapping)
- [ ] `api/pkg/docker/naming_test.go` — NEW file for BuildContainerName / ParseContainerName / IsPlaygroundContainerName (covers SBX-09)
- [ ] `api/internal/recipes/recipes_test.go` — NEW file for the two recipe literals (covers recipe shape forward-compat for Phase 4)
- [ ] `api/internal/session/handler_test.go` — NEW file for create/delete/message handlers, with a mock runner injected (covers SES-01, SES-04, CHT-01)
- [ ] `api/internal/session/secrets_test.go` — NEW file for the dev BYOK env-var → file-on-disk mechanism (covers BYOK dev)
- [ ] `api/internal/session/integration_test.go` — NEW file for real-Docker tests gated by `-short` (covers SES-01 one-active-only with real Postgres + real Docker)
- [ ] `Makefile` — add `build-recipes`, `smoke-test`, `clean-recipes` targets
- [ ] `scripts/smoke-test.sh` — NEW file driving the curl-based hypothesis proof for both agents (idempotent, prints clear pass/fail)
- [ ] `deploy/ap-base/Dockerfile` + `deploy/ap-base/entrypoint.sh` — NEW (covers SBX-01)
- [ ] `agents/picoclaw/Dockerfile` — NEW
- [ ] `agents/hermes/Dockerfile` + `agents/hermes/cli-config.yaml` — NEW

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|---|---|---|
| A1 | tini 0.19 has a `-g` (process group) flag that propagates SIGTERM to all child PIDs | ap-base Dockerfile sketch | Container shutdown is slow / orphan agent processes after stop. Mitigation: read tini man page in plan task; alternative is putting tini in its default mode and adding a trap in entrypoint.sh. |
| A2 | ttyd `--once` exits after the first client disconnect AND keeps the container alive (because the entrypoint shim's tmux+wait loop persists) | ap-base Dockerfile sketch | If `--once` causes the entrypoint wait loop to exit, the container dies after the first ttyd client. Mitigation: drop `--once` from Phase 2 (it's a Phase 5+ concern). |
| A3 | `mkfifo` works on Linux tmpfs | ap-base entrypoint sketch | If false, FIFO bridge is impossible on tmpfs and we'd need a regular file backing. **Mitigated:** Spike 3 already proved this works empirically (p99 = 0.19ms). |
| A4 | `hermes chat -q "<msg>"` does NOT require a TTY | Chat Bridge — Hermes | Smoke test fails with "requires interactive terminal" error. Mitigation: first plan task is to verify this in a fresh container; if false, use `docker exec -t` to allocate a pseudo-TTY. |
| A5 | picoclaw's interactive `picoclaw agent` mode emits responses to stdout in a way that's parseable when redirected from a FIFO (no prompt cruft mixed in) | Chat Bridge — picoclaw + picoclaw Specifics | Response parsing is brittle. Mitigation: Phase 2 plan should test FIFO bridge against picoclaw early and have fallback to `picoclaw agent -m` (per-message exec, like Hermes) ready. |
| A6 | Hermes upstream Dockerfile build steps work when layered on top of `ap-base` (debian:trixie-slim) instead of upstream's bare `debian:13.4` FROM | Hermes Specifics | Build fails because of missing apt deps that upstream installs in an earlier layer. Mitigation: copy upstream's apt install line verbatim into the recipe overlay; do not optimize. |
| A7 | userns-remap on the Hetzner host (Phase 1 install-docker.sh) is configured with the default subuid/subgid range starting at 100000 | BYOK Dev Injection — Pitfall 6 | File-perm strategy may need adjustment if range is different. Mitigation: plan task reads `/etc/subuid` for the dockremap user and prints the actual range during the smoke test sanity check. |
| A8 | The `agents` table from Phase 1's baseline migration is conceptually distinct from the new `sessions` table, NOT a duplicate | Sessions Migration | Plan creates two overlapping tables. Mitigation: surface this to the user in planning — CONTEXT D-26 explicitly says "new sessions table," but a planner should confirm the user wants both tables vs renaming `agents` to `sessions`. (See Open Question 1 below.) |
| A9 | Hermes v0.9.0 release tag is the latest stable and exists | Hermes Specifics | Plan pins to a non-existent or pre-release tag. Mitigation: plan task runs `gh release list -R NousResearch/hermes-agent -L 5` at writing time and pins to whichever tag (or HEAD SHA) is current. |
| A10 | Debian trixie's `tini` package version (0.19.0-3 or similar) is current and includes the `-g` flag | ap-base Dockerfile | Older versions may not. Mitigation: `apt-cache policy tini` in plan task; install from official tini GitHub release if Debian's is too old. |
| A11 | Hermes' `cli-config.yaml` `model.provider: anthropic` value (vs the example's "auto") will route requests to Anthropic without needing the `hermes setup` interactive wizard | Hermes Specifics | Hermes refuses to start without an interactive setup. Mitigation: plan task runs the recipe in a fresh container and verifies `hermes chat -q "test"` works without prior `hermes setup`. If it doesn't, bake the post-setup state into the image at build time by running `hermes setup --provider anthropic --no-prompt` (verify that flag exists) or copy a pre-baked profile dir. |
| A12 | `RunOptions.Network` field already exists in Phase 1 runner.go and maps to `HostConfig.NetworkMode` (so we don't need to add it as a "new" field) | RunOptions → HostConfig Mapping | If Phase 1 used a different name, the new field list is wrong. **Verified at research time:** read runner.go lines 60-76; field is named `Network` and maps via `container.NetworkMode(opts.Network)` on line 156. Confirmed. |

## Open Questions

1. **`sessions` table vs extending the existing `agents` table**
   - **What we know:** Phase 1 baseline migration (`001_baseline.sql`) created an `agents` table with: `id, user_id, name, agent_type, model_provider, model_id, key_source, status, webhook_url, container_id, ssh_port, config jsonb, created_at, updated_at` AND a partial unique index on `(user_id) WHERE status IN ('provisioning','ready','running')`. CONTEXT D-26 explicitly calls for a new `sessions` table with overlapping fields.
   - **What's unclear:** Are these intentionally two distinct concepts (agent = saved configuration; session = runtime instance)? Or did CONTEXT writer not realize Phase 1 already shipped `agents`?
   - **Recommendation:** Honor CONTEXT D-26 — create the new `sessions` table. Note in the plan that `agents` will gain a foreign key from sessions in Phase 4 once the recipe → agent → session chain is fully wired. Surface this for the user during /gsd-plan-phase if they want to revisit.

2. **What runtime does Phase 2 actually use — runc or none specified?**
   - **What we know:** D-13 says `Runtime: ""` (runc default).
   - **What's unclear:** On the Hetzner host, is the default runtime `runc` or has Phase 1 install-docker.sh changed the default? Spike 4 (gVisor install) is still pending, so we should assume runc.
   - **Recommendation:** Pass empty string and let dockerd pick default. Add a smoke test sanity assertion: `docker info | grep "Default Runtime"` should print `runc`. If not, the plan needs to explicitly pass `Runtime: "runc"`.

3. **How aggressive should the Hermes image cache be in CI?**
   - **What we know:** Hermes upstream image is ~3GB; first build is 10+ minutes including Playwright + npm + uv pip install.
   - **What's unclear:** Will Phase 2 ship a CI workflow that builds the recipe image on every PR? If yes, build time becomes a real constraint.
   - **Recommendation:** Phase 2 CI runs `go test` on every PR but `make build-recipes` only on a nightly cron + on-demand label. Smoke test runs against pre-built images that the CI nightly job pushed to a GHCR cache.

4. **Does picoclaw's `agent --session cli:default` interactive mode have a "machine-readable" output mode that strips the readline prompt?**
   - **What we know:** The cobra command exposes `--debug`, `--message`, `--session`, `--model`. There is no `--no-prompt` or `--json` flag in the snippet we read.
   - **What's unclear:** Reading more of `cmd/picoclaw/internal/agent/` may reveal a tagged-line output mode (e.g. `>>> response` markers) that makes FIFO parsing unambiguous.
   - **Recommendation:** Plan task: read all files under `/Users/fcavalcanti/dev/picoclaw/cmd/picoclaw/internal/agent/` and document the actual interactive output format. If it's pure free-form text + a `picoclaw> ` prompt, use the simpler `picoclaw agent -m` per-message mode for Phase 2 (same code path as Hermes).

5. **What's the actual UID/GID for the Hetzner box's `dockremap` userns base?**
   - **What we know:** Phase 1's `install-docker.sh` enables userns-remap with default Docker config (`/etc/subuid` and `/etc/subgid` get a `dockremap:100000:65536` entry on Debian).
   - **What's unclear:** Has the operator manually changed it?
   - **Recommendation:** Plan task: as part of the smoke test setup, `cat /etc/subuid /etc/subgid` and document the actual base. Use the base + the in-container UID (10000) to set the host-side secret file ownership correctly.

## Sources

### Primary (HIGH confidence)

- [`api/pkg/docker/runner.go`](file:///Users/fcavalcanti/dev/agent-playground/api/pkg/docker/runner.go) — Phase 1 ported runner; current `RunOptions` shape, validation helpers, SDK call patterns
- [`api/pkg/migrate/sql/001_baseline.sql`](file:///Users/fcavalcanti/dev/agent-playground/api/pkg/migrate/sql/001_baseline.sql) — existing `agents` table + partial unique index (informs the sessions migration shape)
- [`/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/Dockerfile`](file:///Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/Dockerfile) — MSV's proven entrypoint + privilege-drop pattern (75 lines, ~95% portable)
- [`/Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/entrypoint.sh`](file:///Users/fcavalcanti/dev/meusecretariovirtual/infra/picoclaw/entrypoint.sh) — gosu drop + permission fix pattern (203 lines; lines 13-30 are the verbatim port target)
- [`/Users/fcavalcanti/dev/picoclaw/docker/Dockerfile`](file:///Users/fcavalcanti/dev/picoclaw/docker/Dockerfile) — picoclaw upstream Dockerfile (multi-stage Go builder + alpine runtime; the build half is portable)
- [`/Users/fcavalcanti/dev/picoclaw/cmd/picoclaw/internal/agent/command.go`](file:///Users/fcavalcanti/dev/picoclaw/cmd/picoclaw/internal/agent/command.go) — verified picoclaw `agent` cobra flags including `--message` for non-interactive mode
- [`~/go/pkg/mod/github.com/moby/moby/api@v1.54.1/types/container/hostconfig.go`](file:///Users/fcavalcanti/go/pkg/mod/github.com/moby/moby/api@v1.54.1/types/container/hostconfig.go) — verified verbatim field names: `Memory`, `NanoCPUs`, `PidsLimit`, `Binds`, `NetworkMode`, `AutoRemove`, `CapAdd`, `CapDrop`, `ReadonlyRootfs`, `SecurityOpt`, `Tmpfs`, `Runtime`, `Resources` (lines 373-457)
- [`NousResearch/hermes-agent/cli-config.yaml.example`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/cli-config.yaml.example) — verified `model.provider`, `terminal.backend`, `platform_toolsets` keys; messaging gateways are NOT activated by config
- [`NousResearch/hermes-agent/cli.py`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/cli.py) — verified `-q "your question"` single-query mode in lines 1-12 + main() argparse around line 9787
- [`NousResearch/hermes-agent/hermes_cli/main.py`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/hermes_cli/main.py) — verified `hermes gateway` is a subcommand (lines 5-25); `_require_tty()` check (lines 50-65) for the assumption-flagged TTY question
- [`NousResearch/hermes-agent/Dockerfile`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/Dockerfile) — verified Python 3.13 + uv + Debian 13.4 + Playwright/npm/ffmpeg/ripgrep apt deps + tianon/gosu privilege-drop pattern
- [`NousResearch/hermes-agent/docker/entrypoint.sh`](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/docker/entrypoint.sh) — verified gosu drop pattern + config bootstrap pattern
- [`.planning/research/SPIKE-REPORT.md`](file:///Users/fcavalcanti/dev/agent-playground/.planning/research/SPIKE-REPORT.md) — Spike 1 (proxy honoring), Spike 2 (chat_io modes for picoclaw), Spike 3 (FIFO RTT p99 = 0.19ms PASS)
- [`.planning/phases/01-foundations-spikes-temporal/01-02-SUMMARY.md`](file:///Users/fcavalcanti/dev/agent-playground/.planning/phases/01-foundations-spikes-temporal/01-02-SUMMARY.md) — Phase 1 runner ported to moby/moby/client v0.4.0; established mock injection pattern
- GitHub API `repos/tsl0922/ttyd/releases/latest` — verified ttyd 1.7.7 (2024-03-30) ships static binaries for x86_64, aarch64, arm, mips, etc.
- GitHub API `repos/NousResearch/hermes-agent/commits?per_page=1` — verified HEAD SHA `5621fc4...` (2026-04-14)

### Secondary (MEDIUM confidence)

- ttyd README at https://tsl0922.github.io/ttyd/ — flag list (`--port`, `--interface`, `--writable`, `--max-clients`, `--once`); not directly fetched in this research, references rely on prior knowledge of ttyd 1.7.x behavior. Plan task: verify against ttyd 1.7.7 `--help` output.
- tini man page semantics for `-g` flag — assumed from tini docs; not freshly fetched. Plan task: verify against `tini --help` in a fresh container.
- Docker security-opt syntax (`no-new-privileges:true`, `seccomp=...`) — well-established Docker convention but not freshly cited from docs in this research.

### Tertiary (LOW confidence)

- Exact build time + image size for `ap-hermes` (~3GB, 10+ min) — extrapolated from the Dockerfile's apt + npm + uv steps; needs empirical verification on first build.
- Hermes' behavior when launched without prior `hermes setup` interactive run — assumed config-only setup is sufficient; planner must verify in plan task A11.

## Metadata

**Confidence breakdown:**
- Standard stack (Go libs, image deps, ttyd version): **HIGH** — every version verified live
- ap-base Dockerfile + entrypoint sketch: **MEDIUM** — ports verified MSV pattern + verified ttyd binary, but tmux supervision wiring is plausible-not-tested
- runner.go field mapping: **HIGH** — every HostConfig field name verified verbatim against the Go module on disk
- picoclaw recipe: **HIGH** — local source + upstream Dockerfile both available
- Hermes recipe: **MEDIUM-HIGH** — upstream Dockerfile + cli-config + cli.py all verified; first build will need iteration
- Chat bridges: **HIGH** for Hermes (single-query mode confirmed); **MEDIUM** for picoclaw (FIFO mechanism proven Spike 3, but interaction with picoclaw's specific stdout format is unverified)
- Session API + migration: **HIGH** — straightforward extension of Phase 1 patterns
- BYOK injection: **HIGH** — pure file IO + bind mount + entrypoint shim, all proven techniques
- Smoke test feasibility: **MEDIUM** — depends on real Anthropic key being available + Hermes responding within 120s

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 — Hermes is fast-moving (HEAD SHA dated literally hours before this research); pin to a release tag like v0.9.0 if the planner wants stability over recency. picoclaw HEAD is 2 weeks old, more stable. ttyd is 2 years old and stable.
