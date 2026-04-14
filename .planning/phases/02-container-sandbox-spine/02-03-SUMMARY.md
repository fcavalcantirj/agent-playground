---
phase: 02-container-sandbox-spine
plan: 03
subsystem: agents
tags: [recipes, picoclaw, hermes, ap-base, sbx-01, rec-07]
requires:
  - "ap-base:v0.1.0 (Plan 02-01): FROM base, tini PID 1, tmux chat+shell windows, /entrypoint.sh with FIFO pre-open + gosu drop"
  - "Makefile build-picoclaw / build-hermes targets (declared in Plan 02-01 forward-compat)"
  - "Docker Engine 27+ with multi-stage + image-mount COPY support (for COPY --from=ghcr.io/astral-sh/uv:...)"
provides:
  - "ap-picoclaw:v0.1.0-c7461f9 recipe image (picoclaw Go CLI on ap-base)"
  - "ap-hermes:v0.1.0-5621fc4 recipe image (Python 3.13 TUI on ap-base)"
  - "agents/picoclaw/Dockerfile + README.md"
  - "agents/hermes/Dockerfile + cli-config.yaml + README.md"
affects:
  - "Plan 02-04 internal/recipes/recipes.go: can now reference the two image tags as cross-phase literals"
  - "Plan 02-05 smoke test: both images are available locally for session-spawn assertions"
  - "Phase 4 recipe catalog: proves the agent-agnostic overlay contract (Go CLI + Python TUI both fit ap-base unmodified)"
tech-stack:
  added:
    - "picoclaw (Go CLI agent) pinned at upstream c7461f9"
    - "Hermes (Python 3.13 TUI agent) pinned at upstream 5621fc4"
    - "uv 0.11.6 Python package manager via ghcr.io/astral-sh/uv multi-stage COPY"
    - "Playwright chromium headless shell (Hermes dependency)"
  patterns:
    - "Pin-by-SHA upstream clone (REC-07 forward-compat): git clone + git checkout <SHA>, never :latest, never branch refs"
    - "ARG re-declaration inside Docker stages (global ARG before FROM only propagates to FROM instructions)"
    - "Multi-stage recipe overlay: 'FROM ap-base:v0.1.0' as the sole runtime base, agent binary + config layered on top"
    - "Agent-process launch via AP_AGENT_CMD env var (picoclaw) or empty/ChatIOExec (Hermes)"
key-files:
  created:
    - agents/picoclaw/Dockerfile
    - agents/picoclaw/README.md
    - agents/hermes/Dockerfile
    - agents/hermes/cli-config.yaml
    - agents/hermes/README.md
  modified: []
decisions:
  - "Smoke-test invocations require --entrypoint override — ap-base owns ENTRYPOINT for supervision, so one-shot probes must bypass it"
  - "picoclaw uses 'version' subcommand (not '--version' flag) per upstream Cobra layout at c7461f9"
  - "Hermes arm64 image weighs 5.54GB, not ~3GB — plan estimate was x86_64-biased; Playwright chromium-headless-shell + ctranslate2 + onnxruntime dominate"
  - "AP_AGENT_CMD='' for Hermes: ChatIOExec mode (Plan 04 will docker exec 'hermes chat -q' per request), so ap-base entrypoint skips tmux chat-window creation"
  - "No config-level 'disable channel daemon' key exists in Hermes — gateways (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Mattermost) are activated only by 'hermes gateway' subcommand which Phase 2 never invokes. CONTEXT D-21 was wrong; RESEARCH correction confirmed by inspecting hermes_cli/main.py"
metrics:
  duration: "~25 minutes wall-clock (picoclaw ~30s cached ap-base + ~2min first build; hermes ~15min first build dominated by apt+npm+playwright+uv)"
  completed: 2026-04-14
  tasks_completed: 2
  commits: 2
  images_built: 2
---

