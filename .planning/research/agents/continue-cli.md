---
name: continue-cli
real: true
source: https://github.com/continuedev/continue
language: TypeScript
license: Apache-2.0
stars: 32555
last_commit: 2026-04-14
---

# Continue CLI (`cn`)

## L1 — Paper Recon

**Install mechanism:** npm global install (Node 20+) or curl-to-bash shell script. Lives under `extensions/cli/` in the monorepo — the primary Continue product is still the IDE extension, but the CLI (`cn`) is a real, shipping surface.

**Install command:**
```
npm i -g @continuedev/cli
# or
curl -fsSL https://raw.githubusercontent.com/continuedev/continue/main/extensions/cli/scripts/install.sh | bash
```

**Supported providers:** Inherits from the Continue core config — Anthropic, OpenAI, OpenRouter, Azure, Gemini, Mistral, Ollama, LM Studio, and many more. Provider list not explicit in the CLI README but the shared `config.yaml` schema covers the full Continue ecosystem. **To confirm at L2.**

**Model-selection mechanism:** Via shared Continue `config.yaml` (the same config the IDE extension uses) with `--config <path>` override on the CLI. Models are named entries in the config; the CLI picks by name.

**Auth mechanism (best guess from docs):** `cn login` / `cn logout` subcommands exist → implies an OAuth-ish flow against the Continue Hub. BYOK keys live in the shared `config.yaml`. Env var `CONTINUE_CLI_DISABLE_COMMIT_SIGNATURE` confirmed; full env var list not in README.

**Chat I/O shape:** Dual mode — interactive REPL (`cn`) and headless one-shot (`cn -p "<prompt>"`) for scripts, CI, and Docker. Supports TTY-less execution, `--format json`, `--silent` (strips thinking tags). Explicitly designed for containerized/CI use.

**Persistent state needs:** Auto-saves per-terminal-session chat history; resumable via `cn --resume` or `cn ls`. Config path overridable via `--config`; default location not stated in README (likely `~/.continue/`). Workspace dir is just the cwd.

**Notes from README (anything unusual for sandboxing):**
- **Best headless shape of the six probed here.** `cn -p` + `--format json` + `--silent` makes it trivially scriptable from the Go bridge — maps cleanly to `ChatIOExec` pattern.
- Monorepo: CLI is one of several products, so version tracking is tied to the extension release cadence.
- `cn login` path means the recipe may need to handle interactive auth for hub features vs. pure BYOK — two install modes possible.
- TypeScript/Node runtime → bigger base image than Go/Rust agents.
- Chat history persistence is per-terminal-session, which is the exact pattern our single-user containers would naturally inherit.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
