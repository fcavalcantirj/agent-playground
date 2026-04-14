---
phase: 01-foundations-spikes-temporal
plan: 06
subsystem: research
tags: [spike, proxy, base_url, chat_io, tmux, fifo, gvisor, runsc, openclaw, picoclaw]

# Dependency graph
requires:
  - phase: 01-foundations-spikes-temporal
    provides: research scaffolding (01-RESEARCH.md spike methodology section)
provides:
  - SPIKE-REPORT.md with empirical findings for FND-07
  - Per-agent proxy/base_url behavior decision input for Phase 4 recipes
  - Per-agent chat_io.mode mapping for Phase 5 chat surface design
  - Validated p99 RTT for tmux+FIFO chat plumbing (0.19 ms — 262x headroom)
  - Exact gVisor runsc smoke commands to run on the Hetzner host (Spike 4)
affects: [phase-02-docker-runner, phase-04-recipes, phase-05-chat-surface, phase-08-bootstrap]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Spike report layout: TL;DR table → per-spike sections (goal/method/findings/decision implications) → consolidated Summary"
    - "FIFO+tmux echo-responder microbenchmark — bash holds both FIFOs open with exec 3<; exec 4>; loop reads — Python harness times 100 iterations after warmup"

key-files:
  created:
    - .planning/research/SPIKE-REPORT.md
  modified: []

key-decisions:
  - "v1 metering injection: single HTTPS_PROXY env per container (both OpenClaw and PicoClaw honor it) — no per-provider *_BASE_URL plumbing needed"
  - "Recipe schema must include proxy_mode (http_env|base_url|both) and chat_io.mode (stdin|stdin_fifo|gateway_ws|http_api) from Phase 4 day 1"
  - "First curated recipe to author = PicoClaw on the stdin_fifo path (validates the architecture end-to-end)"
  - "OpenClaw deferred to a follow-up plan with a gateway-protocol adapter (its chat surface is a WebSocket gateway, not stdin)"
  - "tmux+FIFO RTT validated at p99=0.19ms — proceed with the named-pipe chat bridge design from CLAUDE.md"

patterns-established:
  - "Spike methodology: source-grep + local containerized microbenchmark + documented manual checkpoint commands for steps that need production hardware"

requirements-completed: [FND-07]

# Metrics
duration: ~25min
completed: 2026-04-13
---

# Phase 01 Plan 06: Phase-0 Spike Report Summary

**Empirical resolution of four FND-07 unknowns: per-agent HTTP_PROXY/BASE_URL handling (OpenClaw + PicoClaw both honor HTTPS_PROXY env), per-agent chat_io.mode (PicoClaw cobra CLI stdin vs OpenClaw gateway WebSocket), tmux+FIFO RTT measured at p99 = 0.19 ms in alpine:3.20 Docker, and documented exact gVisor runsc smoke commands for SSH execution on the Hetzner host.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-04-13
- **Completed:** 2026-04-13
- **Tasks:** 1 of 2 complete (Task 2 is the human checkpoint)
- **Files modified:** 1 created, 0 modified

## Accomplishments

- **Spike 1 (proxy/base_url):** Source-cited evidence that OpenClaw and PicoClaw both route outbound model traffic through `HTTP(S)_PROXY` env vars AND support per-provider base-URL overrides. Means the v1 metering layer can be a transparent egress proxy without per-provider `*_BASE_URL` plumbing. Hermes/HiClaw/NanoClaw deferred to Phase 4 (sources not on local disk).
- **Spike 2 (chat_io.mode):** OpenClaw documented as `gateway-websocket` (Gateway WS control plane); PicoClaw documented as `cli-stdio` interactive readline + `cli-arg` single-message via `-m` + per-channel adapters. Drives Phase 5's recipe `chat_io.mode` enum.
- **Spike 3 (tmux+FIFO latency):** Real measurement, not theory — built a bash responder that holds both FIFOs open inside a tmux session, ran 100 round-trips from a Python harness in `alpine:3.20`. **p50 = 85 us, p95 = 138 us, p99 = 189 us, max = 238 us** — 262x headroom under the 50 ms pass criterion.
- **Spike 4 (gVisor runsc):** Documented the exact `apt-get` install + `runsc install` + `docker run --runtime=runsc` smoke sequence with a result template, ready for the human to SSH into the Hetzner host and execute. Cannot be run from a Mac dev box.

## Task Commits