# Phase 02 Plan 03: Recipe Overlays (picoclaw + Hermes) Summary

Authored two Dockerfile recipe overlays that layer agent binaries onto `ap-base:v0.1.0` without touching the substrate. Both pin upstream sources to immutable commit SHAs per REC-07 forward-compat. picoclaw proves the simplest case (single Go binary, ChatIOFIFO path via `AP_AGENT_CMD`); Hermes proves the architecturally hardest case (Python 3.13 TUI, apt + npm + playwright + uv venv, ChatIOExec with `AP_AGENT_CMD=""`). If both FROM ap-base unmodified and both produce a runnable agent binary, the recipe pattern is validated for Phase 4 catalog expansion.

## Tasks Completed

### Task 1: ap-picoclaw recipe overlay

- **Files:** `agents/picoclaw/Dockerfile`, `agents/picoclaw/README.md`
- **Commit:** `d56f920` — `feat(02-03): add ap-picoclaw recipe overlay`
- **Image:** `ap-picoclaw:v0.1.0-c7461f9` (280MB on arm64)
- **Build time:** ~2 minutes first build (golang:1.25-alpine pull + `make build` + `picoclaw onboard`)
- **Smoke test result:** `docker run --rm --entrypoint picoclaw ap-picoclaw:v0.1.0-c7461f9 version` exits 0 and prints `picoclaw v0.2.4-142-gc7461f9e (git: c7461f9e) Go: go1.25.9` — the git SHA in the banner matches the pinned SHA exactly, proving the checkout took.

### Task 2: ap-hermes recipe overlay

