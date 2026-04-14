---
name: gemini-cli
real: true
source: https://github.com/google-gemini/gemini-cli
language: TypeScript
license: Apache-2.0
stars: 101000
last_commit: 2026-04-13
---

# Google Gemini CLI

## L1 — Paper Recon

**Install mechanism:** npm

**Install command:**
```
npm install -g @google/gemini-cli
```

**Supported providers:**
- Google Gemini (direct API via AI Studio key)
- Vertex AI (enterprise, ADC)
- MCP servers (extensible, model-agnostic tool layer)

**Model-selection mechanism:** `gemini -m gemini-2.5-flash` (or `-m <model-id>`)

**Auth mechanism (best guess from docs):** **Three-way auth fork — NEW for our matrix:**
1. `GEMINI_API_KEY` env var (from aistudio.google.com) — clean `env_var` fit
2. OAuth via "Sign in with Google" browser flow — **headless-hostile**, same shape as Claude Code
3. Vertex AI via `GOOGLE_API_KEY` + `GOOGLE_GENAI_USE_VERTEXAI=true`, or ADC from a GCP service account JSON — **NEW mechanism: `adc_service_account_json`** (Google Application Default Credentials — a JSON file, typically at a mounted path)

Recipe path: pin to mode 1 (`GEMINI_API_KEY`) for BYOK, with `adc_service_account_json` as a secondary "advanced user" path that uses the secret-file-mount pattern we learned from Praktor.

**Chat I/O shape:**
- Interactive REPL: `gemini` (default)
- **One-shot: `gemini -p "prompt"`** with `--output-format json` or `--output-format stream-json`
- Fits both our `fifo` (REPL) and `exec_per_message` (`-p`) cleanly.

**Persistent state needs:** `~/.gemini/settings.json` for config. OAuth tokens presumably also land here — **pinning to env-var auth avoids this path entirely.**

**Notes from README (anything unusual for sandboxing):**
- **101k stars, updated 2026-04-13** — the most stable, most active CLI in this sweep.
- **Official Google first-party CLI** — unlike Claude Code this is Apache-2.0 OSS, so it doesn't collide with CLAUDE.md.
- Gemini-only (no Anthropic, no OpenAI). **Adds a previously-missing provider (Google) to our matrix.**
- MCP server support — could be the reference implementation for our MCP support story in v2.
- `--output-format stream-json` is ideal for a streaming chat bridge; no ANSI stripping required.
- Node 22+ runtime — fits `ap-runtime-node`.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
