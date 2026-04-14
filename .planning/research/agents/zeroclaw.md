---
name: zeroclaw
real: true
source: https://github.com/zeroclaw-labs/zeroclaw
language: Rust
license: MIT OR Apache-2.0
stars: 30100
last_commit: 2026-04-08
---

# ZeroClaw

## L1 — Paper Recon

**Install mechanism:** Homebrew tap or git clone + install.sh (builds Rust single binary)

**Install command:**
```
brew install zeroclaw
# or
git clone https://github.com/zeroclaw-labs/zeroclaw.git && cd zeroclaw && ./install.sh
```

**Supported providers:** OpenAI (Codex), Anthropic, Gemini + "20+ LLM backends" with failover. OpenAI-compatible base URL so OpenRouter should work.

**Model-selection mechanism:** Config file (profile-based) and CLI flag; encrypted auth profiles

**Auth mechanism (best guess from docs):** OAuth (ChatGPT, Google, Anthropic) OR API key; credentials stored encrypted in `~/.zeroclaw/` profile store

**Chat I/O shape:** Long-running single binary daemon. React 19 + Vite web dashboard provides interactive chat. Multi-channel bridges (Telegram/WhatsApp/Slack/Discord/Signal/Matrix).

**Persistent state needs:** `~/.zeroclaw/` profile + SQLite for memory/vector search

**Notes from README:**
- Alternative Rust rewrite of OpenClaw; same conceptual model, very different runtime shape
- Claims <5MB RAM, <10ms startup — good fit for edge/tiny-session tier
- Sandboxed tool execution with workspace scoping and explicit allowlists
- Another zeroclaw repo exists at `elev8tion/zeroclaw` — not the canonical one; `zeroclaw-labs/zeroclaw` is the catalog entry
- v0 frontend description matches this one exactly ("Rust, <5MB RAM, $10 hardware")

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
