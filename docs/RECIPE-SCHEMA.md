# Agent Playground Recipe Schema — `ap.recipe/v0.2`

Canonical specification for the recipe format consumed by `tools/run_recipe.py`.

This document is the contract between:

- **Recipe authors** — humans (or agents) adding support for a new coding agent.
- **The runner** (`tools/run_recipe.py`) — the Python tool that loads a recipe, builds or pulls an image, launches a one-shot container, and evaluates a smoke probe.
- **The (future) Go orchestrator** — the platform service that will consume these recipes to spin up per-user sessions.

If a field is in use by a committed recipe in `recipes/` or a verb is implemented by the runner, it is documented here. If it is not, it does not exist.

> **Version policy.** `ap.recipe/v0.2` is **additive over `ap.recipe/v0.1.1`**: every field in a valid v0.1/v0.1.1 recipe remains valid unchanged; recipes opt in to the new blocks by declaring `apiVersion: ap.recipe/v0.2` and appending the two new top-level sections — §10.2 `persistent:` and §11 `channels:` — below the existing `metadata:` block. No v0.1 content is removed. The JSON Schema at `tools/ap.recipe.schema.json` now carries the `oneOf: [{$ref: v0_1}, {$ref: v0_2}]` discriminator that was reserved in v0.1.1 §10.1. **The JSON Schema at `tools/ap.recipe.schema.json` is authoritative.** When this markdown and the schema disagree, the schema wins and this document is the bug.
>
> `ap.recipe/v0.1.1` additions over `ap.recipe/v0.1` are still described below: tightened bounds (ref allowlist, name length, timeout maxima), an `annotations` escape valve on every section, optional `metadata.license` and `metadata.maintainer`, and a `$defs`-based versioning seam (§10.1).

---

## File shape at a glance

```yaml
apiVersion: ap.recipe/v0.1       # or ap.recipe/v0.2
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

# v0.2 only — optional additive blocks describing persistent daemon mode
# and messaging channel wiring. See §10.2 and §11.
persistent: { mode, spec: { argv, ready_log_regex, health_check, graceful_shutdown_s, ... } }
channels:   { <channel_id>: { config_transport, required_user_input[], ..., verified_cells[] }, ... }
```

All top-level keys up to `metadata` are required except where noted. `persistent:` and `channels:` are v0.2-only and optional even under v0.2.

Each major section (`build`, `runtime`, `invoke`, `smoke`, `metadata`) may also carry an optional `annotations: { ... }` escape-valve block — see §11 (annotations escape valve).

---

## 1. Top-level identity

| Field | Type | Required | Notes |
|---|---|---|---|
| `apiVersion` | string | yes | Must be exactly `ap.recipe/v0.1` OR `ap.recipe/v0.2`. The JSON Schema root now uses `oneOf: [{$ref: v0_1}, {$ref: v0_2}]` — declarations dispatch to the matching `$defs.v0_N` branch via the per-branch `apiVersion: { const: "ap.recipe/v0.N" }` constraint (see §10.1 "Versioning seam"). Older `ap.recipe/v0` recipes are accepted by the runner but treated as v0.1-compatible. Recipes that declare `ap.recipe/v0.2` MAY additionally carry `persistent:` (§10.2) and `channels:` (§11). |
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

## 9. Compatibility with `ap.recipe/v0` / `v0.1` / `v0.1.1`

All 5 recipes committed at the v0.1 freeze (`hermes`, `openclaw`, `picoclaw`, `nullclaw`, `nanobot`) originally declared `apiVersion: ap.recipe/v0.1`. v0.1.1 is additive over v0.1, and v0.2 is additive over v0.1.1. The runner accepts `v0`, `v0.1`/`v0.1.1` (under the `v0_1` branch), and `v0.2` (under the `v0_2` branch). A recipe without `persistent:` / `channels:` blocks remains a valid v0.1 recipe; opting into those blocks requires declaring `apiVersion: ap.recipe/v0.2` so the oneOf root dispatches to the v0_2 branch. This is the regression gate enforced by `tools/tests/test_schema_selfcheck.py` (Phase 18 D-10).

New recipes that only need the one-shot smoke path SHOULD declare `apiVersion: ap.recipe/v0.1`. Recipes shipping a messaging gateway (persistent + channel wiring) MUST declare `apiVersion: ap.recipe/v0.2`. The minor-version bumps reflect schema maturation; v0.2 is the first wire-format-visible change (new top-level keys).

