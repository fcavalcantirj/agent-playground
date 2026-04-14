---
status: draft
stage: L1-wave2-complete
started: 2026-04-14
last_updated: 2026-04-14
candidates_total: 40
candidates_real: 38
candidates_archived: 7
candidates_fit_recipe_pipeline: 25
next: Read Praktor YAML deeply → draft Phase 02.5 schema → selective L2 ground-truthing
key_insight: Praktor (mtzanidakis/praktor) is direct prior art — fork its schema, don't invent ours
---

# Agent Matrix — L1 Recon Complete

Source of truth for what we're actually building on. Aggregated from 4 parallel L1 research passes across 24 candidates. Every row links to a per-agent file at `agents/<name>.md`.

**Rule:** This file is DATA, not architecture. No schema decisions are made here — that's Phase 02.5.

## Status legend

| Icon | Meaning |
|---|---|
| ✅ | Real repo, maintained, fits the recipe pipeline |
| ⚠️ | Real but known issue (archived / non-OSS / non-LLM / dead) |
| ❌ | Not a runnable coding agent (framework, spec, etc.) |

---

## The full table

| Agent | Status | Stars | Lang | License | Install | Auth mechanism | Chat I/O mode | Providers | Nested-container risk | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| **openclaw** | ✅ | **357k** | TypeScript | MIT | `npm install -g openclaw` | `auth-profiles.json` (per MSV) | `fifo` via tmux | Anthropic, OpenAI, Groq, … | no | **THE runtime.** picoclaw is a config flavor of this, not a separate binary. |
| **picoclaw** | ✅ | (flavor) | Go+TS | MIT | git clone + make build | `.security.yml` (api_keys array) + onboard | `fifo` | Anthropic (via openclaw gateway) | no | Config flavor of openclaw. "Not production before v1.0" — strictest tier. Already in our Phase 2. |
| **nanobot** (HKUDS) | ✅ | 39.5k | Python | MIT | `pip install nanobot` | **`${VAR_NAME}` env substitution in YAML** | `exec_per_message` | Anthropic, OpenAI, OpenRouter | no | **Best BYOK fit** — substitution pattern is stateless + env-native. |
| **nullclaw** | ✅ | 7k | Zig | MIT | binary release | **`nullclaw onboard --api-key <k>`** | `fifo` | Anthropic | no | **Cleanest non-interactive BYOK** in the whole sweep — 1 CLI call sets the key. |
| **zeroclaw** | ✅ | ~30k | Rust | MIT/Apache | `cargo install zeroclaw` | env var | `exec_per_message` | multiple | no | Rust rewrite, <5MB RAM, embedded target. |
| **moltis** (moltis-org) | ✅ | 2.6k | Rust | MIT | binary release (60 MB single binary) | config file | `fifo` + `http_gateway` | Anthropic, OpenAI | **YES** | Wants to spawn its own containers for sandboxed execution. Pin `backend: local` or Sysbox. |
| **ironclaw** (nearai) | ✅ | — | Rust | — | `cargo install` | **keys injected at exec time only (WASM sandbox)** | `exec_per_message` | multiple | no | **Cleanest threat model** — keys never at rest. |
| **HiClaw** (agentscope-ai) | ✅ | — | Shell + Go | Apache-2.0 | docker compose | **"consumer token" pattern** | `http_gateway` (Matrix + Higress) | gateway-routed | **YES** | Multi-container by design. Consumer-token pattern maps onto platform-billed metering cleanly. Needs compose-style recipe. |
| **nanoclaw** (qwibitai) | ⚠️ | — | Python | — | `pip install nanoclaw` | Anthropic-only env | `exec_per_message` | Anthropic only | **YES** | Runs each agent in its OWN Docker — collides with per-user container model. |
| **safeclaw** (princezuda) | ⚠️ | — | Python | — | `pip install safeclaw` | N/A | N/A | — | no | **Deterministic, non-LLM by default.** Doesn't fit BYOK pipeline cleanly. Marginal recipe target. |
| **hermes-agent** (NousResearch) | ✅ | ~35k | Python | MIT | `pip install -e ".[all]"` (5.5 GB with extras!) | `~/.hermes/` via interactive wizard | `exec_per_message` (`hermes chat -q`) | Anthropic, OpenAI, OpenRouter, local | **YES** | 6 terminal backends (local/Docker/SSH/Daytona/Singularity/Modal). **Must pin `backend: local`**. Playwright/Chromium bundled with `[all]` extra — use minimal extra. |
| **Claude Code** (Anthropic) | ⚠️ | — | TypeScript | **non-OSS (Anthropic TOS)** | `npm install -g @anthropic-ai/claude-code` (**marked DEPRECATED in README**) | **OAuth → `~/.claude.json` + macOS Keychain** | `fifo` / `exec_per_message` | Anthropic (direct + gateway) | no | **HEADLESS-HOSTILE** auth. Must force `ANTHROPIC_API_KEY` injection and never invoke `/login`. **License conflict with CLAUDE.md OSS stance — decision needed.** |
| **aider** (paul-gauthier) | ✅ | ~80k | Python | Apache-2.0 | `pip install aider-chat` | **env var + flag, zero state** | `exec_per_message` (`aider --message`) | Anthropic, OpenAI, OpenRouter, Bedrock, Groq, Ollama, … | no | **Cleanest headless target.** ⚠ Auto-commits to git by default. ⚠ Clipboard web-chat mode bypasses egress metering. Both must be disabled in platform-billed tier. |
| **OpenHands** (All-Hands-AI) | ✅ | **40k+** | Python | MIT | `docker run` (primary) or `pip install` | LiteLLM config | `http_gateway` + CLI | 100+ via LiteLLM | **YES** (GUI mode) | **SOTA 77.6 SWE-bench.** CLI mode is sandbox-safe. **GUI mode spawns a second "runtime" container via Docker socket — Sysbox territory.** |
| **Plandex** (plandex-ai) | ✅ | ~12k | **Go** | MIT | binary release + docker-compose | env var (read by **plandex-server**, not CLI) | `http_gateway` (Go server + Go CLI) | Anthropic, OpenAI, OpenRouter, local | no | **Best architectural reference** for us — Go CLI + Go server + docker-compose + Git-style branching for plans. **Injection target = server, not agent binary.** |
| **Continue CLI** (`cn`) | ✅ | ~20k | TypeScript | Apache-2.0 | `npm install -g @continuedev/cn` | shared `config.yaml` with IDE extension | **`cn -p "<prompt>" --format json --silent --resume`** | many | no | **Best headless shape** for `exec_per_message`. Explicitly designed for Docker/CI. |
| **gpt-engineer** (AntonOsika) | ⚠️ | — | Python | MIT | `pip install gpt-engineer` | `OPENAI_API_KEY` env | **`one_shot_task`** (write prompt file, run, read output) | OpenAI | no | **Not a REPL** — whole session = one run. Last push May 2025. README redirects users to aider. |
| **SWE-agent** (princeton-nlp) | ⚠️ | ~15k | Python | MIT | `pip install swe-agent` | LiteLLM config | **`one_shot_task`** (needs GitHub issue + target repo as input) | many via LiteLLM | no | **Soft-deprecated** by maintainers in favor of `mini-swe-agent` (same scores, 100 lines). |
| **smol-developer** (smol-ai) | ⚠️ | — | Python | — | library import, not CLI | `OPENAI_API_KEY` env | **library-first** (`from smol_dev import plan`) | OpenAI only (hardcoded gpt-4-0613) | no | Last touched April 2024. **Dep rot likely.** Expects Modal.com as execution substrate. |
| **mentat** (AbanteAI) | ⚠️ | — | Python | — | `pip install mentat` | env var | **`terminal_only`** (Textual TUI) | OpenAI, Anthropic | no | **Archived upstream** — renamed to `archive-old-cli-mentat` 2025-01-07. mentat.ai is now a different product. Full-screen TUI means **no chat bridge possible — ttyd only.** |
| **Cody** (sourcegraph) | ⚠️ | — | TypeScript | Apache-2.0 | `@sourcegraph/cody-agent` npm | `SRC_ENDPOINT` + `SRC_ACCESS_TOKEN` | **`json_rpc_stdio`** | gateway-routed (Cody Gateway) | no | **Archived upstream** — renamed `cody-public-snapshot` 2025-08-01. Sourcegraph pivoted to **Amp** (`sourcegraph/amp-*` active). **Replace with Amp before L2.** |
| **gh-copilot** (GitHub) | ⚠️ | — | Go | proprietary | `gh extension install github/gh-copilot` | **OAuth device-code** (`gh auth login --web`) | `exec_per_message` | GitHub-hosted only, **no BYOK, no model choice** | no | **Breaks the "any model" pitch.** Would need pre-authed `~/.config/gh/` volume or interactive device-code from chat UI. Proprietary — won't satisfy OSS stance. |
| **crewAI** (crewAIInc) | ❌ | — | Python | MIT | `pip install crewai` | — | — | — | — | **Framework, not a runnable agent.** Listed for reference only. Wrapping it would require shipping a default crew template + chat shim. |
| **openagents-org** | ❌ | — | Python | — | `pip install openagents` | — | — | — | — | **Spec + SDK, not an agent.** ONM defines *post-launch* inter-agent messaging. **Zero schema for install/launch/auth** — orthogonal to Phase 02.5. Revisit in Phase 8+. |

