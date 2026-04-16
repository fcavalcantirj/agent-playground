# Agent Playground Recipes

A recipe is a YAML file that describes, in one self-contained document, how to run a specific coding agent (hermes, openclaw, picoclaw, nullclaw, nanobot, …) inside a throwaway Docker container with a single prompt and a single model, and how to tell whether it worked.

The recipe is the contract. The runner (`tools/run_recipe.py`) is the consumer. The Go orchestrator that will one day power the Agent Playground web platform is a second consumer, still unwritten — but will see the same YAML.

- **Schema spec:** [`../docs/RECIPE-SCHEMA.md`](../docs/RECIPE-SCHEMA.md) (authoritative)
- **Debt / roadmap:** `../.planning/phases/03-recipe-format-v0.1/CONTEXT.md`
- **Recon backlog:** [`BACKLOG.md`](./BACKLOG.md)

---

## Running a recipe

Every recipe can be exercised end-to-end with one command:

```bash
python3 tools/run_recipe.py recipes/<agent>.yaml
```

With no arguments beyond the recipe path, the runner uses `smoke.prompt` from the recipe and the first `PASS` entry in `smoke.verified_cells[]` as the model. You can override either:

```bash
# Explicit prompt and model
python3 tools/run_recipe.py recipes/hermes.yaml "summarize your skills" "openai/gpt-4o-mini"

# JSON verdict for scripts / CI
python3 tools/run_recipe.py --json recipes/picoclaw.yaml

# Sweep every documented cell and refresh wall_time_s in the recipe
python3 tools/run_recipe.py --all-cells --json recipes/hermes.yaml
```

Useful flags:

| Flag | When |
|---|---|
| `--json` | Machine output. Suppresses banners, emits one JSON object (or JSONL under `--all-cells`). |
| `--all-cells` | Iterate every `smoke.verified_cells[]` entry. Exits non-zero only on **drift** (observed ≠ documented), not on documented FAILs. |
| `--no-cache` | Remove the tagged image before build/pull. Useful for testing against upstream changes. |
| `--no-disk-check` | Bypass the 5 GB free-space guard (default aborts if `/` has less space before a build or pull). |
| `--no-write-back` | In `--all-cells` mode, do not update the recipe file. |

### API key

The runner pulls the provider key from (in order) the recipe's canonical `process_env.api_key` env var in `os.environ`, then from the same name in `./.env` at the repo root, then from the local-dev aliases `OPENROUTER_API_KEY` / `OPEN_ROUTER_API_TOKEN`. For example, a `.env` with:

```
OPEN_ROUTER_API_TOKEN=sk-or-v1-...
```

is enough for every committed recipe, because they all declare `provider: openrouter` with `api_key: OPENROUTER_API_KEY`, and `OPEN_ROUTER_API_TOKEN` is one of the runner's local-dev aliases.

`process_env.api_key_fallback` is **documentation only** — it tells you what alternate name the agent's own code will accept internally. The runner does not use it as a value-source hint, so an unrelated `OPENAI_API_KEY` in your shell will never be cross-injected as an OpenRouter key.

---

## The five committed recipes

Snapshot as of `v0.1` consolidation:

| Recipe | Language | Image | PASS model | Wall |
|---|---|---|---|---|
| [hermes](./hermes.yaml) | Python 3.11 | ~5.2 GB | `anthropic/claude-haiku-4-5` | ~13s |
| [openclaw](./openclaw.yaml) | TypeScript / Node 24 | ~2.4 GB | `anthropic/claude-haiku-4-5` | ~62s |
| [picoclaw](./picoclaw.yaml) | Go 1.25 / Alpine | ~45 MB | `openai/gpt-4o-mini` | ~3s |
| [nullclaw](./nullclaw.yaml) | Zig 0.15 / Alpine | ~19 MB | `anthropic/claude-haiku-4-5` | ~3s |
| [nanobot](./nanobot.yaml) | Python 3.12 | ~842 MB | `openai/gpt-4o-mini` | ~9s |

`wall_time_s` values are sourced from the most recent `--all-cells` sweep and are refreshed in the YAML on each run. They are indicative, not contractual — OpenRouter latency and cold model wake times vary run to run.

### What each recipe teaches

- **hermes** — the reference recipe. Full `runtime.warnings[]`, multi-line awk `stdout_filter` to strip an 83-line skill-sync preamble, 3 `verified_cells[]` including a documented FAIL for `google/gemini-2.5-flash`. If you want to see every field in use, read this one first.
- **openclaw** — a two-step bootstrap: `openclaw config set ...` to pin the model, then `openclaw infer model run ... --local --json`, chained via `bash -c`. Also the clearest example of `known_weak_probes` — a bare "who are you?" triggers a birth-conversation flow and never surfaces the agent name, so the smoke prompt is a forcing shape.
- **picoclaw** — entrypoint override (`sh`) + sh-heredoc that writes a `config.json` before the invoke. Alpine-based; remember the image has no `bash`.
- **nullclaw** — `nullclaw onboard` then `nullclaw agent -m` chained inside a single container. Smallest footprint (~19 MB image, static Zig binary). Another `known_weak_probes` case.
- **nanobot** — writes `~/.nanobot/config.json` via sh heredoc with `provider: "openrouter"` set explicitly (the auto-detect path sends a double-prefixed model ID to OpenRouter and gets a 400). Streaming Rich UI noise in stdout is a documented `known_quirks` item.

