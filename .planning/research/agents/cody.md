---
name: cody
real: true
source: https://github.com/sourcegraph/cody-public-snapshot
language: TypeScript
license: Apache-2.0
stars: 3795
last_commit: 2025-08-01
---

# Cody (Sourcegraph) — archived; superseded by Amp

## L1 — Paper Recon

**Install mechanism:** npm package `@sourcegraph/cody-agent` (`npx @sourcegraph/cody-agent help`), or a prebuilt self-contained executable from the `sourcegraph/cody` GitHub releases page. The repo was renamed to `cody-public-snapshot` and **archived 2025-08-01**; Sourcegraph pivoted the agent line to **Amp** (see `sourcegraph/amp-examples-and-guides`, `amp.nvim`, `amp-sdk-demo` — all active through 2026). Cody IDE extensions (VS Code, JetBrains, emacs-cody, cody-vs) are still actively developed but are a different surface.

**Install command:**
```
npx @sourcegraph/cody-agent help
# or download platform binary from https://github.com/sourcegraph/cody/releases
```

**Supported providers:** Routed via the Sourcegraph **Cody Gateway** (Anthropic, OpenAI, Fireworks for embeddings, plus any model the user's Sourcegraph instance is configured to expose). BYOK is possible by pointing the CLI at a self-hosted Sourcegraph instance with its own LLM config. No direct BYOK-without-Sourcegraph path documented.

**Model-selection mechanism:** Determined by the Sourcegraph instance the CLI authenticates against — the server decides which models are available. Client can request a specific model from the allowed list.

**Auth mechanism (best guess from docs):** `SRC_ENDPOINT` + `SRC_ACCESS_TOKEN` environment variables (standard Sourcegraph CLI convention — same pattern `src-cli` uses). Token obtained from the user's Sourcegraph account page. **Requires a Sourcegraph account** (free, work, or self-hosted) — this is NOT a BYOK-direct-to-Anthropic model.

**Chat I/O shape:** The `cody-agent` package is primarily a **JSON-RPC server** spoken by the IDE plugins (JetBrains, Neovim, VS Code) — not a chat REPL. CLI-style invocation exists for scripting but the first-class integration is JSON-RPC over stdio. That means "chat" for a user would require a second-layer shim that speaks JSON-RPC and surfaces messages.

**Persistent state needs:** Workspace dir for indexing; local cache; no fixed persistent state beyond Sourcegraph account config. Indexing context lives on the Sourcegraph server, not the client.

**Notes from README (anything unusual for sandboxing):**
- **Flag: archived upstream.** New Sourcegraph agent work is in Amp. If we add Cody we're wiring in a frozen artifact. Consider Amp as a replacement candidate instead.
- **Flag: NOT CLI-shaped in the traditional sense.** It's a JSON-RPC agent server, which is a third I/O mode we haven't seen in Phase 02 (picoclaw + hermes are both stdio REPLs). Adding it would force the recipe schema to express "agent speaks JSON-RPC on stdio, bridge translates to chat".
- Gateway-only auth model is the most unusual of the six — no BYOK-direct-to-Anthropic, which breaks the Agent Playground "any model" pitch unless we route through a user-owned Sourcegraph instance.
- Self-contained binary releases exist, so install doesn't require npm in the container.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
