---
name: swe-agent
real: true
source: https://github.com/SWE-agent/SWE-agent
language: Python
license: MIT
stars: 18986
last_commit: 2026-04-13
---

# SWE-agent

## L1 — Paper Recon

**Install mechanism:** pip install / git clone + pip — Princeton/Stanford academic project. README strongly steers new users toward the sibling project `mini-swe-agent` instead ("supersedes SWE-agent... we recommend using mini-SWE-agent going forward").

**Install command:**
```
# From source (canonical in docs)
git clone https://github.com/SWE-agent/SWE-agent.git
cd SWE-agent
pip install --editable .
# Then: sweagent run --config ... or sweagent run-batch ...
```

**Supported providers:** LiteLLM-backed — Anthropic (Claude 3.7 / Sonnet 4 featured), OpenAI (GPT-4o), plus anything LiteLLM can route (OpenRouter, Azure, Bedrock, local). The README specifically highlights Claude Sonnet 4 and GPT-4o.

**Model-selection mechanism:** Single YAML config file (`--config path/to/config.yaml`). Model is a field in that YAML, using LiteLLM model strings (e.g. `anthropic/claude-sonnet-4-20250514`). Also overridable via CLI flags on `sweagent run`.

**Auth mechanism (best guess from docs):** Standard LiteLLM env vars — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`. Keys are consumed transparently by LiteLLM inside the process. No OAuth, no keychain.

**Chat I/O shape:** **One-shot / batch** — not a REPL. Designed to be pointed at a GitHub issue (or CTF challenge, or custom task) and run to completion autonomously. `sweagent run` takes a task spec and produces a patch/trajectory; `sweagent run-batch` runs across SWE-bench instances. **Not a conversational agent.** This is a major shape-mismatch for a chat-driven playground.

**Persistent state needs:** Workspace dir + trajectories/logs dir. Historically also needed a Docker sandbox (SWE-ReX) to execute the target repo inside. Config YAML is the source of truth for a run.

**Notes from README (anything unusual for sandboxing):**
- **Maintainers are redirecting new users to `mini-swe-agent`** — SWE-agent proper is in soft-deprecation. For the playground we should probably probe mini-swe-agent (~100 lines of Python, same benchmark scores) instead or in parallel.
- Uses **SWE-ReX** as its execution backend, which itself spawns Docker or modal.com sandboxes. Docker-in-Docker / nested sandbox problem applies.
- Batch mode (`run-batch`) is the primary way academic users invoke it; interactive mode exists but is secondary.
- Agent is "free-flowing" — leaves maximal agency to the LM, no hard-coded workflow. Fits the "any agent" thesis if we accept the one-shot shape.
- EnIGMA variant (offensive cybersecurity / CTF) is on the v0.7 branch, not mainline.
- Requires a target repository / issue as input. **Cannot be launched for "general chat"** the way Claude Code / Codex / OpenHands CLI can.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
