---
name: open-interpreter
real: true
source: https://github.com/OpenInterpreter/open-interpreter
language: Python
license: AGPL-3.0
stars: 63100
last_commit: unknown
---

# Open Interpreter

## L1 — Paper Recon

**Install mechanism:** pip (git-tracked)

**Install command:**
```
pip install git+https://github.com/OpenInterpreter/open-interpreter.git
```

(README prefers the git+https form over a released wheel.)

**Supported providers:** Anything LiteLLM supports — OpenAI (GPT-4, GPT-3.5-turbo), Anthropic (Claude), local inference servers (LM Studio, Ollama, Llamafile, jan.ai).

**Model-selection mechanism:**
- CLI: `interpreter --model gpt-3.5-turbo`
- Python: `interpreter.llm.model = "model-name"`

**Auth mechanism (best guess from docs):** Env var per provider (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) via LiteLLM. Also supports `interpreter.llm.api_key = "..."` for local inference servers. Clean `env_var` fit.

**Chat I/O shape:**
- **Primary: Interactive REPL (`interpreter` command).** Full terminal REPL with meta-commands (`%verbose`, `%reset`, `%undo`, `%tokens`, `%help`).
- Programmatic: `interpreter.chat("message")`
- Streaming: `interpreter.chat(message, stream=True)`

Closest fit is `fifo` (REPL mode) with meta-command stripping, or `exec_per_message` via Python wrapper. **The `%` meta-commands are a NEW schema wrinkle** — the bridge has to avoid passing user input that starts with `%` directly through, or it'll trigger REPL side-effects instead of reaching the model.

**Persistent state needs:** Conversation history in `interpreter.messages` list. YAML profiles via `interpreter --profiles`. No heavy state directory documented.

**Notes from README (anything unusual for sandboxing):**
- **AGPL-3.0** — same footprint as Memoh. Shipping as a recipe in our OSS platform is fine; forking the code requires AGPL compliance. Recipe just invokes the binary, so no derivative-work issues.
- **Open Interpreter's entire point is "runs code on your machine"** — every message triggers arbitrary Python/shell code execution in the current environment. **This is maximally hostile to sandboxing.** Must run inside a container with no host bind mounts and no Docker socket. Fine inside ap-runtime-python, dangerous anywhere else.
- 63k stars — major mindshare, popular expectation for our catalog.
- `%` meta-commands are REPL-only and would leak into chat if we expose the REPL directly. Bridge must filter or route them.
- LiteLLM dependency gives us multi-provider for free — same free lunch as mini-swe-agent and aider.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
