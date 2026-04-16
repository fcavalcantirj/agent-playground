# Agent Playground Recipe Schema — `ap.recipe/v0.1`

Canonical specification for the recipe format consumed by `tools/run_recipe.py`.

This document is the contract between:

- **Recipe authors** — humans (or agents) adding support for a new coding agent.
- **The runner** (`tools/run_recipe.py`) — the Python tool that loads a recipe, builds or pulls an image, launches a one-shot container, and evaluates a smoke probe.
- **The (future) Go orchestrator** — the platform service that will consume these recipes to spin up per-user sessions.

If a field is in use by a committed recipe in `recipes/` or a verb is implemented by the runner, it is documented here. If it is not, it does not exist.

---

## File shape at a glance

```yaml
apiVersion: ap.recipe/v0.1
name: <short-id>
display_name: <Human Name>
description: |
  One or more paragraphs describing the agent and what path this recipe covers.

source:   { repo, ref, ref_note?, upstream_version? }
build:    { mode, ... }              # shape depends on mode
runtime:  { provider, process_env, volumes, warnings? }
invoke:   { mode, spec }
smoke:    { prompt, pass_if, ..., verified_cells[], known_*[] }
metadata: { recon_date, recon_by, source_citations[] }
```

All top-level keys are required except where noted.

---

## 1. Top-level identity

| Field | Type | Required | Notes |
|---|---|---|---|
| `apiVersion` | string | yes | Must be exactly `ap.recipe/v0.1` for this schema. Older `ap.recipe/v0` recipes are still accepted by the runner but treated as v0.1-compatible (all new fields optional). |
| `name` | string | yes | Short slug. Lowercase, `[a-z0-9_-]`. Used to tag the built image (`ap-recipe-<name>`) and as the default needle for `response_contains_name`. |
| `display_name` | string | yes | Human-readable name shown in logs and future UI. |
| `description` | string (multi-line) | yes | What the agent is and which invocation path this recipe covers. Free-form. |

---

## 2. `source` — upstream repository

| Field | Type | Required | Notes |
|---|---|---|---|
| `source.repo` | string (URL) | yes if `build.mode == upstream_dockerfile` | HTTPS clone URL. |
| `source.ref` | string | yes if `build.mode == upstream_dockerfile` | Git ref — SHA (preferred, reproducible), tag, or branch name. Shallow-clone friendly: the runner `git clone --depth=1`, then attempts a pinned fetch; if the fetch fails it falls back to shallow HEAD with a warning. |
| `source.ref_note` | string | no | Free-form explanation of what the ref points at and why (e.g. "main branch head at recon date, pinned for reproducibility"). |
| `source.upstream_version` | string | no | The upstream's self-declared version at recon time (e.g. `v0.9.0`, `2026.4.15-beta.1`). Documentation only — not consumed by the runner. |

For `build.mode == image_pull`, the entire `source` block may be omitted.

---

## 3. `build` — how to produce the image

`build.mode` selects one of two shapes. The enum is closed: adding a new mode is a runner change, not a recipe change.

### 3.1 `build.mode: upstream_dockerfile`

Clone the upstream repo and build its Dockerfile in place. This is the default and by far the most common mode.

| Field | Type | Required | Notes |
|---|---|---|---|
| `build.mode` | enum | yes | `upstream_dockerfile` |
| `build.dockerfile` | string | no | Path to the Dockerfile relative to the clone root. Defaults to `Dockerfile`. Examples seen: `Dockerfile`, `docker/Dockerfile`. |
| `build.context` | string | no | Path to the build context relative to the clone root. Defaults to `.`. |
| `build.observed` | map | no | Documentation-only record of what the recipe author saw at recon time. Suggested keys: `image_size_gb` (float), `wall_time_s` (int), `host_os` (string). |
| `build.notes` | string (multi-line) | no | Free-form build gotchas: multi-stage details, apt mirrors, .dockerignore traps, expected cold-build wall time. |

