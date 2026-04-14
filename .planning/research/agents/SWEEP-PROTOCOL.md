---
status: active
started: 2026-04-14
goal: Probe 23 coding agents end-to-end against ap-base to populate AGENT-MATRIX.md before designing Phase 02.5 recipe manifests.
---

# Agent Sweep Protocol

## Why

Phase 02 shipped 2 agents (picoclaw + hermes) with one bridge mechanism (`ChatIOFIFO` + `ChatIOExec`) and one BYOK injection pattern (`.security.yml`). **Sample size 1.** Any recipe manifest schema designed against that sample will break on contact with the second real agent.

This sweep produces the empirical data to design a schema that actually covers the space.

## Scope

All candidates. All combinations the agent itself claims to support. No pre-filtering beyond "does the GitHub repo exist".

## Three levels, gated by findings

### L1 — Paper recon (parallel, ~5-10 min per agent)

**Goal:** Know what we'd be installing before we install it.

For each candidate:
1. Verify the GitHub repo exists (HTTP 200 on the canonical URL).
2. Read README + any `docs/` tree.
3. Extract into `<name>.md` using the L1 schema below.
4. If the repo doesn't exist → mark `real: false`, stop.

### L2 — Install + `--help` + auth discovery (sequential, ~15 min per agent)

**Goal:** Prove the install path works and identify where the agent reads its API key from.

For each agent with `real: true`:
1. Run the install command (in a scratch container or venv — never the host).
2. Run `<agent> --help` and any `<agent> <subcommand> --help` that looks relevant.
3. `strace`-light probe (or grep source) for API key discovery path: env var, config file, OS keychain, OAuth flow.
4. Note image/install size.
5. Append L2 section to `<name>.md`.

### L3 — Live LLM round-trip (selective, ~30-60 min per agent)

**Goal:** Prove it can actually talk to a model through our ap-base substrate.

For a diverse subset (picked after L2 based on chat I/O mode diversity):
1. Create a minimal harness on top of ap-base (no session API, just docker run).
2. Inject the BYOK key via the discovered auth mechanism.
3. Send "Say hi in 5 words".
4. Capture exact response bytes + latency + exit code.
5. For agents supporting multiple providers: run once per provider (Anthropic, OpenRouter at minimum).
6. Append L3 section to `<name>.md`.

## L1 schema (every `<name>.md` must populate these)

```markdown
---
name: <agent>
real: <true|false>
source: <github url or "not found">
language: <Go|Python|TypeScript|Rust|Node|unknown>
license: <MIT|Apache-2.0|AGPL-3.0|...|unknown>
stars: <number|unknown>
last_commit: <YYYY-MM-DD|unknown>
---

# <Agent Name>

## L1 — Paper Recon

**Install mechanism:** <binary release / go install / cargo install / pip install / npm / git clone + build / docker pull>

**Install command:**
\`\`\`
<exact command from README>
\`\`\`

**Supported providers:** <Anthropic, OpenAI, OpenRouter, Groq, local, ...>

**Model-selection mechanism:** <--model flag / env var / config field / interactive prompt / hardcoded>

**Auth mechanism (best guess from docs):** <env var / config file at $path / OAuth / MCP / keychain>

**Chat I/O shape:** <stdin/stdout REPL / FIFO / HTTP API / WebSocket / MCP / exec-per-message / one-shot>

**Persistent state needs:** <none / session file / workspace dir / ~/.<agent>/ / named volume>

**Notes from README (anything unusual for sandboxing):**
- <bullet>
- <bullet>

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
```

## Aggregated output

`.planning/research/AGENT-MATRIX.md` — a single markdown table with one row per agent and one column per L1 field + a "Recipe fit" column summarizing how this agent maps to a manifest.

## Ground rules

1. **No commits to main during the sweep** except the `.planning/research/` artifacts. Source code stays untouched.
2. **No disk writes outside `.planning/research/` and scratch containers** (agent installs go into ephemeral docker containers that get removed).
3. **BYOK keys never written to disk.** Anthropic key + OpenRouter key are injected via env var at test time only.
4. **Honest failure reporting.** If an install fails, the `<name>.md` says why. Don't paper over it.
5. **No manifest schema design during this sweep.** The output is DATA, not architecture. Architecture happens in Phase 02.5 after the matrix is in.
