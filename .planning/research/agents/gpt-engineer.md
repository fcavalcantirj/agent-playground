---
name: gpt-engineer
real: true
source: https://github.com/AntonOsika/gpt-engineer
language: Python
license: MIT
stars: 55210
last_commit: 2025-05-14
---

# gpt-engineer

## L1 — Paper Recon

**Install mechanism:** pip install — one of the oldest agents in the space (precursor to `gptengineer.app` / Lovable). README itself now redirects serious users to Lovable (commercial) or aider (maintained CLI) — this project is in light-touch maintenance mode (last push May 2025).

**Install command:**
```
# Stable
python -m pip install gpt-engineer
# Invoke via: gpte <project_dir>

# Dev
git clone https://github.com/gpt-engineer-org/gpt-engineer.git
cd gpt-engineer
poetry install && poetry shell
```

**Supported providers:** OpenAI (primary), Azure OpenAI, Anthropic, plus "open source / local models" via documented `open_models.html` guide (likely LiteLLM or direct endpoint override).

**Model-selection mechanism:** CLI positional arg — second arg to `gpte` is the model name (e.g. `gpte projects/example gpt-4-vision-preview`). Defaults to a hardcoded GPT-4 tier. No YAML config for the core loop; `preprompts/` folder overrides identity.

**Auth mechanism (best guess from docs):** Env var `OPENAI_API_KEY`, either exported from shell or loaded from a `.env` file in the working directory (template provided as `.env.template`). No keychain, no OAuth. Anthropic presumably via `ANTHROPIC_API_KEY` same pattern.

**Chat I/O shape:** **One-shot code generator**, not a REPL. Workflow: (1) user creates project dir, (2) writes natural-language spec into a file literally named `prompt` (no extension), (3) runs `gpte <dir>`, (4) gpte writes a full codebase into that dir. Improve-existing-code mode is `gpte <dir> -i`. Human interaction is "edit the prompt file and re-run." **Not conversational.**

**Persistent state needs:** Project directory (the workspace). Contains `prompt` file (input), generated code (output), optional `preprompts/` (identity override), optional `.env` (credentials). All state is filesystem-scoped to the project dir.

**Notes from README (anything unusual for sandboxing):**
- Shape is closer to `create-react-app` than to Claude Code — "scaffold a codebase from a spec" rather than "pair-program in a loop."
- Ships a `bench` binary for benchmarking custom agents against APPS / MBPP — side-channel feature, not relevant to us.
- Vision support via `--image_directory` flag — agent can read UX mockups. Would need image upload path in our chat UI if we wanted to expose this.
- README openly points users to alternatives ("If you are looking for a well maintained hackable CLI, check out aider"). Project lives on for OG value and bench tooling, not active feature development.
- Last push 2025-05-14 — genuinely stale relative to OpenHands / Claude Code / aider. Recipe fit is "historical milestone," not "daily driver."
- Has a Docker path in `docker/README.md` (not shown in root README) — worth probing in L2 as the sandbox-friendly install.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
