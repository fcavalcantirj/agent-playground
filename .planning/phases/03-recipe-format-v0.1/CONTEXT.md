# Phase 03 — Recipe Format v0.1 Consolidation

**Status:** Not started. Checkpoint committed 2026-04-15 ahead of phase work.
**Blocks:** Adding the next agent to the recon queue (ZeroClaw at top of `recipes/BACKLOG.md`).
**Estimated effort:** 2–3 hours focused.

## Why this phase exists

5 agent recipes have been validated end-to-end through `tools/run_recipe.py` (commits `be6fa76` through `ba0fc97`). Each recipe added one or more ad-hoc schema fields. The `ap.recipe/v0` format has grown organically through real contact with Python, TypeScript, Go, Zig, and Python-again agents. It's time to formalize before drift.

See `memory/project_recipe_v0_state.md` (auto-memory) for the 5-recipe state matrix and every format innovation absorbed.
See `memory/feedback_recipe_runner_debt.md` (auto-memory) for the 8-item debt list this phase must pay down.

## Phase scope — must deliver

### 1. `docs/RECIPE-SCHEMA.md`

Canonical `ap.recipe/v0.1` specification. Must be readable standalone by someone who has never seen the existing recipes.

Required sections:
- Top-level fields: `apiVersion`, `name`, `display_name`, `description`, `source`, `build`, `runtime`, `invoke`, `smoke`, `metadata`
- `build.mode` enum: `upstream_dockerfile`, `image_pull` — with every sub-field for each
- `runtime.process_env` schema — `api_key`, `api_key_fallback`, `base_url`, `model`
- `runtime.volumes[]` semantics — `host: per_session_tmpdir` sentinel, `container`, `mode`, `ephemeral`, `owner_uid`
- `runtime.warnings[]` — `id` + `rule` + `reason` structure (free-form but consistent)
- `invoke.mode` enum: `cli-passthrough`, future `http_post`, `repl_pty` placeholders
- `invoke.spec.entrypoint` — optional docker `--entrypoint` override
- `invoke.spec.argv[]` — ordered list with `$PROMPT` and `$MODEL` substitution semantics
- `invoke.spec.stdout_filter` — `engine: awk` for now, keep extensible
- `invoke.spec.session_id_capture` — optional
- `smoke.prompt` — default prompt if CLI doesn't override
- `smoke.pass_if` enum: `response_contains_name`, `response_contains_string`, `response_regex`, `response_not_contains`, `exit_zero`
- `smoke.case_insensitive`, `timeout_s`
- `smoke.verified_cells[]` — the (model, verdict, wall_time_s, notes) matrix
- `smoke.known_incompatible_cells[]`, `known_weak_probes[]`, `known_quirks[]`
- `metadata.recon_date`, `recon_by`, `source_citations[]`

### 2. `tools/run_recipe.py` v0.1

Changes from current state:

- **Read `smoke.prompt` from recipe** when CLI omits the prompt arg. Current CLI `<prompt> <model>` becomes `[prompt] [model]` — both optional with sensible fallbacks.
- **New `pass_if` verbs**:
  - `exit_zero` — just check container exit code
  - `response_contains_string` — needle from `smoke.needle` field (explicit, not derived from recipe name)
  - `response_regex` — pattern from `smoke.regex` field
  - `response_not_contains` — negative check
- **`--json` flag** — emit structured verdict JSON to stdout. Shape:
  ```json
  {
    "recipe": "hermes",
    "model": "openai/gpt-4o-mini",
    "verdict": "PASS",
    "exit_code": 0,
    "wall_time_s": 16.3,
    "filtered_payload": "...",
    "stderr_tail": null
  }
  ```
  When `--json`, suppress human-readable banners. Existing text output stays the default.
- **`--all-cells` sweep mode** — iterate `smoke.verified_cells[]`, run each, write results back to the recipe (updating wall_time_s + verdict). Exit non-zero if any cell regresses to FAIL.
- **Disk budget guard** — `shutil.disk_usage("/")` check before pull/build. Abort with a clear error if free < 5 GB. `--no-disk-check` flag to bypass.
- **Explicit cache management** — `--no-cache` flag: remove the tagged image before pull/build. Useful for regression testing.

