---
name: claude-code
real: true
source: https://github.com/anthropics/claude-code
language: Shell
license: unknown
stars: 113938
last_commit: 2026-04-14
---

# Claude Code

## L1 — Paper Recon

**Install mechanism:** Official install script (curl|bash) is now recommended; Homebrew cask on macOS/Linux; winget/PowerShell on Windows. **npm install is marked DEPRECATED** in the README (as of the read) — but still functions and remains the easiest install inside a minimal Linux container because no root/package-manager hooks are needed.

**Install command:**
```
# Recommended (macOS/Linux):
curl -fsSL https://claude.ai/install.sh | bash

# Homebrew:
brew install --cask claude-code

# Windows:
irm https://claude.ai/install.ps1 | iex
# or: winget install Anthropic.ClaudeCode

# Deprecated but still works (best for containers):
npm install -g @anthropic-ai/claude-code
```

Then run `claude` from any project directory.

**Supported providers:** Anthropic (first-class, default). Official Anthropic docs also document Amazon Bedrock and Google Vertex AI backends via environment variables. OpenAI / OpenRouter are NOT first-class — Claude Code is an Anthropic-owned product optimized for Claude models. (Some community forks add OpenRouter support; upstream does not.)

**Model-selection mechanism:** `--model` CLI flag, `/model` slash command inside the interactive session, or `ANTHROPIC_MODEL` env var. Default picks latest Sonnet.

**Auth mechanism (best guess from docs):** Two paths:
1. **Interactive OAuth** via `/login` (or first-run prompt) — opens browser, user signs in at claude.ai, callback stores a long-lived session credential. Canonical storage path (per Anthropic docs) is `~/.claude/` — specifically `~/.claude.json` for settings and credentials; on macOS the token is placed in the **macOS Keychain** under service name `Claude Code`. On Linux it falls back to a file under `~/.claude/`.
2. **API key** via `ANTHROPIC_API_KEY` env var (recommended for headless / CI / our sandbox). Also `ANTHROPIC_AUTH_TOKEN` for OAuth-style tokens, and `CLAUDE_CODE_USE_BEDROCK=1` / `CLAUDE_CODE_USE_VERTEX=1` to flip backends.

**Chat I/O shape:**
- Interactive TUI REPL (`claude`) — stdin/stdout with full-screen terminal UI (prompt toolkit / Ink-style).
- One-shot non-interactive: `claude -p "prompt"` (or `--print`) — prints response to stdout then exits. Supports stdin piping (`echo "..." | claude -p`).
- `--output-format stream-json` for machine-readable streaming — ideal bridge target for our chat WS bridge.
- Headless mode honors `--permission-mode`, `--allowedTools`, `--disallowedTools` for sandbox policy.

**Persistent state needs:** `~/.claude/` directory holds: `claude.json` (settings), `credentials.json` or keychain entry, `projects/` (per-project session history), `todos/`, `statsig/`, MCP config, and an IDE bridge socket. Per-project conversation history is written under `~/.claude/projects/-<sanitized-cwd>/`. Volume needed for session continuity.

**Notes from README (anything unusual for sandboxing):**
- npm install is flagged deprecated, so long-term we should prefer the shell installer — but the shell installer downloads a native binary from anthropic.com, which a locked-down container may block via egress policy. npm-in-container is pragmatically simpler for v1.
- README is very thin on config internals — real docs live at https://code.claude.com/docs/en/setup and https://code.claude.com/docs/en/settings. We should fetch those in L2 to confirm the exact credentials path on Linux.
- For our BYOK flow, `ANTHROPIC_API_KEY` env injection is the clean path — no OAuth, no keychain, no browser. The OAuth flow is fundamentally incompatible with headless containers.
- Bedrock / Vertex as backends is interesting for users who can't egress directly to api.anthropic.com.
- `/bug` command collects telemetry — should be disabled or policy-disallowed in ephemeral containers (`DISABLE_TELEMETRY=1` or similar).
- LICENSE file does not surface in the gh metadata call (`licenseInfo: null`) — treat license as **proprietary / Anthropic TOS**, not OSS. This matters for our "OSS platform" positioning: we depend on a non-OSS CLI.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
