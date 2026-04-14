---
name: cursor-cli
real: true
source: https://cursor.com/cli
language: unknown
license: proprietary
stars: unknown
last_commit: 2026-01-16
---

# Cursor CLI (`cursor-agent`)

## L1 — Paper Recon

**Install mechanism:** curl | bash shell installer from cursor.com (NOT a GitHub release)

**Install command:**
```
# macOS / Linux / WSL
curl https://cursor.com/install -fsS | bash
# Windows PowerShell
irm 'https://cursor.com/install?win32=true' | iex
```

**Supported providers:** Cursor-hosted only — routes through Cursor's backend to OpenAI / Anthropic / etc. Model selection via `--model` flag (e.g. `--model gpt-5.2`). **No direct BYOK** to upstream providers — users pay Cursor, Cursor pays the upstream. Same shape as **gh-copilot** and **Cody/Amp** in the existing matrix — `gateway-routed` provider tier.

**Model-selection mechanism:** `--model <id>` flag

**Auth mechanism (best guess from docs):** `env_var` — `CURSOR_API_KEY` for script/automation mode; also supports interactive device-code / browser login for first-time setup. **Headless-safe** via the env var path. Previously-reported concern (no Cursor CLI) is OBSOLETE — it shipped 2025-09 and received major updates on **2026-01-16** (agent modes Plan/Ask, cloud handoff, one-click MCP auth).

**Chat I/O shape:** Two modes:
- Interactive REPL: `agent` / `agent "initial prompt"` — matches `fifo` shape (stdin/stdout terminal session)
- Print / non-interactive: `agent -p "<prompt>" --output-format text` — matches `exec_per_message` shape
Session resume: `agent ls` / `agent resume` / `--continue` / `--resume=<chat-id>`. **Closest fit is `exec_per_message` for our headless recipe.**

**Persistent state needs:** session DB for `agent resume` / `agent ls`; API key for `CURSOR_API_KEY`; built-in `/sandbox` setting (the CLI runs its own sandbox — potential collision with our outer sandbox).

**Notes from README (anything unusual for sandboxing):**
- **CORRECTION TO PRIOR RESEARCH:** Previous doc claimed "no standalone Cursor CLI as of March 2026." **WRONG as of 2026-04-14.** Cursor CLI is real, public, beta, and actively developed — most recent major release Jan 16, 2026.
- **Proprietary (closed-source), gateway-routed.** Same policy concerns as Claude Code and gh-copilot:
  - Non-OSS: conflicts with CLAUDE.md OSS stance.
  - Gateway-only: **no BYOK possible** to upstream providers — users cannot bring an Anthropic key and save money; they pay Cursor's markup. Breaks "any model" pitch.
- **Has its own built-in `/sandbox` mode** — NEW concern. An agent that ships its own sandbox layer may collide with our outer Docker isolation (permission denials, double-jailing, etc.). Not a blocker but needs L2 verification.
- **Cloud handoff (`-c` / `--cloud` flags)** — CLI can offload work to Cursor's cloud. **Invisible egress** from our sandbox perspective — the agent decides to send code off-box without our egress proxy seeing it. **Security concern:** our egress allowlist won't catch it because it happens at the Cursor API layer, not at the raw HTTP layer. Flag for Phase 7.5 sandbox hardening.
- **Still in beta** per docs. "Security safeguards still evolving."
- **Recipe fit verdict:** technically viable as a recipe (install, launch, headless flag, env var all exist), **but policy-blocked by the same constraints as Claude Code + gh-copilot:** non-OSS + gateway-only. Ship only if we accept a "non-OSS catalog" tier. Schema gap: need a `policy_flags: [non_oss, gateway_only, cloud_handoff]` field so the frontend can warn users.
