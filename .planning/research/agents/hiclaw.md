---
name: hiclaw
real: true
source: https://github.com/agentscope-ai/HiClaw
language: unknown
license: unknown
stars: unknown
last_commit: 2026-04
---

# HiClaw

## L1 — Paper Recon

**Install mechanism:** unknown at L1 (likely npm or docker-compose — extends OpenClaw)

**Install command:**
```
# Not yet confirmed at L1
git clone https://github.com/agentscope-ai/HiClaw.git
```

**Supported providers:** Inherits whatever OpenClaw + the Higress AI Gateway support (OpenAI, Anthropic, plus the full Higress provider list)

**Model-selection mechanism:** Via the Higress AI Gateway — a consumer token dispatches to the configured upstream model

**Auth mechanism (best guess from docs):**
- **Novel model:** Worker agents NEVER hold real API keys. They hold a "consumer token" (like an employee badge) and the Higress AI Gateway holds the real provider keys.
- Matches our egress-proxy metering pattern closely — possibly the cleanest fit of any agent for our platform-billed path.

**Chat I/O shape:** Multi-agent team. All conversations in Matrix rooms (human-in-the-loop). Manager Agent coordinates Worker Agents.

**Persistent state needs:** Matrix homeserver state + per-worker workspace + Higress gateway config

**Notes from README:**
- NOT in `frontend/components/agent-card.tsx` v0 catalog — user added it separately to the recon list
- Described as "Team edition of OpenClaw"
- **Requires Matrix server + Higress gateway** — this is a MULTI-CONTAINER agent. Does NOT fit our "one container per session" model cleanly without a compose-style recipe.
- agentscope-ai is the canonical org (also mirrored on `higress-group/hiclaw` and listed as `alibaba/hiclaw`)
- Openclaw GitHub issue #36165 is a showcase + Matrix plugin contribution discussion — confirms the relationship to openclaw upstream

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
