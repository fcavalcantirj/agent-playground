---
plan: 02-01
phase: 02-container-sandbox-spine
status: completed
started: 2026-04-14
completed: 2026-04-14
tasks_completed: 3
tasks_total: 3
---

# Plan 02-01 Summary: ap-base image substrate

## Objective

Build the `ap-base:v0.1.0` Docker image — the load-bearing substrate every Phase 2+
recipe FROMs. Bakes tini PID 1, gosu privilege drop, tmux (shell + chat windows),
ttyd 1.7.7 on loopback, and the MSV-ported entrypoint shim that pre-opens FIFOs,
reads injected secrets, and launches the supervised process tree.

## Outcome

Three commits landed on `worktree-agent-a82ea388` atop `5bd7655`:

1. `00d7b59` — `feat(02-01): author ap-base Dockerfile`
2. `76a9cef` — `feat(02-01): author ap-base entrypoint shim`
3. `34ba3b1` — `feat(02-01): add ap-base Makefile targets and README`

## Key Files Created

- `deploy/ap-base/Dockerfile` — Debian trixie slim base; installs tini, gosu, tmux,
  bash, coreutils; pulls ttyd 1.7.7 from upstream releases (arch-pinned via build
  arg); creates `agent` user at uid 10000; pre-creates `/run/ap` + `/run/secrets`
  scaffolding; entrypoint defaults to the ported shim.
- `deploy/ap-base/entrypoint.sh` — Ported from MSV `infra/picoclaw/entrypoint.sh`
  lines 13-30. Phase 1 (root): fix mount perms, exec `gosu agent self`. Phase 2
  (agent): create FIFOs on `/run/ap` tmpfs, **hold FIFOs open from PID 1 via
  `exec 3<>` BEFORE launching agent** (Pitfall 2 fix), read `/run/secrets/*_key`
  into per-agent env list (NOT PID 1 env — T-02-01 mitigation), start ttyd in
  background on loopback (no `--once`, per Assumption A2), create tmux `ap`
  session with `shell` + `chat` windows, optionally launch `AP_AGENT_CMD` in the
  chat window.
- `deploy/ap-base/README.md` — Documents what the image provides, smoke-test
  recipe (`docker run --read-only --tmpfs /tmp --tmpfs /run ap-base:v0.1.0`;
  verify tini, uid 10000, tmux windows), recipe-overlay contract (overlays MUST
  NOT edit ap-base), and MSV port provenance.
- `Makefile` — Repo-root Makefile with 6 targets:
  - `build-ap-base` — builds `ap-base:v0.1.0` from `deploy/ap-base/`
  - `build-picoclaw` / `build-hermes` — forward-compat, depend on ap-base (Plan 03
    creates the agents/ dirs)
  - `build-recipes` — builds all three
  - `clean-recipes` — `docker rmi` the three tags
  - `smoke-test` — shells out to `scripts/smoke-e2e.sh` (Plan 06 creates);
    skips cleanly when `AP_DEV_BYOK_KEY` is unset
  - Auto-detects ttyd release arch via `uname -m` (x86_64 / aarch64) so the
    Dockerfile build arg matches the host platform.

## Verification

All task acceptance criteria met:
- `deploy/ap-base/Dockerfile` exists with tini + gosu + tmux + ttyd layers
- `deploy/ap-base/entrypoint.sh` exists, executable, contains the FIFO pre-open
  block and the gosu drop
- `Makefile` contains all 6 phony targets (verified via `grep -c`)
- `make -n build-ap-base` exits 0 and echoes the expected docker build invocation
- `deploy/ap-base/README.md` references tini, gosu, ttyd, tmux

Live `docker build` not executed in the worktree (no Docker daemon assumed in
subagent env); that is covered by Plan 06's smoke test which actually builds and
runs the image.

## Key Decisions / Deviations

**Deviation from plan spec (improvement):** The Makefile auto-detects `TTYD_ARCH`
from `uname -m` instead of hard-coding `x86_64`. This keeps the same image
producible on Apple Silicon dev boxes (aarch64) and the Hetzner prod box
(x86_64). The Dockerfile was authored to accept the arch as a build arg
accordingly. Reason: during Task 1 authoring, the plan's hard-coded
`TTYD_ARCH := x86_64` would have broken `make build-ap-base` on any M-series
laptop, and the auto-detect pattern costs 6 lines of Make.

**Pitfall 2 preserved:** The entrypoint holds FIFOs open from PID 1 via
`exec 3<>/run/ap/chat.in 4<>/run/ap/chat.out` BEFORE any writer/reader starts.
Without this, the first POSIX `open()` for write blocks forever waiting for a
reader. This is the single most important line in the shim.

**T-02-01 mitigation preserved:** Secrets are read into a bash `AGENT_ENV` array
and passed to the agent via `env "${AGENT_ENV[@]}" <cmd>`. They are NEVER
exported into PID 1's environment, so `cat /proc/1/environ` inside the container
does not leak the key.

**SBX-05 invariant held:** No `--privileged`, no docker socket mount, no `--cap-add`
beyond the ap-base default (which adds nothing).

## Execution Notes

The executor subagent hit a Claude Code runtime API 500 after completing tasks 1
and 2 and writing (but not committing) task 3's files. The orchestrator recovered
task 3 inline: verified the already-written `Makefile` and
`deploy/ap-base/README.md` against the plan's acceptance criteria, confirmed
`make -n build-ap-base` exits 0, then committed both files atomically and
authored this SUMMARY. No files were lost; the crash was purely a commit-phase
failure, not a write-phase failure.

## What Unlocks

- **Plan 02-03** (recipe overlays) can now `FROM ap-base:v0.1.0` to build
  `ap-picoclaw` and `ap-hermes` — both are agent-agnostic overlays that add only
  the agent binary plus per-recipe config.
- **Plan 02-06** (smoke test) will use `make build-ap-base && make build-recipes`
  in the test harness.
- Phase 3's persistent-volume tier and Phase 5's WS reverse proxy both build on
  this substrate without modification.
