---
name: openhands
real: true
source: https://github.com/OpenHands/OpenHands
language: Python
license: MIT
stars: 71199
last_commit: 2026-04-14
---

# OpenHands

## L1 — Paper Recon

**Install mechanism:** docker pull (primary) / pip install (SDK + CLI) — README directs users to three distinct surfaces: the Python SDK (`openhands-sdk`), the CLI (separate repo `OpenHands-CLI`), and the Local GUI (this repo, shipped as Docker images).

**Install command:**
```
# Local GUI (canonical docker path)
docker pull docker.all-hands.dev/all-hands-ai/openhands:latest
docker run -it --rm --pull=always \
    -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:latest \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v ~/.openhands-state:/.openhands-state \
    -p 3000:3000 --add-host host.docker.internal:host-gateway \
    --name openhands-app \
    docker.all-hands.dev/all-hands-ai/openhands:latest

# CLI path (alt surface)
pip install openhands-ai  # then `openhands` command
```

**Supported providers:** Any LiteLLM-supported provider — Anthropic, OpenAI, OpenRouter, Azure, Bedrock, local (Ollama/vLLM), Minimax (featured in Cloud free tier).

**Model-selection mechanism:** LLM config object passed to SDK; in GUI a settings screen persists `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` to `~/.openhands-state`. CLI reads the same state file or env vars.

**Auth mechanism (best guess from docs):** LiteLLM-style env vars (`LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`) OR persisted settings.json inside the mounted `~/.openhands-state` volume. LiteLLM prefix convention: `anthropic/claude-sonnet-4`, `openrouter/anthropic/claude-3.5-sonnet`.

**Chat I/O shape:** Multi-surface. GUI mode = REST API + SPA on port 3000 + WebSocket for streaming. CLI mode = stdin/stdout REPL (claimed parity with Claude Code / Codex). SDK = Python library. For our bridge, the CLI variant is the cleanest fit.

**Persistent state needs:** `~/.openhands-state` volume (settings, conversation history, credentials). GUI needs Docker socket mounted for spawning runtime sandbox containers (Docker-in-Docker pattern).

**Notes from README (anything unusual for sandboxing):**
- GUI mode mounts `/var/run/docker.sock` — OpenHands itself spawns a *second* container (`runtime`) per session for the agent's workspace. This is a hard sandboxing concern: we'd need Sysbox or a host-side proxy that intermediates runtime spawns.
- Two separate container images: `openhands` (control plane) + `runtime` (workspace). Both pinned by tag.
- Enterprise tier in `enterprise/` directory is source-available but non-MIT.
- SWE-bench score 77.6 advertised in README — this is the current SOTA open-source agent.
- README points at a separate `OpenHands-CLI` repo for the terminal surface; the main repo is now primarily the GUI.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
