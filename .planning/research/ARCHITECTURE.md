# ARCHITECTURE — Agent Playground

**Researched:** 2026-04-11
**Confidence:** MEDIUM-HIGH (MSV reference verified; some library choices flagged for Phase-0 spike)

## 1. System Topology

```
                        Hetzner Dedicated (one host)
  ┌────────────────────────────────────────────────────────────────────┐
  │                                                                    │
  │  ┌────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
  │  │  Next.js   │───▶│   Go API (Echo)  │───▶│  Postgres (pgx)  │   │
  │  │  (SSR/CSR) │◀───│  + WS hub        │    │  + Redis         │   │
  │  └────────────┘    └─────────┬────────┘    └──────────────────┘   │
  │       ▲ wss              gRPC│ /unix sock                          │
  │       │                       ▼                                    │
  │       │               ┌──────────────────┐                         │
  │       │               │ Session          │                         │
  │       │               │ Orchestrator     │──── docker CLI ───┐    │
  │       │               │ (Go service)     │                    │    │
  │       │               └──────┬───────────┘                    ▼    │
  │       │                      │                       ┌──────────┐  │
  │       │                      ▼                       │ Docker   │  │
  │       │              ┌───────────────┐               │ daemon   │  │
  │       │              │ Recipe Runner │──────────────▶│ (host)   │  │
  │       │              │ (Go pkg)      │               └────┬─────┘  │
  │       │              └───────────────┘                    │        │
  │       │                                                    ▼        │
  │       │           ┌────────────────────────────────────────────┐   │
  │       │           │  Per-user agent container                  │   │
  │       │           │  ┌────────┐ ┌──────────┐ ┌──────────────┐ │   │
  │       └───wss─────│──│ ttyd   │ │ tmux 0:  │ │ agent stdio  │ │   │
  │       (terminal)  │  │ :7681  │ │ chat     │ │ (chat pane)  │ │   │
  │                   │  └────────┘ │ tmux 1:  │ └──────┬───────┘ │   │
  │                   │             │ shell    │        │         │   │
  │                   │             └──────────┘        │         │   │
  │                   │   model API calls ──────────────┘         │   │
  │                   │            │                              │   │
  │                   │            ▼                              │   │
  │                   │  HTTP_PROXY=host.docker.internal:8088     │   │
  │                   └────────────┬──────────────────────────────┘   │
  │                                ▼                                   │
  │                       ┌────────────────┐                           │
  │                       │ Model Proxy    │──── upstream ───▶ OAI/    │
  │                       │ (LiteLLM       │                   Anth/   │
  │                       │  proxy, host   │                   OR      │
  │                       │  service :8088)│                           │
  │                       └────────┬───────┘                           │
  │                                │ usage events                      │
  │                                ▼                                   │
  │                          Postgres (credits)                        │
  └────────────────────────────────────────────────────────────────────┘
```

**MSV pattern reuse:** MSV's `api/pkg/docker/runner.go` shells out to `docker` CLI (stop/restart/logs) with strict ID/arg validation. Reuse that pattern verbatim — it works, it's audit-friendly, and avoids vendoring the Docker SDK. Add `run`, `exec`, `cp`, `kill`, `inspect`, `volume create/rm` wrappers in the same style. Confidence: HIGH (verified in source).

## 2. Component Boundaries

| # | Component | Language | Process | Talks to | Protocol |
|---|-----------|----------|---------|----------|----------|
| 1 | **Web UI** | Next.js / React | systemd unit | Go API | HTTPS + WSS |
| 2 | **Go API** | Go (Echo) | systemd unit | Postgres, Redis, Orchestrator | HTTP, pgx, redis-go, in-process |
| 3 | **Session Orchestrator** | Go pkg in API binary | in-process goroutine pool | Docker daemon, Postgres, Redis | docker CLI, SQL, redis |
| 4 | **Recipe Runner** | Go pkg | called by Orchestrator | Docker, filesystem (`agents/`) | exec.Command, file IO |
| 5 | **Model Proxy** | LiteLLM Proxy (Python) OR custom Go | systemd unit, port 8088, host-only bind | Postgres (usage), upstream model APIs | HTTP |
| 6 | **In-container PTY mux** | tmux + ttyd | inside each user container | wss to Go API hub | websocket |
| 7 | **Postgres** | postgres 16 | systemd / docker | API, Orchestrator, Proxy | TCP 5432 (loopback) |
| 8 | **Redis** | redis 7 | systemd / docker | API (locks, cache, pubsub) | TCP 6379 (loopback) |
| 9 | **Object store** | MinIO (S3-compat) | docker on host | Orchestrator (volume snapshots) | S3 |