1. **Task 1: Execute spikes 1-3 (agent source analysis + tmux latency test) and write spike report** — `38e4d7e` (docs)
2. **Task 2: Verify spike findings and complete gVisor spike** — *checkpoint pending human verification*

## Files Created/Modified

- `.planning/research/SPIKE-REPORT.md` — 243 lines; per-spike sections with source citations, raw latency numbers, runsc commands, and a Decision Implications block per downstream phase.

## Decisions Made

- **OpenClaw and PicoClaw both honor `HTTP(S)_PROXY` env vars.** PicoClaw via Go's `http.ProxyFromEnvironment` in `pkg/utils/http_client.go:44`. OpenClaw via undici's `EnvHttpProxyAgent` semantics in `src/infra/net/proxy-env.ts:1-55`. Both also expose per-provider base-URL overrides (PicoClaw: per-`ModelConfig` `api_base` field at `pkg/config/config.go:579`; OpenClaw: per-provider auth env candidates in `src/secrets/provider-env-vars.ts`). **v1 metering can use the transparent proxy path** — no per-`OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` plumbing required for these two agents.
- **Recipe schema additions for Phase 4:** add `proxy_mode` enum (`http_env` | `base_url` | `both`) and `chat_io.mode` enum (`stdin` | `stdin_fifo` | `gateway_ws` | `http_api`) so adding new agents is a config change.
- **Hermes/HiClaw/NanoClaw analysis deferred to Phase 4 recipe authoring** rather than expanding this spike — the spike's job is to unblock Phase 2's design decisions, and the two locally-available agents are sufficient signal for the architectural choice.
- **OpenClaw shipping path deferred to a follow-up plan** because its chat surface is a WebSocket gateway, not stdin. Phase 4 ships PicoClaw on the `stdin_fifo` path first.

## Deviations from Plan

None — plan executed exactly as written. Spike 3 was successfully run locally (Docker available on the dev machine), so it did not need to be marked "pending host access". Spike 4 remains pending per plan, gated on the human checkpoint as designed.

## Issues Encountered

- **First Spike 3 attempt deadlocked** because the initial bash responder was wired as `cat /work/.ap/chat.in | while read line; do ...; done > /work/.ap/chat.out` — `cat` exits after the first read on a FIFO, so subsequent writes hung. Fix: rewrote the responder to `exec 3</work/.ap/chat.in; exec 4>/work/.ap/chat.out; while read line <&3; do ...; done >&4` so both FIFOs stay open across iterations. Second run produced clean numbers. Documented in the spike report's "Method" subsection.

## User Setup Required

None for this plan. The follow-on Spike 4 (Task 2 checkpoint) requires the human to SSH to the Hetzner host and run the documented commands, then update §"Spike 4 — Result template" in `.planning/research/SPIKE-REPORT.md`.

## Next Phase Readiness

- **Phase 2 unblocked** — sandbox tier and egress-proxy injection mechanism are decided.
- **Phase 4 unblocked** — recipe schema fields decided; PicoClaw is the first recipe to author; Hermes/HiClaw/NanoClaw analysis is queued as part of recipe authoring.
- **Phase 5 unblocked** — named-pipe FIFO chat bridge is empirically validated.
- **Phase 8 still gated on Spike 4** — the human checkpoint must produce a PASS result for `runsc` on the Hetzner kernel before Phase 8 plans can be written. If FAIL, Phase 8 must pivot to Sysbox-only or microVMs, which is a non-trivial replan (called out in the report's open follow-ups).

## Self-Check: PASSED

- File `.planning/research/SPIKE-REPORT.md` exists (243 lines).
- Commit `38e4d7e` exists in the worktree branch (`docs(01-06): spike report — proxy/base_url, chat_io, FIFO latency`).
- Verification command from the plan passes: `test -f` + `grep HTTPS_PROXY` + `grep chat_io` → `SPIKE_REPORT_EXISTS`.
- All Task 1 acceptance criteria satisfied: spike report contains Spike 1 (HTTPS_PROXY), Spike 2 (chat_io), Spike 3 (latency methodology + raw data + p50/p95/p99 + PASS verdict), Spike 4 (pending — exact commands documented), and a Summary section. Each spike has a table.

---
*Phase: 01-foundations-spikes-temporal*
*Plan: 06*
*Completed: 2026-04-13 (Task 1); Task 2 awaiting human checkpoint*