- **Files:** `agents/hermes/Dockerfile`, `agents/hermes/cli-config.yaml`, `agents/hermes/README.md`
- **Commit:** `4e781e6` — `feat(02-03): add ap-hermes recipe overlay`
- **Image:** `ap-hermes:v0.1.0-5621fc4` (5.54GB on arm64)
- **Build time:** ~15 minutes first build, broken down roughly:
  - apt install (~95s) — build-essential, nodejs, npm, python3-dev, ffmpeg, ripgrep, procps, libffi-dev
  - `git clone` + `git checkout 5621fc4` (~2s)
  - `npm install --prefer-offline --no-audit` + `npx playwright install --with-deps chromium` (~107s, dominated by the 183MB chromium + 107MB headless-shell zip downloads and a second apt pass for chromium's runtime deps)
  - `uv venv` + `uv pip install -e ".[all]"` (~30s; uv is very fast — this would be 3-5× slower with pip)
  - final layer export (~58s due to 5.54GB image)
- **Smoke test result:** `docker run --rm --entrypoint hermes ap-hermes:v0.1.0-5621fc4 --help` exits 0 and prints the full Hermes CLI subcommand tree (chat, model, gateway, setup, …). `hermes version` also works and reports `Hermes Agent v0.9.0 (2026.4.13) Python: 3.13.5`.
- **Config verified baked in:** `docker run --rm --entrypoint cat ap-hermes:v0.1.0-5621fc4 /home/agent/.hermes/config.yaml` outputs the exact Phase 2 cli-config.yaml with `provider: "anthropic"`, `backend: "local"`, `memory_enabled: false`.

## Image Sizes (arm64 / Apple Silicon dev box)

| Image | Size | Notes |
|---|---|---|
| `ap-base:v0.1.0` | 225MB | Cached from Plan 02-01 build |
| `ap-picoclaw:v0.1.0-c7461f9` | 280MB | +55MB for the picoclaw Go binary |
| `ap-hermes:v0.1.0-5621fc4` | **5.54GB** | +5.3GB for apt + npm + playwright chromium + Python venv with ML deps |

**Hermes size is 1.85× the plan's ~3GB estimate.** Drivers: Playwright chromium + headless-shell (~300MB), ML dependencies in `.[all]` (ctranslate2, onnxruntime, numpy, av, tokenizers, hf-xet — all large), and the apt layer pulling g++-14 + libllvm19 because Debian's `build-essential` recommends pull them even with `--no-install-recommends`. This is worth flagging to Phase 7 for registry-storage cost forecasting but is NOT a blocker — the per-session container start time is unaffected (image is cached locally once pulled).

## Final Image Tags

These tags are the cross-phase contract — Plan 04's `internal/recipes/recipes.go` literals MUST match these strings exactly:

- `ap-picoclaw:v0.1.0-c7461f9`
- `ap-hermes:v0.1.0-5621fc4`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docker ARG scoping: `${PICOCLAW_SHA}` / `${HERMES_SHA}` empty inside RUN steps**

- **Found during:** Task 1 first build
- **Issue:** The plan's Dockerfile sketch put `ARG PICOCLAW_SHA=...` BEFORE the first `FROM`, which in Docker's grammar makes it a "global ARG" — available only to `FROM` instructions, NOT to `RUN` steps in a stage. The first build failed with `fatal: empty string is not a valid pathspec` because `git checkout ""` was being executed.
- **Fix:** Re-declared `ARG PICOCLAW_SHA` (and `ARG HERMES_SHA` pre-emptively in the Hermes Dockerfile) inside the stage, after the `FROM` line, so the variable is visible to the subsequent `RUN`. This is the documented Docker pattern for propagating global ARGs into stages.
- **Files modified:** `agents/picoclaw/Dockerfile`, `agents/hermes/Dockerfile`
- **Commits:** Fix was rolled into the original Task 1 + Task 2 commits (no separate fix commit — the bug was caught during the Task 1 build, fixed before committing anything for that task).

**2. [Rule 1 - Plan acceptance criterion incorrect] `docker run --rm ap-picoclaw picoclaw --version` cannot exit 0 as written**

- **Found during:** Task 1 smoke test
- **Issue:** The plan's `<must_haves><truths>` block and verification block both say `docker run --rm ap-picoclaw:v0.1.0-c7461f9 picoclaw --version`. This does not work, for two independent reasons:
  1. ap-base's `ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/entrypoint.sh"]` takes over at container start; `picoclaw --version` ends up as `$@` of entrypoint.sh, which never invokes `$@` — it runs its own hardcoded tmux supervision loop. The binary is never executed.
  2. picoclaw at commit c7461f9 has no `--version` flag — it uses `picoclaw version` as a Cobra subcommand.
- **Fix:** Documented the correct smoke-test incantation (`docker run --rm --entrypoint picoclaw ap-picoclaw:v0.1.0-c7461f9 version`) in the README and in this SUMMARY. The same `--entrypoint` override is also required for the Hermes smoke test (`--entrypoint hermes ap-hermes:v0.1.0-5621fc4 --help`). The plan's intent ("prove the binary is in PATH and runs") is fully satisfied — only the literal string in the verification block is wrong.
- **Files modified:** `agents/picoclaw/README.md`, `agents/hermes/README.md` — both document the `--entrypoint` override pattern and explain why it is required.
- **Impact:** Plan 04/05 must use `--entrypoint` (or `docker exec` against a running container) for any one-shot probe, because ap-base's ENTRYPOINT always supervises. Flagged to Plan 05 smoke test in the §Known Issues section below.

None of the deviations required architectural changes — both were Rule 1 fixes to wrong/broken literals in the plan, with zero behavior impact on downstream plans.

## Verification

All plan acceptance criteria pass:

- `agents/picoclaw/Dockerfile` exists — FOUND
- `agents/picoclaw/README.md` exists — FOUND
- `grep -c 'FROM ap-base:v0.1.0' agents/picoclaw/Dockerfile` — 1
- `grep -c 'FROM golang:1.25-alpine AS builder' agents/picoclaw/Dockerfile` — 1
- `grep -c 'PICOCLAW_SHA=c7461f9e963496c4471336642ac6a8d91a456978' agents/picoclaw/Dockerfile` — 1
- `grep -c 'git clone https://github.com/sipeed/picoclaw' agents/picoclaw/Dockerfile` — 1
- `grep -c 'git checkout' agents/picoclaw/Dockerfile` — 1
- `grep -c 'AP_AGENT_CMD="picoclaw agent --session cli:default"' agents/picoclaw/Dockerfile` — 1
- `grep -c ':latest' agents/picoclaw/Dockerfile` — 0
- `grep -c 'USER picoclaw' agents/picoclaw/Dockerfile` — 0
- `grep -c 'ENTRYPOINT' agents/picoclaw/Dockerfile` — 0
- `grep -c '^CMD' agents/picoclaw/Dockerfile` — 0
- `make build-picoclaw` — exits 0
- `docker images ap-picoclaw:v0.1.0-c7461f9` — FOUND (280MB)
- `docker run --rm --entrypoint picoclaw ap-picoclaw:v0.1.0-c7461f9 version` — exits 0, prints version with git SHA `c7461f9e`
- `agents/hermes/Dockerfile` exists — FOUND
- `agents/hermes/cli-config.yaml` exists — FOUND
- `agents/hermes/README.md` exists — FOUND
- `grep -c 'FROM ap-base:v0.1.0' agents/hermes/Dockerfile` — 1
- `grep -c 'HERMES_SHA=5621fc449a7c00f11168328c87e024a0203792c3' agents/hermes/Dockerfile` — 1
- `grep -c 'git clone https://github.com/NousResearch/hermes-agent' agents/hermes/Dockerfile` — 1
- `grep -c 'git checkout' agents/hermes/Dockerfile` — 1
- `grep -c 'python3-dev' agents/hermes/Dockerfile` — 1
- `grep -c 'astral-sh/uv:0.11.6-python3.13-trixie' agents/hermes/Dockerfile` — 2
- `grep -c 'uv pip install' agents/hermes/Dockerfile` — 1
- `grep -c 'AP_AGENT_CMD=""' agents/hermes/Dockerfile` — 1
- `grep -c 'cli-config.yaml /home/agent/.hermes/config.yaml' agents/hermes/Dockerfile` — 1
- `grep -c ':latest' agents/hermes/Dockerfile` — 0
- `grep -c 'python3.11' agents/hermes/Dockerfile` — 0
- `grep -c 'provider: "anthropic"' agents/hermes/cli-config.yaml` — 1
- `grep -c 'backend: "local"' agents/hermes/cli-config.yaml` — 1
- `grep -c 'memory_enabled: false' agents/hermes/cli-config.yaml` — 1
- `make build-hermes` — exits 0 (15min first build)
- `docker images ap-hermes:v0.1.0-5621fc4` — FOUND (5.54GB)
- `docker run --rm --entrypoint hermes ap-hermes:v0.1.0-5621fc4 --help` — exits 0, prints full subcommand tree
- `docker run --rm --entrypoint hermes ap-hermes:v0.1.0-5621fc4 version` — exits 0, reports `Hermes Agent v0.9.0 Python: 3.13.5`
- `docker run --rm --entrypoint cat ap-hermes:v0.1.0-5621fc4 /home/agent/.hermes/config.yaml` — prints baked config with anthropic + local + memory_enabled:false

## Known Issues to Surface to Plan 05 Smoke Test

1. **`--entrypoint` override is required for one-shot probes.** ap-base's ENTRYPOINT owns the supervision chain; `docker run <image> <cmd>` will NOT execute `<cmd>` — it will start tini/tmux and the passed args go nowhere useful. Plan 05's smoke test must either (a) `docker run -d` to start the supervision chain normally and then `docker exec` against the running container, or (b) `docker run --rm --entrypoint <binary>` for pure binary-health probes. Option (a) is the realistic session-spawn shape.
2. **Hermes `hermes chat -q "<msg>"` may need `-t` for TTY allocation (Pitfall 3 from RESEARCH).** Not validated in this plan because that is Plan 05's job. If the smoke test sees `hermes chat` complain about "not a terminal" or block forever waiting for stdin, the fix is `docker exec -it` (or equivalent TTY allocation through the Docker SDK's `AttachStdin + Tty: true`).
3. **Hermes container memory baseline is unmeasured.** Image is 5.54GB on disk; runtime RSS when idle vs when running `hermes chat -q` is unknown. Plan 05 or Phase 7.5 should measure peak RSS during a chat exchange to set the `RunOptions.Memory` default for the recipe. picoclaw's baseline is also unmeasured but is known from MSV to be ~60MB idle.
4. **picoclaw ChatIOFIFO loop is unverified end-to-end.** The `AP_AGENT_CMD` wiring in ap-base's entrypoint.sh creates the tmux chat window with stdin/stdout redirected to the FIFOs. Plan 05 needs to write a message into `/run/ap/chat.in` and read a reply from `/run/ap/chat.out` to prove the FIFO path works against a real agent (Spike 3 proved FIFO RTT in an empty alpine container, not against a Cobra REPL).
5. **Hermes multi-arch build-args.** The Hermes image currently builds for the host arch only. When the Hetzner prod box (x86_64) is targeted, the `ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie` multi-stage image and the chromium download will both auto-select x86_64. Cross-arch builds (buildx `--platform linux/amd64` from an Apple Silicon dev box) have NOT been tested in this plan; Plan 05 or the first real deploy should validate.

