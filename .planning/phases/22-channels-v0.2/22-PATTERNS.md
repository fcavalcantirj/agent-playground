# Phase 22a: Channels v0.2 — Pattern Map

**Mapped:** 2026-04-18
**Files analyzed:** 4 new artifacts (schema+loader, runner `--mode persistent`, 4 API endpoints, frontend Step 2.5)
**Analogs found:** 4 / 4 (all have exact in-repo prior art — everything is additive)
**Read-only:** this is the prior-art map; it does not plan.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `docs/RECIPE-SCHEMA.md` (rev → v0.2) + `tools/ap.recipe.schema.json` (additive `persistent:` + `channels:`) | schema / config | static contract | `docs/RECIPE-SCHEMA.md` v0.1.1 + co-located `ap.recipe.schema.json` | exact |
| `api_server/src/api_server/services/recipes_loader.py` (stays backward-compat; surface unchanged) | service | file-I/O + transform | itself + `services/lint_service.py` | exact |
| `tools/run_recipe.py` — new `run_cell_persistent` / `--mode persistent` | utility / CLI | request-response → long-lived process management | `run_cell(...)` (lines 664-856) | exact (same primitive, `docker run -d` instead of `--rm`) |
| `api_server/src/api_server/routes/agents.py` — add `/v1/agents/:id/start`, `/stop`, `/status`, `/channels/:cid/pair` | controller | request-response (spawn/reap container) + DB | `routes/runs.py::create_run` (POST path, lines 82-238) | exact |
| `api_server/src/api_server/services/runner_bridge.py` — new `execute_persistent_start`/`stop`/`status`/`exec` | service | per-tag-lock + semaphore + `to_thread` bridge | existing `execute_run` (lines 78-120) | exact |
| `api_server/src/api_server/models/agents.py` — new `AgentStartRequest`, `AgentStartResponse`, `AgentStatusResponse`, `ChannelPairRequest` | model (Pydantic) | request/response schema | `models/runs.py::RunRequest/RunResponse` (lines 49-120) | exact |
| `api_server/src/api_server/services/run_store.py` — new `agent_container_*` columns + CRUD | service | CRUD | existing `upsert_agent_instance` + `insert_pending_run` + `write_verdict` (lines 36-169) | exact |
| `frontend/components/playground-form.tsx` — new Step 2.5 | component | controlled-form + radio/conditional | Step 3 "Name + Personality" block (lines 384-452) inside PlaygroundForm | exact |

---

## Shared Patterns (apply to every new artifact in this phase)

### 1. Python runner ↔ api_server bridge is `importlib.util.spec_from_file_location`
- **Source:** `api_server/src/api_server/services/runner_bridge.py` lines 38-60 (`_import_run_cell`); mirror lives in `services/lint_service.py` lines 53-71.
- **Rule:** `tools/` is NOT on `sys.path`. Any new runner verb (e.g. `run_cell_persistent`) is imported the same way, cached in `sys.modules["run_recipe"]`. Do NOT restructure tools/ into a package.

### 2. BYOK keys and bot tokens are LOCAL VARIABLES, never stored
- **Source:** `routes/runs.py` lines 94-109 + 193-198 (`provider_key = authorization[len("Bearer "):]`; module-level logger `_log` never receives the key; exception redaction via `str(e).replace(provider_key, "<REDACTED>")`).
- **Source:** `run_recipe.py::_redact_api_key` (lines 378-401) — replaces both `VAR=value` and bare `value` substrings, applied to every `detail` string.
- **Source:** `run_cell` env-file pattern (lines 699-704): creates `/tmp/ap-env-<uuid>`, chmod 600, unlinked in `finally`. The docker CLI invocation uses `--env-file` not `-e` so the value never lands in `ps`/`/proc/*/cmdline`.
- **Rule for channels:** `TELEGRAM_BOT_TOKEN` is in the same class as `OPENROUTER_API_KEY`. All `channels.telegram.required_user_input[*]` entries where `secret: true` MUST flow through the same env-file pattern, be added to the redaction set, and be cleared from React state after submit (Step 2.5 mirrors Step 4 `byok` pattern at `playground-form.tsx` lines 223-228).

### 3. Error envelope is Stripe-shape; `ErrorCode` is a string-constants class
- **Source:** `models/errors.py` lines 31-64 — `ErrorCode.UNAUTHORIZED`, `INFRA_UNAVAILABLE`, `INVALID_REQUEST`, `RECIPE_NOT_FOUND`, `RUNNER_TIMEOUT`, `INTERNAL`.
- **Source:** `routes/runs.py::_err()` helper (lines 60-78) — one `JSONResponse` builder for every 4xx/5xx so no drift.
- **New codes likely needed (do NOT invent freely; follow the same pattern):** `AGENT_NOT_FOUND`, `AGENT_NOT_RUNNING`, `AGENT_ALREADY_RUNNING`, `CHANNEL_NOT_CONFIGURED`. Each gets a `_CODE_TO_TYPE` entry (lines 52-64) — types stay Stripe-style (`not_found`, `conflict`, `invalid_request`, ...).

