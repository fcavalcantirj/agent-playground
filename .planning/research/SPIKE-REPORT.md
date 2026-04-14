---
phase: 01-foundations-spikes-temporal
plan: 06
requirement: FND-07
date: 2026-04-13
author: Claude (automated source analysis + local Docker latency test)
status: spikes 1-3 complete; spike 4 pending host access (human checkpoint)
---

# Phase 0 Spike Report

**Date:** 2026-04-13
**Author:** Claude (automated analysis + local Docker measurement) — manual verification pending
**Scope:** Resolves FND-07 — four empirical unknowns that gate Phase 2 (sandbox) and Phase 4 (recipe) decisions.

## TL;DR

| Spike | Question | Result |
|-------|----------|--------|
| 1 | Per-agent `HTTPS_PROXY` vs `*_BASE_URL` honored? | OpenClaw + PicoClaw both honor `HTTP(S)_PROXY` AND a per-provider base-URL override. Hermes/HiClaw/NanoClaw: source not on disk locally — needs clawclones clone in Phase 4. |
| 2 | `chat_io.mode` per agent | OpenClaw: gateway WebSocket (control plane). PicoClaw: cobra CLI (`agent -m` non-interactive, `agent` interactive readline) + per-channel adapters (Telegram/Discord/IRC/etc). Hermes/HiClaw: needs clone. |
| 3 | tmux + named-pipe round-trip latency | **PASS** — p50 = 85 us, p99 = **189 us** (0.19 ms), well under the 50 ms budget (262× headroom). Measured locally in Alpine 3.20 Docker. |
| 4 | gVisor `runsc` feasibility on Hetzner kernel | **PENDING HUMAN CHECKPOINT** — exact commands documented below for SSH execution on the actual host. |

---

## Spike 1: HTTPS_PROXY vs *_BASE_URL Per Agent

**Goal:** For each curated agent (OpenClaw, Hermes, HiClaw, PicoClaw, NanoClaw), determine which environment variable controls upstream model API routing. This decides whether Phase 4's metering layer can sit transparently as an HTTP proxy or has to be wired in via per-provider `*_BASE_URL` env vars.

**Method:** Source-grep of locally-available agents (`/Users/fcavalcanti/dev/openclaw`, `/Users/fcavalcanti/dev/picoclaw`) for proxy and base-URL plumbing.

### Findings