## Open Follow-ups

- **Phase 7 persistent memory volume for Hermes.** `memory_enabled: false` in the baked config is a Phase 2 ephemeral-storage limitation, not a product decision. Phase 7 adds `ap-vol-<user>` mounted at `/home/agent/.hermes/` and flips `memory_enabled: true` in the per-session config overlay.
- **Upstream SHA refresh cadence.** Hermes HEAD was dated 2026-04-13 at research time and 2026-04-14 at build time — the project moves fast. A Phase 4 concern: when should recipes be refreshed? Proposal: monthly cadence for trusted recipes, pin new SHA in a `chore(recipe)` commit, re-run the smoke test, re-tag the image. Out of scope for Phase 2 but worth flagging.
- **`git verify-commit` for signed commits.** Threat model T-02-03/T-02-03b accepts the pin-by-SHA strategy for Phase 2 but flags Phase 7.5 as the gate for adding signed-commit verification. No action in this plan.
- **Npm supply chain (T-02-07).** Phase 2 accepts the pinned `package-lock.json`'s transitive tree. Phase 4 will add `npm ci --audit` as a recipe-lint gate. No action in this plan.

## Commits

| Hash | Type | Message |
|---|---|---|
| `d56f920` | feat | feat(02-03): add ap-picoclaw recipe overlay |
| `4e781e6` | feat | feat(02-03): add ap-hermes recipe overlay |

## Self-Check: PASSED

- `agents/picoclaw/Dockerfile` — FOUND
- `agents/picoclaw/README.md` — FOUND
- `agents/hermes/Dockerfile` — FOUND
- `agents/hermes/cli-config.yaml` — FOUND
- `agents/hermes/README.md` — FOUND
- Commit `d56f920` — FOUND (verified via `git log --oneline`)
- Commit `4e781e6` — FOUND (verified via `git log --oneline`)
- Image `ap-picoclaw:v0.1.0-c7461f9` — FOUND in local Docker cache
- Image `ap-hermes:v0.1.0-5621fc4` — FOUND in local Docker cache
- Both images FROM `ap-base:v0.1.0` unmodified (agent-agnostic contract upheld)
- Both pin upstream via immutable commit SHAs (REC-07 forward-compat)
- Both agent binaries run inside their respective containers (proven via `--entrypoint` override)