---

## 10. Out of scope for v0.2

Deferred to `ap.recipe/v0.3` or later:

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

> The JSON Schema's root uses `oneOf: [ { "$ref": "#/$defs/v0_1" }, { "$ref": "#/$defs/v0_2" } ]` as a discriminator branch keyed on `apiVersion`. Each branch body carries its own `apiVersion: { "const": "ap.recipe/v0.N" }` constraint so a recipe declaring `apiVersion: ap.recipe/v0.1` matches the `v0_1` branch and a recipe declaring `apiVersion: ap.recipe/v0.2` matches the `v0_2` branch exactly — no branch-cross collisions. The v0.2 branch is a structural clone of v0.1 with two additive optional top-level properties (`persistent`, `channels`). This is the Kubernetes CRD versioning idiom applied to recipes.
>
> Future `ap.recipe/v0.3` (etc.) extends the same pattern — append a `v0_3` branch, extend the root `oneOf` array. Adding a branch is a purely additive schema change.
>
> The 11-value category enum (`PASS`, `ASSERT_FAIL`, `INVOKE_FAIL`, `BUILD_FAIL`, `PULL_FAIL`, `CLONE_FAIL`, `TIMEOUT`, `LINT_FAIL`, `INFRA_FAIL`, `STOCHASTIC` reserved, `SKIP` reserved) lives once at `$defs.category` and is referenced via `$ref` from both `verified_cells[].category` and `known_incompatible_cells[].category` (D-02). Adding a category is a one-line edit in a single place. v0.2 introduces a distinct `$defs.channel_category` enum — the existing category enum plus `BLOCKED_UPSTREAM` — scoped to channel `verified_cells[].category` only so the `BLOCKED_UPSTREAM` value does not leak into smoke-level v0.1 semantic space (see §11).

---

## 10.2 `persistent:` — daemon/gateway mode (v0.2)

> **v0.2 only.** Declares the long-running in-container daemon that boots the agent's messaging gateway. Parallel to (not a replacement for) `invoke:` — `invoke:` is the one-shot smoke path, `persistent:` is the live-session path driven by `channels:` (§11). A recipe MAY declare both; the runner selects one at deploy time via `--mode one-shot | persistent`.

### 10.2.1 `persistent.mode`

| Field | Type | Required | Notes |
|---|---|---|---|
| `persistent.mode` | enum | yes | `gateway-daemon` is the only mode implemented in v0.2. Future modes (`http-server`, `worker-pool`) are reserved. |

### 10.2.2 `persistent.spec`

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec.argv` | list of strings | yes | Ordered argv passed after the container entrypoint. Same `$MODEL`/`$VAR` substitution rules as `invoke.spec.argv` (§5.2), MINUS `$PROMPT` — persistent mode receives prompts via channel events, not argv. |
| `spec.ready_log_regex` | string | yes | Python regex matched against container stderr+stdout by the runner after `docker run -d`. When the pattern matches, the container is considered ready. Example: hermes uses `"gateway\\.run: ✓ (\\w+) connected"`; picoclaw uses `"Telegram bot connected username="`. |
| `spec.health_check` | object | yes | One of two kinds — see §10.2.3. |
| `spec.graceful_shutdown_s` | int | yes | SIGTERM → `docker wait` timeout before `docker rm -f`. Range `[0, 600]` seconds. Recipes seen use 5-15s. The value `0` is a sentinel meaning "skip graceful shutdown — go straight to `docker rm -f`" and is used by recipes whose daemon ignores SIGTERM (nanobot per spike-07; pair with `sigterm_handled: false`). |
| `spec.entrypoint` | string | no | `docker run --entrypoint` override for persistent mode, same semantics as `invoke.spec.entrypoint` (§5.2). hermes has none; picoclaw, nullclaw, nanobot, openclaw all use `sh` to chain config-write + exec. |
| `spec.user_override` | string | no | Docker `--user` override. Required when the image has an ownership bug that blocks the non-root UID from writing to a declared `runtime.volumes[*]` mount. nullclaw is the only recipe that declares `user_override: root` today. Charset: shell-safe identifier (`^[a-zA-Z0-9_:-]+$`). |
| `spec.sigterm_handled` | bool | no | Documentation flag — `true` asserts the agent handles SIGTERM gracefully within `graceful_shutdown_s`. If absent the runner treats as unspecified and still applies the graceful timeout + force-remove fallback. Every v0.2-draft recipe sets `true`. |
| `spec.argv_note` | string | no | Free-form explanation of why the argv is shaped the way it is (parallel to `invoke.spec.argv_note`). Essential for sh-heredoc config writers. |
| `spec.lifecycle_note` | string | no | Free-form operational notes: `docker run -d` invocation examples, shutdown signal semantics, known-good startup wall times. |

### 10.2.3 `persistent.spec.health_check`

The health check is a strict `oneOf` union keyed on `kind`:

| Kind | Extra fields | Runner semantics |
|---|---|---|
| `process_alive` | — | `docker inspect <cid>` asserts `State.Running == true`. Used by hermes + nullclaw. |
| `http` | `port: int [1, 65535]`, `path: string (must start with "/")` | HTTP GET to `http://<container>:<port><path>` after ready-log match; first 2xx is a pass. Used by picoclaw (`18790/health`), nanobot (`18790/health`), openclaw (`18789/`). **Note** (per empirical spike-11): picoclaw's `/health` endpoint returns 200 when Telegram is connected; `/ready` returns 503 even when Telegram is connected, so `/health` is the correct path. |