### 4. DB pool scope: open + close AROUND `to_thread`, never across it
- **Source:** `routes/runs.py` lines 166-180 (pre-run DB scope), 199-208 (error-path scope), 217-218 (post-run scope). Commented as "Pitfall 4 — DB pool exhaustion if conn held across the run."
- **Rule:** persistent-start handler follows the identical 3-scope shape. Pre-run: insert `agent_container` row with status=`starting`. Long await: `execute_persistent_start` (no DB held). Post-run: update row to `running` + ready_at, or rollback to `start_failed` on exception.

### 5. Correlation ID + access log middleware already redacts Authorization header
- **Source:** `main.py` lines 96-104; middleware stack = `CorrelationIdMiddleware` → `AccessLogMiddleware` → `RateLimitMiddleware` → `IdempotencyMiddleware` → router. Declaration order is outermost last.
- **Rule:** new endpoints do not re-implement auth/log plumbing. They inherit the middleware. Bearer-token parsing follows the exact `authorization: str = Header(default="")` + `authorization.startswith("Bearer ")` check from `routes/runs.py` lines 85-109.

### 6. ANONYMOUS_USER_ID is the Phase 19 single-tenant anchor
- **Source:** `constants.py` lines 14-16; `ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000001")`. Seeded in `alembic/versions/001_baseline.py`.
- **Rule:** every new endpoint resolves user_id via `ANONYMOUS_USER_ID` (import from `..constants`, not re-type the UUID). Action-list B2 notes this is the multi-tenancy seam for later; the `/start`/`/stop`/`/status`/`/pair` endpoints all pass `ANONYMOUS_USER_ID` to the store layer like `agents.py` line 23 already does.

---

## Pattern Assignments

### Artifact 1 — `docs/RECIPE-SCHEMA.md` v0.2 + `tools/ap.recipe.schema.json` additive blocks

**Analog:** the file itself. v0.1.1 was already an additive revision over v0.1 (preamble bullet at line 13: "additive over `ap.recipe/v0.1`: every field in a valid v0.1 recipe remains valid"). Phase 22a does the same trick once more for v0.1 → v0.2.

**JSON Schema versioning seam — already baked in** (`tools/ap.recipe.schema.json` lines 5-9):
```json
"$comment": "Root uses $ref to the single v0_1 branch today. When v0.2 ships (Phase 13), this becomes `oneOf: [{$ref: v0_1}, {$ref: v0_2}]` with apiVersion discriminator. Keeping $ref today preserves deep error paths from jsonschema; oneOf with a single branch collapses inner errors into an opaque top-level message (WR-01)."
```
The v0.2 work is **exactly** what that comment describes: add a `v0_2` branch under `$defs`, flip the root `$ref` into a `oneOf` with an `apiVersion` discriminator. Do NOT remove v0_1; both branches must coexist so existing recipes stay valid. See schema lines 10-40 for the `v0_1` branch shape — `v0_2` copies it then adds `persistent` and `channels` to `required` (or leaves them optional if older recipes should still parse as v0.2) and adds the two new top-level subschemas.

