---
name: mini-swe-agent
real: true
source: https://github.com/SWE-agent/mini-swe-agent
language: Python
license: MIT
stars: 3800
last_commit: 2026-03-24
---

# mini-swe-agent

## L1 — Paper Recon

**Install mechanism:** pip

**Install command:**
```
pip install mini-swe-agent
```

**Supported providers:** LiteLLM, OpenRouter, Portkey, and any provider exposing `/completion` and `/response` endpoints. Effectively "any provider LiteLLM supports" (Anthropic, OpenAI, Groq, Bedrock, local, …).

**Model-selection mechanism:** `LitellmModel(model_name=...)` in Python bindings or CLI config. Model name is a LiteLLM-format string (e.g. `anthropic/claude-sonnet-4-6`).

**Auth mechanism (best guess from docs):** Environment variables (LiteLLM convention — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`). **Clean `env_var` fit** — no config file, no keychain.

**Chat I/O shape:** Multi-mode. Primary entry point is `mini` CLI REPL, plus **batch inference for benchmarks** and **Python bindings** for programmatic use. Fits both `exec_per_message` (via CLI invocation) and `one_shot_task` (via batch mode). **No FIFO needed.**

**Persistent state needs:** Trajectory browser for inspection; linear message history appended per step. **No stateful shell session** — each step is self-contained, which is unusual compared to the SWE-agent parent project. This makes it trivial to sandbox: no PTY, no long-lived process.

**Notes from README (anything unusual for sandboxing):**
- **~100 lines of Python for the agent class** — explicit design goal. Successor to princeton-nlp/SWE-agent, scores ">74% on SWE-bench verified" with a fraction of the code.
- **Recommended as the replacement for the archived SWE-agent** in our matrix. Active (March 2026), maintained by the same group.
- Dependency on LiteLLM means we automatically get multi-provider for free — one of the cleanest "any model" fits in the catalog.
- Trajectory browser implies an output artifact (JSON trace) that our bridge can surface in the chat UI — aligns with `one_shot_task` output-file pattern.
- No stateful shell = no ttyd dependency for this agent; can be invoked purely via `docker exec` or Python subprocess from the bridge.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