**Key boundary decision:** Orchestrator is an in-process Go package inside the API binary, not a separate microservice. MSV does the same — `internal/service/container_service.go` lives next to the HTTP handlers. One binary, one deploy unit, simpler ops. Split out only if scaling demands it.

## 3. Hot Path Data Flows

### 3.1 create-session

```
Browser POST /api/sessions {agent: "openclaw", model: "anthropic/claude-sonnet-4", key_source: "byok", api_key: "sk-..."}
  │
  ▼
Go API handler
  1. JWT middleware → user_id
  2. Credit/BYOK check (poken_service equivalent)
  3. SELECT FROM sessions WHERE user_id=$1 AND status='active'  -- one-active invariant
     If exists → 409 Conflict (or auto-reuse if same agent+model)
  4. Acquire Redis lock SETNX session:create:{user_id} EX 60
  5. INSERT session row (status='provisioning')
  6. orchestrator.Spawn(ctx, SessionSpec{...})  -- BLOCKING in goroutine, status updates streamed
  ▼
Orchestrator.Spawn:
  a. recipe := recipeRunner.Resolve("openclaw")        -- reads agents/openclaw/recipe.yaml
  b. volume := dockerCLI.VolumeCreate("ap-vol-{user_id}")   -- if persistent tier
  c. envs := buildEnv(recipe, model, byok_key, proxy_url)
  d. containerID := dockerCLI.Run(recipe.image, envs, mounts, --network ap-net, --label ap.user={uid})
  e. recipeRunner.Execute(containerID, recipe.install_steps)
  f. recipeRunner.Launch(containerID, recipe.launch_cmd)  -- spawns tmux session inside
  g. healthcheck loop (poll ttyd port + agent ping)
  h. UPDATE session SET status='ready', container_id=$1, ttyd_port=$2
  ▼
Response: {session_id, ws_url: "/api/sessions/{id}/stream", terminal_url: "/api/sessions/{id}/tty"}
```

### 3.2 send-chat-message

```
Browser → wss /api/sessions/{id}/stream
  │
  ▼
Go API WS handler
  1. JWT validation, session ownership check
  2. Subscribe to redis pubsub: chan session:{id}:chat:out
  3. Loop:
     - WS recv → write to docker exec stdin of tmux pane "chat" (or use named pipe inside container)
     - pubsub recv → WS send to browser
```

The chat pane in tmux runs the agent attached to a named pipe (`/work/.ap/chat.in` → stdin, `/work/.ap/chat.out` ← stdout). The orchestrator runs a tiny `docker exec` shim that reads/writes those pipes and republishes to Redis pubsub. This decouples WS connections from container lifetime — reconnecting browser does not lose state.

### 3.3 open-terminal

```
Browser → wss /api/sessions/{id}/tty
  │
  ▼
Go API reverse-proxies wss to container's ttyd at 127.0.0.1:{allocated_port}
```

ttyd runs inside the container on a host-bound port (`-p 127.0.0.1:N:7681`), allocated at spawn time and recorded in the sessions row. The Go API does a websocket proxy. Auth lives in the Go API; ttyd runs without its own auth (`-W` write-enabled, no credentials), only reachable via loopback. Confidence: HIGH (ttyd is the standard pattern; LinuxServer.io ships it; verified in docs).

### 3.4 meter-token-usage (platform-billed only)

```
Inside container: agent calls https://api.anthropic.com/v1/messages
  │
  │ HTTP_PROXY=http://host.docker.internal:8088 (set by orchestrator)
  ▼
LiteLLM Proxy on host
  1. Validates virtual key (one per session, minted at spawn)
  2. Maps virtual key → real provider key from vault
  3. Forwards to upstream (anthropic/openai/openrouter)
  4. Response: parses {usage: {input_tokens, output_tokens}}
  5. Computes cost via configured price table
  6. POST to Postgres usage_events table (LiteLLM has built-in pg logging)
  7. Atomic UPDATE users SET credit_balance = credit_balance - $cost WHERE id=$uid
  8. If balance < 0 → API/orchestrator polls usage_events and triggers session pause
```

