---
name: mentat
real: true
source: https://github.com/AbanteAI/archive-old-cli-mentat
language: Python
license: Apache-2.0
stars: 2558
last_commit: 2025-01-07
---

# Mentat — archived; replaced by hosted mentat.ai GitHub bot

## L1 — Paper Recon

**Install mechanism:** `pip install mentat` from PyPI (Python 3.10+). Repo was renamed to `archive-old-cli-mentat` and **archived 2025-01-07**; the name "Mentat" is now a hosted GitHub code-review bot at mentat.ai — a completely different product. The CLI tool is dead upstream.

**Install command:**
```
python -m pip install mentat
```
Last usable release tag: `v1.0.17` (v1.0.19 is the deprecation stub that just prints an EOL notice).

**Supported providers:** OpenAI (default, GPT-4 era), Azure OpenAI, Ollama, and "other services" via configuration. No first-class Anthropic or OpenRouter path documented in the README.

**Model-selection mechanism:** Config file + CLI flags. Model name passed through to the underlying OpenAI-compatible client.

**Auth mechanism (best guess from docs):** `OPENAI_API_KEY` environment variable, loaded from a `.env` file in the project root or from the shell environment. Also supports `AZURE_OPENAI_*` vars for the Azure path.

**Chat I/O shape:** Interactive **TUI** built on the Python Textual framework, launched as `mentat <paths>` where paths are files/directories to include as context. Not a simple stdio REPL — Textual draws a full-screen terminal UI, which complicates headless bridging. No documented one-shot / `-p` mode.

**Persistent state needs:** Requires `git init` in the target workspace — Mentat uses git history and `.gitignore` rules to filter files. Project-scoped, works on a cwd. No `~/.mentat/` documented; context is rebuilt per run.

**Notes from README (anything unusual for sandboxing):**
- **Flag: archived.** Pinning to `v1.0.17` is the only way to use it; no upstream fixes, no new models. Low priority for Phase 02.5.
- **Flag: Textual TUI, not stdio.** Adding it would force the recipe schema to express "full-screen TTY app" which is *only* reachable via ttyd (the terminal view), not via the chat bridge. That's a meaningful data point — it proves the schema needs a "no-chat-bridge, terminal-only" mode.
- Hard git dependency inside the container (workspace must be `git init`-ed before launch).
- Python deps are heavy vs. the Go agents; base image would need Python 3.10+ plus Textual's compiled deps.
- The new mentat.ai is a hosted SaaS GitHub App, not a CLI — it cannot run inside our containers at all.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
