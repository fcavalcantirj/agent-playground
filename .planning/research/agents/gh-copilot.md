---
name: gh-copilot
real: true
source: https://github.com/github/gh-copilot
language: unknown
license: unknown
stars: 1139
last_commit: 2025-10-30
---

# GitHub Copilot CLI (`gh copilot`)

## L1 — Paper Recon

**Install mechanism:** GitHub CLI extension. Requires `gh` (GitHub CLI) already installed; the extension is a sidecar binary distributed through GitHub's extension registry. Repo is a distribution manifest + docs, not open source — the binary itself is closed.

**Install command:**
```
gh extension install github/gh-copilot --force
```
Prerequisite: `gh auth login --web` with a GitHub account that has an active **GitHub Copilot subscription** (Individual, Business, or Enterprise).

**Supported providers:** **GitHub Copilot only.** No BYOK to Anthropic, OpenAI direct, or OpenRouter. Models are whatever GitHub Copilot's backend currently routes to (GPT-4o / o1 / Claude / Gemini depending on Copilot tier). User does not pick the provider; GitHub does.

**Model-selection mechanism:** Server-side — `gh copilot config` exposes settings but model identity is opaque to the user. No `--model` flag on `suggest` / `explain`.

**Auth mechanism (best guess from docs):** **OAuth via `gh auth login --web`.** Classic PATs and fine-grained PATs are explicitly unsupported — may need to unset `GITHUB_TOKEN` and `GH_TOKEN` env vars in the container so the CLI forces the interactive OAuth flow. Credentials cached by `gh` in its own config (`~/.config/gh/hosts.yml`).

**Chat I/O shape:** **Not a chat REPL.** Two one-shot subcommands:
- `gh copilot suggest "<natural language>"` → shell command suggestion
- `gh copilot explain "<command>"` → explanation
Plus `ghcs` / `ghce` aliases that can execute the suggested command. There is no multi-turn chat; each invocation is independent.

**Persistent state needs:** `gh copilot config` (analytics opt-in, confirm-before-exec). Auth token lives in `gh`'s config dir. No workspace state.

**Notes from README (anything unusual for sandboxing):**
- **Flag: NOT a general coding agent.** This is a shell-command-suggestion tool, not a file-editing agent. Recipe fit is marginal — it doesn't edit code, doesn't take project context beyond cwd, and has no chat mode. Document for completeness but expect to classify as "utility, not agent".
- **Flag: auth model is unique.** Every other candidate uses env-var API keys; this one uses OAuth via a second binary (`gh`). Recipe must install `gh` first, then the extension, then handle interactive `gh auth login --web` — which is *impossible* in a fully-headless container. Either the user brings a pre-authed `~/.config/gh/` volume, or the recipe opens a device-code flow in the browser from the chat UI.
- **Flag: no BYOK.** Contradicts the Agent Playground "any model" pitch entirely — this one is "any user with a Copilot sub".
- Classic/fine-grained PATs are *unsupported*, so we cannot paper over the OAuth flow with a PAT shortcut. Device-code flow is the only option.
- The extension binary is closed-source; only the install manifest lives in the GitHub repo. Supply-chain trust is "trust GitHub".

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