### 3.2 `build.mode: image_pull`

Pull a prebuilt image from a registry and retag it.

| Field | Type | Required | Notes |
|---|---|---|---|
| `build.mode` | enum | yes | `image_pull` |
| `build.image` | string | yes | Full registry reference (e.g. `ghcr.io/example/agent:latest`). The runner pulls and retags it as `ap-recipe-<name>`. |
| `build.notes` | string | no | Same semantics as above. |

The runner will `docker image inspect ap-recipe-<name>` first; if present, pull is skipped. `--no-cache` (see runner flags) forces removal and repull.

---

## 4. `runtime` — container environment contract

### 4.1 `runtime.provider`

| Field | Type | Required | Notes |
|---|---|---|---|
| `runtime.provider` | string | yes | Which LLM gateway the recipe plumbs: `openrouter`, `anthropic`, `openai`, etc. Informational in v0.1; the orchestrator will key billing/routing off this later. |

### 4.2 `runtime.process_env`

Declarative description of which environment variables the agent reads. The runner uses this to resolve the API key and inject it via `docker run -e`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `process_env.api_key` | string | yes | Canonical env var name the agent reads (e.g. `OPENROUTER_API_KEY`). The runner resolves a value for this from process env first, then from `./.env` at repo root, then from the local-dev aliases `OPENROUTER_API_KEY` / `OPEN_ROUTER_API_TOKEN`. |
| `process_env.api_key_fallback` | string | no | **Documentation only.** An alternate env var name the agent's own code accepts internally (e.g. hermes will also read `OPENAI_API_KEY` for some providers). The runner does **not** use this field as a value-source hint, to avoid cross-provider key bleed — a host-env `OPENAI_API_KEY` should never be auto-injected as an `OPENROUTER_API_KEY`. |
| `process_env.base_url` | string \| null | yes (explicit null OK) | Override for the provider base URL. `null` means "agent's default is fine" (e.g. hermes defaults to OpenRouter). |
| `process_env.model` | string \| null | yes (explicit null OK) | Default model. `null` means "set per-call" (the standard case — the runner substitutes `$MODEL` into `invoke.spec.argv`). |

### 4.3 `runtime.volumes[]`

One or more bind mounts from host to container. The recipes committed today use exactly one, but the list is open for future agents that need multiple data roots.

| Field | Type | Required | Notes |
|---|---|---|---|
| `volumes[].name` | string | yes | Identifier for logs and future orchestrator use. |
| `volumes[].host` | string | yes | Host path, OR the sentinel `per_session_tmpdir` which the runner resolves to a fresh `tempfile.mkdtemp()` per invocation. This is the common case: each run gets a clean, disposable directory. |
| `volumes[].container` | string | yes | Mount point inside the container (e.g. `/opt/data`, `/home/node/.openclaw`, `/nullclaw-data`). |
| `volumes[].mode` | enum | no | `rw` (default) or `ro`. |
| `volumes[].ephemeral` | bool | no | Documentation flag — `true` means the volume is expected to be thrown away at container teardown. Defaults to `true`. |
| `volumes[].owner_uid` | int | no | UID the container runs as, documented so operators know what the bind mount must be writable for. 0 (alpine root), 1000 (node/nanobot), 10000 (hermes), 65534 (nullclaw `release` target). |
| `volumes[].notes` | string | no | Free-form: what the agent writes here, first-run bootstrap behavior, persistence implications. |

### 4.4 `runtime.warnings[]`

Per-recipe footgun log. Consumed by humans and by the future orchestrator's linter. Every warning documents one non-obvious thing that must be true for the recipe to work.

| Field | Type | Required | Notes |
|---|---|---|---|
| `warnings[].id` | string (slug) | yes | Short identifier, e.g. `sh_entrypoint_override`, `no_touch_env_file`. Unique within the recipe. |
| `warnings[].rule` | string | yes | One-line prescriptive rule. "Do NOT write to /opt/data/.env", "Override `--entrypoint sh` to bypass upstream entrypoint.sh", etc. |
| `warnings[].reason` | string (multi-line) | yes | The evidence: file paths, line numbers, empirical observations from recon. |