---

## Adding a new recipe

Before writing a single line of YAML:

1. **Read [`BACKLOG.md`](./BACKLOG.md).** It's the stars-desc queue and it lists the next target. Don't pick a different one without updating the queue. Two rows are **BLOCKED(format)** (nanoclaw, openhands) — their entries explain why.
2. **Read the upstream repo's `Dockerfile`, entrypoint script, and the CLI help text for the one-shot subcommand** (`<agent> chat -q`, `<agent> agent -m`, `<agent> infer model run`, etc.). Most recipes live or die on what the entrypoint does before the agent process starts.
3. **Find the canonical API-key env var** the agent reads from process env. Usually one of `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, or an agent-specific name. Verify with `grep -r OPENROUTER_API_KEY` in the cloned repo.
4. **Figure out what a reliable `smoke.prompt` looks like** for this agent's default persona. A bare "who are you?" is surprisingly often wrong — see `known_weak_probes` in openclaw and nullclaw.

Then write the YAML. Start by copying the closest existing recipe and diffing. The order of fields to fill in:

1. `apiVersion: ap.recipe/v0.1`
2. `name`, `display_name`, `description`
3. `source.{repo, ref, upstream_version}`
4. `build.{mode, dockerfile, context, notes}`
5. `runtime.provider`, `runtime.process_env.*`, `runtime.volumes[0]`
6. `runtime.warnings[]` — one entry per non-obvious gotcha you hit during recon
7. `invoke.spec.{entrypoint, argv, argv_note, stdout_filter}` — substitute `$PROMPT` and `$MODEL`
8. `smoke.{prompt, pass_if, verified_cells[]}` with at least one `verdict: PASS` cell
9. `metadata.{recon_date, recon_by, source_citations[]}`

Then exercise it:

```bash
python3 tools/run_recipe.py recipes/<new-agent>.yaml
python3 tools/run_recipe.py --all-cells --json recipes/<new-agent>.yaml
```

The first run covers the default path end-to-end. The sweep verifies each documented cell and writes back `wall_time_s`.

A recipe is ready to commit when:

- `--all-cells --json` exits 0 with no `drift: true` lines.
- Every `runtime.warnings[]` entry cites the upstream source (file + line) you derived it from.
- `metadata.source_citations[]` lists the exact file paths and line numbers that justify each non-obvious claim in the recipe.

Commit message shape (matches existing recipes):

```
feat(recipes): add <agent> recipe (<language>, <notable-innovation>)
```

---

## Debugging a failing recipe

Start with `--json` off so you see the full banner output:

```bash
python3 tools/run_recipe.py recipes/<agent>.yaml
```

Common failure modes observed during recon of the first five:

- **"provider resolver returned empty API key"** — the agent is reading from a different env var than you think. Check `process_env.api_key_fallback` (documentation only — but it tells you what names the agent's code looks at). Either pass the right env var, or put it in `./.env`. Do **not** put it in the recipe.
- **Container exits 0 but `pass_if` fails** — the response was successful but didn't contain the name. Re-read the filtered payload. If the agent's default persona is blank-slate (openclaw, nullclaw), switch to a forcing prompt ("What is X? Reply starting with 'X is'") and add a `known_weak_probes` entry so the next person doesn't repeat the mistake.
- **Container exits non-zero with an empty filtered payload** — the `stdout_filter` awk program is eating everything. Temporarily replace with `{print}` and re-run to see raw stdout.
- **Agent starts a long "birth / onboard / setup" flow on first run** — the default entrypoint might be two-stage (first run does setup + exits, normal runs do the thing). Override `invoke.spec.entrypoint` to `sh`/`bash` and write a small script that does the setup inline, then invokes the one-shot path. See `picoclaw` and `nullclaw` for examples.
- **Disk guard aborts before build** — you have less than 5 GB free. Either free space (`docker image prune`) or pass `--no-disk-check` if you know what you're doing.

---

## Blocked / deferred agents

Two agents hit format walls that cannot be papered over in `v0.1`:

- **NanoClaw** (qwibitai/nanoclaw) — **BLOCKED(format)**. Requires the external OneCLI Agent Vault service for credential injection at request time (no API keys inside the container) and ships as Claude-Agent-SDK-only. Needs `runtime.external_services[]` + provider-proxy support. Deferred to `v1`.
- **OpenHands** (All-Hands-AI/OpenHands) — **BLOCKED(format) AND out of scope**. Writes its response to trajectory JSON files instead of stdout, the V0 headless entrypoint is marked for removal, and the project isn't part of the clawclones.com ecosystem this project targets.

Full reasoning for both lives in [`BACKLOG.md`](./BACKLOG.md) under "Blocked / deferred".

---

## Pointers

- Schema spec: [`../docs/RECIPE-SCHEMA.md`](../docs/RECIPE-SCHEMA.md)
- Runner source: [`../tools/run_recipe.py`](../tools/run_recipe.py)
- Recon backlog: [`BACKLOG.md`](./BACKLOG.md)
- Phase brief that created `v0.1`: `../.planning/phases/03-recipe-format-v0.1/CONTEXT.md`
- Parent project context: [`../CLAUDE.md`](../CLAUDE.md)
