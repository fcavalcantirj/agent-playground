# Recon Protocol — how to produce a recipe for one agent

**Audience:** a human or subagent assigned exactly one agent to recon.
**Scope:** observation only. You produce a recipe YAML and a recon report. You do not build substrate, you do not commit, you do not touch anything outside `recon/`.
**Budget:** 25 minutes wall-clock per agent. If you blow it, the verdict is `BLOCKED (budget)` with a note of the step you were on — never a silent partial recipe.

---

## What you are producing

For one agent named `<AGENT>` at `<URL>`, you leave behind exactly three artifacts:

```
recon/recipes/<AGENT>.yaml     # the recipe (schema below)
recon/reports/<AGENT>.md       # verbatim observations: help dumps, install log tail, smoke transcript
recon/smoke/<AGENT>.json       # machine-readable verdicts, one row per (agent × model) cell
```

Everything else is throwaway. Containers, images, clones — tear them down clean.

---

## Recipe shape (what you are filling in)

```yaml
apiVersion: recon/v0
name: <agent>
source: <repo-url>@<ref>

build:
  base: <image>                 # e.g. debian:12-slim, python:3.12-slim, node:20-bookworm-slim
  steps:                        # opaque shell; each line runs in order
    - <sh>
    - <sh>

runtime:
  provider: openrouter          # openrouter | anthropic | openai
  env:                          # which env var NAMES this agent reads — not values
    api_key:  <VAR_NAME>        # e.g. OPENROUTER_API_KEY, ANTHROPIC_API_KEY
    base_url: <VAR_NAME>        # optional; null if the agent hardcodes the URL
    model:    <VAR_NAME>        # optional; null if model is set in a config file
  config_files: []              # paths the agent reads instead of / in addition to env

invoke:
  mode: <cli-arg|cli-stdin|cli-flag|repl-pty|http|file-drop>
  spec: { ... }                 # mode-specific; see "invoke modes" below

smoke:
  prompt: "who are you?"
  pass_if: response_contains_name
  timeout_s: 60
```

Field rules:

- **`build.steps` is opaque shell on purpose.** Do not try to schema-ize install. Every agent is a snowflake.
- **`runtime.env` is a name map, not values.** The harness injects secrets at run time. You are documenting *which variables this agent reads*.
- **`invoke.mode` is the extensibility seam.** One of six modes (below). If a real agent forces a seventh mode, that is a finding — record it in the report and leave a note on the recipe.

---

## Invoke modes (the six shapes)

| mode | meaning | `spec` fields |
|------|---------|---------------|
| `cli-arg` | `<bin> "prompt"` — prompt is a positional arg | `{cmd: [..], prompt_index: <int>}` |
| `cli-stdin` | `echo "prompt" \| <bin>` — prompt arrives on stdin | `{cmd: [..]}` |
| `cli-flag` | `<bin> --prompt "..."` — prompt passed by named flag | `{cmd: [..], flag: "--prompt"}` |
| `repl-pty` | Interactive REPL/TUI, no non-interactive mode; drive with pty + expect | `{cmd: [..], ready_re: "<regex>", quit: "<cmd>"}` |
| `http` | Agent runs a local HTTP server; prompt is a POST | `{cmd: [..], port: <int>, path: "<url>", method: "POST", body_tmpl: "..."}` |
| `file-drop` | Agent watches a directory and writes replies back as files | `{cmd: [..], in_dir: "/work/in", out_dir: "/work/out"}` |

If step 5 (below) concludes the agent does not fit any mode, the verdict is `BLOCKED (no non-interactive surface)` and the report must quote the help text that proves it.

---

## The 7 steps

Each step maps to one or more recipe fields. Each step has its own failure verdict.

### 1. Identify

- Read the README once, top to bottom.
- Run `<binary> --help` and every visible subcommand's `--help`. Capture verbatim into the report.
- Classify the agent into one of: CLI-oneshot, REPL/TUI, HTTP server, file-watcher, hybrid, unknown.

Fills: candidate `invoke.mode`.
Fails to: `UNKNOWN` → stop, write report, do not waste budget on install.

### 2. Pin source

- `git clone <URL> /tmp/recon-<agent>`
- Record commit SHA: `git -C /tmp/recon-<agent> rev-parse HEAD`
- Prefer the most recent release tag if one exists; otherwise use the SHA.

Fills: `source: <URL>@<sha-or-tag>`.
Fails to: `BLOCKED (source unreachable)` — repo gone, private, or auth-walled.

### 3. Install in a throwaway container

- Pick the minimal base image that matches the agent's language (`debian:12-slim`, `python:3.12-slim`, `node:20-bookworm-slim`, `golang:1.23-alpine`, etc.).
- Run the install inside `docker run --rm -it <base> bash`.
- Iterate `apt/pip/npm/go/cargo` steps until `<binary> --version` (or the closest equivalent) exits 0.
- Record each step verbatim into `build.steps`. No squashing, no "obvious" omissions.
- Capture the tail of the install log into the report.

Fills: `build.base`, `build.steps[]`.
Fails to:
- `FAIL (install)` — install never converges after reasonable iteration.
- `SKIP (infra)` — agent needs GPU, kernel modules, privileged mode, or anything we will not grant.

### 4. Find the model-config surface

