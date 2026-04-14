---
name: nanobot
real: true
source: https://github.com/HKUDS/nanobot
language: Python
license: MIT
stars: 39500
last_commit: 2026-04-14
---

# nanobot

## L1 — Paper Recon

**Install mechanism:** pip install

**Install command:**
```
pip install nanobot-ai
nanobot onboard
nanobot agent
```

**Supported providers:** OpenRouter (recommended), OpenAI, Anthropic, DeepSeek, Groq, Azure OpenAI, Gemini, Qwen, Ollama, vLLM, OpenVINO. Day-1 full coverage of our required 3 (Anthropic + OpenAI + OpenRouter).

**Model-selection mechanism:** Config file `~/.nanobot/config.json`

**Auth mechanism (best guess from docs):**
- API keys in `~/.nanobot/config.json` with `${VAR_NAME}` env var references supported (BYOK-friendly)
- OAuth available for GitHub Copilot and OpenAI Codex

**Chat I/O shape:** `nanobot agent` is a long-running process. Separate `onboard` for setup. Not yet confirmed whether it's CLI REPL or HTTP.

**Persistent state needs:** `~/.nanobot/` config dir

**Notes from README:**
- Referenced directly in MSV README as a known agent flavor ("~100MB RAM, Research/extension") — HKUDS is the canonical source
- Claims software-engineering capability (code agent) not just chat
- Env-var substitution in config is the CLEANEST BYOK pattern of the 9 — can template config once and inject key via `ANTHROPIC_API_KEY` env at container start
- Matches v0 frontend description ("Micro" / research / Python)

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