**Authoritative shape of `persistent:` (drawn verbatim from the 5 recipes' v0.2 DRAFT blocks):**

From `recipes/hermes.yaml` lines 213-240 (env-transport variant — minimal):
```yaml
persistent:
  mode: gateway-daemon           # enum candidate: [gateway-daemon] — v0.2 ships one mode
  spec:
    argv: [gateway, run, -v]     # required; runner substitutes no tokens (no $PROMPT/$MODEL)
    ready_log_regex: "gateway\\.run: ✓ (\\w+) connected"
    health_check:
      kind: process_alive        # enum: [process_alive | http]
    graceful_shutdown_s: 5       # int seconds; SIGTERM timeout before force-rm
```

From `recipes/picoclaw.yaml` lines 194-241 (file-transport variant with `entrypoint: sh`, health_check http):
```yaml
persistent:
  mode: gateway-daemon
  spec:
    entrypoint: sh               # same as invoke.spec.entrypoint — optional override
    argv:
      - -c
      - |
        set -e
        ...heredoc config writes + exec picoclaw gateway -d
    ready_log_regex: "Telegram bot connected username="
    health_check:
      kind: http
      port: 18790
      path: /ready
    graceful_shutdown_s: 5
```

From `recipes/nullclaw.yaml` lines 214-261 — introduces **one extra field** that v0.2 must codify:
```yaml
persistent:
  ...
  spec:
    ...
    user_override: root          # Docker --user override; required for image-ownership bugs
```

**Authoritative shape of `channels:` — empirically proven across all 5 recipes.** Schema-v0.2 candidate fields (all seen in the wild):

```yaml
channels:
  <channel_id>:                      # enum candidates: telegram|discord|slack|whatsapp|matrix|signal|...
    config_transport: env | file     # REQUIRED. env = docker -e injection; file = sh-heredoc config write
    required_user_input:             # REQUIRED. ordered; drives deploy-form field order
      - env: TELEGRAM_BOT_TOKEN
        secret: true | false         # REQUIRED. gates masking + redaction
        kind: telegram_numeric_id
              | telegram_numeric_id_csv
              | telegram_numeric_id_or_username  # only kinds seen so far
        hint: "..."                  # REQUIRED. user-facing short help
        hint_url: "https://..."      # OPTIONAL. when set, UI renders as clickable link
        prefix_required: "tg:"       # OPTIONAL. runner auto-prepends to the value before injection (openclaw only)
    optional_user_input: [...]       # same shape, empty array allowed
    ready_log_regex: "..."           # REQUIRED. per-channel ready signal (may differ from persistent.spec.ready_log_regex when multiple channels run in one gateway — see hermes)
    response_routing: per_message_origin | fixed_home_channel  # REQUIRED
    multi_user_model: allowlist
                    | pairing_then_allowlist
                    | allowlist_or_dm_pairing     # 3 values seen
    multi_account_supported: true | false         # OPTIONAL (default false)
    provider_compat:                              # OPTIONAL — used by openclaw only
      supported: [anthropic]
      deferred: [openrouter]
    known_quirks:                                 # OPTIONAL — openclaw uses this heavily
      - id: openrouter_provider_plugin_silent_fail
        severity: blocks_llm_reply_with_openrouter
        description: |
          multi-line ...
    verified_cells:                               # REQUIRED. non-empty in battle-proven recipes
      - date: "2026-04-17"                        # YYYY-MM-DD
        bot_username: "@AgentPlayground_bot"
        allowed_user_id: 152099202                # int
        model: openrouter/anthropic/claude-haiku-4.5
        env_var: OPENROUTER_API_KEY               # OPTIONAL (openclaw uses to disambiguate provider)
        provider: openrouter|anthropic            # OPTIONAL (openclaw)
        boot_wall_s: 10                           # int seconds
        first_reply_wall_s: 1                     # OPTIONAL
        reply_sample: "..."                       # OPTIONAL
        verdict: PASS | FULL_PASS | CHANNEL_PASS_LLM_FAIL   # 3 verbs seen
        notes: |
          multi-line
        category: PASS | BLOCKED_UPSTREAM                   # must be subset of existing Category enum + 1 new
```

**Gotchas in the 5 recipes that the v0.2 schema MUST accommodate:**
1. `persistent.spec.entrypoint` is optional (hermes has none, picoclaw/nullclaw/nanobot/openclaw all use `sh`).
2. `persistent.spec.user_override` is nullclaw-only — codify as optional Docker --user string.
3. `channels.telegram.verified_cells[*].verdict` has evolved beyond PASS/FAIL; `FULL_PASS`, `CHANNEL_PASS_LLM_FAIL`, `BLOCKED_UPSTREAM` all appear. Either expand the verdict enum or add a channel-specific `verdict` enum distinct from `smoke.verified_cells[*].verdict`.
4. `channels.telegram.known_quirks[*]` shape in openclaw (lines 318-441) uses `id` + `severity` + `description`, which differs from `smoke.known_quirks[*]` which uses `quirk` + `impact` (schema lines 444-459). Reconcile at v0.2 — probably by keeping the two distinct (channel-scoped vs. smoke-scoped).
5. The `prefix_required` field (openclaw `"tg:"`) is already load-bearing — runner must honor it before injecting into the `file`-transport heredoc.

### Artifact 2 — `tools/run_recipe.py` `--mode persistent` / `run_cell_persistent`

**Analog:** `run_cell()` at `tools/run_recipe.py` lines 664-856.

**Code to copy (lines 683-720) — docker invocation build-up:**
```python
raw_argv = recipe["invoke"]["spec"]["argv"]
argv = substitute_argv(list(raw_argv), prompt, model)

vol = recipe["runtime"]["volumes"][0]
container_mount = vol["container"]
entrypoint = recipe["invoke"]["spec"].get("entrypoint")
data_dir = Path(tempfile.mkdtemp(prefix=f"ap-recipe-{recipe['name']}-data-"))

cidfile = Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")
env_file = Path(f"/tmp/ap-env-{uuid.uuid4().hex}")
env_file.write_text(f"{api_key_var}={api_key_val}\n")
env_file.chmod(0o600)

docker_cmd = [
    "docker", "run", "--rm",                        # <-- CHANGE #1 for persistent: drop --rm, add -d + --name
    f"--cidfile={cidfile}",
    "--env-file", str(env_file),                    # <-- CHANGE #2: append more env entries for channel creds
    "-v", f"{data_dir}:{container_mount}",
]
if entrypoint:
    docker_cmd += ["--entrypoint", entrypoint]      # <-- Persistent variant reads persistent.spec.entrypoint, not invoke.spec.entrypoint
docker_cmd += [image_tag] + argv                    # <-- argv comes from persistent.spec.argv (NO $PROMPT substitution in persistent mode)
```

**Persistent-mode deltas (what needs to change from `run_cell`):**

| Step | `run_cell` (one-shot) | `run_cell_persistent` (new) |
|------|------------------------|------------------------------|
| docker flags | `docker run --rm --cidfile=...` | `docker run -d --name ap-agent-<run_id> ...` (drop `--rm`, add `-d`, add `--name`) |
| env-file | single `api_key_var=api_key_val` line | multi-line: api_key line + one line per `channels.<cid>.required_user_input[*]` entry |
| `--user` flag | not set | set if `persistent.spec.user_override` present (nullclaw path) |
| argv source | `recipe["invoke"]["spec"]["argv"]` with `$PROMPT`/`$MODEL` substitution | `recipe["persistent"]["spec"]["argv"]` — substitute `$MODEL` + `$TELEGRAM_ALLOWED_USER` etc, but NOT `$PROMPT` |
| ready detection | wait for process exit via `subprocess.run(timeout=smoke_timeout_s)` | poll `docker logs <cid>` for `ready_log_regex` (use `run_with_timeout` + re-invocation pattern) |
| health check | none | run once after ready_log match. `kind: process_alive` = `docker inspect ... State.Running == true`. `kind: http` = curl `http://127.0.0.1:<port><path>` from HOST (port is loopback per openclaw notes); docker exec fallback if port isn't published |
| cleanup | cidfile + env_file + data_dir unlinked in `finally` | cidfile + env_file + data_dir kept as long as container lives — unlinked on `stop`. Capture container_id from cidfile AFTER ready (same read pattern as lines 756-759) |
| return | `(Verdict, details_dict)` | `(Verdict, dict)` with new keys: `container_id`, `ready_at` (ISO timestamp), `boot_wall_s`, `ready_log_match`. Preserve existing keys so downstream response models don't fork |
| teardown | N/A | separate function `stop_persistent(container_id, graceful_shutdown_s)` that `docker kill -s TERM <cid>` + wait + `docker rm -f <cid>` (copies timeout-reap pattern from `run_cell` lines 754-772) |

**Stop-path prior art — copy from `run_cell` timeout handler (lines 754-772):**
```python
# docker kill -- check=False because the container may have exited
# on its own between TimeoutExpired and now (RESEARCH.md §Pitfall 4).
subprocess.run(
    ["docker", "kill", cid],
    timeout=10, check=False, capture_output=True,
)
subprocess.run(
    ["docker", "rm", "-f", cid],
    timeout=10, check=False, capture_output=True,
)
```
For graceful stop: change `docker kill <cid>` to `docker kill -s TERM <cid>`, then `docker wait --timeout <graceful_shutdown_s>` (or a poll-loop), then `docker rm -f` (the same two-step fallback to force-remove).

**Exec-path prior art (for `/channels/:cid/pair`) — no existing analog in `run_recipe.py`. Use `subprocess.run(["docker", "exec", cid, ...], timeout=...)`; model the return dict on `run_cell`'s `details`** (recipe, exit_code, stdout_tail, stderr_tail, wall_time_s). The openclaw `pairing approve <channel> <code>` invocation is the first caller; argv comes from a new `channels.<cid>.pairing:` block (not yet in any recipe v0.2 draft — introduce here per 22-CONTEXT.md §5).

**Gotchas in `run_cell` relevant to persistent:**
- **Cidfile pre-creation must NOT happen** (line 692 comment: "DO NOT pre-create. Docker errors if file exists.") — persistent mode inherits this.
- **Env vars leak via `docker run -e` to `/proc/*/cmdline`** — hermes pattern from lines 696-704 (env-file + chmod 600 + unlink) is mandatory. Additional channel secrets go in the SAME env-file, not into `-e` args.
- **TimeoutExpired bytes-vs-str decode** (lines 745-751, "defensive decode for Python 3.10 per RESEARCH.md §Pitfall 3") applies identically when polling `docker logs`.
- **`_redact_api_key` widens with ≥8-char values** (line 399) — channel tokens are longer than 8 chars, so invoking it with `(text, "TELEGRAM_BOT_TOKEN", bot_token_value)` triggers both the `VAR=` and bare-value substitution. Reuse verbatim.

### Artifact 3 — new endpoints in `api_server/src/api_server/routes/agents.py`

**Analog:** `api_server/src/api_server/routes/runs.py::create_run` (lines 82-238). The full 9-step flow is documented in the module docstring (lines 1-29):

```python
# 1. Parse Authorization: Bearer <key> → provider_key (memory only)
# 2. Validate body.recipe_name against app.state.recipes
# 3. Resolve user_id = ANONYMOUS_USER_ID (Phase 19)
# 4. Upsert agent_instances(user_id, recipe_name, model)
# 5. Mint ULID run_id, insert runs row (verdict=NULL)
# 6. RELEASE DB connection (Pitfall 4)
# 7. Acquire per-tag Lock + Semaphore → to_thread(run_cell)
# 8. Re-acquire DB connection; write_verdict(run_id, details)
# 9. Return RunResponse
```

**Per-endpoint pattern assignment (follow the 9 steps verbatim; deviation only where noted):**

#### `POST /v1/agents/:id/start`

Request/response model pattern from `routes/runs.py::create_run` (lines 82-238).

- **Auth — lines 94-109 copied verbatim.** Bearer token is `provider_key` (the agent's LLM key). Additional channel creds come from the request body, NOT the header. Treat the same way: local variable, never logged, redacted on exception.
- **Lookup — lines 111-120 copied.** But resolves `agent_instance` by `agent_id` UUID from the path, not `recipe_name` from body. Query follows `services/run_store.py::list_agents` shape (lines 72-108); 404 with `ErrorCode.AGENT_NOT_FOUND` (new code).
- **Recipe fetch — lines 112-136 pattern.** Recipe comes from `request.app.state.recipes[agent.recipe_name]`. 500/`ErrorCode.INTERNAL` if `recipe["persistent"]` block is missing (same defensive style as lines 131-136 for missing `api_key_var`).
- **DB scope 1 — lines 166-180 pattern.** Insert a new `agent_containers` row (status=`starting`, container_id=NULL) before long await. Close connection.
- **Long await — lines 184-214 pattern.** `await execute_persistent_start(app.state, recipe, channel_creds=..., ...)`. Wrap in try/except; on failure redact + write `start_failed` row like lines 197-214.
- **DB scope 2 — lines 217-218 pattern.** Update agent_containers row with container_id, ready_at, boot_wall_s, status=`running`.
- **Response — lines 220-238 pattern.** Return a Pydantic response model.

Pydantic request body model (copy `RunRequest` at `models/runs.py` lines 49-83 verbatim, rename + swap fields):
```python
class AgentStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")               # SAME — rejects unknown fields
    channel: str = Field(..., pattern=r"^[a-z0-9_-]+$")     # e.g. "telegram" — key into recipe["channels"]
    channel_inputs: dict[str, str] = Field(default_factory=dict)   # {env_var: value}, validated against recipe["channels"][channel]["required_user_input"]
    # NO prompt/metadata — agents are not one-shots; the prompt comes later from the channel itself
```

#### `POST /v1/agents/:id/stop`

Simpler than `/start`: look up `agent_containers`, read `container_id`, call `execute_persistent_stop(container_id, graceful_shutdown_s)` inside `to_thread`, mark row `stopped`.
- Auth step — copy `routes/runs.py` lines 94-109 but the Bearer header is optional here (stopping doesn't need the LLM key; it needs the session cookie, which Phase 22a still fakes via `ANONYMOUS_USER_ID`).
- DB scope 1: fetch container_id, confirm status=`running` (409/`AGENT_NOT_RUNNING` if not).
- Long await: `execute_persistent_stop` (no Lock+Semaphore needed for stop — SAME image, different container).
- DB scope 2: update row status=`stopped`, stopped_at=NOW().

#### `GET /v1/agents/:id/status`

Read-only. No runner call except `docker inspect <cid>` for liveness + `docker logs --tail N <cid>`.
- Pattern lives 100% in `services/run_store.py`. Add `fetch_agent_container(conn, agent_id)` — copy `fetch_run` shape (lines 172-211).
- Thin `to_thread` wrap for `docker inspect` + `docker logs --tail <n>`; no image-tag lock needed (read-only).
- Response shape: `AgentStatusResponse { container_id, status, ready_at, last_health_probe_at, last_health_probe_ok, log_tail: list[str] }`.

#### `POST /v1/agents/:id/channels/:cid/pair`

Openclaw-specific. Body `{code: str}`.
- Auth: same Bearer pattern (this endpoint runs a container command that may need the LLM key? — no, `openclaw pairing approve` is local). Still enforce Bearer for API consistency (treat header as session, not LLM key; 401 if missing).
- Validate `:cid` is in `recipe["channels"]` and that `recipe["channels"][cid]` has a `pairing` block (new v0.2 field — add to schema at the same time).
- `execute_persistent_exec(container_id, argv)` where argv is built from `recipe["channels"][cid]["pairing"]["approve_argv"]` with `$CODE` substituted via the same `substitute_argv` pattern (`run_recipe.py` lines 282-303).
- Return exit_code + stdout_tail + stderr_tail.

### Artifact 4 — `services/runner_bridge.py` new functions

**Analog:** existing `execute_run` at `runner_bridge.py` lines 78-120.

**Code to copy (lines 98-113):**
```python
run_cell = _import_run_cell()
image_tag = f"ap-recipe-{recipe['name']}"   # matches tools/run_recipe.py convention
tag_lock = await _get_tag_lock(app_state, image_tag)
async with tag_lock:                         # serialize SAME-tag builds
    async with app_state.run_semaphore:      # bound total concurrent runs
        result = await asyncio.to_thread(
            run_cell,
            recipe,
            image_tag=image_tag,
            prompt=prompt,
            model=model,
            api_key_var=api_key_var,
            api_key_val=api_key_val,
            quiet=True,
        )
```

**New functions (copy structure, swap inner callable):**
- `execute_persistent_start(app_state, recipe, *, model, api_key_var, api_key_val, channel_creds)` — identical tag_lock + semaphore wrap (first call to an image still needs an `ensure_image` inside `run_cell_persistent`). Inner callable is `run_cell_persistent`.
- `execute_persistent_stop(container_id, graceful_shutdown_s)` — NO tag_lock (container already exists; stop doesn't touch images). Still wrap in `to_thread`. No semaphore either (stop is cheap and concurrent-safe).
- `execute_persistent_status(container_id)` — read-only `docker inspect` + `docker logs --tail N`. `to_thread` wrap only; no lock, no semaphore.
- `execute_persistent_exec(container_id, argv, *, timeout_s)` — `to_thread`-wrapped `subprocess.run(["docker", "exec", container_id, ...])`. No lock (not touching the image); the semaphore is optional — the openclaw-pair use case is infrequent enough to skip it (decide at planning).

**Import cache gotcha (lines 44-49):** the `_import_run_cell` helper checks `sys.modules["run_recipe"]` first and re-uses the existing module if present. The new `run_cell_persistent` function lives in the same `run_recipe` module, so `_import_run_cell` needs a sibling `_import_run_cell_persistent()` OR gets refactored to return the whole module (then callers do `mod.run_cell` vs. `mod.run_cell_persistent`). The refactor is cheaper — plan picks.

### Artifact 5 — new Pydantic models in `models/agents.py`

**Analog:** `models/runs.py::RunRequest` (lines 49-83) + `RunResponse` (lines 86-109).

**Patterns to copy verbatim:**
- `model_config = ConfigDict(extra="forbid")` on every request model — rejects inline-YAML injection + unknown fields at parse time.
- Field-level validation: `pattern=r"^[a-z0-9_-]+$"` for channel ID; `min_length=1, max_length=128` for model + agent name; `max_length=16384` for any free-form string body.
- Both camel/snake happy path: `populate_by_name=True` only on response shapes that read aliases (see `models/recipes.py::RecipeSummary` line 41).
- Required-vs-optional conventions mirror `models/runs.py` — `| None = None` with explicit null defaults, never bare `Optional[...]`.

### Artifact 6 — new `run_store.py` CRUD for `agent_containers`

**Analog:** `services/run_store.py` lines 36-211 — 5 CRUD functions total.

**Patterns to copy:**
- `asyncpg` only. Every query uses `$1, $2, ...` placeholders. No f-string interpolation with user input (line 6-8 docstring is explicit).
- UUID primary keys minted server-side: `gen_random_uuid()` (line 57). The `agent_containers` table gets the same `id UUID DEFAULT gen_random_uuid() PRIMARY KEY` + FK to `agent_instances.id`.
- `ON CONFLICT` upsert pattern (lines 54-67) applies if we add a uniqueness constraint on `(agent_instance_id)` to prevent double-start.
- Two-phase insert pattern (lines 111-130 + 133-169) for the long-await flow: `insert_pending_*` fills NULL columns, `write_*` completes the row. `agent_containers` follows identical shape (status=`starting` → `running` with ready_at/container_id/boot_wall_s filled).
- Read-back function (lines 172-211) returns `dict(row)` (not the raw asyncpg Record), with numeric `NUMERIC` fields explicitly cast via `float(...)`.

**New migration 003:** copy shape from `alembic/versions/002_agent_name_personality.py` (full file, 69 lines). Add columns to `agent_instances` or create a sibling `agent_containers` table — phase 22a planner picks between additive columns on `agent_instances` (simpler) vs. separate table (lets an agent have a history of containers across start/stop cycles, useful for Phase 23 persistent volumes).

### Artifact 7 — `frontend/components/playground-form.tsx` Step 2.5

**Analog:** Step 3 "Name + Personality" inside the same file (lines 384-453).

**Code-shape to copy — `SectionHeader` + grid + label/input or radio-card pattern:**
```tsx
<section>
  <SectionHeader
    step={2.5}                                                        // bump all downstream step numbers or use "2.5"
    icon={<MessageSquareText className="size-5" />}                   // lucide-react — already imported line 17
    title="How will you use this?"
    subtitle="Pick one-shot smoke to verify the recipe works, or persistent mode to get a live Telegram bot."
  />

  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
    {/* Radio-card pattern — mirror PERSONALITIES.map() at lines 420-450 */}
    {[
      { id: "smoke",     label: "One-shot smoke",        emoji: "🧪", description: "..." },
      { id: "persistent", label: "Persistent + Telegram", emoji: "💬", description: "..." },
    ].map((mode) => {
      const active = deployMode === mode.id;
      return (
        <button
          key={mode.id}
          type="button"
          onClick={() => setDeployMode(mode.id as DeployMode)}
          disabled={isRunning}
          aria-pressed={active}
          className={cn(
            "group flex h-full items-start gap-3 rounded-xl border p-4 text-left transition-all",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
            active
              ? "border-primary/70 bg-primary/10 shadow-lg shadow-primary/15"
              : "border-border/50 bg-card/40 hover:border-primary/40 hover:bg-card/70",
            isRunning && "cursor-not-allowed opacity-60",
          )}
        >
          {/* ...same inner structure as personality cards (lines 439-446)... */}
        </button>
      );
    })}
  </div>
</section>
```

**Conditional channel-input fields — copy the `byok` input pattern from Step 4 (lines 469-490):**
```tsx
{deployMode === "persistent" && selectedRecipe && (
  // For each entry in channels.telegram.required_user_input (fetched from /v1/recipes/:name):
  <div className="flex flex-col gap-3">
    <Label htmlFor={input.env} className="flex items-center gap-2 text-base font-semibold text-foreground">
      <KeyRound className="size-5 text-foreground/70" /> {input.env}
    </Label>
    <Input
      id={input.env}
      type={input.secret ? "password" : "text"}                   // mirror line 475 (byok is password)
      autoComplete={input.secret ? "new-password" : "off"}        // mirror line 476
      autoCorrect="off"
      autoCapitalize="off"
      spellCheck={false}
      placeholder="..."
      required
      disabled={isRunning}
      value={channelInputs[input.env] ?? ""}
      onChange={(e) => setChannelInputs(prev => ({...prev, [input.env]: e.target.value}))}
      className="h-14 max-w-2xl text-lg font-mono"
    />
    <p className="text-sm leading-relaxed text-foreground/70">
      {input.hint}
      {input.hint_url && (
        <a href={input.hint_url} target="_blank" rel="noopener noreferrer" className="ml-1 underline">
          get one here
        </a>
      )}
    </p>
  </div>
)}
```

**State mirroring Step 4's `byok` clear-after-submit (lines 224-228):**
```ts
finally {
  setByok("");
  setChannelInputs({});                 // clear all channel inputs after submit — same BYOK discipline
  setIsRunning(false);
}
```

**CRITICAL Rule-2 enforcement (CLAUDE.md golden rule #2 + ACTION-LIST.md P2 for `RECIPE_TAGLINES`/`RECIPE_ACCENTS`):**
- **DO NOT** hardcode a `CHANNELS` array or channel-specific field lists in React. The `channels.<id>.required_user_input[]` comes from `GET /v1/recipes/:name` — extend `RecipeSummary` (or add a `RecipeDetailResponse` fetch on recipe-select) to surface it.
- Action-list P2 already flags `RECIPE_TAGLINES` and `RECIPE_ACCENTS` at lines 52-66 of `playground-form.tsx` as client-side catalog violations. The v0.2 work MUST NOT extend that anti-pattern with a client-side `CHANNELS` constant. Read channel metadata from the server.

**Gotchas in `playground-form.tsx` relevant to Step 2.5:**
- `canDeploy` gate (lines 198-204) must grow: `deployMode === "smoke" || (deployMode === "persistent" && allRequiredChannelInputsFilled)`.
- `onDeploy` (lines 206-229) currently POSTs to `/api/v1/runs`. Step 2.5 forks the call: smoke → existing `/v1/runs`; persistent → new `/v1/agents/:id/start` (requires agent_instance_id — the smoke path creates it as a side-effect today at `upsert_agent_instance` in `runs.py` line 171; planning must decide if persistent-start creates the agent_instance inline or demands a prior smoke run).
- The existing "Deploy" button copy at lines 506-510 needs conditional copy for persistent mode ("Deploy & start Telegram bot" vs. "Deploy smoke").
- openclaw special case (per 22-CONTEXT.md §3 + §6): when `selectedRecipe.name === "openclaw"` AND `deployMode === "persistent"`, the Bearer-key Label copy flips from "OpenRouter API key" to "Anthropic API key" per the `provider_compat.deferred: [openrouter]` recipe field. Drive this off the recipe's `channels.telegram.provider_compat` (server-supplied), not a hardcoded check.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `ap.recipe.v0.2.schema.json` (new $defs branch) | schema | static contract | Partially new — the `$defs.v0_1` branch IS the shape to copy; `v0_2` duplicates it + adds `persistent` + `channels` subschemas. Not a full "no analog" — just no co-located v0.2 yet. |
| Channel-specific `/pair` exec route | controller | docker-exec request-response | No existing endpoint `docker exec`s into a user container. Closest is the lint flow (`routes/recipes.py::lint_recipe`, lines 57-92) — bytes in, validation out — but the data-flow is totally different. The pair endpoint is the first `exec` surface; the planner invents it from scratch using the `runner_bridge` per-tag-lock + semaphore scaffold as the container-safe shell. |

---

## Existing `verified_cells` shape — authoritative for v0.2

### Smoke `verified_cells` (already in schema, lines 352-391 of `tools/ap.recipe.schema.json`):
```yaml
smoke:
  verified_cells:
    - model: anthropic/claude-haiku-4.5
      verdict: PASS              # enum [PASS, FAIL]
      category: PASS             # $ref category — 9 live + 2 reserved
      detail: ''                 # required; empty string convention for PASS
      wall_time_s: 12.86         # optional; runner writes back on --all-cells
      notes: "..."               # optional free-form
      annotations: {...}         # optional escape valve
```

### Channel `verified_cells` (empirically proven across 4 recipes — schema addition for v0.2):
**Keys observed in at least one recipe** (union of hermes + picoclaw + nullclaw + nanobot + openclaw):
- `date` (str, YYYY-MM-DD) — **every recipe**
- `bot_username` (str) — **every recipe**
- `allowed_user_id` (int) — **every recipe**
- `model` (str) — **every recipe EXCEPT hermes** (hermes gateway auto-detects model, so absent there)
- `verdict` (str — extended: PASS | FULL_PASS | CHANNEL_PASS_LLM_FAIL) — **every recipe**
- `category` (str — extended: PASS | BLOCKED_UPSTREAM) — **every recipe**
- `notes` (str, multiline) — **every recipe**
- `boot_wall_s` (int) — **every recipe**
- `first_reply_wall_s` (int) — hermes + picoclaw only
- `reply_sample` (str) — picoclaw only
- `provider` (str: openrouter|anthropic) — openclaw only
- `env_var` (str) — openclaw only

**Recommended v0.2 schema shape (minimum viable, from empirical majority):**
```json
{
  "type": "object",
  "required": ["date", "bot_username", "allowed_user_id", "verdict", "category", "notes"],
  "properties": {
    "date":            {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    "bot_username":    {"type": "string"},
    "allowed_user_id": {"type": "integer"},
    "model":           {"type": "string"},
    "provider":        {"type": "string"},
    "env_var":         {"type": "string"},
    "verdict":         {"type": "string", "enum": ["PASS", "FULL_PASS", "CHANNEL_PASS_LLM_FAIL"]},
    "category":        {"type": "string", "enum": [..., "BLOCKED_UPSTREAM"]},
    "boot_wall_s":     {"type": "integer"},
    "first_reply_wall_s": {"type": "integer"},
    "reply_sample":    {"type": "string"},
    "notes":           {"type": "string"}
  }
}
```

Planner should decide whether to accept `additionalProperties: true` on channel verified_cells (forgiving) or enumerate the exact set (strict — matches the rest of the schema where every block uses `additionalProperties: false`). The 5 recipes' drafts already diverge in field presence, so strict enumeration is feasible once the full union is codified above.

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/routes/` — 5 modules (agents, runs, recipes, schemas, health)
- `api_server/src/api_server/services/` — 6 modules (run_store, runner_bridge, recipes_loader, lint_service, personality, rate_limit)
- `api_server/src/api_server/models/` — 5 modules (agents, runs, recipes, errors, schemas)
- `tools/run_recipe.py` — the single 1182-line runner
- `tools/ap.recipe.schema.json` — the authoritative JSON Schema
- `recipes/*.yaml` — 5 battle-proven recipes (hermes, picoclaw, nullclaw, nanobot, openclaw)
- `frontend/components/playground-form.tsx` — the single 1162-line deploy form

**Files scanned:** ~20. **Analogs selected:** 7 exact + 2 partially-new.
**Pattern extraction date:** 2026-04-18
