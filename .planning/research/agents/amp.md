---
name: amp
real: true
source: https://github.com/sourcegraph/amp-examples-and-guides
language: TypeScript
license: proprietary
stars: unknown
last_commit: 2026-04
---

# Amp (Sourcegraph)

## L1 — Paper Recon

**Install mechanism:** shell installer OR npm

**Install command:**
```
curl -fsSL https://ampcode.com/install.sh | bash
# or
npm i -g @sourcegraph/amp
```

**Supported providers:** **Gateway-routed, NOT BYOK.** Sourcegraph manages upstream provider keys internally; users purchase Amp credits consumed across "Anthropic API usage and OpenAI API usage handled by the platform." Models named: Claude (Opus 4.6 as "smart"), GPT-5.2, Gemini 3, Grok, Kimi K2.5 — switched via command palette (`Ctrl+O`), not a `--model` flag.

**Model-selection mechanism:** Three mode labels — `smart` (Opus 4.6), `rush` (faster/cheaper), `deep` (GPT-5.4 + extended thinking). Model switched via interactive command palette. **No model flag for headless use** — flags for this exist in `.amp/settings.json`.

**Auth mechanism (best guess from docs):** `AMP_API_KEY` env var. CLI prompts for login on first interactive run if not set. Key is scoped to Amp's own gateway, not to Anthropic/OpenAI. **Fits our existing `gateway_token` category** — same shape as the Cody pattern it replaces.

**Chat I/O shape:**
- Interactive REPL: `amp` (default)
- **One-shot / headless: `amp -x "prompt"`** — exits after agent completes
- **`--stream-json`** flag for structured output
- Piped stdin supported in both modes

Fits our `exec_per_message` mode cleanly (`amp -x "<msg>"`). This is a much cleaner headless story than Cody's JSON-RPC-over-stdio.

**Persistent state needs:**
- Workspace config: `.amp/settings.json` (or `.jsonc`)
- User config: `~/.config/amp/settings.json`
- `--settings-file` flag for custom location — helpful for recipe-level overrides at image build time.

**Notes from README (anything unusual for sandboxing):**
- **Proprietary / closed-source** — no public source repo. Examples and guides live at `sourcegraph/amp-examples-and-guides`; the CLI itself is a closed-source npm package. **Collides with CLAUDE.md OSS stance.** Same bucket as Claude Code — needs user decision.
- **Gateway-only → breaks the "any model × any agent" pitch.** Users can't BYOK an Anthropic key directly; they must pay Sourcegraph in Amp credits. Same limitation as gh-copilot.
- **Much cleaner headless mode than Cody** (`amp -x "prompt" --stream-json`) — if we ship it, recipe is trivial: `{install: npm, entry: amp, io_mode: exec_per_message, auth: gateway_token(AMP_API_KEY)}`.
- Sub-agents: Oracle (code analysis), Librarian (remote/GitHub code search), Painter (image gen). None of these spawn extra containers — all run inside the same CLI process.
- Successor to Cody after Sourcegraph's 2025-08 pivot. Matrix should swap Cody → Amp.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
