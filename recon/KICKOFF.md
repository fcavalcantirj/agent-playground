# Agent Playground — recon kickoff

We are in RECON. N agents × M models. Observe, don't build.
Do NOT touch `api/`, `agents/`, `deploy/`, `test/`, `.planning/`.
Only write under `recon/`.

**Procedure:** follow `recon/PROTOCOL.md` — it defines the 7-step observation flow, the recipe shape each step fills in, the verdict rules, and the artifact layout. This file is the one-page brief; PROTOCOL.md is the how.

## Targets (4 cells, parallel)

- **openclaw** — https://github.com/openclaw/openclaw (hiclaw's recon found the real ship is `johnlanni/openclaw@86dad1383c12629ad3aa48575f2dd350fc0775d4`; figure out which is canonical)
- **hermes** — https://github.com/NousResearch/hermes-agent
- **picoclaw** — https://github.com/sipeed/picoclaw
- **nanoclaw** — https://github.com/qwibitai/nanoclaw

hiclaw already done in `recon/hiclaw.md` — it's not a coding agent, skip.

## Models (OpenRouter free tier, rate-limited, $0)

- `google/gemma-3-27b-it:free`
- `meta-llama/llama-3.3-70b-instruct:free`
- `qwen/qwen3-coder:free`

Base URL: `https://openrouter.ai/api/v1`
Anthropic fallback has credits if an agent can't hit OpenRouter.

## Keys (paste inline before firing)

- OpenRouter: `<PASTE_OPENROUTER_KEY>`
- Anthropic fallback: `<PASTE_ANTHROPIC_KEY>`

## Subagent prompt template (one per agent)

> Recon `<AGENT>` at `<URL>`. Observation only. Write to `recon/<AGENT>.md`.
>
> 1. Read `.planning/research/agents/<AGENT>.md` as hypothesis
> 2. Clone to `/tmp/recon-<AGENT>`
> 3. Read README. Run `<binary> --help` + every subcommand `--help`, capture verbatim
> 4. Install in throwaway docker container
> 5. For each of 3 OpenRouter models: non-interactive probe, record PASS/FAIL/BLOCKED/SKIP + snippet
> 6. Tear down clean
> 7. Write findings using `recon/hiclaw.md` as section template
>
> Rules: read docs before guessing flags. UNKNOWN/BLOCKED/SKIP valid. Redact keys. 25 min budget. Don't commit.
>
> OpenRouter key: `<KEY>` | Anthropic fallback: `<KEY>`

## After 4 return

Write `recon/FINDINGS.md` aggregate → STOP. Do not design substrate. Do not write recipes. User conversation next.

## Yesterday's scars (don't repeat)

- Env inheritance doesn't reach subagents. Paste keys in prompt text.
- Canary ONE cell before parallelizing the other 3.
- Verification failures are reports, not things to fix-forward.
- Read `<agent> --help` before writing any recipe.
- Don't flip locked decisions (picoclaw D-40b). Ask first.
- Substrate on main (`api/` + `agents/*` + `deploy/ap-runtime-*`) is leftover from a premature Phase 02.5. Audit happens AFTER recon lands, not before. Ignore it.
