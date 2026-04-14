---
name: metagpt
real: true
source: https://github.com/geekan/MetaGPT
language: Python
license: MIT
stars: 67100
last_commit: 2024-04-22
---

# MetaGPT

## L1 — Paper Recon

**Install mechanism:** pip install

**Install command:**
```
pip install --upgrade metagpt
```

**Supported providers:** OpenAI, Azure OpenAI, Ollama, Groq, Anthropic (via config), others configurable through `api_type` field

**Model-selection mechanism:** config field (`~/.metagpt/config2.yaml` — `api_type` + `model`)

**Auth mechanism (best guess from docs):** config_file at `~/.metagpt/config2.yaml` — LLM credentials + `api_type` field. No env-var path documented as primary; file is the source of truth. Closest match to our `config_file` taxonomy, but NOT templated with `${VAR}` substitution like nanobot — keys live raw in YAML.

**Chat I/O shape:** `one_shot_task` — `metagpt "Create a 2048 game"` is the canonical invocation; the whole "software company" (PM → Architect → Engineer → QA roles) runs as a single blocking job, writes artifacts to `./workspace/<project>`, exits. Also usable as a Python library (`from metagpt.software_company import generate_repo`), but there is NO REPL, NO HTTP server, NO incremental chat bridge.

**Persistent state needs:** `./workspace/<project>` for generated repo artifacts; `~/.metagpt/config2.yaml` for creds. Named volume required if sessions should persist.

**Notes from README (anything unusual for sandboxing):**
- Multi-agent simulation — one invocation spawns multiple internal "role" agents, but all in-process, NOT nested containers.
- **Last release v0.8.1 (April 2024) — likely soft-stagnant despite 67k stars.** Verify commit freshness in L2.
- **Chat I/O is `one_shot_task`** — existing matrix category (`gpt-engineer`, `SWE-agent`). Not a new mode.
- CLI binary exists (`metagpt` command). Runnable, not library-only.
- Config file with raw keys means the recipe needs to **render the YAML at container start** from the user's BYOK secret (same as hermes flow).
- "Generate repo → exit" shape means no terminal session to stream; the bridge either waits for the whole run or tails `./workspace` for progress.
