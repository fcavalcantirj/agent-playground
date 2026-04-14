---
name: openagents-org
real: true
source: https://github.com/openagents-org/openagents
language: Python
license: unknown
stars: unknown
last_commit: unknown
category: platform-spec
---

# OpenAgents (openagents-org)

**NOTE:** This is NOT a runnable coding agent like picoclaw or aider. It is a **spec + Python SDK** for how agents discover and talk to each other after they're running. Listed in the sweep so we know not to reinvent it later and so we can evaluate whether it belongs in Phase 8+ (multi-agent / agent-to-agent orchestration).

## L1 — Paper Recon

**What it is:** An "Open Agent Network Model" (ONM) — an event-driven specification for how agents communicate, discover each other, and share resources *once they are already running*. Website tagline: *"An Open Agent Network and a Community to Build It."*

**Install mechanism (for the SDK, not for target agents):** `pip install openagents` (published on PyPI).

**Supported providers:** N/A — ONM is provider-agnostic, lives above the model-call layer. Agents using ONM still BYOK their own LLM providers.

**Model-selection mechanism:** N/A.

**Auth mechanism:** "Progressive Verification" — from anonymous agents to full W3C DID verification, each network sets its own minimum.

**Chat I/O shape:** Event-driven. *"Events, not requests, form the basis — every interaction is an event. Request-response is two events linked by a correlation ID."* Mentions MCP + A2A protocols as the wire layer.

**Persistent state needs:** Not prescribed — networks handle their own.

**Notes from README:**
- Runtime-agnostic: "does not prescribe a specific runtime, language, or framework"
- Network-boundary concept: events don't leak across network boundaries unless explicitly bridged
- Extensibility via **mods** (auth, persistence, analytics are mods in the event pipeline, not baked into core)
- Agents have URN-style addresses: `agent:alice`, `openagents:claude`, `channel/general`, `resource/tool/search_web`
- The docs page explicitly labels its "Agent Marketplace" as **aspirational / future feature** — no actual catalog yet.
- Docs are marked: *"This documentation is still under active revision. Some code examples might be using outdated APIs."*

## L2 — Install + Help

NOT RUN. Out of scope — we're not running it as an agent, we're evaluating it as a spec.

## L3 — Live round-trip

NOT APPLICABLE — ONM is a protocol spec, not a model-calling CLI.

## Relevance to Agent Playground

**Does it solve our Phase 02.5 recipe problem?** **No.** ONM is entirely about *post-launch* agent-to-agent communication. It defines zero schema for:

- Install commands
- Binary / entrypoint paths
- Auth file locations
- Container / sandbox requirements
- Chat I/O bridging (stdin/stdout ↔ our FIFO bridge)

These are exactly the fields our recipe manifest needs. ONM is orthogonal.

**Where it WOULD matter later:**
- **Phase 8+ (multi-agent orchestration):** if we want two agents in two different sandboxes to cooperate on a task, ONM is a candidate for the inter-agent wire protocol. MCP (Anthropic's Model Context Protocol) is the more established alternative and is already referenced in ONM docs as a prerequisite layer.
- **Phase 5 (terminal/bridge layer):** if any target agent (e.g. a future "openagents-native" agent) only speaks ONM events and not stdin/stdout, our bridge layer would need an ONM adapter. Currently no agent in our candidate list requires this.

**Action:** Skip for Phase 02.5. Revisit when we plan Phase 8 multi-agent work — at that point evaluate ONM vs MCP vs plain HTTP message passing.

## Related but separate

- **`xlang-ai/OpenAgents`** (COLM 2024) — an academic paper-code release titled "An Open Platform for Language Agents in the Wild". Completely different project despite name collision. Worth a separate L1 entry later if relevant.
- **`OpenAgentsInc/openagents`** — a different GitHub org's agent project (tagline: "Autopilot and the agent network"). Name collision #2.
- **Oracle Agent Spec (`oracle/agent-spec`)** — a *different* "Open Agent Specification" from Oracle, published 2026-03. This one IS focused on "a unified representation for AI agents" and might overlap more with what we need. Flagged for follow-up L1.
