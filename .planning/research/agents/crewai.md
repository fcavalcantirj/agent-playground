---
name: crewai
real: true
source: https://github.com/crewAIInc/crewAI
language: Python
license: MIT
stars: 48873
last_commit: 2026-04-14
---

# crewAI

## L1 — Paper Recon

**Install mechanism:** pip / uv install. Python 3.10 to <3.14. Optional extras bundle for built-in tools.

**Install command:**
```
uv pip install crewai
# or with built-in tools
uv pip install 'crewai[tools]'
```

**Supported providers:** Default OpenAI via `OPENAI_API_KEY`. LiteLLM under the hood → means almost any provider (Anthropic, OpenRouter, Azure, Bedrock, Ollama, Gemini, …) is reachable by setting the matching LiteLLM env vars. Local models via Ollama documented.

**Model-selection mechanism:** Declared per-agent in the Python code or in a `crew.yaml` (and `agents.yaml` / `tasks.yaml` when using the `crewai create crew` scaffold). Each agent in the crew can pick a different model. No single `--model` flag.

**Auth mechanism (best guess from docs):** `.env` file in the project root loaded at process start; `OPENAI_API_KEY` required by default, plus any tool-specific keys (e.g. `SERPER_API_KEY`). LiteLLM conventions for other providers.

**Chat I/O shape:** **Not a chat agent.** crewAI is a *framework* for defining multi-agent pipelines. Entry points are:
- `python src/<project>/main.py` (direct script)
- `crewai run` (CLI wrapper that runs the scaffolded project)
The output is structured results from a defined task graph, not an interactive conversation. No REPL. Flows provide Pydantic-based state management between tasks.

**Persistent state needs:** Project scaffold directory (`crewai create crew <name>` generates `src/<name>/...` with yaml configs, tools, and a main.py). Flow state persisted via Pydantic BaseModel snapshots. Workspace = the scaffold dir.

**Notes from README (anything unusual for sandboxing):**
- **Flag: framework, not a runnable agent — marginal fit for the recipe pipeline.** Users don't "chat with crewAI"; they author a Python project that instantiates crewAI and run it. A recipe for crewAI would have to ship a *default crew template* (e.g. a generic "code assistant" crew) plus a chat-bridge shim that forwards user messages as a task's input and streams task output back as chat. That's a meaningful recipe-schema stress test: "agent requires user-authored Python code before it can run".
- The LiteLLM layer means crewAI is *already* provider-agnostic, which is nice — but the BYOK injection has to populate multiple env vars (`OPENAI_API_KEY` *and* `ANTHROPIC_API_KEY` *and* …) rather than one, because different agents in the same crew may want different providers.
- Entirely independent of LangChain (explicitly stated), so no transitive LangChain dep cascade.
- The `crewai` CLI is a project-management tool (`create`, `run`, `install`, `reset-memories`), not a chat CLI. Document it but do not count it as a runnable agent in the matrix.
- Useful mainly as a data point for what a "framework recipe" would look like if we ever support that class.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
