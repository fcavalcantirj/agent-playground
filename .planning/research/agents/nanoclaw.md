---
name: nanoclaw
real: true
source: https://github.com/qwibitai/nanoclaw
language: unknown
license: MIT
stars: unknown
last_commit: unknown
---

# NanoClaw

## L1 — Paper Recon

**Install mechanism:** unknown at L1 — `/setup` skill is invoked interactively via Claude Code (AI-native install)

**Install command:**
```
# Per README: install triggered by running the /setup skill inside Claude Code
# No traditional one-liner — Claude Code is the installer
```

**Supported providers:** Anthropic only — runs directly on Anthropic's Agents SDK. No multi-provider story.

**Model-selection mechanism:** Whatever model Claude Code is configured with

**Auth mechanism (best guess from docs):** `ANTHROPIC_API_KEY` env var (inherited from the Claude Code session that bootstraps it)

**Chat I/O shape:** Runs each agent in its OWN Linux container — "agent swarms" built on Claude Code's agent-teams capability. Multi-channel bridges (WhatsApp/Telegram/Slack/Discord/Gmail).

**Persistent state needs:** Per-agent container state; memory store; scheduled job state

**Notes from README:**
- NOT in `frontend/components/agent-card.tsx` v0 catalog — user added it separately to the recon list
- ~3,900 LoC across 15 files — genuinely tiny and auditable
- **Architectural collision:** NanoClaw's core premise is "each AI agent in its own Docker container." This collides with our per-user container model. Either:
  - Requires Sysbox / DinD for v1.5, OR
  - We treat the ENTIRE user session as one NanoClaw agent (no swarm)
- Built on top of Claude Code — so the install is effectively "bootstrap Claude Code, then let it install itself." This is the same shape as our generic Claude-Code-bootstrap recipe path.
- Other `nanoclaw` repos exist (`Clawland-AI/nanoclaw` Python, `hustcc/nano-claw`); `qwibitai/nanoclaw` is the canonical one referenced by thenewstack.io writeup
- Anthropic-only locks it to the Anthropic BYOK path — no OpenRouter/OpenAI

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
