---
name: auto-code-rover
real: true
source: https://github.com/AutoCodeRoverSG/auto-code-rover
language: Python
license: unknown
stars: 3100
last_commit: unknown
---

# AutoCodeRover

## L1 — Paper Recon

**Install mechanism:** docker build (primary path is a minimal Dockerfile)

**Install command:**
```
docker build -f Dockerfile.minimal -t acr .
docker run -it -e OPENAI_KEY="${OPENAI_KEY:-OPENAI_API_KEY}" acr
```

**Supported providers:**
- OpenAI (GPT-4o, GPT-4 variants, GPT-3.5)
- Anthropic (Claude 3 variants)
- Meta (Llama 3)
- AWS Bedrock (Claude, Nova)
- Groq (Llama, Mixtral, Gemma)
- LiteLLM (generic catchall)

**Model-selection mechanism:** CLI flag on `app/main.py` entry point. Model name passed per-task.

**Auth mechanism (best guess from docs):** Env vars — `OPENAI_KEY` (note: unusual name, not `OPENAI_API_KEY`), `ANTHROPIC_API_KEY`, `GROQ_API_KEY`. AWS Bedrock uses standard AWS credential resolution (env or `~/.aws/credentials`). **`OPENAI_KEY` naming collision is a schema stressor** — our recipe needs a per-agent env var alias map, not a global "OPENAI_API_KEY" assumption.

**Chat I/O shape:** **`one_shot_task` — no REPL.** Three operational modes, all one-shot:
1. GitHub issue URL + clone link + commit hash
2. Local repo path + issue description file
3. SWE-bench task identifier with setup map

Whole session = one run. Output is a `selected_patch.json` in a timestamped directory. Perfect fit for `one_shot_task` mode alongside gpt-engineer and mini-swe-agent (benchmark mode).

**Persistent state needs:** Timestamped output directories containing the selected patch + trajectory artifacts. Needs a mounted output volume or a copy-out step at session end.

**Notes from README (anything unusual for sandboxing):**
- **Ships its own Dockerfile.minimal** — the recipe is "mount a repo, set an env var, run the container, read the JSON". Cleanest `one_shot_task` pipeline in the sweep.
- **License not explicitly stated** in the README excerpt — repo has a LICENSE file but it wasn't quoted. Mark as `unknown` until L2 resolves it.
- `OPENAI_KEY` instead of `OPENAI_API_KEY` — **second agent with a nonstandard env var name** (Claude Code also does this differently). Confirms we need an env-var alias table in the recipe schema.
- `selected_patch.json` output format means the bridge has to know about output artifacts, not just stdout — reinforces the `one_shot_task.output_file` field we sketched in the matrix.
- Repo-level repair agent shape (input = GitHub issue, output = patch) is a narrower UX than chat — might belong in a "tasks" tab rather than the main chat UI.

## L2 — Install + Help

[filled in during L2 pass]

## L3 — Live round-trip

[filled in during L3 pass]