| Agent | `HTTPS_PROXY` honored? | `*_BASE_URL` honored? | Which vars / mechanism | Evidence (file:line) |
|-------|------------------------|------------------------|-------------------------|----------------------|
| **OpenClaw** | YES — explicit | YES — per-provider | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` (and lowercase variants) via undici `EnvHttpProxyAgent` semantics. Per-provider auth env vars like `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` etc. resolved by plugin manifests. | `src/infra/net/proxy-env.ts:1-55` (PROXY_ENV_KEYS, resolveEnvHttpProxyUrl); `src/secrets/provider-env-vars.ts:3-43` (provider auth env candidates) |
| **PicoClaw** | YES — Go default | YES — per-model `api_base` + per-model `proxy` | Uses `http.ProxyFromEnvironment` in `pkg/utils/http_client.go:44` (honors `HTTP(S)_PROXY`). Per-`ModelConfig` JSON fields `api_base` and `proxy` (`pkg/config/config.go:579-580`) override per model. Anthropic provider takes a `BaseURL` constructor param wired through to `option.WithBaseURL` in the official `anthropic-sdk-go` (`pkg/providers/anthropic/provider.go:27-53`). | `pkg/utils/http_client.go:11-44`; `pkg/config/config.go:573-605`; `pkg/providers/anthropic/provider.go:27-53`; `pkg/providers/claude_provider.go:18-37` |
| **Hermes** | UNKNOWN — source not on disk | UNKNOWN | Needs clone from clawclones.com (`hermes-agent`). Documented Phase 4 prerequisite. | n/a — scope-out for this spike |
| **HiClaw** | UNKNOWN | UNKNOWN | Same — needs clone. | n/a |
| **NanoClaw** | UNKNOWN | UNKNOWN | Same — needs clone. | n/a |

### Decision implications

- For OpenClaw and PicoClaw, **the metering layer can sit as a transparent egress HTTP proxy** injected via `HTTPS_PROXY` env at container start. No per-provider `*_BASE_URL` plumbing is required for v1 — both agents already route all outbound model traffic through the Go stdlib's `ProxyFromEnvironment` (Go) / undici's `EnvHttpProxyAgent` (Node) chain.
- This is the **architecturally simpler** outcome: one env injection per container, agent-agnostic.
- For unknown agents (Hermes/HiClaw/NanoClaw and the generic Claude-Code bootstrap path), Phase 4 must still verify per-agent. Recipe loader should declare a `proxy_mode` field (`http_env` | `base_url` | `both`) so the runner can pick the right injection at start time.
- **Action for Phase 4:** Clone the missing clawclones into a research workspace and re-run this analysis as part of recipe authoring.

---

## Spike 2: chat_io.mode Per Agent

**Goal:** Determine how each agent exposes chat I/O. Drives Phase 5's chat surface design — does the chat WebSocket bridge speak stdin/stdout, named pipes, or a per-agent API/WebSocket?

**Method:** Source-read of entry-point commands and architecture docs for locally-available agents.

### Findings

| Agent | `chat_io.mode` | stdin/stdout? | Named pipe? | API / WebSocket? | Notes / Evidence |
|-------|----------------|---------------|-------------|------------------|------------------|
| **OpenClaw** | `gateway-websocket` | No (CLI is for ops, not chat) | No | YES — single Gateway WebSocket control plane | OpenClaw exposes its chat surface as a Gateway WebSocket; macOS/iOS/Android nodes pair into the gateway, and WebChat connects through the same WS. CLI (`openclaw …`) is operator-side. README:201, 247, 449. **Implication:** the Go-side chat bridge would speak the OpenClaw gateway protocol, not stdin. |
| **PicoClaw** | `cli-stdio` (interactive) **or** `cli-arg` (single message via `-m`) **plus** per-channel adapters | YES — `picoclaw agent` runs interactive readline; `picoclaw agent -m "msg"` runs non-interactive | Easy to wrap externally with `mkfifo` -> `tmux send-keys` (validated by Spike 3) | Channel adapters available out-of-the-box for Telegram, Discord, IRC, WeChat, WeCom, Discord, Slack | `cmd/picoclaw/internal/agent/command.go:7-30` (cobra command, `--message`, `--session`, `--model` flags); module imports `ergochat/readline` (go.mod) for the interactive prompt loop. |
| **Hermes** | UNKNOWN — needs clone | ? | ? | ? | Out of scope; document in Phase 4. |
| **HiClaw** | UNKNOWN — needs clone | ? | ? | ? | Out of scope. |
| **NanoClaw** | UNKNOWN — needs clone | ? | ? | ? | Out of scope. |

### Decision implications

- The chat surface architecture must support **at least two distinct integration modes** in v1:
  1. **stdio-bridge mode** (PicoClaw, and likely most CLI-shaped clones): Go bridge runs `docker exec -i <container> picoclaw agent` and pipes stdin/stdout over a per-session WebSocket. Spike 3 confirms tmux + named-pipe wrapping is fast enough (p99 = 0.19 ms) if we want a long-lived agent process behind a FIFO instead of fresh `exec` per message.
  2. **gateway-protocol mode** (OpenClaw): Go bridge speaks the agent's native WebSocket protocol upstream, and forwards client messages over our own WS to the browser. This is heavier — needs a per-agent protocol adapter — and should be deferred to a v1.5 milestone unless a launch user demands OpenClaw on day 1.
- **Recipe schema implication:** add `chat_io.mode` (enum: `stdin` | `stdin_fifo` | `gateway_ws` | `http_api`) and `chat_io.cmd` to the recipe spec. Phase 4's recipe authoring task must populate these fields per agent.
- **v1 scope recommendation:** Ship PicoClaw on the `stdin_fifo` path first (the architecture chosen in CLAUDE.md). Defer OpenClaw to a follow-up plan that builds the gateway protocol adapter.

---

## Spike 3: tmux + Named-Pipe Round-Trip Latency

**Goal:** Validate that the named-pipe chat architecture (`/work/.ap/chat.in` -> tmux session -> agent -> `/work/.ap/chat.out`) is fast enough to feel real-time. Pass criterion: **p99 < 50 ms**.

**Method:**

1. Local Docker run (Alpine 3.20) — same kernel and process model as the Hetzner host's user containers.
2. Inside the container: install `tmux`, `bash`, `python3`. `mkfifo /work/.ap/chat.in /work/.ap/chat.out`.
3. Spawn a tmux session running a bash responder that holds both FIFOs open with `exec 3</work/.ap/chat.in; exec 4>/work/.ap/chat.out` and loops `read line <&3; printf 'echo: %s\n' "$line" >&4`.
4. From a Python harness, write timestamped messages to `chat.in` and read from `chat.out`. Measure round-trip with `time.perf_counter_ns` over 100 iterations after a 3-message warmup.

The responder is wrapped in tmux (not run directly) because that's the production architecture: tmux holds the agent's pseudo-terminal so a user can also attach a web terminal (ttyd/`tmux attach`) to the same session and watch the chat scroll by — chat and terminal are two views of one process.

**Measurement environment:**

- Host: macOS Darwin 25.3.0 (development laptop, not Hetzner)
- Docker: Docker Desktop 28.5.1
- Container: `alpine:3.20`
- tmux version: latest from Alpine 3.20 packages
- Python: 3.x from Alpine 3.20

### Raw results (N = 100, after 3 warm-up messages)

| Metric | Microseconds | Milliseconds |
|--------|-------------:|-------------:|
| min    | 69.2 us      | 0.07 ms |
| p50    | 85.4 us      | 0.09 ms |
| p95    | 138.2 us     | 0.14 ms |
| **p99** | **189.0 us** | **0.19 ms** |
| max    | 238.5 us     | 0.24 ms |
| mean   | 93.5 us      | 0.09 ms |

### Verdict

**PASS.** p99 = 189.0 us = 0.19 ms, well under the 50 ms budget — 262× headroom. The named-pipe architecture is comfortably fast enough; the perceptible-latency floor for chat will be the model's first-token time, not the FIFO plumbing.

### Caveats and what this does NOT measure

1. **Host kernel difference:** measured on macOS Docker Desktop's Linux VM, not on the Hetzner box's bare-metal Linux 6.x kernel. Hetzner is expected to be at least as fast (no virtualization overhead). **Recommend re-running this exact harness on the Hetzner box at the end of Phase 1** as a sanity check; the script lives at `/tmp/spike3-runner.sh` (see "Reproduction" below).
2. **Echo responder is trivial:** the agent process in production will be doing real work (LLM call, tool dispatch, etc.). This spike measures the **plumbing overhead only**, which is exactly what we wanted to bound. Application latency adds linearly on top.
3. **Single-message-at-a-time:** the harness sends sequentially. We did not test concurrent FIFO writers; the Phase 5 chat bridge will only have one writer per FIFO by design (one client per session) so this is sufficient.
4. **No tmux-attach load:** the test does not have a concurrent `tmux attach` consumer reading the same pty. Phase 5 should re-test with both the chat FIFO and a `ttyd` attached.

### Reproduction

The runner script lives at `/tmp/spike3-runner.sh` and was executed via:

```bash
docker run --name spike-tmux --rm \
  -v /tmp/spike3-runner.sh:/runner.sh:ro \
  alpine:3.20 sh /runner.sh