### 3. Retroactive re-validation

Run all 5 committed recipes (`hermes`, `openclaw`, `picoclaw`, `nullclaw`, `nanobot`) against the new runner. Every existing `verified_cells[0]` cell must still PASS. Any drift is a phase-blocker that must be fixed in the same phase.

The image tags are cached from the original session (`ap-recipe-hermes`, etc.) — if Docker Desktop was restarted, they may need rebuilding, which adds wall time but no other cost.

### 4. `recipes/README.md`

User-facing guide covering:
- How to use an existing recipe (`python3 tools/run_recipe.py recipes/<agent>.yaml`)
- How to add a new agent (recon checklist → write YAML → run → commit)
- How the v0.1 schema works (pointer to `docs/RECIPE-SCHEMA.md`)
- Known BLOCKED agents (nanoclaw, openhands) and why
- Known weak probes / quirks / incompatible cells

### 5. BACKLOG banner update

`recipes/BACKLOG.md` top banner reflects "v0.1 format canonical — see `docs/RECIPE-SCHEMA.md`." The stars-desc queue stays intact; only the status banner changes.

## Out of scope for this phase

- **Adding any new agent recipe.** The backlog waits.
- **Format v1 fields**: `runtime.external_services[]`, `setup.interactive: true`, `invoke.spec.response_source: trajectory_file`, `invoke.spec.mode: http_post`. Those are for agents we haven't reached yet (nanoclaw v1, openhands v1, etc.).
- **Substrate work**: no `api/`, no `deploy/`, no platform code. This phase is 100% `recipes/`, `tools/`, and `docs/`.
- **Rewriting existing recipes.** They stay as-is unless the retroactive re-validation breaks them. If a retrofit is needed, keep it minimal and explain in the commit message.

## Phase exit gate

Runner invocations that MUST succeed at phase end:

```bash
python3 tools/run_recipe.py --all-cells --json recipes/hermes.yaml
python3 tools/run_recipe.py --all-cells --json recipes/openclaw.yaml
python3 tools/run_recipe.py --all-cells --json recipes/picoclaw.yaml
python3 tools/run_recipe.py --all-cells --json recipes/nullclaw.yaml
python3 tools/run_recipe.py --all-cells --json recipes/nanobot.yaml
```

Every cell returns structured JSON with `"verdict": "PASS"` (or an honest FAIL/known_quirk that's pre-documented in the recipe).

After the gate passes, the stars-desc queue in `recipes/BACKLOG.md` resumes with **ZeroClaw** (30,171 ★, Rust).

## How to start when resuming from a fresh context

1. Read this file.
2. Read `recipes/BACKLOG.md` to see the state.
3. Read `docs/RECIPE-SCHEMA.md` if it exists (it won't at phase start).
4. Read `tools/run_recipe.py` current state.
5. Read each of `recipes/*.yaml` to understand the field set that's grown.
6. Draft `docs/RECIPE-SCHEMA.md` first (the contract), then modify the runner to match, then re-validate, then document.
7. Commit incrementally — one commit per deliverable: schema, runner, regression run, README, BACKLOG banner.

## Background context (read if memory is gone)

If you're reading this with no prior context and the auto-memory is also gone:

- **What the project is**: `/Users/fcavalcanti/dev/agent-playground` — a planned web platform for running any coding agent × any model in isolated Docker containers. Inspired by `/Users/fcavalcanti/dev/meusecretariovirtual` (MSV) but decoupled from Telegram, PicoClaw, and Anthropic-only. See the main project README and the original 9-phase roadmap in `.planning/ROADMAP.md` (HISTORICAL, not authoritative as of 2026-04-15).
- **The pivot**: The 9-phase roadmap was paused on 2026-04-15 in favor of a recipe-first recon approach. 5 agent recipes now exist in `recipes/`, the runner is in `tools/run_recipe.py`, and the backlog is in `recipes/BACKLOG.md`. This phase is the first formal consolidation of that work.
- **The key deliverable across the whole project** is *any agent × any model × any user, in one click*, which translates to "a recipe format expressive enough that a Go orchestrator can load a YAML and spin up a valid session." That orchestrator is still unwritten — the recipes are the contract it will consume.