- Grep source + docs for: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `LLM_API_KEY`, `BASE_URL`, `ENDPOINT`, `MODEL`, `model:`, `provider:`.
- Inspect any default config files the agent creates on first run.
- **Never guess env var names.** If docs are thin, read source.
- Identify:
  - Which env var the agent reads for the API key.
  - Whether it honors an override for the base URL (this is the load-bearing question for the "any model" story — if no, verdict is `BLOCKED (no base-url override)`).
  - Which env var or config file selects the model.

Fills: `runtime.provider`, `runtime.env.{api_key,base_url,model}`, `runtime.config_files[]`.
Fails to: `BLOCKED (hardcoded config)` — agent cannot be redirected to OpenRouter.

### 5. Find the non-interactive prompt surface

- Re-read `--help` with a specific question: how do I give this agent one prompt and get one reply, in one process, without a human at a keyboard?
- Look for: `--prompt`, `-p`, positional prompt, stdin support, `--batch`, `--no-tui`, `--headless`, `--once`, `--exec`.
- If there is no non-interactive mode and the agent only runs as a REPL/TUI, plan `repl-pty` with an expect-style driver. Record the readiness regex and quit sequence.

Fills: `invoke.mode`, `invoke.spec`.
Fails to: `BLOCKED (no non-interactive path)` — agent cannot be driven without a human.

### 6. Smoke: "who are you?"

For each of the three free OpenRouter models:

```
google/gemma-3-27b-it:free
meta-llama/llama-3.3-70b-instruct:free
qwen/qwen3-coder:free
```

Run the agent in a fresh `docker run --rm` with:

- `OPENROUTER_API_KEY` injected into whatever env var name step 4 found
- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1` injected into whatever env var name step 4 found
- Model id injected into whatever env var name step 4 found (or written into the config file)
- Prompt `"who are you?"` delivered via the mode from step 5
- `timeout_s: 60`

Capture stdout, stderr, exit code, wall-time. Redact keys. Save into `recon/smoke/<agent>-<model>.json`.

Fills: one row per model in `smoke/<agent>.json`.

### 7. Record

Write all three artifacts. Keys redacted everywhere. Do not commit.

---

## Verdict rules

Exactly one verdict per (agent × model) cell. Two reconners looking at the same output must reach the same verdict.

| verdict | definition |
|---------|------------|
| `PASS` | Agent ran, hit OpenRouter, response contains the agent's own name (case-insensitive, substring) within `timeout_s`. |
| `FAIL` | Agent ran and hit OpenRouter, but the response did not name itself, or upstream returned 4xx/5xx, or the model refused. Record the response verbatim. FAIL is a finding, not a bug to fix. |
| `BLOCKED` | Agent could not be tested at all. Must be accompanied by a one-line reason from this fixed list: `source`, `install`, `hardcoded config`, `no base-url override`, `no non-interactive path`, `budget`, `infra`. |
| `SKIP` | Agent out of scope (e.g. "not a coding agent"). One-line reason required. |

Agent-level verdict = worst cell across its three model rows, except `PASS` if any row is `PASS` and the others are `FAIL` (partial compatibility is still shipping information).

---

## Hard rules (don't-repeat-yesterday's-scars)

1. **Read help before writing any field.** `<binary> --help` and every subcommand's `--help`. No guessing flags.
2. **Paste API keys inline into subagent prompts.** Env inheritance does not reach subagents. This is a known scar.
3. **Redact all keys in written artifacts.** Regex `(sk-[a-zA-Z0-9-_]{20,})` → `<REDACTED>`. Same for `OPENROUTER_API_KEY=...`.
4. **25 minute budget per agent.** If you blow it, write `BLOCKED (budget)` and note the step you were on. Do not submit a half-filled recipe.
5. **Tear down clean.** `docker rm -f`, delete the clone. No orphaned volumes, images tagged `recon-*` are fair game to prune at the end of the sweep.
6. **Do not commit during recon.** The `recon/` directory is working scratch.
7. **Observation only.** Do not edit `api/`, `agents/`, `deploy/`, `test/`, or `.planning/`. If you notice substrate bugs, write them into the report under a `## Drive-by observations` section and keep moving.
8. **Canary one cell before parallelizing.** Run one agent × one model end-to-end first. If the harness is wrong, you want to know before kicking off four in parallel.
9. **Never `docker run --privileged`.** If an install seems to need it, that is a `SKIP (infra)`, not a workaround.

---

## Artifact layout

```
recon/
├── KICKOFF.md                  # the one-page brief (targets, models, keys, scars)
├── PROTOCOL.md                 # this file
├── recipes/
│   ├── openclaw.yaml
│   ├── hermes.yaml
│   ├── picoclaw.yaml
│   └── nanoclaw.yaml
├── reports/
│   ├── openclaw.md
│   ├── hermes.md
│   ├── picoclaw.md
│   └── nanoclaw.md
├── smoke/
│   ├── openclaw-gemma-3-27b.json
│   ├── openclaw-llama-3.3-70b.json
│   ├── openclaw-qwen3-coder.json
│   └── ... (12 total for the 4×3 sweep)
└── FINDINGS.md                 # aggregate, written AFTER all four agents land
```

`FINDINGS.md` is the final deliverable of the recon phase. It contains the 4×3 matrix, the list of recipe-shape fields that had to be stretched or added, the list of agents that hit `BLOCKED` and why, and a one-paragraph call on whether the recipe shape is ready to be locked or needs another pass.

---

## What happens after recon

Nothing, until the user says so. Do not design substrate. Do not start writing Go code. Do not touch `.planning/`. The conversation after recon decides whether the shape survives, whether the 9-phase roadmap gets reshaped or scrapped, and what the first post-recon unit of work is.
