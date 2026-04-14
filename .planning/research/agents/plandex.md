---
name: plandex
real: true
source: https://github.com/plandex-ai/plandex
language: Go
license: MIT
stars: 15236
last_commit: 2025-10-03
---

# Plandex

## L1 — Paper Recon

**Install mechanism:** Shell script that drops a prebuilt binary (zero-dep CLI); Docker compose for the self-hosted server component.

**Install command:**
```
curl -sL https://plandex.ai/install.sh | bash
```

**Supported providers:** Anthropic, OpenAI, Google, OpenRouter, plus arbitrary open-source providers via OpenRouter or local endpoints. Ships "curated model packs" combining models from different vendors inside one plan.

**Model-selection mechanism:** Model packs selected via CLI command / config; individual roles inside a plan (planner, coder, summarizer, verifier, etc.) can be overridden per-pack. Not a single `--model` flag — Plandex is explicitly multi-model-per-session.

**Auth mechanism (best guess from docs):** Environment variables per provider, e.g. `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. Claude Pro/Max subscription connect prompted interactively on first run. Keys are read by the **plandex-server**, not the CLI — the CLI talks to the server via HTTP.

**Chat I/O shape:** REPL with fuzzy autocomplete for commands and file loading; also accepts one-shot subcommands (`plandex tell`, `plandex chat`, etc.). CLI is a thin client against a local or remote **plandex-server** HTTP API. Plans have a "chat mode" and a "tell mode".

**Persistent state needs:** Substantial. Requires a running `plandex-server` (Docker compose locally, or cloud — note Plandex Cloud winding down 2025-10-03, self-host is now canonical). Server persists plans, versions, context, and branches. Plans have full Git-style version control of every update. CLI side keeps a workspace/project dir; plans live server-side keyed by project.

**Notes from README (anything unusual for sandboxing):**
- Architecturally closest match to Agent Playground: Go CLI + Go server, same stack family.
- Server-side state model is exactly the "multi-project session" pattern we want to learn from — plans are persistent objects with branches, not ephemeral conversations.
- Self-hosted Docker mode means we could potentially run plandex-server *inside* the per-user container as the agent backend, with the CLI as the user-facing surface.
- Keys live on the server, not the CLI — recipe has to inject env into the *server* process, not the agent binary.
- Windows requires WSL. Irrelevant for our Linux containers but worth noting.
- Cloud offering wound down; community is pushed to self-host — lowers the risk that upstream yanks the install URL.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