```

The runner script content is preserved in the Phase 1 work tree and will be moved to `deploy/spikes/spike3-tmux-fifo-latency.sh` during Phase 1 final cleanup if the team wants to keep it as a regression check.

---

## Spike 4: gVisor `runsc` Feasibility on Hetzner Kernel

**Goal:** Confirm gVisor `runsc` runs on the Hetzner host's kernel version. This is the v2 sandbox tier from CLAUDE.md, but per STATE.md "Init: gVisor (`runsc`) is mandatory for the Phase 8 bootstrap path; curated recipes may use `runc`" — it must be verified feasible **before** Phase 8 plans, otherwise the bootstrap path needs a different sandbox strategy (Sysbox or microVMs).

**Status:** **PENDING HUMAN CHECKPOINT** — requires SSH access to the actual Hetzner host. Cannot be run on a local Mac (gVisor only runs on Linux ≥ 4.14 with specific kernel features).

### Exact commands to run on the Hetzner host

The human operator should SSH to the production host and run these commands in order, then update this report's "Result" section.

```bash
# 1) Capture kernel version (gVisor requires Linux 4.14.77+ at minimum;
#    modern Hetzner Ubuntu boxes ship 5.15 / 6.x — should be fine).
uname -r
uname -a
cat /etc/os-release

# 2) Capture Docker version (gVisor needs Docker Engine 17.05+).
docker --version
docker info | grep -i -E "runtimes|server version|cgroup"

# 3) Install runsc (gVisor) following the official Debian/Ubuntu instructions.
#    Source: https://gvisor.dev/docs/user_guide/install/
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" \
  | sudo tee /etc/apt/sources.list.d/gvisor.list > /dev/null
sudo apt-get update
sudo apt-get install -y runsc

# 4) Capture runsc version
runsc --version

# 5) Register runsc as a Docker runtime (do not make it the default).
sudo runsc install
sudo systemctl reload docker

# Verify Docker now sees runsc as an available runtime
docker info | grep -A2 -i runtimes

# 6) Smoke test: run a hello-world under runsc
docker run --rm --runtime=runsc alpine:3.20 echo "hello from gvisor"