`additionalProperties: false` inside each `oneOf` branch — `kind: process_alive` recipes MUST NOT include `port` or `path`.

---

## 11. `channels:` — messaging platform wiring (v0.2)

> **v0.2 only.** Describes how a persistent-mode agent connects to inbound/outbound messaging platforms (Telegram, Discord, Slack, WhatsApp, Matrix, Signal, …). Every entry documents which env vars / config files the channel wants, what the ready signal looks like, how replies are routed, and which model × bot combinations have been empirically verified to complete a round-trip.

### 11.1 Shape

`channels:` is a dict keyed by channel id (`^[a-z0-9_-]+$`). `telegram` is the only channel shipped and battle-proven in v0.2; other ids are reserved for later expansion.

Each channel entry is a strict object (`additionalProperties: false`):

| Field | Type | Required | Notes |
|---|---|---|---|
| `config_transport` | enum | yes | `env` — runner injects the channel's required env vars via `docker run --env-file`. `file` — runner writes a config file inside the container at startup (typical pattern: sh-chained heredoc in `persistent.spec.argv`). |
| `required_user_input` | list of `user_input_entry` | yes | Ordered list. Drives deploy-form field order. Empty list NOT allowed — if no user input is required, the channel probably doesn't need to live here. See §11.2. |
| `optional_user_input` | list of `user_input_entry` | no | Optional extras the user MAY provide. Same shape as `required_user_input`. |
| `ready_log_regex` | string | yes | Per-channel ready signal pattern. May differ from `persistent.spec.ready_log_regex` when multiple channels share one gateway process. |
| `response_routing` | enum | yes | `per_message_origin` (reply lands in the chat the sender messaged from — telegram, discord DM, slack IM) or `fixed_home_channel` (reply always lands in a preconfigured chat — useful for proactive cron/alert agents). |
| `multi_user_model` | enum | yes | `allowlist` (static list of allowed_user IDs baked into config at deploy time), `pairing_then_allowlist` (users DM the bot, get a one-time code, operator approves via an exec to grant allowlist membership), `allowlist_or_dm_pairing` (hermes' both-paths variant). |
| `multi_account_supported` | bool | no | Defaults to `false`. `true` iff the recipe can run multiple bot accounts within one container. Today only nullclaw + nanobot + openclaw declare `true`. |
| `provider_compat` | object | no | `{supported: [...], deferred: [...]}` listing LLM-provider IDs known to work/not-work for this channel path. Openclaw-only today: `{supported: [anthropic], deferred: [openrouter]}` because of the isolated openrouter-provider-plugin silent-fail bug (see 22-CONTEXT.md §3). When present, `supported` lists providers with end-to-end empirical PASS; `deferred` lists providers the recipe explicitly disallows until the upstream bug clears. |
| `known_quirks` | list of `{id, severity, description}` | no | Channel-scoped caveats the runner or the deploy UI must honor. Distinct shape from `smoke.known_quirks[]` (which uses `{quirk, impact}`) — the two are NOT unified. |
| `pairing` | object `{approve_argv: [string]}` | no | Introduced for openclaw. When `multi_user_model` is `pairing_then_allowlist`, `approve_argv` is the exec-argv the runner runs via `docker exec <cid>` to approve a pairing code (the runner substitutes `$CODE` with the operator-supplied value). Example: `["openclaw", "pairing", "approve", "telegram", "$CODE"]`. |
| `verified_cells` | list of `channel_verified_cell` | yes | Empirical PASS evidence. Non-empty in battle-proven recipes. See §11.3. |

### 11.2 `required_user_input[*]` shape

Each entry:

| Field | Type | Required | Notes |
|---|---|---|---|
| `env` | string | yes | Env var name the agent reads. Pattern `^[A-Z][A-Z0-9_]*$`. |
| `secret` | bool | yes | Gates UI masking + redaction semantics. `true` → treat like `runtime.process_env.api_key`: inject via `--env-file`, redact from logs. `false` → non-secret operational config (allowlist IDs, channel names). |
| `hint` | string | yes | User-facing short help for the deploy form. Explains WHERE to get the value (usually a @BotFather-style upstream flow). |
| `kind` | enum | no | Typed hint for input validation on the deploy form: `telegram_numeric_id`, `telegram_numeric_id_csv`, `telegram_numeric_id_or_username`. Future channels add their own values. |
| `hint_url` | string (URI) | no | Clickable upstream link (e.g. `https://t.me/userinfobot`). When present the UI renders `hint` with the URL as a link. |
| `prefix_required` | string (≤16 chars) | no | Runner auto-prepends this literal prefix to the value BEFORE injection into the `file`-transport heredoc. openclaw-only today (`"tg:"`) — openclaw's `channels.telegram.allowFrom` expects `["tg:<numeric-id>"]`, not the bare numeric id the user types. |

`additionalProperties: false` inside the entry.

### 11.3 `verified_cells[*]` shape (channel-scoped)

Parallel to `smoke.verified_cells[]` (§6.3) but with **channel-specific enums**:

| Field | Type | Required | Notes |
|---|---|---|---|
| `date` | string `YYYY-MM-DD` | yes | When the cell was exercised. |
| `bot_username` | string | yes | The bot the cell was run against. Usernames begin with `@` by telegram convention. |
| `allowed_user_id` | int | yes | The numeric user id that successfully round-tripped. |
| `verdict` | enum | yes | `PASS` (basic round-trip OK), `FULL_PASS` (end-to-end including pairing + reply), `CHANNEL_PASS_LLM_FAIL` (channel wiring proven but the LLM layer silently failed — reserved for upstream-bug documentation). This enum is **distinct** from `smoke.verified_cells[].verdict` (which is `{PASS, FAIL}`). |
| `category` | enum | yes | `$ref: channel_category` = the 11-value smoke category enum plus `BLOCKED_UPSTREAM`. `BLOCKED_UPSTREAM` is channel-specific and MUST NOT appear in smoke-level cells. |
| `notes` | string | yes | Multi-line free-form observations (bot state, approve flow specifics, model choice reasoning). |
| `model` | string | no | Model identifier when the cell exercised a specific LLM binding. Absent for hermes (auxiliary auto-detects its model). |
| `provider` | enum | no | `openrouter | anthropic | openai | ...` — which upstream provider the LLM call went to. openclaw uses this field to distinguish its anthropic-direct PASS from its openrouter-deferred BLOCKED_UPSTREAM. |
| `env_var` | string | no | Which env var the cell used for the provider key (disambiguates when a recipe supports multiple). |
| `boot_wall_s` | int | no | Observed wall time from `docker run -d` to `ready_log_regex` match. |
| `first_reply_wall_s` | int | no | Observed wall time from first user message to first agent reply. |
| `reply_sample` | string | no | Verbatim or lightly redacted sample of the agent's first reply, for reviewer sanity. |

`additionalProperties: false` inside the cell.

### 11.4 Cross-references

- Runner: `tools/run_recipe.py --mode persistent` (Phase 22a plan 22-02) consumes `persistent.spec` + `channels.<id>`; the current runner only consumes `invoke:` + `smoke:`.
- API surface: `GET /v1/recipes` exposes `channels_supported` + `persistent_mode_available` + `channel_provider_compat` on every recipe summary; the full channel entry is in `GET /v1/recipes/{name}` (opaque dict passthrough).
- BYOK contract (golden rule #2): every `required_user_input[*]` with `secret: true` is BYOK — value passes through the request body only, never stored server-side.

---

## 12. Annotations escape valve

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