---

## Architectural findings

### 1. 🦞 `picoclaw = config flavor of openclaw`, not a separate binary

From MSV grep (`router/src/agent-client.js`, `infra/picoclaw/Dockerfile`, and MSV README lines 46-52, 99-105): **PicoClaw is a CONFIG FLAVOR of OpenClaw, not a separate binary.** MSV lists `NullClaw, PicoClaw, NanoBot, OpenClaw` as *"known flavors"* of the same runtime.

**Implication:** our recipe schema is not `(agent, install, launch)` — it's `(runtime, config_flavor, launch)`. The number of base images collapses from ~20 (one per agent) to ~5 runtime families:

| Runtime family | Base image | Flavors & agents |
|---|---|---|
| `ap-runtime-node` | node 22 + npm | openclaw (+ picoclaw flavor), Claude Code, Continue CLI, Cody/Amp |
| `ap-runtime-python` | python 3.13 + uv | aider, hermes, gpt-engineer, mentat, nanobot, nanoclaw, OpenHands CLI, SWE-agent, safeclaw, smol-developer |
| `ap-runtime-rust` | rust + cargo | zeroclaw, moltis, ironclaw |
| `ap-runtime-zig` | zig toolchain | nullclaw |
| `ap-runtime-go` | go 1.25 | Plandex |

