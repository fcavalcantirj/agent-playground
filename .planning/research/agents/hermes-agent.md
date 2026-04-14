---
name: hermes-agent
real: true
source: https://github.com/NousResearch/hermes-agent
language: Python
license: MIT
stars: 83847
last_commit: 2026-04-14
---

# Hermes Agent

## L1 — Paper Recon

**Install mechanism:** Curl-to-bash install script that bootstraps a Python venv (uv) and installs the `hermes-agent` package with extras. Supports Linux, macOS, WSL2, Android/Termux. Not supported natively on Windows. Heavy deps (the `.[all]` extra pulls Playwright/Chromium and voice libs — README explicitly warns).

**Install command:**
```
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# From source (contributor path):
git clone https://github.com/NousResearch/hermes-agent.git
cd hermes-agent
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv venv --python 3.11
source venv/bin/activate
uv pip install -e ".[all,dev]"
```

**Supported providers:** Nous Portal, OpenRouter (200+ models), Xiaomi MiMo, z.ai/GLM, Kimi/Moonshot, MiniMax, Hugging Face, OpenAI, Anthropic (implied via OpenClaw migration importing an ANTHROPIC key), and any custom OpenAI-compatible endpoint.

**Model-selection mechanism:** `hermes model` interactive subcommand, or `/model [provider:model]` slash command inside the CLI/messaging session. Can also be set via `hermes config set`.

**Auth mechanism (best guess from docs):** Config + secrets in `~/.hermes/` directory. Allowlisted API keys (Telegram, OpenRouter, OpenAI, Anthropic, ElevenLabs) are imported during `hermes claw migrate` from `~/.openclaw/`. Likely stored in a YAML/JSON config under `~/.hermes/`. The setup wizard (`hermes setup`) writes them. No documented OS-keychain integration.

**Chat I/O shape:** Multi-modal:
- `hermes` → full TUI with multiline editing, slash commands, streaming tool output, Ctrl+C interrupt
- `hermes gateway` → long-running process bridging Telegram/Discord/Slack/WhatsApp/Signal/Email
- Python RPC for subagent spawning
- Six "terminal backends" for command execution: local, Docker, SSH, Daytona, Singularity, Modal — meaning Hermes itself can spawn nested execution environments (relevant for our sandbox: we must pin the local backend or it may try to nest Docker)

**Persistent state needs:** `~/.hermes/` for config, memory, skills (`~/.hermes/skills/`), session FTS5 SQLite DB, personalities, context files (AGENTS.md). Assumes a persistent home dir across sessions. Baked volume for our platform-billed tier.

**Notes from README (anything unusual for sandboxing):**
- `.[all]` extra pulls Playwright + Chromium; Termux uses a restricted `.[termux]` extra — our container should use the minimal extra to keep image size down unless browser tools are needed.
- Native tool system spans 40+ tools including subagent spawning — may attempt to exec additional processes inside the container, relevant for PID/cpu limits.
- Has a built-in learning loop that writes to `MEMORY.md` / `USER.md` autonomously. State grows over time; not ephemeral-friendly.
- Cron scheduler built in — if enabled inside a sandboxed container, needs a long-lived process (not `--rm` one-shot).
- Honcho dialectic user modeling is an external service dep (may phone home).
- `hermes claw migrate` imports from OpenClaw — path-based detection of `~/.openclaw`; won't trigger in clean container unless we seed it.
- Python 3.11 pinned by contributor docs.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
