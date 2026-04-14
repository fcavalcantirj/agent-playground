---
name: ironclaw
real: true
source: https://github.com/nearai/ironclaw
language: Rust
license: unknown
stars: unknown
last_commit: unknown
---

# IronClaw

## L1 — Paper Recon

**Install mechanism:** cargo build from source (requires Rust toolchain)

**Install command:**
```
git clone https://github.com/nearai/ironclaw.git
cd ironclaw
cargo build --release
```

**Supported providers:** Anthropic, OpenAI, GitHub Copilot, Google Gemini, MiniMax, Mistral, Ollama (local)

**Model-selection mechanism:** Config file + CLI (not explicitly documented in recon)

**Auth mechanism (best guess from docs):** API keys injected ONLY at point of execution — NOT loaded into LLM context at any time. Strong anti-leak posture. Config file location unconfirmed at L1.

**Chat I/O shape:** Web Gateway with browser UI; Agent Loop + Router + Scheduler + Worker architecture. Likely HTTP.

**Persistent state needs:** Workspace dir; audit log

**Notes from README:**
- WASM sandboxing for tool execution (isolated from filesystem)
- Matches v0 frontend description: "Rust, prioritizes isolation, telemetry discipline, safer defaults"
- Owned by `nearai` org — likely connected to NEAR protocol folks
- Security-first design aligns well with our v1.5 Sysbox tier
- Multi-component (router/scheduler/worker/gateway) may complicate containerization — needs multiple processes or one binary that fans out

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