For BYOK, the proxy is bypassed entirely — orchestrator injects `ANTHROPIC_API_KEY` (etc.) directly into the container env and unsets `HTTP_PROXY`. Zero billing touch. Confidence: HIGH on LiteLLM capability (verified — LiteLLM Proxy supports virtual keys, budgets, postgres logging, callback hooks); MEDIUM on whether agents respect HTTP_PROXY for HTTPS traffic — some agents use Node fetch which honors `HTTPS_PROXY`, others use raw TLS. **Phase-0 spike required** per agent: confirm HTTPS_PROXY honored, otherwise force base URL override (`ANTHROPIC_BASE_URL=http://host.docker.internal:8088`, which all major SDKs support and is more reliable than HTTP_PROXY).

## 4. Session Orchestrator (detailed)

Single Go package `internal/orchestrator/`. Public surface:

```go
type Orchestrator interface {
    Spawn(ctx context.Context, spec SessionSpec) (*Session, error)
    Get(ctx context.Context, sessionID string) (*Session, error)
    Stop(ctx context.Context, sessionID string, reason string) error
    Pause(ctx context.Context, sessionID string) error  // for credit exhaustion
    AttachChat(ctx context.Context, sessionID string) (io.ReadWriteCloser, error)
    ProxyTTY(ctx context.Context, sessionID string) (string, error)  // returns loopback url
    ListByUser(ctx context.Context, userID string) ([]*Session, error)
}
```

**One-active invariant** enforced at TWO layers:
1. Postgres `UNIQUE (user_id) WHERE status IN ('provisioning','ready','running')` partial index — hard guarantee.
2. Redis `SETNX session:create:{user_id}` lock — prevents two concurrent spawn requests racing past the SELECT.

**Volume strategy:**
- Free tier: `--rm`, no volume, container destroyed on stop.
- Paid tier: named volume `ap-vol-{user_id}` mounted at `/work`. Survives container recreation. Snapshotted to MinIO nightly via `docker run --rm -v ap-vol-X:/src busybox tar c /src | mc pipe ...`.

**Idle timeout:** Each session row has `last_activity_at`, updated by:
- WS message (chat or tty input)
- Heartbeat ping from inside container (cron in tmux pane)

