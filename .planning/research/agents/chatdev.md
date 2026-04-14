---
name: chatdev
real: true
source: https://github.com/OpenBMB/ChatDev
language: Python
license: Apache-2.0
stars: 32700
last_commit: 2026-03-23
---

# ChatDev

## L1 — Paper Recon

**Install mechanism:** git clone + uv sync (backend) + npm install (frontend). NOT a single `pip install`.

**Install command:**
```
git clone https://github.com/OpenBMB/ChatDev
cd ChatDev && uv sync
cd frontend && npm install
# Also published on PyPI as `chatdev` for SDK use.
```

**Supported providers:** Provider-agnostic — uses `API_KEY` + `BASE_URL` env vars in `.env`, any OpenAI-compatible endpoint (so OpenAI, OpenRouter, local, …). No Anthropic-native path documented.

**Model-selection mechanism:** config field in YAML workflow files + `.env` BASE_URL override

**Auth mechanism (best guess from docs):** `env_var_substitution_in_config` — `.env` file sets `API_KEY` + `BASE_URL`, which YAML workflow files reference via `${API_KEY}` syntax. **Same pattern as nanobot** — matches existing matrix taxonomy.

**Chat I/O shape:** `http_gateway` + library hybrid. Backend is `python server_main.py` (HTTP server) with a Vue frontend on `:5173`. SDK exposes `run_workflow()` returning structured `result.final_message` objects. **No single-process CLI that takes a prompt.** Closest matrix analog: `http_gateway` like OpenHands / Plandex / HiClaw.

**Persistent state needs:** workspace dir for generated artifacts; `.env` for creds; multi-service means named volumes for both backend state and frontend build cache.

**Notes from README (anything unusual for sandboxing):**
- **ChatDev 2.0 (v2.2.0, March 2026) is ACTIVE** — unlike MetaGPT which has been stale since April 2024.
- **Branding shift:** "Zero-Code Multi-Agent Platform for Developing Everything" — no longer just a software company simulation. Broader than MetaGPT but also less focused.
- **Two-process minimum** (`server_main.py` + `npm run dev` frontend). **This is a compose-style recipe, not single-container.** Same isolation_tier category as HiClaw.
- **Differentiator vs MetaGPT:** active maintenance, HTTP/web-console primary UX, env-var substitution (headless-friendly), and Vue frontend suggests the human-in-the-loop workflow is first-class.
- **Nested-container risk:** unclear; README doesn't mention Docker-in-Docker, but the multi-service shape + visual workflow editor is suspicious. Verify in L2.
- Uses `uv` for deps — fast but requires uv in the runtime image.
