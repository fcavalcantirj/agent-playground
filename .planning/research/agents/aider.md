---
name: aider
real: true
source: https://github.com/Aider-AI/aider
language: Python
license: Apache-2.0
stars: 43330
last_commit: 2026-04-09
---

# Aider

## L1 — Paper Recon

**Install mechanism:** `pip` / `pipx` / a bootstrap helper `aider-install`. Distributed on PyPI as `aider-chat`. Official docs also offer a Docker image. Python ≥ 3.9.

**Install command:**
```
# Recommended (README):
python -m pip install aider-install
aider-install

# Direct:
python -m pip install aider-chat
# or:
pipx install aider-chat

# Docker (official):
docker pull paulgauthier/aider
# docker pull paulgauthier/aider-full   (includes more model backends)
```

**Supported providers:** Effectively everything LiteLLM supports: Anthropic, OpenAI, OpenRouter, DeepSeek, Google Gemini/Vertex, Groq, Azure OpenAI, Cohere, Mistral, Together, Fireworks, Ollama / local (llama.cpp / LM Studio), and any OpenAI-compatible endpoint. Claude 3.7 Sonnet, DeepSeek R1/V3, OpenAI o1/o3-mini/GPT-4o explicitly called out as "best".

**Model-selection mechanism:** `--model <name>` CLI flag (e.g. `--model sonnet`, `--model deepseek`, `--model o3-mini`, or full LiteLLM ids like `anthropic/claude-3-7-sonnet-latest`). Aliases: `--sonnet`, `--opus`, `--4o`, `--deepseek`, `--haiku`. Also configurable via `~/.aider.conf.yml` (`model:` field) or `AIDER_MODEL` env var.

**Auth mechanism (best guess from docs):** Multiple layered options:
- `--api-key provider=<key>` on the CLI (e.g. `--api-key anthropic=sk-...`)
- Provider-specific env vars — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `GEMINI_API_KEY`, etc. Uses LiteLLM's env-var conventions.
- `~/.aider.conf.yml` config file with `api-key:` array
- `.env` file in the project directory (auto-loaded)
- `--openai-api-base` / env `OPENAI_API_BASE` to point at OpenRouter (`https://openrouter.ai/api/v1`) or any OpenAI-compatible endpoint
No OAuth flow, no keychain. **Cleanest BYOK target of the four.**

**Chat I/O shape:**
- Interactive REPL (`aider`) — stdin/stdout with a prompt_toolkit line editor, `/add`, `/drop`, `/run`, `/commit`, `/ask`, `/code` slash commands.
- `--message "..."` / `-m "..."` → non-interactive single-turn
- `--message-file path` → drive a session from a file
- stdin piping: `cat prompt | aider --message -`
- `--watch-files` → file-watcher mode; reads inline comments like `# ai:` as instructions (IDE integration)
- Copy/paste web-chat mode (`/web`) — user drives a browser LLM manually

**Persistent state needs:** Writes to the git repo it's invoked in: `.aider.chat.history.md`, `.aider.input.history`, `.aider.llm.history`, and `.aider.tags.cache.v*/` (repomap cache). Global config at `~/.aider.conf.yml`, model metadata at `~/.aider.model.settings.yml` / `~/.aider.model.metadata.json`. **Commits directly to git by default** — our container must either disable this (`--no-auto-commits`) or isolate git identity.

**Notes from README (anything unusual for sandboxing):**
- Auto-commits to git are ON by default. Sandboxed containers need `--no-auto-commits --no-dirty-commits` OR a pre-set `git config user.email` so commits don't fail.
- Lint & test integration shells out arbitrary commands (`--test-cmd`, `--lint-cmd`) — allowlist implications inside the sandbox.
- Repomap uses tree-sitter — relies on native extensions, makes the pip install heavier than expected (~150MB).
- "Copy/paste to web chat" mode bypasses our metering proxy entirely — users could use platform container for free LLM access. Need to disable `/web` in platform-billed tier.
- `--openai-api-base` pointing at OpenRouter works out of the box — single knob to flip the metering proxy on/off.
- Voice-to-code requires PortAudio + a speech API — not applicable in our sandbox.
- The Docker image `paulgauthier/aider-full` is probably the right base for our recipe (pre-installed tree-sitter, git, python deps).

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
