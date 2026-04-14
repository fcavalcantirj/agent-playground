---
name: devika
real: true
source: https://github.com/stitionai/devika
language: Python
license: MIT
stars: 19500
last_commit: unknown
---

# Devika

## L1 — Paper Recon

**Install mechanism:** git clone + venv + uv pip + bun (frontend). No published package.

**Install command:**
```
git clone https://github.com/stitionai/devika && cd devika
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
playwright install --with-deps
python devika.py           # backend
cd ui && bun install && bun run start   # frontend (separate process)
```

**Supported providers:** Anthropic (Claude 3), OpenAI (GPT-4), Google Gemini, Mistral, Groq, local via Ollama. Plus Bing/Google search API keys for the browsing agent.

**Model-selection mechanism:** UI settings page (config.toml written by the web UI)

**Auth mechanism (best guess from docs):** `config_file` at `config.toml` (auto-generated on first run) + **UI-driven key entry**. Keys are written to disk through the settings page — **headless-hostile unless we pre-populate config.toml from BYOK before container start** (same fix as hermes interactive wizard).

**Chat I/O shape:** `http_gateway` — browser UI at `http://127.0.0.1:3001` is the only supported interaction mode. Users "create projects, configure model, provide task descriptions in chat interface, monitor progress." **No CLI, no REPL, no exec mode.** Same category as OpenHands GUI mode / ChatDev 2.0 / SuperAGI.

**Persistent state needs:** workspace dir, `config.toml`, SQLite DB for project state, Playwright browser cache (Chromium ~300MB).

**Notes from README (anything unusual for sandboxing):**
- **Heavy install:** Python + Node + bun + Playwright browsers. Runtime image ≥ 1.5GB. Expect build-time pain.
- **"Early development / experimental stage. Lots of unimplemented/broken features."** — maintainer-acknowledged fragility.
- **Devika's Playwright agent opens real browsers to scrape web pages** — that's an outbound nested-process surface (not container) but still needs egress allowlist handling.
- **Two-process compose-style** (backend Python + bun frontend on 3001) — another compose-tier candidate.
- **Last release data not visible** in README — commit freshness needs verification in L2. Previously reported as stalling after the initial hype; this was NOT verified here.
- **UI-only means our browser chat bridge can't reuse the existing `exec_per_message` or `fifo` patterns** — we'd reverse-proxy its WebSocket straight through, same as Plandex.