A scheduler goroutine in the API (mirror MSV's `service/scheduler.go`) runs every 60s, finds sessions where `now() - last_activity_at > tier.idle_ttl`, calls `Stop`. Free tier 15min, paid tier 4h, defaults configurable.

**Resource limits per container** (set on `docker run`):
```
--cpus=1.5 --memory=2g --memory-swap=2g --pids-limit=512
--security-opt no-new-privileges
--cap-drop ALL --cap-add CHOWN --cap-add SETUID --cap-add SETGID
--read-only --tmpfs /tmp:size=256m
--network ap-net  (custom bridge, no internet except via proxy if metered)
```

For the generic-bootstrap path (untrusted git URL), add `--user 10001:10001` and run inside a gVisor runtime (`--runtime=runsc`) if available. Confidence: MEDIUM — gVisor on Hetzner dedicated is doable but adds setup; flag as a Phase-3 hardening item.

## 5. Recipe Runner

Recipe lives at `agents/<name>/recipe.yaml`. Schema (proposed):

```yaml
# agents/openclaw/recipe.yaml
schema: ap.recipe/v1
name: openclaw
display_name: OpenClaw
homepage: https://github.com/openclaw/openclaw
license: MIT

base:
  image: node:22-bookworm-slim          # or "ubuntu:24.04"
  workdir: /work
  user: ap                              # created by base layer
  packages:                             # apt packages baked into base
    - git
    - curl
    - python3

source:
  type: git                             # git | npm | pip | docker_image
  url: https://github.com/openclaw/openclaw
  ref: main                             # branch | tag | sha
  path: .                               # subdir to cd into

install:
  - run: npm ci
    timeout: 300s
  - run: npm run build
    timeout: 600s
    optional: true

env:
  required:
    - name: MODEL_API_KEY
      maps_to: ANTHROPIC_API_KEY        # or dynamic based on model.provider
  optional:
    - name: OPENCLAW_LOG_LEVEL
      default: info

models:
  supported_providers: [anthropic, openai, openrouter]
  base_url_env:                         # env var the agent reads for proxy override
    anthropic: ANTHROPIC_BASE_URL
    openai: OPENAI_BASE_URL
    openrouter: OPENROUTER_BASE_URL

launch:
  command: ["node", "dist/cli.js", "--mode", "stdio"]
  pty: true
  chat_io:                              # how the chat UI talks to it
    mode: stdio                         # stdio | http | named_pipe
  ready_check:
    type: log_match
    pattern: "OpenClaw ready"
    timeout: 30s

healthcheck:
  command: ["node", "dist/cli.js", "--ping"]
  interval: 30s
  failure_threshold: 3

resources:                              # tier overrides
  free:
    cpu: 0.5
    memory: 1g
  paid:
    cpu: 1.5
    memory: 2g

tested_at: 2026-04-11
tested_by: pico-test-rig
```

The runner has two modes:

1. **Deterministic mode** — `recipe.yaml` exists. Runner parses, validates against JSON-Schema (committed in `agents/_schema/recipe.schema.json`), executes `install` steps via `docker exec`, then `launch` via `docker exec` inside tmux pane named `chat`.

2. **Bootstrap mode** — git URL only, no recipe. Runner:
   1. Spins a base container (`ap-base:bootstrap`) with Claude Code preinstalled and the user's BYOK key (or proxy creds).
   2. Mounts a templated bootstrap prompt at `/prompt.md`:
      ```
      You are bootstrapping an unknown coding agent at {{.RepoURL}}.
      Read README, package.json/pyproject.toml/etc. Determine:
      1. base image / runtime
      2. install commands
      3. launch command and stdio interface
      Install it. Verify it runs. Then EMIT a recipe.yaml conforming to ap.recipe/v1
      schema (see /schema/recipe.schema.json) at /work/.ap/recipe.yaml.
      Do NOT exit until either recipe.yaml is written and validated, or you have
      determined this repo cannot be supported.
      ```
   3. Claude Code runs inside that container, drives install, writes recipe.yaml.
   4. Runner reads the emitted recipe, validates, then either: (a) caches to `agents/_cache/{repo_hash}/recipe.yaml` for that user/session, (b) optionally PRs it to the catalog after human review.
   5. Subsequent sessions for the same repo hit deterministic mode.

Confidence: HIGH on schema design (standard pattern); MEDIUM on bootstrap reliability — Claude Code works for this exact use case but unknown repos will fail ~30% of the time. Plan for a "bootstrap failed, here's the log" UX path.

## 6. Terminal + Chat Simultaneous Access (the contention problem)

**The trap:** if you give the agent ONE PTY and try to attach both web-tty and chat to it, every keystroke from one shows up in the other and the agent receives interleaved garbage.

**Solution: tmux with TWO panes inside the container.**

```
Container init script (PID 1 = tini):
  $ tmux new-session -d -s ap -n main
  $ tmux send-keys -t ap:main 'mkfifo /work/.ap/chat.in /work/.ap/chat.out' C-m
  $ tmux send-keys -t ap:main 'exec <agent launch cmd> <>/work/.ap/chat.in >/work/.ap/chat.out 2>&1' C-m
  $ tmux new-window -t ap -n shell 'bash'
  $ ttyd -p 7681 -W tmux attach -t ap:shell
```

Now:
- **Chat UI** writes to `/work/.ap/chat.in` and reads from `/work/.ap/chat.out` via `docker exec` (or a small Go shim that holds the FDs open and republishes to Redis pubsub). It does NOT touch a PTY at all — the agent's stdio is named pipes, not a terminal.
- **Web terminal** connects to ttyd, which attaches the user to tmux window `shell` — a regular bash session in the SAME container with the SAME `/work` filesystem. User can `cd /work && ls` and see what the agent is doing on disk.
- Power user can also `tmux attach -t ap:main` from inside the shell window to spectate the agent pane (read-only mode optional).

**Why named pipes for chat instead of a second PTY:**
- Agents in "stdio mode" (most CLI agents) don't need terminal capabilities; they need line-oriented JSON or text.
- Pipes survive WS reconnects (the pipe holds buffered output until the chat shim reads it).
- No PTY contention because there's only one PTY (tmux's), and chat doesn't use it.

