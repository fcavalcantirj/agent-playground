---
name: smol-developer
real: true
source: https://github.com/smol-ai/developer
language: Python
license: MIT
stars: 12189
last_commit: 2024-04-07
---

# smol-developer

## L1 — Paper Recon

**Install mechanism:** git clone + poetry / pip install library — dual shape. README is explicit: smol-developer is both a standalone script AND a Python library (`pip install smol_dev`) you can embed in your own app. **Unmaintained since April 2024.**

**Install command:**
```
# Script mode
git clone https://github.com/smol-ai/developer.git
cd developer
poetry install
python main.py "a HTML/JS/CSS Tic Tac Toe Game"
# or: python main.py --prompt prompt.md --debug True

# Library mode
pip install smol_dev
# then: from smol_dev.prompts import plan, specify_file_paths, generate_code_sync
```

**Supported providers:** OpenAI only in the canonical path (hardcoded to `gpt-4-0613` / `gpt-3.5-turbo-0613`). An experimental `anthropic.py` entrypoint exists in-repo (`modal run anthropic.py --prompt prompt.md`) but README flags it as "doesn't work well because Anthropic doesn't follow instructions to generate file code." Effectively **OpenAI-only**.

**Model-selection mechanism:** CLI `--model` flag on `main.py` (e.g. `--model=gpt-3.5-turbo-0613`). Otherwise hardcoded in the prompts module. No config file.

**Auth mechanism (best guess from docs):** Env var `OPENAI_API_KEY`. Relies on Modal.com's env var plumbing when run in "Modal is all you need" mode — README is emphatic about Modal as the canonical execution substrate (handles deps, parallelization, retries). Running bare-`python main.py` also works but is off the blessed path.

**Chat I/O shape:** **One-shot whole-program synthesis** — not a REPL, not a chat agent. The loop is "human edits prompt.md, runs script, reads output, edits prompt.md again." Also exposes an **HTTP API via the Agent Protocol** (`poetry run api` → POST `/agent/tasks`, POST `/agent/tasks/<id>/steps`) which is closer to a chat shape but still task-step structured, not free-form conversation.

**Persistent state needs:** Workspace dir only. Prompt lives in `prompt.md` (or passed as first positional arg). Output is written directly into the working directory. No session state, no ~/.smol/ config.

**Notes from README (anything unusual for sandboxing):**
- **Library-first design** is unique among our candidates — the whole point is you import `plan()`, `specify_file_paths()`, `generate_code_sync()` and build your own agent around them. This is a *building block*, not a shipped agent.
- Execution substrate was **Modal.com** (serverless Python). Running locally/in-Docker works but the README's mental model assumes Modal handles dep hell + parallelism + retries. Our container recipe would need to replace that layer.
- Supports OpenAI Function Calling for structured `file_paths` output — if API changes broke that, the library may be silently degraded.
- Agent Protocol HTTP mode uses e2b-dev's `agent-protocol` package — if we wanted a network-attached surface, this is the one.
- **Last commit 2024-04-07** — stalest of the four. Almost certainly broken against current OpenAI SDK versions; L2 install will likely reveal dependency rot.
- Author explicitly positions it as "build the thing that builds the thing" / educational — not a production daily driver.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
