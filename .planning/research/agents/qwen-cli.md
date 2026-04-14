---
name: qwen-cli
real: true
source: https://github.com/QwenLM/qwen-agent
language: Python
license: Apache-2.0
stars: 16000
last_commit: 2025-05-29
---

# qwen-agent (Alibaba / QwenLM)

## L1 — Paper Recon

**Install mechanism:** pip

**Install command:**
```
pip install -U "qwen-agent[gui,rag,code_interpreter,mcp]"
```

**Supported providers:**
- DashScope (Alibaba Cloud — primary)
- Any OpenAI-compatible endpoint (vLLM, Ollama, local)
- Qwen models: Qwen3.5, Qwen3-VL, Qwen3-Coder, QwQ-32B, Qwen2.5 series

**Model-selection mechanism:** Python constructor argument passed to LLM config dict. **No first-class CLI** — framework is library-first.

**Auth mechanism (best guess from docs):** `DASHSCOPE_API_KEY` env var for Alibaba Cloud path. OpenAI-compatible mode uses standard `OPENAI_API_KEY` / `OPENAI_BASE_URL`. Fits `env_var` category.

**Chat I/O shape:** **Library-first, not CLI.** Primary entry point is `WebUI(bot).run()` which stands up a Gradio web interface. Conversational messages stored as a Python list. To make this match our recipe pipeline we'd need a thin wrapper: `python -m qwen_wrapper --message "<x>"`. Closest fit is `exec_per_message` with our own shim, OR `http_gateway` if we expose the Gradio UI.

**Persistent state needs:** Chat history is in-process Python state unless explicitly persisted. No documented state directory.

**Notes from README (anything unusual for sandboxing):**
- **Last release May 2025 (v0.0.26)** — nearly a year stale as of April 2026. Less active than Gemini CLI / mini-swe-agent.
- **No dedicated `qwen-coder-cli`** binary despite the name. Coder capabilities are a model choice (`Qwen3-Coder`), not a separate CLI.
- **Library-first architecture** is a schema stressor — our recipe manifest assumes there's an argv to run. Handling qwen-agent cleanly needs either (a) a `launch.wrapper_script` field so we ship our own entry point, or (b) a `library_mode` chat_io type. Neither exists yet.
- Adds **DashScope** as a new provider to the matrix (Alibaba Cloud, Chinese/EU availability).
- Heavy extras (`[gui,rag,code_interpreter,mcp]`) — install footprint will be large; pin to minimum set at recipe time.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