---

## 5. `invoke` — how to call the agent

### 5.1 `invoke.mode`

| Field | Type | Required | Notes |
|---|---|---|---|
| `invoke.mode` | enum | yes | `cli-passthrough` is the only mode implemented today. `http_post` and `repl_pty` are reserved placeholders for v1 agents (OpenHands-style HTTP services, REPL-driven agents). Using them in a v0.1 recipe is a runner error. |

### 5.2 `invoke.spec` (for `cli-passthrough`)

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec.entrypoint` | string | no | Value passed to `docker run --entrypoint`. Common choices: `sh` (alpine, no bash), `bash`, `python`. Omit to use the image's baked entrypoint. Recipes that need to chain multiple commands inside one container lifetime (config-write then invoke, onboard then agent, etc.) override this to `sh`/`bash` and use `-c` with a script in `argv`. |
| `spec.argv` | list of strings | yes | Ordered argv passed after the entrypoint. The runner performs **token substitution** before calling `docker run`: each element is scanned for `$PROMPT` and `$MODEL`, which are replaced with the actual values (both for whole-element matches like `$PROMPT` and for embedded matches like `openrouter/$MODEL`). Any other `$VAR` references are **not** substituted by the runner — they are passed through verbatim and interpolated by the shell inside the container at runtime. This is how recipes reference `${OPENROUTER_API_KEY}` in sh heredocs: the runner leaves it alone, `docker run -e` puts it in the container env, and `sh -c` expands it there. |
| `spec.argv_note` | string | no | Free-form explanation of why the argv is shaped the way it is. Essential for non-trivial recipes (picoclaw's heredoc config write, openclaw's `bash -c` chain, nullclaw's two-step onboard+agent). |
| `spec.stdout_filter` | map | no | Post-processing program applied to the container's stdout before `pass_if` is evaluated. See §5.3. |
| `spec.session_id_capture` | map | no | Optional probe that extracts a session identifier from stdout so that subsequent calls can resume the session. See §5.4. |

### 5.3 `invoke.spec.stdout_filter`

| Field | Type | Required | Notes |
|---|---|---|---|
| `stdout_filter.engine` | enum | yes | `awk` is the only engine implemented. Future engines (`jq`, `python`) are not accepted today. |
| `stdout_filter.program` | string (multi-line) | yes | For `engine: awk`, a valid awk program fed the raw stdout on stdin. Used to strip preambles (hermes skill-sync noise), select a window, or pass-through (`"{print}"`). |
| `stdout_filter.notes` | string | no | What the filter does and why. |

If `stdout_filter` is absent, the runner treats the payload as the raw stdout.

### 5.4 `invoke.spec.session_id_capture`

| Field | Type | Required | Notes |
|---|---|---|---|
| `session_id_capture.engine` | enum | yes | `awk` or `none`. |
| `session_id_capture.program` | string | yes if engine != `none` | Awk program that prints the session ID on one line. |
| `session_id_capture.notes` | string | no | How the resulting ID can be reused (`-r SESSION_ID`, etc.). |

Not consumed by the runner today; reserved for multi-turn orchestration.

---

## 6. `smoke` — how to verify the recipe works

### 6.1 Default probe

| Field | Type | Required | Notes |
|---|---|---|---|
| `smoke.prompt` | string | yes | Default prompt sent to the agent when the runner is invoked without an explicit `--prompt`. This field is **load-bearing** in v0.1 — the runner reads it. Recipes that have a special persona shape (nullclaw's blank slate) should encode the probe that actually works, not "who are you?". |
| `smoke.pass_if` | enum | yes | Verdict verb. See §6.2. |
| `smoke.needle` | string | required for `response_contains_string` | Literal substring to search for. |
| `smoke.regex` | string | required for `response_regex` | Python regex pattern. Matched with `re.search` over the filtered payload. |
| `smoke.case_insensitive` | bool | no | Default `false`. Applies to `response_contains_name`, `response_contains_string`, `response_not_contains`. |
| `smoke.timeout_s` | int | no | Max wall time for the container run. Default 180. |

### 6.2 `smoke.pass_if` verbs

| Verb | What it checks | Extra fields |
|---|---|---|
| `response_contains_name` | Case-sensitive/insensitive substring match of `recipe.name` in the filtered payload. | — |
| `response_contains_string` | Substring match of `smoke.needle` in the filtered payload. | `needle` |
| `response_regex` | `re.search(smoke.regex, filtered_payload)` is truthy. | `regex` |
| `response_not_contains` | Inverse of `response_contains_string` — passes when `needle` is **absent**. | `needle` |
| `exit_zero` | Container exited with code 0, regardless of output content. | — |

The runner evaluates exactly one verb per invocation. Compound logic is not in scope for v0.1 — if a recipe needs it, use `response_regex` with an alternation pattern.

### 6.3 Cell matrices

A "cell" is one `(recipe × model)` execution. Recipes document which cells they have actually exercised.

| Field | Type | Required | Notes |
|---|---|---|---|
| `smoke.verified_cells[]` | list of maps | yes | At least one cell must be present. Keys: `model` (required), `verdict` (required, `PASS` or `FAIL`), `wall_time_s` (optional float), `notes` (optional, multi-line). Cells with `verdict: PASS` are the canonical "this works" matrix. |
| `smoke.known_incompatible_cells[]` | list of maps | no | Cells that have been tried and found to fail for model-specific reasons (not recipe bugs). Same key shape as `verified_cells[]`, plus `notes` explaining the failure mode. |
| `smoke.known_weak_probes[]` | list of maps | no | Prompts that look reasonable but don't exercise `pass_if` correctly for this agent. Keys: `prompt` (required), `problem` (required, multi-line). |
| `smoke.known_quirks[]` | list of maps | no | Non-blocking oddities worth knowing. Keys: `quirk` (required), `impact` (required, multi-line). Example: nanobot's Rich streaming UI injecting ANSI codes even with `--no-markdown`. |

The runner's `--all-cells` sweep mode iterates `verified_cells[]` and re-runs each one. `known_*` lists are documentation only — the runner does not attempt to run them.

---

## 7. `metadata`

| Field | Type | Required | Notes |
|---|---|---|---|
| `metadata.recon_date` | string (YYYY-MM-DD) | yes | When the recipe was researched and verified. |
| `metadata.recon_by` | string | yes | Who/what produced it — human name, agent name, "main-conversation", "subagent", or a combination with tools. |
| `metadata.source_citations[]` | list of strings | yes | Specific evidence used to write the recipe: file paths with line numbers, doc URLs, empirical observations. The point is that a reviewer can verify each claim without running the agent. |

---

## 8. Runner interface (`tools/run_recipe.py`)

This section documents the contract on the runner side, so authors know what the recipe must satisfy.

### 8.1 CLI

```
python3 tools/run_recipe.py [OPTIONS] <recipe.yaml> [prompt] [model]
```

- `<recipe.yaml>` — path to the recipe file. Required.
- `[prompt]` — override for `smoke.prompt`. If omitted, the runner reads the prompt from the recipe. Pass an explicit empty string to force an error rather than use the default.
- `[model]` — override for the model. If omitted, the runner uses the first entry in `smoke.verified_cells[]` whose `verdict` is `PASS`.

Options:

| Flag | Effect |
|---|---|
| `--json` | Emit a single JSON object on stdout with the verdict and suppress human-readable banners. Shape: `{recipe, model, prompt, pass_if, verdict, expected_verdict, drift, exit_code, wall_time_s, filtered_payload, stderr_tail}`. `expected_verdict` and `drift` are populated from the recipe cell (or default to `PASS`/`false` in single-cell mode). Errors during setup (missing Docker, missing API key) still go to stderr as text. |
| `--all-cells` | Sweep every entry in `smoke.verified_cells[]`, running each as its own cell. When combined with `--json`, emits one JSON object per line (JSONL). This is the **regression detector**: exit is non-zero only when observed verdict ≠ documented verdict (drift), not when a cell's documented FAIL stays FAIL. Cells that drift are also logged on stderr as `DRIFT: <name> × <model> — expected X, got Y`. |
| `--no-cache` | Remove the tagged image (`ap-recipe-<name>`) before build/pull. Useful for regression testing against upstream changes. |
| `--no-disk-check` | Skip the free-space guard. Default is to abort if `/` has less than 5 GB free before a build or pull. |
| `--write-back / --no-write-back` | In `--all-cells` mode, control whether the recipe file is updated in place. Only `wall_time_s` is ever updated; the authored `verdict` is intentionally left alone so drift is reported via exit code, never by silent mutation. Default is `--write-back`. |

### 8.2 API key resolution

For each recipe, the runner builds an alias list: `[process_env.api_key, "OPENROUTER_API_KEY", "OPEN_ROUTER_API_TOKEN"]` (deduped, order preserved). For each alias in order, it checks `os.environ` first, then `./.env` at repo root. The first hit is injected into the container as the recipe's canonical `process_env.api_key` name. `process_env.api_key_fallback` is **not** consulted during resolution — see its definition in §4.2.

### 8.3 Disk guard

Before any `docker build` or `docker pull`, the runner calls `shutil.disk_usage("/")`. If free space is below **5 GB**, the run aborts with an error naming the shortfall. `--no-disk-check` bypasses. This guard exists because a single large image (hermes ~5 GB, openclaw ~5 GB) can consume 20%+ of a typical recon host's free space, and silent mid-build failures are hard to debug.

### 8.4 Image cache

Built/pulled images are retagged `ap-recipe-<name>` and retained across runs. Subsequent invocations short-circuit the build/pull step unless `--no-cache` is passed. Clone dirs are cached at `/tmp/ap-recipe-<name>-clone`. Data dirs (the per-session tmpdir for `host: per_session_tmpdir` volumes) are created fresh per invocation and removed in the runner's `finally` block.

---

## 9. Compatibility with `ap.recipe/v0`

All 5 recipes committed at the v0.1 freeze (`hermes`, `openclaw`, `picoclaw`, `nullclaw`, `nanobot`) declare `apiVersion: ap.recipe/v0`. The runner accepts both `v0` and `v0.1` and applies identical validation — every field added in v0.1 (`smoke.needle`, `smoke.regex`, the new `pass_if` verbs, `--all-cells` write-back) is optional. An unmodified v0 recipe will sweep green against the v0.1 runner; this is the regression gate enforced by the format-v0.1 consolidation phase.

New recipes should declare `apiVersion: ap.recipe/v0.1`.

---

## 10. Out of scope for v0.1

Explicitly deferred to a future `ap.recipe/v1`:

- `runtime.external_services[]` — sidecar containers a recipe depends on (needed for NanoClaw's OneCLI Agent Vault pattern).
- `setup.interactive: true` — AI-native fork-and-customize install flow.
- `invoke.spec.response_source: trajectory_file` — agents that write their response to a file instead of stdout (OpenHands pattern).
- `invoke.mode: http_post` — long-running service + REST API invocation.
- `invoke.mode: repl_pty` — REPL-driven agents that can't be driven from a single argv.
- Compound `pass_if` logic (AND/OR of multiple verbs).
- `stdout_filter.engine` values other than `awk`.
- Multi-host orchestration fields.

If a new agent needs one of these, it is **blocked by format** until `v1` — not a v0.1 patch.
