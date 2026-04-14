---
name: nullclaw
real: true
source: https://github.com/nullclaw/nullclaw
language: Zig
license: MIT
stars: 7200
last_commit: 2026-04-10
---

# NullClaw

## L1 — Paper Recon

**Install mechanism:** Homebrew OR Zig build from source

**Install command:**
```
brew install nullclaw
# or
git clone https://github.com/nullclaw/nullclaw.git && cd nullclaw && zig build -Doptimize=ReleaseSmall
```

**Supported providers:** "50+ providers" — OpenRouter, Anthropic, OpenAI, Azure OpenAI, Gemini, Vertex AI, Ollama, Groq, Mistral, DeepSeek, custom OpenAI-compatible endpoints

**Model-selection mechanism:** `--provider` CLI flag on `onboard`; config file afterward

**Auth mechanism (best guess from docs):**
- `nullclaw onboard --api-key sk-... --provider openrouter` (non-interactive, takes key directly)
- Interactive wizard: `nullclaw onboard --interactive`
- Stored encrypted at rest in `~/.nullclaw/config.json`

**Chat I/O shape:** Long-running agent binary; multi-channel (Telegram/Discord/Signal/etc.) — exact local chat protocol not yet confirmed

**Persistent state needs:** `~/.nullclaw/config.json` (encrypted)

**Notes from README:**
- Referenced in MSV README as "~1MB RAM, maximum density (100k/machine)" — extreme tiny-session candidate
- Zig language — novelty; needs zig toolchain in base image only if building from source (brew tap avoids this)
- Non-interactive onboard with `--api-key` flag is the simplest BYOK injection of any candidate
- Latest release v2026.4.9 (April 10 2026) — very active
- MSV `specs/ARCHITECTURE.md` explicitly says "Spins up PicoClaw/NullClaw container" — already baked into MSV's mental model

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