**Fallback:** if a specific agent demands a real TTY for chat (rare — some agents do TUI), the recipe sets `chat_io.mode: tmux_pane` and the chat UI talks to tmux pane `main` via `tmux pipe-pane`. Slower path, but supported.

Confidence: HIGH — tmux + named pipes + ttyd is a standard combo; verified each piece works independently. Spike in Phase 0 to confirm latency on a real agent.

## 7. Model Proxy / Metering Layer

**Recommendation: LiteLLM Proxy as a host service on `127.0.0.1:8088`, single instance shared across all containers.**

Why LiteLLM over custom Go proxy:
- Already supports OpenAI, Anthropic, OpenRouter, Bedrock, Vertex, etc.
- Virtual API keys with per-key budgets and TPM/RPM limits.
- Postgres logging built in (writes `LiteLLM_SpendLogs`).
- Cost calculation per model with maintained price table.
- Callback hooks for custom logic (Slack alerts, custom DB writes).
- Active project, used in production.

Why NOT a sidecar per container:
- ~50MB Python process per user × 1000 users = 50GB RAM gone. Brutal.
- Single host service with virtual keys per session is the standard LiteLLM deployment pattern.

Why not pure custom Go:
- Maintaining per-provider request/response shape parity is a never-ending tax.
- Cost tables drift weekly.
- LiteLLM does this work for free.

**Wire-up:**
1. Orchestrator on session spawn → LiteLLM admin API: create virtual key with `max_budget = remaining_credits`, metadata `{user_id, session_id}`.
2. Inject into container env: `ANTHROPIC_BASE_URL=http://host.docker.internal:8088`, `ANTHROPIC_API_KEY=sk-litellm-{virtual_key}`. Same for OpenAI/OpenRouter base URLs.
3. Container network: `--add-host=host.docker.internal:host-gateway` and bridge network with no default route OR with masquerade allowed only for the proxy IP.
4. LiteLLM logs each call to Postgres → trigger or polling job decrements `users.credit_balance` and writes to `usage_events`.
5. On credit exhaustion: LiteLLM returns 429 (built-in budget enforcement) → agent sees error → orchestrator's poller marks session paused → frontend prompts top-up.

**BYOK path:** entirely bypasses proxy. Orchestrator injects user's raw key, no `*_BASE_URL` override. LiteLLM is not involved. Zero billing surface.

Confidence: HIGH on LiteLLM capability set; MEDIUM on the host-vs-sidecar choice surviving until 1000 users (latency, single point of failure). **Mitigation:** run LiteLLM under systemd with auto-restart, plan for 2-instance HA with shared Postgres if it ever becomes the bottleneck.

## 8. Data Stores

| Store | Purpose | Schemas / keys |
|-------|---------|---------------|
| **Postgres** | Source of truth | `users`, `oauth_identities`, `sessions`, `containers`, `volumes`, `recipes` (cached metadata), `credit_ledger`, `usage_events`, `stripe_events`, `byok_keys` (encrypted), `audit_log` |
| **Redis** | Locks, cache, pubsub | `session:create:{uid}` SETNX lock; `session:{id}:chat:out` pubsub; `recipe:{name}:meta` cache; `idle:{sid}` TTL keys |
| **MinIO (S3)** | Volume snapshots | `ap-volumes/{user_id}/{date}.tar.zst`; recipe cache for bootstrap-discovered repos |
| **Filesystem** | Recipe catalog | `agents/<name>/recipe.yaml`, `agents/<name>/Dockerfile`, `agents/_schema/recipe.schema.json`, `agents/_cache/{repo_hash}/` |
| **LiteLLM Postgres** | Usage logs | `LiteLLM_SpendLogs`, `LiteLLM_VerificationToken` (can share the main Postgres instance, separate schema) |

