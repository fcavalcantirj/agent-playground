---
name: openclaw
real: true
source: https://github.com/openclaw/openclaw
language: TypeScript
license: MIT
stars: 357000
last_commit: 2026-04
---

# OpenClaw

## L1 — Paper Recon

**Install mechanism:** npm global install

**Install command:**
```
npm install -g openclaw@latest
openclaw onboard --install-daemon
```

**Supported providers:** OpenAI (Codex/ChatGPT OAuth), Anthropic, and many others; claims "any provider" via config

**Model-selection mechanism:** `agent.model` field in `~/.openclaw/openclaw.json`

**Auth mechanism (best guess from docs):** OAuth subscription (ChatGPT) OR API key via config file `~/.openclaw/openclaw.json`

**Chat I/O shape:** Long-running daemon; OpenAI-compatible HTTP API (confirmed from MSV's `router/src/agent-client.js` which POSTs to openclaw with `X-OpenClaw-Channel` header). Also multi-channel bridges (Telegram/WhatsApp/Discord/etc).

**Persistent state needs:** `~/.openclaw/` (config + workspace + agents). MSV persists `~/.openclaw/workspace` and `~/.openclaw/agents/main/agent`.

**Notes from README (anything unusual for sandboxing):**
- Requires Node 22.16+ / Node 24 recommended
- Daemon-based — install step is `openclaw onboard --install-daemon`
- MSV's PicoClaw Dockerfile treats OpenClaw as the runtime (`npm install -g openclaw@latest`) and layers PicoClaw config/plugins on top — PicoClaw is an OpenClaw CONFIG flavor, not a separate binary
- Native HTTP API; no FIFO bridge needed (unlike hermes in Phase 02)

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