Our current `ap-picoclaw:v0.1.0-c7461f9` is misnamed — it's `ap-runtime-node` with the picoclaw flavor baked in. Reshape target: one install of each runtime, config flavors layered on top as data, not Docker layers.

### 2. `chat_io.mode` was 2 values. It needs at least 6.

| Mode | Example agents | Bridge implementation |
|---|---|---|
| `fifo` | openclaw, picoclaw, moltis, nullclaw | stdin/stdout tmux chat window, `/run/ap/chat.in` + `/run/ap/chat.out` (our current picoclaw path) |
| `exec_per_message` | aider (`aider --message`), Continue CLI (`cn -p`), hermes (`hermes chat -q`), nanobot, nanoclaw, zeroclaw | `docker exec <container> <cmd>` per message (our current hermes path) |
| `one_shot_task` | gpt-engineer, SWE-agent, smol-developer | **NEW.** Whole session = one run. Task definition (prompt file / GitHub issue / target repo) is the entire input, output is the final artifact. Bridge writes the task, runs the container, reads the output, terminates. |
| `http_gateway` | OpenHands, Plandex, HiClaw | **NEW.** Agent runs an HTTP server on an in-container port. Bridge is a Go reverse proxy, not a FIFO. Phase 5's web-terminal architecture already anticipates this. |
| `json_rpc_stdio` | Cody / Amp | **NEW.** Agent speaks JSON-RPC 2.0 over stdin/stdout (MCP-adjacent). Bridge is a framed stdio pipe, not line-buffered. |
| `terminal_only` | mentat (Textual full-screen TUI) | **NEW.** No chat bridge possible — agent owns the whole screen. Access is ttyd-only (Phase 5 web terminal). No `POST /message` endpoint. |

**Plus a future 7th:** `event_driven` for ONM-native agents. Phase 8+.

### 3. Auth mechanism taxonomy (8 categories)

| Category | Example agents | Headless-safe? | Recipe field shape |
|---|---|---|---|
| `env_var` | aider, Plandex (server), gpt-engineer, nanoclaw | ✅ | `{mechanism: env_var, var_name: "ANTHROPIC_API_KEY"}` |
| `env_var_substitution_in_config` | nanobot | ✅ | `{mechanism: config_template, var_refs: [...], target_path: "..."}` |
| `config_file` | hermes, picoclaw, moltis | ✅ (via render template) | `{mechanism: config_file, path: "...", template_id: "..."}` (our current `AgentAuthFiles`) |
| `cli_flag_on_onboard` | nullclaw | ✅ | `{mechanism: onboard_flag, command: "nullclaw onboard --api-key $KEY"}` |
| `exec_time_only` | ironclaw | ✅ (gold standard) | `{mechanism: exec_time, var_name: "..."}` |
| `gateway_token` | Cody/Amp | ✅ | `{mechanism: gateway_token, endpoint_var: "SRC_ENDPOINT", token_var: "SRC_ACCESS_TOKEN"}` |
| `oauth_flow_with_keychain` | **Claude Code** | ❌ HEADLESS-HOSTILE | **UNSUPPORTED** in v1. Frontend filters out. |
| `oauth_device_code` | **gh-copilot** | ❌ HEADLESS-HOSTILE | Possible with pre-authed volume mount, deferred. |
| `interactive_wizard` | hermes setup flow | ❌ but bypassable | Override with pre-populated config file at image build time (what our current ap-hermes does). |

### 4. Nested-container collisions (5 agents)

Agents whose documented operating mode tries to spawn its own sub-containers from inside our sandbox:

| Agent | Why it spawns | Fix |
|---|---|---|
| **hermes** | 6 terminal backends: local/Docker/SSH/Daytona/Singularity/Modal | Pin `backend: local` in baked config (already doing this for Phase 2) |
| **moltis** | Docker + Apple Container sandboxed execution built in | Pin `execution: local` OR run under **Sysbox** runtime |
| **nanoclaw** | Runs each sub-agent in its own Docker | Use `--single-container` flag if it exists, else Sysbox |
| **OpenHands** | GUI mode spawns a runtime container via Docker socket | CLI mode is safe. Frontend only exposes CLI mode OR require Sysbox |
| **HiClaw** | Multi-container by design (Matrix + Higress gateway + agent pods) | Recipe must be `compose-style`, not single-container. Or skip for v1. |