No need for: Kafka, RabbitMQ, ClickHouse, Vault (use SOPS or pgcrypto for byok_keys encryption), Kubernetes.

## 9. Build Order / Minimum Cut

**Minimum end-to-end flow** ("pick openclaw + claude-sonnet via BYOK and chat with it"):

| # | Component | Why required | Effort |
|---|-----------|--------------|--------|
| 1 | Postgres + migrations (`users`, `sessions`, `byok_keys`) | Persist state | S |
| 2 | Go API skeleton (Echo) + JWT + Google OAuth | Auth gate | M |
| 3 | `pkg/docker/runner.go` (port from MSV) extended with `Run`, `Exec`, `Inspect`, `VolumeCreate` | Talk to Docker | S |
| 4 | Recipe loader + JSON-Schema validator | Read `agents/openclaw/recipe.yaml` | S |
| 5 | `agents/openclaw/recipe.yaml` + `agents/_base/Dockerfile` (node22 + tmux + ttyd + tini) | The one supported agent | M (mostly testing) |
| 6 | Orchestrator.Spawn (deterministic mode only) | Wire 3+4+5 | M |
| 7 | tmux + named pipe init script in base image | Chat IO substrate | S |
| 8 | Chat WS handler in API (read/write `/work/.ap/chat.{in,out}` via docker exec) | Browser → agent | M |
| 9 | Minimal Next.js: login, "New session", chat textarea | UI | M |
| 10 | One-active-session invariant (DB unique partial index + Redis lock) | Correctness | S |

That cut delivers value. Defer until after the MVP works:
- Web terminal (ttyd proxy) — adds 1 day once base works
- LiteLLM proxy + credit metering — only needed for non-BYOK tier
- Stripe — only needed for credit top-ups
- Persistent volumes + MinIO — only needed for paid tier
- Bootstrap-mode recipe runner — biggest unknown, do AFTER deterministic works
- All agents beyond OpenClaw — additive, recipe-by-recipe

**Suggested phase ordering for the roadmap:**

1. **Phase 0 — Foundations & Spikes** (1 week)
   - Hetzner provisioned, Docker installed, Postgres/Redis up, base image built
   - Spike: tmux+ttyd+pipes work end-to-end with one hand-launched container
   - Spike: HTTPS_PROXY vs BASE_URL behavior on each target agent (decides metering wiring)

2. **Phase 1 — Auth + Skeleton** (1 week)
   - OAuth (Google), users table, JWT, Next.js shell

3. **Phase 2 — Single-Agent BYOK MVP** (2 weeks)
   - Recipe schema + loader, OpenClaw recipe, Orchestrator.Spawn, chat WS, one-active invariant
   - **Demo-able milestone: log in, paste Anthropic key, chat with OpenClaw in a container**

4. **Phase 3 — Web Terminal** (3 days)
   - ttyd proxy, second tmux window, terminal UI page

5. **Phase 4 — Recipe Catalog Expansion** (1 week)
   - Add Hermes, HiClaw, PicoClaw recipes (one per day, mostly testing)
   - Build the local recipe-test rig (`make test-recipe AGENT=hermes`)

6. **Phase 5 — Metering + Stripe + Credits** (2 weeks)
   - LiteLLM proxy deployed, virtual key minting, BASE_URL injection
   - Stripe Checkout for top-ups, credit_balance ledger, usage_events
   - Pause-on-zero-balance flow

7. **Phase 6 — Persistence Tier** (1 week)
   - Named volumes, MinIO snapshots, free vs paid tier gating

8. **Phase 7 — Generic Bootstrap** (2 weeks, high-risk)
   - `ap-base:bootstrap` image with Claude Code, prompt template, recipe extraction, validation, caching
   - Sandbox hardening (gVisor optional, network egress lockdown mandatory)

9. **Phase 8 — Hardening & OSS Release** (1 week)
   - Audit logs, rate limits, abuse handling, public README, contribution guide for new recipes

**Critical-path dependencies:**
- (3) Docker runner blocks (6) Orchestrator
- (5) Base image + recipe blocks (6)
- (6) blocks (8) blocks the demo
- LiteLLM (Phase 5) blocks all non-BYOK flows but does NOT block the MVP
- Bootstrap (Phase 7) is the highest-risk component and is correctly placed last so it never blocks shipping