# 7) Slightly heavier sanity check: confirm the agent base image will boot under runsc.
#    (Use the same base we plan for Phase 4 — e.g. debian:bookworm-slim — once it exists.)
docker run --rm --runtime=runsc debian:bookworm-slim sh -c 'uname -a; cat /etc/os-release; echo OK'

# 8) Optional: nested capability check — does ttyd start under runsc?
#    (Phase 5 needs this; if it fails here, ttyd inside gVisor is a Phase 8 blocker.)
# docker run --rm --runtime=runsc -p 7681:7681 tsl0922/ttyd:latest ttyd -p 7681 sh
```

### Result template (fill in after running)

```
Kernel version    : <output of uname -r>
OS                : <PRETTY_NAME from /etc/os-release>
Docker version    : <output of docker --version>
runsc version     : <output of runsc --version>

Hello-world test  : PASS / FAIL
Debian boot test  : PASS / FAIL
ttyd test (opt)   : PASS / FAIL / not run

Notes / errors    : <anything noteworthy — warnings, slow startup, kernel feature missing>

Conclusion        : gVisor IS / IS NOT viable on the Hetzner host for the Phase 8 bootstrap sandbox.
                    If NOT viable: required kernel upgrade path = <e.g. apt full-upgrade to HWE kernel; switch to Sysbox; etc.>
```

### Why this can't be automated from a worktree agent

- A Mac development laptop cannot install or run `runsc` (Linux-only).
- The Hetzner host is provisioned out-of-band; this spike must run on the production substrate to be meaningful — running it on a generic Ubuntu cloud VM would only prove gVisor exists, not that the *target* host's specific kernel build supports it.
- The result also gates the Phase 8 architecture: if gVisor fails on the actual kernel, Phase 8 must pivot to Sysbox-only or microVMs, which is a non-trivial replan.

---

## Summary — Decisions These Findings Inform

### For Phase 2 (Docker runner + base image hardening)

- **Sandbox tier defaults:** v1 ships on plain `runc` with dropped caps + read-only rootfs + cgroup limits + userns-remap, exactly as CLAUDE.md "Container Isolation Tiers — v1" prescribes. No change.
- **Egress proxy injection mechanism (decided):** inject `HTTPS_PROXY=http://127.0.0.1:NNNN` (and `HTTP_PROXY`, `NO_PROXY` for local hosts) into every container — both OpenClaw and PicoClaw honor it. The proxy lives on a per-session unix socket forwarded to a tcp port inside the container. **No per-provider `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` plumbing required for v1 curated recipes.**
- **Recipe schema additions (decided):** `proxy_mode` enum (`http_env` | `base_url` | `both`) and `chat_io.mode` enum (`stdin` | `stdin_fifo` | `gateway_ws` | `http_api`) must be in the recipe schema from Phase 4 day 1 so adding new agents is a config change, not a code change.

### For Phase 4 (Recipe authoring)

- **Phase 4 must clone Hermes, HiClaw, NanoClaw** into a research workspace and re-run Spike 1 + Spike 2 against each before authoring their recipes. Document findings as an extension of this report.
- The first recipe to author is **PicoClaw with `chat_io.mode = stdin_fifo`** — it's the simplest path and validates the architecture end-to-end.

### For Phase 5 (Session lifecycle + chat surface)

- **Named-pipe FIFO chat bridge is validated** at p99 = 0.19 ms — proceed with the design from CLAUDE.md (chat <-> Go WS <-> FIFO inside container <-> tmux <-> agent process).
- **Re-run the Spike 3 harness on the Hetzner host** as part of Phase 5's smoke tests; expected to be at least as fast.
- **Defer OpenClaw to a follow-up plan** that builds the gateway-protocol adapter — don't try to ship it on the same `stdin_fifo` path.

### For Phase 8 (Generic Claude-Code bootstrap path)

- **BLOCKER:** Spike 4 must complete (human checkpoint) before Phase 8 plans are written. If gVisor fails on the Hetzner kernel, Phase 8 must pivot to Sysbox-only.

---

## Open follow-ups for the human reviewer

1. Run the Spike 4 commands on the Hetzner host and update §"Spike 4 — Result template" with real numbers.
2. Confirm the Spike 1 + Spike 2 findings for OpenClaw and PicoClaw match your knowledge of those tools — if anything looks wrong, comment in the checkpoint reply.
3. Decide whether to clone Hermes/HiClaw/NanoClaw now (extending this report) or defer to Phase 4's recipe-authoring task. Recommendation: defer — the spike report's job was to unblock Phase 2, not to author all recipes.