**All 5 are blocked by Phase 7.5** (Sandbox Hardening Spine) unless we ship recipe-level overrides that hardcode them to single-container mode. **Decision needed:** support these 5 via Sysbox in Phase 7.5, or drop them from v1 catalog?

### 5. License reality (CLAUDE.md "whole platform ships OSS")

| License status | Count | Agents |
|---|---|---|
| **OSS, clean** | 13 | picoclaw, openclaw, hermes, aider, OpenHands, Plandex, Continue CLI, nanobot, moltis, ironclaw, zeroclaw, nullclaw, HiClaw |
| **OSS but archived** | 4 | SWE-agent, gpt-engineer, smol-developer, mentat, Cody |
| **Non-OSS** | 2 | **Claude Code** (Anthropic TOS), **gh-copilot** (proprietary) |
| **Non-LLM / marginal** | 1 | safeclaw (deterministic, doesn't fit BYOK) |

**Claude Code decision required:** ship it as a recipe despite non-OSS license? (User value is real — most people want Claude Code.) Drop it? Ship it under a separate "non-OSS catalog" tier? **Flagging for user input — not a technical decision.**

### 6. Install mechanism distribution

| Mechanism | Agents |
|---|---|
| `pip install` | aider, OpenHands, hermes, gpt-engineer, mentat, nanobot, nanoclaw, SWE-agent, smol-developer, safeclaw, crewAI |
| `npm install -g` | Claude Code, openclaw, Continue CLI, Cody, (picoclaw historically) |
| `cargo install` | zeroclaw, moltis, ironclaw |
| `binary release` | nullclaw, Plandex, moltis |
| `docker pull` | OpenHands (primary distribution) |
| `docker compose` | HiClaw (multi-container), Plandex (CLI + server) |
| `git clone + build` | picoclaw (Go build via upstream Makefile) |

**Implication:** one `install` field is insufficient. It needs **install.type** (discriminator) + install-type-specific fields. E.g.:

```yaml
install:
  type: pip
  package: aider-chat
  version: ">=0.50.0"
---
install:
  type: cargo
  package: ironclaw
  git: https://github.com/nearai/ironclaw
  rev: c7461f9
---
install:
  type: docker_compose
  compose_file: HiClaw/docker-compose.yml
  services: [agent, higress, matrix]
```

### 7. Provider coverage — "any model" pitch feasibility

| Provider | Count of agents that support it natively |
|---|---|
| Anthropic direct | 15+ (universal) |
| OpenAI direct | 15+ (universal) |
| OpenRouter | ~10 (aider, nanobot, Plandex, OpenHands, hermes, …) |
| Groq | 6-8 |
| Local (Ollama/LMStudio) | 8+ |
| AWS Bedrock | aider, OpenHands |
| Gateway-only (Cody, gh-copilot) | 2 — **no BYOK possible** |

"Any agent × any model" holds for 13 agents. The 2 gateway-only agents (Cody/Amp, gh-copilot) can only run on their own provider — frontend must surface this constraint.

---

## What's dead / needs replacing before L2

- **SWE-agent** → `mini-swe-agent` (same scores, 100 lines, active)
- **Cody** → `sourcegraph/amp` (Sourcegraph's active replacement)
- **mentat** → skip (mentat.ai hosted bot is a different product)
- **gpt-engineer** → skip (upstream redirects to aider)
- **smol-developer** → skip (dep rot, April 2024 stale)

**Post-cleanup candidate count for L2: 15 live agents** (down from 24 after removing archived / marginal / non-runnable).

---

## What L2 must answer for each of the 15 live candidates

1. **Does the documented install command actually succeed** in a minimal ap-runtime-{lang} container? What's the real install-time footprint (disk / duration)?
2. **Where does the binary/entrypoint actually live** after install? (`/usr/local/bin/<name>`, `~/.cargo/bin/<name>`, `/opt/<name>/bin/<name>`, …)
3. **What's the real auth-discovery path?** (`strings <binary>` + grep for `ANTHROPIC_API_KEY` / config path / keychain lookups) — overriding any README claims.
4. **Does `<binary> --help` confirm the chat_io.mode we predicted from README?** (Some agents have both a REPL and an exec mode.)
5. **What's the minimum viable `recipe.yaml`** that would let our session handler launch it? (Rough shape — not a final schema.)

## What L3 must answer

For a diversity-sampled subset (at least one per chat_io.mode, both healthy auth mechanisms, and at least one agent per runtime family):

1. **Does the agent successfully complete a round-trip LLM call** from inside our hardened sandbox, against our BYOK key, through the auth mechanism we picked?
2. **How does it fail?** (Log shapes, stderr patterns, exit codes — needed so the bridge can surface errors to the UI.)
3. **Does the response text land in chat.out / stdout / http response cleanly**, or does it need ANSI stripping / multiplexed demuxing / JSON-RPC framing?

**L3 agent picks for diversity (tentative):**
- `fifo` mode → openclaw (the real parent runtime, not just picoclaw flavor)
- `exec_per_message` mode → aider (cleanest BYOK)
- `one_shot_task` mode → gpt-engineer OR mini-swe-agent (replacement for SWE-agent)
- `http_gateway` (single-container) mode → Plandex (Go reference, closest architectural match)
- `http_gateway` (multi-container compose) mode → **HiClaw** — Matrix rooms + Higress gateway + consumer-token metering pattern. This is the agent most likely to inform our **platform-billed tier** (CLAUDE.md explicitly mentions a Go egress proxy on a unix socket; HiClaw's Higress consumer-token layer is prior art for that exact pattern).
- `json_rpc_stdio` mode → sourcegraph/amp (Cody replacement)
- Terminal-only mode → mentat (archived) — **SKIP** unless replaced

**HiClaw L3 has a second motivation beyond diversity:** it's the only compose-style agent in the catalog, so it's the only one that exercises `isolation_tier: compose` in the recipe schema. If the schema handles HiClaw, it handles every other agent trivially.

---

## What Phase 02.5 must plan against

The recipe manifest schema needs, at minimum:

```yaml
# Required
id: <slug>
name: <display>
description: <one-liner>
runtime: node | python | rust | zig | go  # picks base image
license: <SPDX>
headless_safe: true | false                # frontend filters

# Install
install:
  type: pip | npm | cargo | binary | docker | docker_compose | git_build
  # type-specific fields

# Launch
launch:
  cmd: [<argv>]                            # default argv for fifo/REPL modes
  entrypoint_override: null | "..."        # for images with ENTRYPOINT conflicts
  workdir: "~/"                            # $HOME inside the container

# Chat I/O
chat_io:
  mode: fifo | exec_per_message | one_shot_task | http_gateway | json_rpc_stdio | terminal_only
  # mode-specific fields:
  fifo: { fifo_in, fifo_out }
  exec_per_message: { cmd_template: [...] }
  one_shot_task: { input_file, output_file }
  http_gateway: { internal_port, path_prefix }
  json_rpc_stdio: { framing: ... }
  terminal_only: { }

# Auth
auth:
  mechanism: env_var | env_var_substitution_in_config | config_file | cli_flag_on_onboard | exec_time_only | gateway_token
  required_secrets: [anthropic_key, openai_key, ...]
  # mechanism-specific fields:
  env_var: { var_name, mapped_from: anthropic_key }
  config_file: { path, template_id }
  # ...

# Providers
providers_supported: [anthropic, openai, openrouter, groq, bedrock, local, gateway]
model_flag: "--model"                      # how to pass model_id to the agent
model_env_var: null                        # alternative to model_flag

# State
persistent_state:
  tmpfs: [/home/agent/.picoclaw/workspace/sessions, ...]
  named_volume: null                       # Phase 7 persistent tier
  bind_mounts: []

# Isolation
isolation_tier: strict | standard | sysbox | compose
nested_container_collision: false | true

# Frontend
frontend:
  icon: <lucide icon name>
  category: <claw | chat | scaffold | sandbox | gateway>
  stars: <from GitHub>

# Optional
config_flavor_of: null                     # e.g. picoclaw → openclaw
egress_allowlist: [api.anthropic.com, ...]
resource_overrides:
  memory_mib: 2048
  cpus: 1.0
  pids_limit: 256
```

That's 15 top-level keys. **Hard to trim further without losing a real-world agent's requirements.** Better to design for this now than to hit each missing field as a surprise L3 failure.

---

## Decisions that need user input before Phase 02.5 planning

1. **Claude Code: ship or drop?** (Non-OSS, most-requested agent, headless-hostile auth.)
2. **Nested-container agents (hermes/moltis/nanoclaw/OpenHands GUI/HiClaw): Sysbox in v1 or drop to v2?** Gates ~5 agents.
3. **Dead/archived candidates — replace or skip?** `SWE-agent → mini-swe-agent`, `Cody → Amp`, others skip. Confirm the replacement list.
4. **L2 budget:** 15 agents × ~15 min install + verification ≈ 3-4 hours wall. OK to run sequentially now, or pause recon here and move to planning?
5. **Do the Phase 02.5 schema keys above feel right**, or is there a dimension you want me to add/remove before turning it into a proper plan?

This is the part where **the architect picks direction**, not the researcher.

---

# 🌊 Wave 2 addendum — 16 more agents + schema prior art

Added 2026-04-14 after a second parallel L1 pass. This section is ADDITIVE to everything above — all Wave 1 findings still hold. Wave 2 adds 16 candidates and 5 net-new schema dimensions.

## Wave 2 decisions from the architect (locked in)

- **Claude Code — keep**, marked `license: non-OSS` + `category: proprietary` + `headless_safe: false` + `requires: ANTHROPIC_API_KEY forced injection`. Frontend filters it out of the OSS-only view. We never invoke `/login`.
- **Sysbox — pragmatic tier, not final tier.** v1 stays plain Docker + cap-drop. v1.5 adds Sysbox for nested-Docker agents (Phase 7.5). v2 adds gVisor / Firecracker for untrusted bootstrap path (Phase 8+). Tiered sandbox, not monolithic.
- **Dead replacements: mini-swe-agent replaces SWE-agent; Amp replaces Cody** (both confirmed in Wave 2). mentat, gpt-engineer, smol-developer: keep L1 entry as ecosystem history, do not install.

## Wave 2 agents added to the sweep

### 🔥 Schema prior art (highest value in entire sweep)

| Agent | Status | Language | License | Why it matters |
|---|---|---|---|---|
| **Praktor** (mtzanidakis/praktor) | ✅ | Go | MIT | **Direct prior art.** Go orchestrator + YAML-declared agents + encrypted vault + per-agent Docker isolation. Architecturally the same shape we're building, minus Telegram lock-in. 23 stars but active (April 2026). Hardcoded to Claude Code inside, but the **schema shape** is what we steal. See `agents/praktor.md` for the full YAML dump. |
| **Memoh** (memohai/Memoh) | ✅ | Go + Vue 3 | AGPL-3.0 | containerd-per-agent + **gRPC-over-UDS** bridge between control plane and workspace containers. Introduces a **NEW chat_io mode** (`grpc_uds`) where keys never land in env or filesystem — they're pulled over the UDS at exec time. Cleanest threat model in the sweep. |

### High-value replacements + official vendor CLIs

| Agent | Status | Language | License | Note |
|---|---|---|---|---|
| **mini-swe-agent** (princeton-nlp) | ✅ | Python | MIT | Replaces archived SWE-agent. `pip install mini-swe-agent`, `mini` CLI, LiteLLM multi-provider. Fits `one_shot_task`. |
| **sourcegraph/amp** | ⚠️ | TypeScript | **non-OSS (proprietary)** | Replaces Cody. Cleaner headless (`amp -x --stream-json`) but **gateway-only + `AMP_API_KEY` + no BYOK**. Same license bucket as Claude Code. |
| **google-gemini/gemini-cli** | ✅ | Python | Apache-2.0 | **101k stars** — best license + traction in Wave 2. Official Google CLI. Auth: Google API key OR **ADC service account JSON** (new auth mechanism). Fits `fifo` (default) + `exec_per_message` (`gemini -p`). |
| **QwenLM/qwen-agent** | ⚠️ | Python | Apache-2.0 | Library-first, **no CLI**. Official Alibaba. Needs a `launch.wrapper_script` field or `library_mode` chat_io type. Introduces `DASHSCOPE_API_KEY` as new provider key. |
| **OpenInterpreter/open-interpreter** | ✅ | Python | AGPL-3.0 | Very popular REPL-shaped. Fits `fifo` or `exec_per_message` (`interpreter --fast`). `%`-prefixed REPL meta-commands leak into chat stream — bridge needs per-recipe escape filter. |
| **AutoCodeRoverSG/auto-code-rover** | ✅ | Python | — | **Cleanest one_shot in catalog** — Docker in, patch JSON out. Uses `OPENAI_KEY` (not `OPENAI_API_KEY`) — second agent with nonstandard env-var name. |

### Ecosystem breadth (shape stress tests)

| Agent | Status | Shape | Note |
|---|---|---|---|
| **MetaGPT** (geekan) | ✅ | `one_shot_task` | Multi-agent software company, runnable as a single command. |
| **ChatDev** (OpenBMB) | ✅ | `http_gateway` (compose) | Multi-container platform, similar shape to MetaGPT but heavier. |
| **Devika** (stitionai) | ✅ | `http_gateway` (compose) | Devin clone. Config via UI (headless-hostile, pre-populate to bypass). |
| **Devon** (entropy-research) | ⚠️ | `terminal_only` + `exec_per_message` | Devin alt. **Stagnant** since 2024-07-29. `devon-tui` is a second `terminal_only` target. AGPL-3.0. |
| **SuperAGI** (TransformerOptimus) | ⚠️ | `http_gateway` (compose, 4+ services) | **Worst-offender stress test.** If schema handles SuperAGI (backend + frontend + Postgres + Redis + vector DB), it handles everything. Soft-stagnant (~15 months, last commit Jan 2025). |
| **Codium-ai/pr-agent** | ✅ | `one_shot_task` (typed input) | Narrow-domain: PR URL + verb enum. **Introduces `input_schema` / `task_shape` field** — no existing agent had this. AGPL-3.0. |
| **voideditor/void** | ⚠️ | IDE-only | Cursor fork. **Team paused development.** No standalone CLI. Marginal recipe fit. |
| **Cursor CLI** | ⚠️ | `exec_per_message` | **Exists and active** (major update 2026-01-16, previous compass doc was wrong). Proprietary + gateway-only + `--cloud` flag bypasses our egress proxy. Introduces **`policy_flags` field** — `non_oss`, `gateway_only`, `cloud_handoff`. |

## 🚨 Wave 2 architectural finds (things Wave 1 didn't surface)

### 1. A 7th `chat_io.mode`: `grpc_uds` (Memoh)

Memoh runs an orchestrator with a **Unix-domain-socket gRPC bridge** between the control plane and each workspace container. API keys are **never placed in env or on filesystem** — they're pulled over the UDS at the exact moment the agent needs them. Cleanest threat model in the sweep (matches ironclaw's "exec-time only" philosophy but with a different mechanism).

**Implication:** our recipe schema's `chat_io.mode` enum grows from 6 → 7. Bridge layer needs a `grpc_uds` implementation eventually (Phase 5 web-terminal work or later).

### 2. `secret_file_mount` auth mechanism (Praktor) — **replaces our `AgentAuthFiles` hack**

Praktor's recipe YAML has a dead-clean shape for what we hacked in Phase 2:

```yaml
files:
  - secret: gcp-service-account   # vault entry ID, NOT the secret value
    target: /etc/gcp/sa.json
    mode: "0600"
```

The recipe **references** a vault entry by ID and specifies **where to mount it** with **what mode bits**. The vault abstraction decouples secret source from target. This is exactly what we hacked into `renderPicoclawSecurityYAML` but **generalized, not picoclaw-specific**.

**Implication:** our `recipes.AuthFile{HostFilename, ContainerPath, Render}` shape from Phase 2 is close but wrong in one dimension — the renderer is a Go function closure, not data. Praktor's is pure YAML: `{secret, target, mode}`. **Phase 02.5 migrates to Praktor's shape.**

### 3. `env_var_aliases` map — Praktor's `env:` with `secret:` prefix

```yaml
env:
  EDITOR: vim
  GITHUB_TOKEN: "secret:github-token"
```

Praktor's `env:` block accepts BOTH literal values AND `secret:<vault-key>` references in the same map. Our Phase 2 hermes/picoclaw recipes had separate `EnvOverrides` + `AgentAuthFiles` — Praktor collapses both into one.

**Plus**: this solves the `OPENAI_KEY` vs `OPENAI_API_KEY` problem (AutoCodeRover uses the non-standard name). Per-recipe `env:` map with arbitrary key names is the natural home.

### 4. `allowed_tools` field — NEW dimension we didn't have

```yaml
agents:
  researcher:
    allowed_tools: [WebSearch, WebFetch, Read, Write]
```

Praktor supports tool-level capability gating — an agent can only use the listed tools (in Claude Code's case, the MCP / built-in tool set). This is a **per-recipe capability surface** we don't have at all. Directly relevant to Phase 7.5 sandbox hardening.

**Implication:** Phase 02.5 adds `allowed_tools: [list]` to the recipe schema. Enforced by the agent itself (if it honors the list) OR by our egress proxy (if the tool makes a network call) OR by bind-mount scope (if the tool touches files).

### 5. `input_schema` / `task_shape` — narrow-domain agents need typed forms

PR-Agent doesn't take free-text chat. Its input is `{pr_url: string, action: enum[describe|improve|review|ask]}`. MetaGPT takes `{project_goal: string}`. AutoCodeRover takes `{github_issue_url, target_repo}`. None of these are chat REPLs — they're **task forms**.

**Implication:** `chat_io.mode: one_shot_task` isn't enough. The mode needs a sub-field:

```yaml
chat_io:
  mode: one_shot_task
  input_schema:
    - { key: pr_url, type: url, required: true }
    - { key: action, type: enum, values: [describe, improve, review, ask] }
```

The frontend renders a typed form instead of a chat box. This is a **category of agents** (narrow-domain) that the v0 frontend doesn't yet know about — it only has chat-shaped playground pages.

### 6. `policy_flags` field — for agents that can escape our sandbox policy

Cursor CLI has a `--cloud` flag that sends the session to Cursor's own backend regardless of our local BYOK config. That's **invisible egress** that bypasses our metering proxy. Claude Code has `/login` that triggers OAuth. gh-copilot has device-code.

**Implication:** Phase 02.5 adds a `policy_flags: []` recipe field with a closed vocabulary: `non_oss`, `gateway_only`, `cloud_handoff`, `oauth_required`, `interactive_setup`, `nested_container`. Frontend surfaces these as badges. Phase 7.5 hardening decides which flags block a recipe from the default catalog.

### 7. `runtime_extension` — nix_enabled, containerd, etc.

Praktor has `nix_enabled: true` per agent — at container start, nix is installed into the workspace so the agent can `nix-shell` arbitrary tools. Memoh uses **containerd** instead of Docker. These are **runtime-level extensions** below the agent binary.

**Implication:** a `runtime_extension` field on the recipe: `{nix: true, devcontainer: false, containerd: false}`. Most recipes have none. Phase 02.5 adds the field, implements `nix` as the first extension in Phase 7.5 sandbox hardening territory.

## Updated Phase 02.5 schema (Wave 1 + Wave 2)

After all 40 candidates, the recipe schema needs these top-level keys. **This is the final draft** before Phase 02.5 planning:

```yaml
# --- Identity ---
id: <slug>
name: <display>
description: <one-liner>
license: <SPDX string or "proprietary">
category: <claw | chat | scaffold | one-shot | multi-agent | narrow-domain | library>

# --- Runtime family (replaces 1-image-per-agent) ---
runtime: node | python | rust | zig | go   # picks ap-runtime-<x> base image
config_flavor_of: null | <parent_id>       # e.g. picoclaw flavor_of openclaw
runtime_extension:
  nix: false
  devcontainer: false
  containerd: false

# --- Install ---
install:
  type: pip | npm | cargo | binary | docker | docker_compose | git_build
  package: <name>                          # or url for binary
  version: null | "<semver>"
  git:                                     # when type=git_build
    repo: <url>
    rev: <sha>
    build_cmd: [...]
  compose_file: <path>                     # when type=docker_compose
  extras: []                               # e.g. hermes [all] (FORBIDDEN default)

# --- Launch ---
launch:
  cmd: [<argv>]                            # default argv for fifo/REPL modes
  workdir: "~/"                            # $HOME inside container
  wrapper_script: null                     # for library-first agents like qwen-agent

# --- Chat I/O (7 modes now) ---
chat_io:
  mode: fifo | exec_per_message | one_shot_task | http_gateway | json_rpc_stdio | terminal_only | grpc_uds
  # mode-specific fields:
  fifo: { fifo_in: /run/ap/chat.in, fifo_out: /run/ap/chat.out }
  exec_per_message: { cmd_template: [<agent>, chat, -q, "{text}"] }
  one_shot_task:
    input_schema:                          # typed form (PR-Agent, AutoCodeRover, MetaGPT)
      - { key: pr_url, type: url, required: true }
      - { key: action, type: enum, values: [describe, improve, review] }
    output_path: /tmp/result.json
  http_gateway: { internal_port: 8787, path_prefix: /v1 }
  json_rpc_stdio: { framing: "length-prefixed" }
  terminal_only: { }                       # ttyd access only, no POST /message
  grpc_uds: { socket_path: /run/ap/agent.sock }

# --- Auth (MERGED env + files per Praktor's shape) ---
auth:
  mechanism: env_var | env_var_substitution_in_config | secret_file_mount | cli_flag_on_onboard | exec_time_only | gateway_token | grpc_injected_at_runtime | adc_service_account_json | oauth_flow_with_keychain | oauth_device_code | interactive_wizard
  env:                                     # Praktor-style: literal OR "secret:<key>"
    EDITOR: vim
    ANTHROPIC_API_KEY: "secret:anthropic-key"
    GITHUB_TOKEN: "secret:github-token"
  files:                                   # Praktor-style secret_file_mount
    - secret: anthropic-security-yml
      target: /home/agent/.picoclaw/.security.yml
      mode: "0600"
      template: picoclaw_security_yml     # our Render closure becomes a named template
  headless_safe: true | false              # oauth_flow_with_keychain → false, etc.

# --- Model / Provider ---
providers_supported: [anthropic, openai, openrouter, groq, bedrock, gemini, dashscope, local, gateway]
model_flag: "--model"                      # how to pass model_id
model_env_var: null

# --- Capabilities & policy ---
allowed_tools: [...]                       # Praktor-style (Phase 7.5 enforces)
policy_flags:                              # closed vocabulary
  - non_oss
  - gateway_only
  - cloud_handoff
  - oauth_required
  - interactive_setup
  - nested_container
egress_allowlist: [api.anthropic.com, ...]

# --- State ---
persistent_state:
  tmpfs: [/home/agent/.picoclaw/workspace/sessions]
  named_volume: null                       # e.g. "coder" workspace (Phase 7)
  bind_mounts: []

# --- Isolation ---
isolation_tier: strict | standard | sysbox | compose | gvisor
nested_container_collision: false | true

# --- Frontend hints ---
frontend:
  icon: <lucide icon name>
  stars: <github stars>
  category_badge: <display string>
```

**17 top-level keys**, up from 15 after Wave 1. Every key is justified by ≥1 real agent in the matrix, not speculation.

## Wave 2 verdict on L2

**L2 is optional now.** The schema is grounded in Praktor's actual-working-in-production YAML + Memoh's container model + 38 README reads. L2 would ground-truth install commands, but the biggest schema risks have been surfaced by L1+prior-art, not by install failures.

**My recommendation:**
- **Skip L2 for Phase 02.5 planning.** We have enough signal.
- Do L2 **lazily, per-recipe, during implementation**. When Phase 02.5 plans a task to "add openclaw recipe", the plan includes a `verify install path` subtask that does the `npm install -g openclaw` probe in a scratch container at that moment.
- Keep L3 as the **acceptance gate** for Phase 02.5: when a recipe claims it works, we prove it with a real LLM round-trip.

## Next steps (updated)

1. **Mark recon complete.** Commit `.planning/research/agents/*` + `AGENT-MATRIX.md` as one batch.
2. **Draft the Phase 02.5 schema in `.planning/research/RECIPE-SCHEMA-DRAFT.md`** with Praktor's YAML as the starting template, our 17 keys layered in. This is a pre-phase artifact — the planner will lift it into `02.5-PLAN.md`.
3. **Run `/gsd-insert-phase 02.5 Recipe Manifest Reshape`** with the schema draft as a reference in the phase's initial context.
4. **Phase 02.5 execution lazy-runs L2** per-recipe, as verification tasks inside plans.