## 10. Anti-Patterns to Avoid

| Anti-pattern | Why bad | Instead |
|--------------|---------|---------|
| Embed Docker SDK directly | Heavy dep, version churn, harder to audit. MSV proves CLI-shellout is enough. | `pkg/docker/runner.go` shell-out with strict arg validation |
| One PTY for both chat and terminal | Keystroke contention, garbled state | tmux with named pipes for chat + separate window for terminal |
| LiteLLM sidecar per container | RAM blowout at scale | Single host LiteLLM with virtual keys |
| Trust HTTP_PROXY for HTTPS metering | Some SDKs ignore it | Force `*_BASE_URL` env for each provider |
| Custom recipe DSL | Yet another mini-language to debug | YAML + JSON-Schema validator |
| Spawn containers from HTTP request goroutine without lock | Two clicks → two containers → broken invariant | Postgres unique partial index + Redis SETNX |
| Storing BYOK keys plaintext in Postgres | One leak, total compromise | pgcrypto symmetric encrypt with key from systemd credential, or use SOPS-encrypted Vault file mounted at boot |
| Letting containers reach the internet freely | Exfil + abuse risk on bootstrap path | Custom bridge network, egress only via LiteLLM proxy or explicit allowlist (registry mirrors, package indexes) |
| Coupling Orchestrator state to in-memory map | Lost on API restart | Postgres `containers` table is the truth, in-memory is cache only |
| K8s | Overkill for one host, learning tax, networking pain | Plain Docker, mirror MSV |

## 11. Scalability Notes

| Concern | 100 users | 10K users | 100K users |
|---------|-----------|-----------|------------|
| Container density | Trivial | ~200 concurrent active sessions on AX162; idle sessions hibernated | Need worker fleet (Option B from MSV README); orchestrator stays single |
| Postgres | 1 instance | 1 instance + read replica | Citus / partitioned tables for usage_events |
| LiteLLM proxy | 1 instance | 1 instance, 4 workers | 2-3 instances behind nginx, shared Postgres |
| Recipe catalog | git repo | git repo | git repo (catalog grows linearly with agents, not users) |
| Volume snapshots | nightly tar | nightly tar to MinIO | per-tier schedule, deduped |

## 12. Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Docker CLI shell-out pattern | HIGH | Verified in MSV `api/pkg/docker/runner.go` |
| One-active invariant via DB+Redis | HIGH | Standard pattern |
| tmux + ttyd + named pipes | HIGH on each piece, MEDIUM combined — needs Phase-0 spike |
| LiteLLM Proxy as metering layer | HIGH on capability, MEDIUM on operational fit at >1K users |
| HTTPS_PROXY vs BASE_URL injection | MEDIUM — agent-specific; spike each agent |
| Recipe YAML schema | HIGH (proposed schema is conservative and extensible) |
| Bootstrap mode (Claude Code drives unknown repo) | LOW-MEDIUM — works in principle, ~30%+ failure rate expected on real-world repos |
| gVisor on Hetzner for bootstrap sandboxing | MEDIUM — doable, adds setup tax; flagged as Phase-7 hardening |
| Single-binary API+orchestrator | HIGH — MSV ships this way |

## 13. Open Questions for Phase-0 Spike

1. Does each target agent (OpenClaw, Hermes, HiClaw, PicoClaw) honor `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` for transparent proxying, or do we need per-agent shims?
2. What is the chat IO surface for each agent — pure stdin/stdout, JSON-RPC over stdio, HTTP server, custom socket? Drives the `chat_io.mode` enum in the recipe schema.
3. Will tmux + named-pipe + docker-exec round-trip latency for chat be acceptable (<100ms p50) compared to a direct WS-to-agent path? If not, fall back to a small Go shim inside the container that holds the FDs and exposes a unix socket.
4. Does `--runtime=runsc` (gVisor) work on the chosen Hetzner kernel, and what's the perf hit for Node-based agents? Determines whether gVisor is feasible for the bootstrap path.
5. Does Stripe support credit-style top-ups cleanly (Customer Balance API) or do we need to roll our own ledger on top of one-time payments? (Almost certainly the latter, but worth confirming.)
