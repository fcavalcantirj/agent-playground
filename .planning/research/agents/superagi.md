---
name: superagi
real: true
source: https://github.com/TransformerOptimus/SuperAGI
language: Python
license: MIT
stars: 17400
last_commit: 2025-01-22
---

# SuperAGI

## L1 — Paper Recon

**Install mechanism:** docker compose (primary); also a Python SDK

**Install command:**
```
git clone https://github.com/TransformerOptimus/SuperAGI
cd SuperAGI
docker compose -f docker-compose.yaml up --build
# GPU variant available
```

**Supported providers:** OpenAI (primary). Multiple LLM integrations documented but not exhaustively listed. Integrates with multiple vector DBs (Pinecone, Weaviate, etc.) — unusually memory-heavy agent platform.

**Model-selection mechanism:** web UI / config.yaml

**Auth mechanism (best guess from docs):** `config_file` at `config.yaml` for local; GitHub OAuth for the hosted cloud version. **The local deploy path is config-file-only** — no env-var-first flow documented.

**Chat I/O shape:** `http_gateway` — full web UI at `http://localhost:3000` is the canonical interface. Org/project/agent hierarchy is a **platform**, not a runnable agent. Users create agents via UI, assign toolkits, monitor runs.

**Persistent state needs:** Postgres + Redis + vector DB (per compose file) — this is multi-service by design.

**Notes from README (anything unusual for sandboxing):**
- **REVERSAL OF PRIOR CLAIM:** Earlier research doc claimed "~393 days since last commit, appears stagnant." **Re-verified against the commits page: most recent commit is 2025-01-22**, with regular activity through 2024 into early 2025. Not active in early 2026 — ~15 months since last commit as of 2026-04-14 — but **not as dead as previously claimed.** Soft-stagnant, not abandoned.
- **This is a FRAMEWORK/PLATFORM, not a runnable agent.** Same category as crewAI / openagents-org in the existing matrix. Does not fit the "one-click session" shape without writing a default-template crew shim on top.
- **Compose-style install with 4+ services** (backend + frontend + Postgres + Redis + vector DB). **Maximum compose complexity in the sweep so far.** Any recipe would require `isolation_tier: compose` + a much bigger service graph than HiClaw.
- **Last release v0.0.14, January 2024.** Despite later commits, no tagged release in 2+ years → production-readiness is questionable.
- **Recipe fit verdict:** marginal. Mark as `category: framework` and defer behind a "platform-style agents" tier, same bucket as crewAI.
- **Schema gap exposed:** a "platform" agent needs `install.services: [...]` + `install.healthchecks: [...]` fields that single-container agents don't have. If we ship SuperAGI, the recipe schema grows.
