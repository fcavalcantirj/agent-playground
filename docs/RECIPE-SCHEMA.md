# Agent Playground Recipe Schema — `ap.recipe/v0.1.1`

Canonical specification for the recipe format consumed by `tools/run_recipe.py`.

This document is the contract between:

- **Recipe authors** — humans (or agents) adding support for a new coding agent.
- **The runner** (`tools/run_recipe.py`) — the Python tool that loads a recipe, builds or pulls an image, launches a one-shot container, and evaluates a smoke probe.
- **The (future) Go orchestrator** — the platform service that will consume these recipes to spin up per-user sessions.

If a field is in use by a committed recipe in `recipes/` or a verb is implemented by the runner, it is documented here. If it is not, it does not exist.

> **Version policy.** `ap.recipe/v0.1.1` is additive over `ap.recipe/v0.1`: every field in a valid v0.1 recipe remains valid, and new recipe authors see tightened bounds (ref allowlist, name length, timeout maxima), an `annotations` escape valve on every section, optional `metadata.license` and `metadata.maintainer`, and a `$defs`-based versioning seam (§10.1). **The JSON Schema at `tools/ap.recipe.schema.json` is authoritative.** When this markdown and the schema disagree, the schema wins and this document is the bug.

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
metadata: { recon_date, recon_by, source_citations[], license?, maintainer? }
```

All top-level keys are required except where noted.

Each major section (`build`, `runtime`, `invoke`, `smoke`, `metadata`) may also carry an optional `annotations: { ... }` escape-valve block — see §11.

---

## 1. Top-level identity

| Field | Type | Required | Notes |
|---|---|---|---|
| `apiVersion` | string | yes | Must be exactly `ap.recipe/v0.1`. The JSON Schema uses a `$defs.v0_1` discriminator branch to enforce this (see §10.1 "Versioning seam"). Older `ap.recipe/v0` recipes are accepted by the runner but treated as v0.1-compatible. |
| `name` | string | yes | Short slug. Lowercase, `[a-z0-9_-]`. Used to tag the built image (`ap-recipe-<name>`) and as the default needle for `response_contains_name`. Maximum length 64 characters; used as the image-tag suffix (`ap-recipe-<name>`) where the Docker tag limit of 128 leaves headroom for the `ap-recipe-` prefix (D-05). |
| `display_name` | string | yes | Human-readable name shown in logs and future UI. |
| `description` | string (multi-line) | yes | What the agent is and which invocation path this recipe covers. Free-form. |

---

## 2. `source` — upstream repository

| Field | Type | Required | Notes |
|---|---|---|---|
| `source.repo` | string (URL) | yes if `build.mode == upstream_dockerfile` | HTTPS clone URL. |
| `source.ref` | string | yes if `build.mode == upstream_dockerfile` | Git ref — SHA (preferred, reproducible), tag, or branch name. Must match the allowlist pattern `^[a-zA-Z0-9._/-]{1,255}$` (D-04). The pattern admits plain ref characters including `/` (for `refs/heads/main`) and `.` (for `v1.2.3`) but rejects shell metacharacters and `--upload-pack=<cmd>`-style option-as-value injections that `git fetch` would otherwise accept. Shallow-clone friendly: the runner `git clone --depth=1`, then attempts a pinned fetch; if the fetch fails it falls back to shallow HEAD with a warning. |
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
| `build.timeout_s` | int | no | Max wall time for `docker build` (upstream_dockerfile) or `docker pull` (image_pull). Range `[1, 10800]` seconds (3h ceiling — cold builds for image-heavy agents like hermes or openclaw routinely exceed 15min; 3h is ample). Default 900 when absent. |
| `build.clone_timeout_s` | int | no | Max wall time for git clone + checkout in upstream_dockerfile mode. Range `[1, 1800]` seconds (30min ceiling for large repos). Default 300 when absent. |

### 3.2 `build.mode: image_pull`

Pull a prebuilt image from a registry and retag it.

| Field | Type | Required | Notes |
|---|---|---|---|
| `build.mode` | enum | yes | `image_pull` |
| `build.image` | string | yes | Full registry reference (e.g. `ghcr.io/example/agent:latest`). The runner pulls and retags it as `ap-recipe-<name>`. |
| `build.notes` | string | no | Same semantics as above. |

The runner will `docker image inspect ap-recipe-<name>` first; if present, pull is skipped. `--no-cache` (see runner flags) forces removal and repull.

> Each `build:` block may carry an optional `annotations: { ... }` object — see §11. New recipes should prefer `annotations` over `observed` for recon metadata; `observed` remains accepted for back-compat.

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
| `volumes[].owner_uid` | int | no | UID the container runs as, documented so operators know what the bind mount must be writable for. Range `[0, 4294967295]` — full Linux `uid_t`. Values greater than 65535 typically indicate a userns-remapped container. Values seen in the committed catalog: 0 (alpine root), 1000 (node/nanobot), 10000 (hermes), 65534 (nullclaw release target) (D-07). |
| `volumes[].notes` | string | no | Free-form: what the agent writes here, first-run bootstrap behavior, persistence implications. |

### 4.4 `runtime.warnings[]`

Per-recipe footgun log. Consumed by humans and by the future orchestrator's linter. Every warning documents one non-obvious thing that must be true for the recipe to work.

| Field | Type | Required | Notes |
|---|---|---|---|
| `warnings[].id` | string (slug) | yes | Short identifier, e.g. `sh_entrypoint_override`, `no_touch_env_file`. Unique within the recipe. |
| `warnings[].rule` | string | yes | One-line prescriptive rule. "Do NOT write to /opt/data/.env", "Override `--entrypoint sh` to bypass upstream entrypoint.sh", etc. |
| `warnings[].reason` | string (multi-line) | yes | The evidence: file paths, line numbers, empirical observations from recon. |

> Each `runtime:` block may carry an optional `annotations: { ... }` object — see §11.

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

> Each `invoke:` block may carry an optional `annotations: { ... }` object — see §11.

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
| `smoke.timeout_s` | int | no | Max wall time for the container run. Range `[1, 3600]` seconds (1h ceiling — smoke probes should not run longer than a human attention span). Default 180 (D-06). |

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
| `smoke.verified_cells[]` | list of maps | yes | At least one cell must be present. Required keys per cell: `model` (string), `verdict` (enum `{PASS, FAIL}`), `category` (enum from `$defs.category`, 11 values — see §10.1), `detail` (string; empty string is the convention when `category: PASS`). Optional keys: `wall_time_s` (float), `notes` (multi-line). Cells with `verdict: PASS` are the canonical "this works" matrix. |
| `smoke.known_incompatible_cells[]` | list of maps | no | Cells that have been tried and found to fail for model-specific reasons (not recipe bugs). Same required key shape as `verified_cells[]` — `model`, `verdict`, `category`, `detail`. The `verdict` field is now constrained to the same enum as `verified_cells[].verdict` (`{PASS, FAIL}`); previously unconstrained, this closed-form enum was the Phase 10 WR-05 silent-typo gap (D-03). |
| `smoke.known_weak_probes[]` | list of maps | no | Prompts that look reasonable but don't exercise `pass_if` correctly for this agent. Keys: `prompt` (required), `problem` (required, multi-line). |
| `smoke.known_quirks[]` | list of maps | no | Non-blocking oddities worth knowing. Keys: `quirk` (required), `impact` (required, multi-line). Example: nanobot's Rich streaming UI injecting ANSI codes even with `--no-markdown`. |

The runner's `--all-cells` sweep mode iterates `verified_cells[]` and re-runs each one. `known_*` lists are documentation only — the runner does not attempt to run them.

> Each `smoke:` block, and each item in `verified_cells[]` and `known_incompatible_cells[]`, may carry an optional `annotations: { ... }` object — see §11.

---

## 7. `metadata`

| Field | Type | Required | Notes |
|---|---|---|---|
| `metadata.recon_date` | string (YYYY-MM-DD) | yes | When the recipe was researched and verified. |
| `metadata.recon_by` | string | yes | Who/what produced it — human name, agent name, "main-conversation", "subagent", or a combination with tools. |
| `metadata.source_citations[]` | list of strings | yes | Specific evidence used to write the recipe: file paths with line numbers, doc URLs, empirical observations. The point is that a reviewer can verify each claim without running the agent. |
| `metadata.license` | string | no (today) | SPDX identifier (e.g. `MIT`, `Apache-2.0`). **Optional in v0.1.1; required before external contribution lands in phase 19+.** Documented here as the optional-today-required-later pattern (D-09). |
| `metadata.maintainer` | object `{ name, url? }` | no (today) | `name` is a string (maintainer handle or full name). `url` is an optional string (maintainer homepage or contact URL, `format: uri`). **Optional in v0.1.1; required before external contribution lands in phase 19+.** (D-09) |

> Each `metadata:` block may also carry an optional `annotations: { ... }` object — see §11.

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

All 5 recipes committed at the v0.1 freeze (`hermes`, `openclaw`, `picoclaw`, `nullclaw`, `nanobot`) declare `apiVersion: ap.recipe/v0.1`. v0.1.1 is additive over v0.1: every v0.1 recipe remains a valid v0.1.1 recipe. The runner accepts both `v0` and `v0.1`/`v0.1.1` and applies identical validation — fields added in v0.1.1 (bounds, `annotations`, optional `license`/`maintainer`) are all optional, so an unmodified v0 or v0.1 recipe sweeps green against the v0.1.1 schema. This is the regression gate enforced by `tools/tests/test_schema_selfcheck.py` (Phase 18 D-10).

New recipes should declare `apiVersion: ap.recipe/v0.1`. The minor-version bump to v0.1.1 reflects schema maturation, not a wire-format change.

---

## 10. Out of scope for v0.1.1

Deferred to a future `ap.recipe/v0.2` or later:

- `runtime.external_services[]` — sidecar containers a recipe depends on (needed for NanoClaw's OneCLI Agent Vault pattern).
- `setup.interactive: true` — AI-native fork-and-customize install flow.
- `invoke.spec.response_source: trajectory_file` — agents that write their response to a file instead of stdout (OpenHands pattern).
- `invoke.mode: http_post` — long-running service + REST API invocation.
- `invoke.mode: repl_pty` — REPL-driven agents that can't be driven from a single argv.
- Compound `pass_if` logic (AND/OR of multiple verbs).
- `stdout_filter.engine` values other than `awk`.
- Multi-host orchestration fields.
- **Capability advertisement block** (MCP-style `capabilities.{streaming, trajectories, multi_turn}`) — deferred to Phase 22 or later.
- **`runtime.limits`** with token/turn/cost budgets (currently smuggled into `argv`) — deferred to Phase 23.
- **GPU / hardware declaration** (`build.gpu`, `build.cuda`) — deferred until the first GPU-requiring backlog agent triggers it.
- **Collapse of the 3 `known_*` arrays into `known_issues[]` with a typed discriminator** — shape change, deferred to `v0.2`.
- **Richer `verified_cells[]`** with `probe_id`, typed metrics (`tokens_in/out`, `cost_usd`), env fingerprint — deferred to Phase 24.
- **Making `metadata.license` + `metadata.maintainer` required** — flips when external contribution lands, not today.

If a new agent needs one of these, it is **blocked by format** until the relevant phase — not a v0.1.1 patch.

---

## 10.1 Versioning seam

> The JSON Schema's root uses `oneOf: [ { "$ref": "#/$defs/v0_1" } ]` as a discriminator branch keyed on `apiVersion`. The full v0.1/v0.1.1 body lives under `$defs.v0_1`. Adding `ap.recipe/v0.2` will append a second `$defs.v0_2` branch and extend the `oneOf` array — a purely additive schema change that does not break v0.1 recipes. Recipes declaring `apiVersion: ap.recipe/v0.1` continue to match the `v0_1` branch exactly because each branch body carries its own `apiVersion: { "const": "ap.recipe/v0.N" }` constraint. This is the Kubernetes CRD versioning idiom applied to recipes.
>
> The 11-value category enum (`PASS`, `ASSERT_FAIL`, `INVOKE_FAIL`, `BUILD_FAIL`, `PULL_FAIL`, `CLONE_FAIL`, `TIMEOUT`, `LINT_FAIL`, `INFRA_FAIL`, `STOCHASTIC` reserved, `SKIP` reserved) lives once at `$defs.category` and is referenced via `$ref` from both `verified_cells[].category` and `known_incompatible_cells[].category` (D-02). Adding a category is a one-line edit in a single place.

---

## 11. Annotations escape valve

> Every major section — `build`, `runtime`, `invoke`, `smoke`, `metadata` — and every item in `verified_cells[]` and `known_incompatible_cells[]` may carry an optional `annotations: { ... }` object. Keys inside `annotations` are open (`additionalProperties: true`); keys at any other level remain strictly enumerated (`additionalProperties: false`). This pattern matches OpenAPI's `x-*` extensions and Kubernetes' `annotations` field: a strict known shape with an explicit extension point.
>
> Use `annotations` for recon observations, tool-specific metadata, experimental fields that might become first-class in a future version, and anything that would otherwise fight the schema's strict-by-default stance. Example:
>
> ```yaml
> build:
>   mode: upstream_dockerfile
>   annotations:
>     recon.image_size_gb: 5.19
>     recon.wall_time_s: 451
>     recon.host_os: darwin 25.3.0 arm64
> ```
>
> The legacy `build.observed` object is preserved for back-compat with the 5 committed recipes but is **deprecated in favor of `build.annotations` for new recipes**.
