---
name: moltis
real: true
source: https://github.com/moltis-org/moltis
language: Rust
license: MIT
stars: unknown
last_commit: 2026-02
---

# Moltis

## L1 — Paper Recon

**Install mechanism:** cargo build from source OR install.sh (single 60MB Rust binary)

**Install command:**
```
git clone https://github.com/moltis-org/moltis.git && cd moltis && cargo run --release --bin moltis
# or
curl -sSf https://raw.githubusercontent.com/moltis-org/moltis/main/install.sh | sh
```

**Supported providers:** OpenAI (Codex), GitHub Copilot, Local. Multi-provider LLM gateway internal to the binary.

**Model-selection mechanism:** Config file + CLI; agent loop with sub-agent delegation

**Auth mechanism (best guess from docs):** Secrets managed through `secrecy::Secret` (zeroed on drop, redacted from tool output). Config + per-session secret handling.

**Chat I/O shape:** HTTP server on `https://moltis.localhost:3000` with web UI + API. Also Telegram/WhatsApp/Discord/Teams/MCP channels.

**Persistent state needs:** Per-session sandbox state; 150k lines of Rust compiled into one 60MB binary

**Notes from README:**
- EVERY command runs in a sandboxed container (Docker + Apple Container) — collides with our "container inside container" model. Likely needs Sysbox to work inside our per-user container, or needs a recipe flag that disables its internal sandboxing.
- SSRF protection built-in (blocks loopback/private/link-local)
- Secret redaction from tool output is a strong BYOK-friendly feature
- Matches v0 frontend description exactly: "Rust-native framework with sandboxed execution and local key storage. Single-binary with voice, memory, and multi-platform integrations."

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
