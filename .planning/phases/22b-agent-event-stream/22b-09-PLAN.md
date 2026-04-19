---
phase: 22b
plan: 09
type: execute
wave: 5
depends_on: ["22b-06"]
files_modified:
  - tools/ap.recipe.schema.json
  - tools/tests/test_lint.py
  - tools/tests/conftest.py
autonomous: true
gap_closure: true
requirements:
  - SC-03-GATE-A
  - SC-03-GATE-B

must_haves:
  truths:
    - "tools/ap.recipe.schema.json $defs.v0_2 declares a top-level optional `direct_interface` property pointing at a new `$defs.direct_interface_block` whose oneOf branches are: `docker_exec_cli` (argv_template + timeout_s + reply_extract_regex + exit_code_success + stdout_reply) and `http_chat_completions` (port + path + auth + request_template + response_jsonpath + timeout_s)"
    - "tools/ap.recipe.schema.json $defs.channel_entry declares `event_log_regex` (object map: kind name → regex string OR null) and `event_source_fallback` (oneOf: docker_logs_stream / docker_exec_poll / file_tail_in_container) — both as additive optional properties"
    - "Running `pytest tools/tests/test_lint.py::TestLintPositive::test_minimal_valid_recipe_passes` returns PASS"
    - "Running `python3 -c 'from run_recipe import lint_recipe; import json,yaml; s=json.load(open(\"tools/ap.recipe.schema.json\")); [print(r, len(lint_recipe(yaml.safe_load(open(f\"recipes/{r}.yaml\")), s))) for r in [\"hermes\",\"picoclaw\",\"nullclaw\",\"nanobot\",\"openclaw\"]]'` outputs each recipe with `0` lint errors (currently outputs `2` for each — the `direct_interface` and `event_log_regex` additionalProperties violations)"
    - "tools/tests/test_lint.py grows a new positive test class `TestLintRealRecipes` that asserts each of the 5 committed recipes lints clean against the v0.2 schema (regression guard for any future schema drift)"
    - "The 12 broken recipes in tools/tests/broken_recipes/*.yaml STILL fail lint (no regression in negative tests) — the existing `TestLintBrokenRecipes::test_broken_recipe_fails_lint` parametrize sweep stays GREEN"
    - "The Go-side stale schemas at `agents/schemas/recipe.schema.json` and `api/internal/recipes/schema/recipe.schema.json` are NOT touched in this plan — those are pre-v0.2 legacy `ap.recipe/v1` schemas with a separate scope (the Phase 22b-08 SUMMARY reads them but does NOT enforce them); future cleanup tracked under tech-debt"
  artifacts:
    - path: "tools/ap.recipe.schema.json"
      provides: "v0.2 schema extended with direct_interface_block + event_log_regex + event_source_fallback definitions and references"
      contains: "direct_interface_block"
    - path: "tools/tests/test_lint.py"
      provides: "TestLintRealRecipes class with one parametrized test per real recipe asserting `lint_recipe(...) == []`"
      contains: "class TestLintRealRecipes"
    - path: "tools/tests/conftest.py"
      provides: "real_recipes fixture providing the 5 recipe paths (used by TestLintRealRecipes)"
      contains: "real_recipes"
  key_links:
    - from: "tools/ap.recipe.schema.json::$defs.v0_2.properties.direct_interface"
      to: "tools/ap.recipe.schema.json::$defs.direct_interface_block"
      via: "$ref"
      pattern: "#/\\$defs/direct_interface_block"
    - from: "tools/ap.recipe.schema.json::$defs.channel_entry.properties.event_log_regex"
      to: "object map of kind names to regex strings (or null per spike-01c/01e fallback)"
      via: "additionalProperties: { oneOf: [string, null] }"
      pattern: "event_log_regex"
    - from: "tools/ap.recipe.schema.json::$defs.channel_entry.properties.event_source_fallback"
      to: "tools/ap.recipe.schema.json::$defs.event_source_fallback"
      via: "$ref + oneOf discriminated on kind enum"
      pattern: "event_source_fallback"
    - from: "tools/tests/test_lint.py::TestLintRealRecipes"
      to: "all 5 recipes in recipes/*.yaml"
      via: "parametrized test calls lint_recipe and asserts errors == []"
      pattern: "TestLintRealRecipes"
---

<objective>
**Gap 3 closure — recipe lint schema lags the recipe contract.** Verifier verdict: Plan 22b-06 added `direct_interface` (top-level) and `event_log_regex` (under channels.telegram) to all 5 recipes; Plan 22b-08 (this gap closure batch) adds `event_source_fallback` references via the existing nullclaw/openclaw definitions. The canonical schema at `tools/ap.recipe.schema.json` does not declare any of these fields, so strict-mode lint (`additionalProperties: false`) rejects every committed recipe.

**Empirical confirmation (2026-04-19, in this planning session):**
```
$ python3 -c "from run_recipe import lint_recipe; import json,yaml;
              s=json.load(open('tools/ap.recipe.schema.json'));
              print(lint_recipe(yaml.safe_load(open('recipes/hermes.yaml')), s))"
['(root): Additional properties are not allowed (\\'direct_interface\\' was unexpected)',
 'channels.telegram: Additional properties are not allowed (\\'event_log_regex\\' was unexpected)']
```

**Important note on the "two stale schemas" framing in the verifier prompt:** The user prompt pointed at `agents/schemas/recipe.schema.json` and `api/internal/recipes/schema/recipe.schema.json` as the files needing edits. Empirical verification (`grep` + `python3` lint reproducer) shows both of those files are pre-v0.2 legacy `ap.recipe/v1` schemas (257 lines each, declare `id`/`name`/`runtime`/`launch`/`chat_io`/`isolation` — fields that don't exist in v0.2 recipes at all). They are NOT referenced by `test_lint.py` (which uses `tools/ap.recipe.schema.json` per `tools/tests/conftest.py:33`) and NOT referenced by api_server's lint pipeline (`api_server/src/api_server/services/lint_service.py:80` loads `tools/ap.recipe.schema.json`). They ARE embedded by `api/internal/recipes/schema.go` for the Go API's recipe loader, but that loader expects the legacy v1 shape — adding v0.2 fields to those files would not solve gap 3 and would break the Go loader if it ever runs.

The ACTIVE schema is `tools/ap.recipe.schema.json` (1356 lines, v0.2). All work in this plan targets that file. The Go-side stale schemas are documented in the SUMMARY as a separate tech-debt item; they don't block SC-03.

**Scope:** Three additive subschema definitions land in `tools/ap.recipe.schema.json $defs`:

1. **`direct_interface_block`** — top-level oneOf-discriminated block with `kind` enum `{docker_exec_cli, http_chat_completions}` and per-kind `spec`. Field-by-field shape extracted verbatim from the 5 committed recipes (Plan 22b-06 SUMMARY canonicalizes the shape; Plan 22b-07 alters openclaw's spec but does NOT introduce new fields).

2. **`event_log_regex`** — additive property under `channel_entry` (which today is the only channel type — `channels.telegram`). Object map: keys are kind names from `VALID_KINDS` plus the `inbound_message` and `response_ready` extras hermes uses (per recipes/hermes.yaml lines 305-308); values are either a regex string (engine-readable) OR `null` (the docker-logs-not-available signal used by nullclaw + openclaw, per spike-01c/01e). Schema enforces the value union via `oneOf: [{type: string}, {type: null}]`.

3. **`event_source_fallback`** — additive property under `channel_entry`. Required when ANY `event_log_regex.<kind>` is null (this conditional is enforced via `allOf:if/then` per the existing schema's pattern at lines 1261-1352). oneOf-discriminated on `kind` enum `{docker_logs_stream, docker_exec_poll, file_tail_in_container}` (matching watcher_service.py `_select_source` dispatch at line 380-387). Per-kind spec mirrors what nullclaw + openclaw declare today (verified verbatim against recipes/nullclaw.yaml + recipes/openclaw.yaml).

Plus a regression-guard test class in `test_lint.py` that asserts every committed recipe lints clean — so future schema drift is caught immediately rather than at the next SC-03 gate run.

Output: ~120 lines added to `tools/ap.recipe.schema.json` (3 new $defs + 3 new property references in v0_2/channel_entry); 1 new test class with 5 parametrized cases; 1 new fixture; SUMMARY documents what `tools/ap.recipe.schema.json` looked like before/after AND why the Go-side schemas at `agents/schemas/` + `api/internal/recipes/schema/` are intentionally not touched.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22b-agent-event-stream/22b-CONTEXT.md
@.planning/phases/22b-agent-event-stream/22b-VERIFICATION.md
@.planning/phases/22b-agent-event-stream/22b-06-SUMMARY.md
@tools/ap.recipe.schema.json
@tools/tests/test_lint.py
@tools/tests/conftest.py
@tools/run_recipe.py
@recipes/hermes.yaml
@recipes/picoclaw.yaml
@recipes/nullclaw.yaml
@recipes/nanobot.yaml
@recipes/openclaw.yaml

<interfaces>
<!-- The lint_recipe function and existing schema patterns -->

From tools/run_recipe.py (line 120):
```python
def lint_recipe(recipe: dict, schema: dict | None = None) -> list[str]:
    """Validate a recipe dict against the JSON schema. Returns list of human-readable
    error messages, empty list if recipe is valid."""
    # Uses jsonschema.Draft201909Validator under the hood (per tests/test_lint.py imports).
```

From tools/tests/conftest.py:
```python
@pytest.fixture
def schema():
    """Load the JSON Schema for recipe validation."""
    schema_path = Path(__file__).parent.parent / "ap.recipe.schema.json"
    return json.loads(schema_path.read_text())

@pytest.fixture
def minimal_valid_recipe():
    """A minimal recipe dict that passes lint (apiVersion=ap.recipe/v0.1; lines 178-231)."""
    return { ... }   # MUST stay valid after schema extension

@pytest.fixture
def broken_recipes_dir():
    return Path(__file__).parent / "broken_recipes"
```

From tools/ap.recipe.schema.json structure (verified by grep):
- `$defs` block at line 12 contains 12 definitions: category, channel_category, health_check, persistent_block, user_input_entry, channel_verified_cell, channel_entry, channels_block, v0_1, v0_2 (+ helpers).
- The `v0_2` $def at line 946 has `additionalProperties: false` and references `persistent_block` + `channels_block` as optional top-level properties (lines 1254-1259).
- The `channel_entry` $def at line 240 has `additionalProperties: false` and currently declares: config_transport, required_user_input, optional_user_input, ready_log_regex, response_routing, multi_user_model, multi_account_supported, provider_compat, known_quirks, pairing, verified_cells.
- The `allOf:if/then` block at lines 1261-1352 holds cross-field constraints (e.g. `pass_if=response_contains_string` requires `needle`).

Watcher_service.py kind dispatch (line 380-387 — authoritative for event_source_fallback enum):
```python
fallback = channel_spec.get("event_source_fallback")
if fallback is None:
    return DockerLogsStreamSource(container_id, stop_event)
spec = fallback.get("spec") or {}
kind = fallback.get("kind")
if kind == "docker_exec_poll":
    return DockerExecPollSource(container_id, spec, chat_id_hint, stop_event)
if kind == "file_tail_in_container":
    return FileTailInContainerSource(container_id, spec, chat_id_hint, stop_event)
raise ValueError(f"unknown event_source_fallback.kind: {kind!r}")
```

So the enum is: `{docker_logs_stream, docker_exec_poll, file_tail_in_container}`. `docker_logs_stream` is the implicit default when the entire `event_source_fallback` block is absent — the schema MUST allow either form.

From recipes (verified field shapes — DO NOT INVENT, USE THESE VERBATIM):

**hermes direct_interface (recipes/hermes.yaml lines 254-261):**
```yaml
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["/opt/hermes/.venv/bin/hermes", "chat", "-q", "{prompt}", "-Q", "-m", "{model}", "--provider", "openrouter"]
    timeout_s: 60
    stdout_reply: true
    reply_extract_regex: "(?s)(?P<reply>.+?)(?=\\n\\s*session_id:|$)"
    exit_code_success: 0
```

**picoclaw direct_interface (recipes/picoclaw.yaml — read at execution time for exact field set):**
```yaml
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["picoclaw", "agent", "-m", "{prompt}"]
    ... (timeout_s, exit_code_success per spike-06)
```

**nullclaw direct_interface (recipes/nullclaw.yaml):**
```yaml
direct_interface:
  kind: docker_exec_cli
  spec:
    argv_template: ["nullclaw", "agent", "-m", "{prompt}", "--model", "openrouter/{model}"]
```

**nanobot direct_interface (recipes/nanobot.yaml):**

CORRECTION (2026-04-19, in this plan's revision): nanobot is `docker_exec_cli`, NOT `http_chat_completions` as the original interfaces block claimed. Verified by:
```
python3 -c "import yaml; di=yaml.safe_load(open('recipes/nanobot.yaml'))['direct_interface']; print(di['kind'], list(di['spec'].keys()))"
# → docker_exec_cli ['argv_template', 'timeout_s', 'stdout_reply', 'exit_code_success']
```

So nanobot's spec keys are a SUBSET of the docker_exec_cli oneOf branch (omits `reply_extract_regex` — schema field is optional, so this is fine).

The ACTUAL `http_chat_completions` consumer in the current catalog is openclaw (PRE-22b-07; AFTER 22b-07 lands openclaw rewrites to `docker_exec_cli`, leaving the http_chat_completions branch with ZERO consumers in the v0.2 catalog — but the branch must remain because it's the structural shape for any future HTTP-surface recipe; the schema is forward-looking).

```yaml
direct_interface:
  kind: docker_exec_cli   # actual today
  spec:
    argv_template: ["nanobot", "agent", "-m", "{prompt}"]
    timeout_s: 60
    stdout_reply: true
    exit_code_success: 0
```

**openclaw direct_interface (recipes/openclaw.yaml AFTER Plan 22b-07 closure):**
```yaml
direct_interface:
  kind: docker_exec_cli      # (was http_chat_completions; rewritten in 22b-07)
  spec:
    argv_template: ["sh", "-c", "openclaw config set ... && openclaw infer model run --prompt \"{prompt}\" --local --json"]
    timeout_s: 90
    stdout_reply: true
    reply_extract_regex: "(?s)\"outputs\"\\s*:\\s*\\[\\s*\"(?P<reply>[^\"]*)\""
    exit_code_success: 0
```

**hermes event_log_regex (recipes/hermes.yaml lines 304-308):**
```yaml
event_log_regex:
  reply_sent: "..."
  inbound_message: "..."
  response_ready: "..."
  agent_error: "..."
```

**openclaw event_log_regex (recipes/openclaw.yaml lines 365-368):**
```yaml
event_log_regex:
  reply_sent: null           # not observable via docker logs
  inbound_message: null      # not observable via docker logs
  agent_error: "(?:\"logLevelName\":\"(?:ERROR|FATAL)\")"
```

So the schema MUST allow `null` as a value (signaling docker-logs-not-available; consumer falls back to event_source_fallback).

**nullclaw event_source_fallback (recipes/nullclaw.yaml — verbatim):**
```yaml
event_source_fallback:
  kind: docker_exec_poll
  spec:
    argv_template: ["nullclaw", "history", "show", "{session_id}", "--json"]
    session_id_template: "agent:main:telegram:direct:{chat_id}"
    tail_file: "/nullclaw-data/llm_token_usage.jsonl"
```

**openclaw event_source_fallback (recipes/openclaw.yaml lines 369-380):**
```yaml
event_source_fallback:
  kind: file_tail_in_container
  spec:
    sessions_manifest: /home/node/.openclaw/agents/main/sessions/sessions.json
    session_log_template: "/home/node/.openclaw/agents/main/sessions/{session_id}.jsonl"
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add direct_interface_block + event_log_regex + event_source_fallback to tools/ap.recipe.schema.json $defs</name>
  <files>tools/ap.recipe.schema.json</files>
  <read_first>
    **Empirical field-set audit (RAN 2026-04-19 in this plan's revision — confirms the schema's two oneOf branches cover ALL 5 recipes' direct_interface.spec keys; field set IS CLOSED).** Re-run before editing to detect drift:
    ```
    python3 -c "
    import yaml
    for r in ['hermes','picoclaw','nullclaw','nanobot','openclaw']:
        di = yaml.safe_load(open(f'recipes/{r}.yaml')).get('direct_interface', {})
        print(f'{r}: kind={di.get(\"kind\")!r} spec_keys={list(di.get(\"spec\",{}).keys())}')
    "
    ```
    Expected output (verified 2026-04-19, MUST match — if any recipe shows a NEW key not in the lists below, ADD that key to the matching oneOf branch's `properties` block in Change 1; do NOT relax `additionalProperties: false`):
    ```
    hermes:   kind='docker_exec_cli'        spec_keys=['argv_template', 'timeout_s', 'stdout_reply', 'reply_extract_regex', 'exit_code_success']
    picoclaw: kind='docker_exec_cli'        spec_keys=['argv_template', 'timeout_s', 'stdout_reply', 'exit_code_success']
    nullclaw: kind='docker_exec_cli'        spec_keys=['argv_template', 'timeout_s', 'stdout_reply', 'exit_code_success']
    nanobot:  kind='docker_exec_cli'        spec_keys=['argv_template', 'timeout_s', 'stdout_reply', 'exit_code_success']
    openclaw: kind='http_chat_completions'  spec_keys=['port', 'path', 'auth', 'request_template', 'response_jsonpath', 'timeout_s']
              (POST-22b-07 — same recipe, expected: kind='docker_exec_cli' spec_keys=['argv_template', 'timeout_s', 'stdout_reply', 'reply_extract_regex', 'exit_code_success'])
    ```
    Both oneOf branches in Change 1 below cover the union: docker_exec_cli enumerates {argv_template, timeout_s, stdout_reply, reply_extract_regex, exit_code_success} (all 4-5 docker_exec_cli recipes pass — extras like missing reply_extract_regex are tolerated by JSON Schema's `properties` semantics: only declared properties are constrained when `additionalProperties: false`, missing optional ones are fine); http_chat_completions enumerates {port, path, auth, request_template, response_jsonpath, timeout_s} (only openclaw-pre-22b-07 uses this; AFTER 22b-07 the branch remains for future-use but has no current consumer in the v0.2 catalog).

    - tools/ap.recipe.schema.json (THE file being edited — read in full; locate $defs at line 12; locate the persistent_block $def at line 83 (it's the structural analog for the new direct_interface_block — both are top-level optional v0.2 additions referenced from `v0_2.properties`); locate channel_entry $def at line 240 (that's where event_log_regex + event_source_fallback get added as new properties); locate v0_2 $def at line 946 (the `properties` block at line 1254-1259 references persistent + channels — direct_interface lands as a NEW property reference here))
    - recipes/hermes.yaml (lines 254-308 — direct_interface + event_log_regex EMPIRICAL field shapes; copy structure verbatim)
    - recipes/picoclaw.yaml (direct_interface block — confirm field set matches hermes for docker_exec_cli kind)
    - recipes/nullclaw.yaml (event_source_fallback `docker_exec_poll` shape — extract spec keys)
    - recipes/openclaw.yaml (event_source_fallback `file_tail_in_container` shape — extract spec keys; AFTER Plan 22b-07 the direct_interface kind is docker_exec_cli)
    - recipes/nanobot.yaml (direct_interface `http_chat_completions` shape — port + path + auth + request_template + response_jsonpath)
    - api_server/src/api_server/services/watcher_service.py lines 380-387 (the AUTHORITATIVE event_source_fallback.kind enum: docker_exec_poll, file_tail_in_container; docker_logs_stream is the implicit default when the entire block is absent)
  </read_first>
  <action>
**Edit `tools/ap.recipe.schema.json`. THREE additive changes; preserve every other line.**

**Change 1 — ADD `direct_interface_block` $def.** Insert AFTER the existing `persistent_block` $def (which ends around line 142) and BEFORE `user_input_entry` (which starts around line 143). Insert the following JSON object as a sibling under `$defs`:

```json
    "direct_interface_block": {
      "type": "object",
      "required": ["kind", "spec"],
      "additionalProperties": false,
      "description": "v0.2 direct_interface declaration (Phase 22b D-19..D-22). Top-level sibling of `persistent` + `channels`. Declares the recipe's primary programmatic invocation surface — a docker exec CLI invocation OR an HTTP POST to an in-container endpoint. Used by SC-03 Gate A (test/lib/agent_harness.py send-direct-and-read) to invoke the agent directly without involving the channel layer (Telegram bot-self impersonation is filtered by allowFrom; direct_interface bypasses the gateway entirely).",
      "oneOf": [
        {
          "type": "object",
          "required": ["kind", "spec"],
          "additionalProperties": false,
          "properties": {
            "kind": { "const": "docker_exec_cli" },
            "spec": {
              "type": "object",
              "required": ["argv_template"],
              "additionalProperties": false,
              "properties": {
                "argv_template": {
                  "type": "array",
                  "items": { "type": "string" },
                  "minItems": 1,
                  "description": "argv list passed after `docker exec <cid>`. {prompt} and {model} are substituted by the harness via Python str.format() before invocation. SUBSTITUTION IS LITERAL — no shell expansion (subprocess.run(shell=False)). For sh-chained recipes, use the explicit form ['sh', '-c', '<single-string-pipeline>'] (openclaw post-22b-07 example)."
                },
                "timeout_s": {
                  "type": "integer",
                  "minimum": 1,
                  "maximum": 300,
                  "description": "Wall-time budget for the docker exec. Range [1, 300] seconds. Default 60 if omitted by harness logic."
                },
                "stdout_reply": {
                  "type": "boolean",
                  "description": "true → reply text is captured from stdout (typical). false reserved for future stderr-only modes."
                },
                "reply_extract_regex": {
                  "type": "string",
                  "description": "Optional regex applied to stdout. If the regex matches AND has a named group `reply`, harness uses m.group('reply'); else uses m.group(0); else falls back to full stdout. Used to strip trailing session_id lines (hermes), strip JSON envelope wrappers (openclaw), etc."
                },
                "exit_code_success": {
                  "type": "integer",
                  "minimum": 0,
                  "maximum": 255,
                  "description": "Expected exit code for a successful invocation. Defaults to 0; some agents emit non-zero in success states (none currently in catalog, reserved)."
                }
              }
            }
          }
        },
        {
          "type": "object",
          "required": ["kind", "spec"],
          "additionalProperties": false,
          "properties": {
            "kind": { "const": "http_chat_completions" },
            "spec": {
              "type": "object",
              "required": ["port", "path", "request_template", "response_jsonpath"],
              "additionalProperties": false,
              "properties": {
                "port": {
                  "type": "integer",
                  "minimum": 1,
                  "maximum": 65535,
                  "description": "TCP port inside the container exposing the OpenAI-compatible chat completions endpoint."
                },
                "path": {
                  "type": "string",
                  "pattern": "^/",
                  "description": "URL path; must begin with '/'. Typical: /v1/chat/completions"
                },
                "auth": {
                  "type": "object",
                  "required": ["header", "value_template"],
                  "additionalProperties": false,
                  "properties": {
                    "header": { "type": "string", "description": "HTTP header name carrying the credential. Typical: Authorization." },
                    "value_template": { "type": "string", "description": "Template string. {api_key} is substituted with the harness --api-key value at invocation time. Typical: 'Bearer {api_key}'." }
                  }
                },
                "request_template": {
                  "type": "object",
                  "description": "OpenAI-compatible request body template. The harness merges {prompt} into messages[].content at invocation time; other fields (model, temperature, etc.) flow through verbatim. additionalProperties:true to accommodate per-recipe model parameters."
                },
                "response_jsonpath": {
                  "type": "string",
                  "pattern": "^\\$",
                  "description": "Tiny JSONPath subset (must start with '$'). Resolves to the assistant's reply text in the JSON response. Typical: $.choices[0].message.content"
                },
                "timeout_s": {
                  "type": "integer",
                  "minimum": 1,
                  "maximum": 300,
                  "description": "Wall-time budget for the curl invocation. Range [1, 300] seconds. Default 60 if omitted."
                }
              }
            }
          }
        }
      ]
    },
```

**Change 2 — ADD `event_source_fallback` $def.** Insert AFTER `direct_interface_block` and BEFORE `user_input_entry`. Sibling under `$defs`:

```json
    "event_source_fallback": {
      "type": "object",
      "required": ["kind", "spec"],
      "additionalProperties": false,
      "description": "v0.2 channel-scoped event source dispatcher (Phase 22b D-23). Declares the alternate observation path when docker logs do NOT carry per-message events for this recipe. Watcher_service _select_source() (api_server/src/api_server/services/watcher_service.py line 380-387) dispatches on `kind`. When this block is ABSENT entirely, the watcher defaults to docker_logs_stream (the typical case for hermes/picoclaw/nanobot whose docker logs DO carry events).",
      "oneOf": [
        {
          "type": "object",
          "required": ["kind"],
          "additionalProperties": false,
          "properties": {
            "kind": { "const": "docker_logs_stream" },
            "spec": {
              "type": "object",
              "additionalProperties": true,
              "description": "No required spec — docker_logs_stream uses Docker SDK logs(follow=True) directly. spec field reserved for future tuning (buffer size, etc.)."
            }
          }
        },
        {
          "type": "object",
          "required": ["kind", "spec"],
          "additionalProperties": false,
          "properties": {
            "kind": { "const": "docker_exec_poll" },
            "spec": {
              "type": "object",
              "required": ["argv_template"],
              "additionalProperties": false,
              "properties": {
                "argv_template": {
                  "type": "array",
                  "items": { "type": "string" },
                  "minItems": 1,
                  "description": "argv passed to docker exec. {session_id} and {chat_id} are substituted at watcher invocation time."
                },
                "session_id_template": {
                  "type": "string",
                  "description": "Template producing the session_id from chat_id. {chat_id} is substituted. nullclaw example: 'agent:main:telegram:direct:{chat_id}'."
                },
                "tail_file": {
                  "type": "string",
                  "pattern": "^/",
                  "description": "Optional alternative observation surface — a file path the watcher can `docker exec tail -f`. Currently used by nullclaw as a 'something happened' signal even when the per-turn JSON poll is unreliable."
                }
              }
            }
          }
        },
        {
          "type": "object",
          "required": ["kind", "spec"],
          "additionalProperties": false,
          "properties": {
            "kind": { "const": "file_tail_in_container" },
            "spec": {
              "type": "object",
              "required": ["session_log_template"],
              "additionalProperties": false,
              "properties": {
                "sessions_manifest": {
                  "type": "string",
                  "pattern": "^/",
                  "description": "Container-path to the JSON file mapping chat_ids to session_ids. openclaw example: /home/node/.openclaw/agents/main/sessions/sessions.json"
                },
                "session_log_template": {
                  "type": "string",
                  "pattern": "^/",
                  "description": "Container-path template for per-session JSONL files. {session_id} is substituted at watcher invocation time."
                }
              }
            }
          }
        }
      ]
    },
```

**Change 3 — ADD three new property declarations to existing $defs:**

3a. **In `$defs.v0_2.properties`** (currently line 1254-1259 declares `persistent` + `channels`), add `direct_interface` as a third optional sibling:

Find:
```json
        "persistent": {
          "$ref": "#/$defs/persistent_block"
        },
        "channels": {
          "$ref": "#/$defs/channels_block"
        }
      },
```

Replace with:
```json
        "persistent": {
          "$ref": "#/$defs/persistent_block"
        },
        "channels": {
          "$ref": "#/$defs/channels_block"
        },
        "direct_interface": {
          "$ref": "#/$defs/direct_interface_block"
        }
      },
```

3b. **In `$defs.channel_entry.properties`** (line ~252-340), add `event_log_regex` and `event_source_fallback` as optional siblings of the existing `pairing` + `verified_cells` properties.

**Pre-edit verification (MANDATORY — golden rule 5).** Before applying the search-and-replace below, verify that `verified_cells` is the LAST property in `channel_entry.properties`. If it is NOT, the verbatim search pattern below will not match (the trailing `}` after `verified_cells` would close a different sibling, not the parent properties block). Halt and re-investigate before applying the edit.

```bash
python3 -c "import json; s=json.load(open('tools/ap.recipe.schema.json')); print(list(s['\$defs']['channel_entry']['properties'].keys())[-1])"
```

Must output exactly `verified_cells`. (Verified 2026-04-19 in this plan's revision: output is `verified_cells`. Full property order today: `['config_transport', 'required_user_input', 'optional_user_input', 'ready_log_regex', 'response_routing', 'multi_user_model', 'multi_account_supported', 'provider_compat', 'known_quirks', 'pairing', 'verified_cells']`. If a future schema edit reorders properties, this check will surface the change before the search-and-replace silently corrupts the file.)

Find the existing `verified_cells` property in channel_entry.properties (the LAST property; it's a `$ref` to channel_verified_cell items array):
```json
        "verified_cells": {
          "type": "array",
          "items": { "$ref": "#/$defs/channel_verified_cell" },
          "description": "Empirical PASS evidence."
        }
      }
    },
```

Replace with:
```json
        "verified_cells": {
          "type": "array",
          "items": { "$ref": "#/$defs/channel_verified_cell" },
          "description": "Empirical PASS evidence."
        },
        "event_log_regex": {
          "type": "object",
          "description": "v0.2 channel-scoped log-line regex map (Phase 22b D-04). Keys: event kind names (reply_sent, reply_failed, agent_ready, agent_error from VALID_KINDS, plus optional inbound_message + response_ready for the hermes-style metric pipeline). Values: regex string (Python re syntax) OR null (signals 'this kind is NOT observable via docker logs for this recipe' — consumer must use event_source_fallback). additionalProperties allowed because some recipes add bespoke metric kinds (response_ready in hermes).",
          "additionalProperties": {
            "oneOf": [
              { "type": "string" },
              { "type": "null" }
            ]
          },
          "propertyNames": {
            "pattern": "^[a-z][a-z0-9_]*$"
          }
        },
        "event_source_fallback": {
          "$ref": "#/$defs/event_source_fallback",
          "description": "v0.2 channel-scoped event source dispatcher (Phase 22b D-23). Optional — defaults to docker_logs_stream when absent. REQUIRED in practice when ANY event_log_regex.<kind> is null (the watcher needs an alternative observation path for the null kinds; nullclaw + openclaw use this today)."
        }
      }
    },
```

(Note: `additionalProperties: false` on channel_entry is preserved by inserting the new properties INSIDE the existing properties object — additionalProperties applies to the OBJECT, not to the properties block. Verify by reading the channel_entry $def in full first.)

**Validation strategy** (post-edit, golden rule 5 — empirical confirmation):

```bash
# 1. JSON parses (basic syntax check):
python3 -c "import json; json.load(open('tools/ap.recipe.schema.json'))" && echo OK

# 2. All 5 recipes lint clean:
for r in hermes picoclaw nullclaw nanobot openclaw; do
  python3 -c "
import json, yaml, sys
sys.path.insert(0, 'tools')
from run_recipe import lint_recipe
schema = json.load(open('tools/ap.recipe.schema.json'))
recipe = yaml.safe_load(open(f'recipes/$r.yaml'))
errs = lint_recipe(recipe, schema)
print(f'$r:', len(errs), 'errors', errs[:3] if errs else '')
"
done

# 3. Minimal valid recipe (test fixture) STILL passes (no regression):
cd tools && pytest -x tests/test_lint.py::TestLintPositive -v 2>&1 | tail -5

# 4. Broken recipes STILL fail (no regression in negative tests):
cd tools && pytest -x tests/test_lint.py::TestLintBrokenRecipes -v 2>&1 | tail -10
```

All 4 must pass. If any recipe still has lint errors, root-cause the SPECIFIC field that's misshapen — do NOT bandage by adding `additionalProperties: true` anywhere in the new $defs (golden rule 4 — never fix-to-pass). Common likely-needed adjustments:

- nanobot's request_template may have a richer model parameter set than the verbatim hermes example shows; if `additionalProperties: false` rejects a key in nanobot's request_template, change `additionalProperties` on `request_template` from `true` (what the spec above declares) to leave it as `true` (already correct in the proposed schema — verify the recipe doesn't have a deeper nesting that needs explicit allowance).
- hermes's `event_log_regex` includes `inbound_message` and `response_ready` keys not in the canonical `VALID_KINDS` set — the proposed schema uses `additionalProperties: oneOf[string, null]` with `propertyNames pattern` instead of an enum, so these custom keys are allowed (verify by reading the hermes recipe's event_log_regex block at lines 304-308).
- If a recipe's `direct_interface.spec` has a field not in our enumeration (e.g. picoclaw might have a slightly different shape), READ the actual recipe and ADD the field to the appropriate $def. Document the addition in the SUMMARY.
  </action>
  <verify>
    <automated>set -e; python3 -c "import json; json.load(open('tools/ap.recipe.schema.json'))" && python3 -c "
import json, yaml, sys
sys.path.insert(0, 'tools')
from run_recipe import lint_recipe
schema = json.load(open('tools/ap.recipe.schema.json'))
total_errs = 0
for r in ['hermes','picoclaw','nullclaw','nanobot','openclaw']:
    recipe = yaml.safe_load(open(f'recipes/{r}.yaml'))
    errs = lint_recipe(recipe, schema)
    if errs:
        print(f'{r}:', errs)
        total_errs += len(errs)
assert total_errs == 0, f'{total_errs} lint errors across recipes — see prints above'
print('all 5 recipes lint clean')
"</automated>
  </verify>
  <acceptance_criteria>
    - `python3 -c "import json; s=json.load(open('tools/ap.recipe.schema.json')); print('direct_interface_block' in s['$defs'], 'event_source_fallback' in s['$defs'])"` outputs `True True`
    - `python3 -c "import json; s=json.load(open('tools/ap.recipe.schema.json')); print('direct_interface' in s['$defs']['v0_2']['properties'])"` outputs `True`
    - `python3 -c "import json; s=json.load(open('tools/ap.recipe.schema.json')); ce=s['\$defs']['channel_entry']['properties']; print('event_log_regex' in ce, 'event_source_fallback' in ce)"` outputs `True True`
    - All 5 recipes lint clean: the verify automated command exits 0
    - The test_minimal_valid_recipe_passes test STILL passes: `cd tools && pytest -x tests/test_lint.py::TestLintPositive -q 2>&1 | tail -3 | grep -qE "passed"` exits 0
    - The 12 broken recipes STILL fail lint: `cd tools && pytest -x tests/test_lint.py::TestLintBrokenRecipes -q 2>&1 | tail -3 | grep -qE "passed"` exits 0
    - Schema file size grew but is still valid JSON: `wc -l tools/ap.recipe.schema.json` returns >1450 lines (was 1356; +120 for the 3 changes)
    - The Go-side legacy schemas are UNTOUCHED: `git diff agents/schemas/recipe.schema.json api/internal/recipes/schema/recipe.schema.json | wc -l` returns `0`
  </acceptance_criteria>
  <done>tools/ap.recipe.schema.json gains direct_interface_block + event_source_fallback $defs and three new property references (v0_2.direct_interface + channel_entry.event_log_regex + channel_entry.event_source_fallback); all 5 committed recipes lint clean against the extended schema; minimal valid + 12 broken recipe tests unchanged; Go-side legacy schemas not touched.</done>
</task>

<task type="auto">
  <name>Task 2: Add TestLintRealRecipes regression-guard test class to tools/tests/test_lint.py</name>
  <files>tools/tests/test_lint.py, tools/tests/conftest.py</files>
  <read_first>
    - tools/tests/test_lint.py (THE file being extended — read in full; the class hierarchy: TestLintPositive, TestLintApiVersion, TestLintAdditionalProperties, TestLintCrossFieldInvariants, TestLintBrokenRecipes; the new class lands at the end)
    - tools/tests/conftest.py (THE file being extended — locate the schema fixture line 30-34 and the minimal_valid_recipe fixture line 178-231; new `real_recipes` fixture lands alongside)
    - tools/run_recipe.py (lint_recipe signature line 120; behavior is `recipe + schema → list[str]`)
    - recipes/ directory (the 5 recipe YAMLs are the test inputs; the fixture returns their paths)
  </read_first>
  <action>
**Part A — Extend `tools/tests/conftest.py`.**

After the existing `broken_recipes_dir` fixture (line ~234-237), APPEND:

```python
@pytest.fixture
def real_recipes():
    """Paths to the 5 committed recipes — used by TestLintRealRecipes regression guard.

    Returns a list of (name, Path) tuples. Adding a new recipe to recipes/
    means adding it here too — explicit list keeps the test deterministic
    and surfaces the addition in code review.
    """
    repo_root = Path(__file__).resolve().parents[2]
    return [
        ("hermes",   repo_root / "recipes" / "hermes.yaml"),
        ("picoclaw", repo_root / "recipes" / "picoclaw.yaml"),
        ("nullclaw", repo_root / "recipes" / "nullclaw.yaml"),
        ("nanobot",  repo_root / "recipes" / "nanobot.yaml"),
        ("openclaw", repo_root / "recipes" / "openclaw.yaml"),
    ]
```

**Part B — Extend `tools/tests/test_lint.py`.**

After the existing `TestLintBrokenRecipes` class (the LAST class in the file, ending around line 106), APPEND:

```python
class TestLintRealRecipes:
    """Regression guard for Phase 22b-09 (Gap 3 closure).

    Asserts that every committed recipe in recipes/*.yaml lints clean
    against tools/ap.recipe.schema.json. Phase 22b-06 added direct_interface
    + event_log_regex to all 5 recipes; Phase 22b-08 (gap closure) carries
    event_source_fallback for nullclaw + openclaw. The schema gained
    direct_interface_block + event_source_fallback $defs (Phase 22b-09).

    A FAIL here means either:
      (a) the schema regressed (a future edit broke an existing field), OR
      (b) a recipe gained a new field the schema doesn't declare yet (the
          recipe needs additive schema work, NOT a relaxed `additionalProperties`).

    The 5 recipes are an explicit list (not a glob) so adding a new recipe
    forces a code review of this test. See conftest.py::real_recipes fixture.
    """

    @pytest.mark.parametrize("recipe_name,recipe_path", [
        ("hermes",   None),
        ("picoclaw", None),
        ("nullclaw", None),
        ("nanobot",  None),
        ("openclaw", None),
    ])
    def test_real_recipe_lints_clean(self, real_recipes, schema, recipe_name, recipe_path):
        # Resolve path from the fixture (parametrize ids are cosmetic; fixture
        # is the source of truth).
        match = next((p for n, p in real_recipes if n == recipe_name), None)
        assert match is not None, f"recipe {recipe_name!r} not in real_recipes fixture"
        recipe = _y.load(match.read_text())
        errors = lint_recipe(recipe, schema)
        assert errors == [], (
            f"Real recipe {recipe_name!r} should lint clean against tools/ap.recipe.schema.json "
            f"but produced {len(errors)} errors:\n  - " + "\n  - ".join(errors[:10])
        )

    def test_all_5_recipes_listed(self, real_recipes):
        """Sanity: catch accidental fixture truncation."""
        names = {n for n, _ in real_recipes}
        assert names == {"hermes", "picoclaw", "nullclaw", "nanobot", "openclaw"}, \
            f"real_recipes fixture missing or extra entries: {names}"

    def test_all_5_recipe_files_exist(self, real_recipes):
        """Sanity: catch accidental file deletion."""
        for name, path in real_recipes:
            assert path.exists(), f"recipe file missing: {name} at {path}"
```

(The existing test_lint.py imports `pytest`, `Path`, `_y` (= `YAML(typ='safe')`), and `lint_recipe` at the top; reuse those — do not re-import.)

Verify:
```bash
cd tools && pytest -x tests/test_lint.py::TestLintRealRecipes -v 2>&1 | tail -15
cd tools && pytest -x tests/test_lint.py -v 2>&1 | tail -10   # full lint suite, no regression
```
All 7 new tests (5 parametrized + 2 sanity) green; full suite green.
  </action>
  <verify>
    <automated>cd tools && pytest -x tests/test_lint.py::TestLintRealRecipes -v 2>&1 | grep -cE "PASSED" | awk '$1 >= 7 { exit 0 } { exit 1 }' && pytest -x tests/test_lint.py -q 2>&1 | tail -3 | grep -qE "passed"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "class TestLintRealRecipes" tools/tests/test_lint.py` returns `1`
    - `grep -c "def test_real_recipe_lints_clean" tools/tests/test_lint.py` returns `1`
    - `grep -c "def real_recipes" tools/tests/conftest.py` returns `1`
    - `cd tools && pytest -x tests/test_lint.py::TestLintRealRecipes -v 2>&1 | grep -cE "PASSED"` returns `>=7` (5 parametrized + 2 sanity)
    - `cd tools && pytest -x tests/test_lint.py -q 2>&1 | tail -3` shows ALL tests green (no regression in TestLintPositive/TestLintApiVersion/TestLintAdditionalProperties/TestLintCrossFieldInvariants/TestLintBrokenRecipes)
    - `cd tools && pytest tests/ -q 2>&1 | tail -5` shows no regression elsewhere (other test modules in tools/tests/ are untouched)
  </acceptance_criteria>
  <done>tools/tests/conftest.py gains real_recipes fixture; tools/tests/test_lint.py gains TestLintRealRecipes class with 5 parametrized cases + 2 sanity checks; all green; full lint suite green; the regression guard for Gap 3 lands.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Recipe YAML → JSON Schema validator | Both are static files in the repo; no untrusted input crosses this boundary at runtime. The schema is a compile-time artifact whose validator runs at lint time + at API boot (api_server.services.lint_service loads tools/ap.recipe.schema.json). |
| Lint test → real recipe files | tools/tests/test_lint.py reads recipes/*.yaml at test time; if a recipe is malformed YAML, ruamel.yaml raises during fixture eval — surfaces as test ERROR, not silent skip. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22b-09-01 | Tampering | Schema-relaxation drift via `additionalProperties: true` | mitigate | TestLintRealRecipes catches the drift early — if a recipe gains a field that the schema doesn't declare, the test FAILS rather than silently allowing it via a relaxed parent. The `real_recipes` fixture is an explicit list (not a glob) so adding a recipe requires updating the test, which forces a code review. |
| T-22b-09-02 | Information Disclosure | Schema documentation reveals internal implementation details | accept | The schema $def descriptions reference watcher_service.py file paths and line numbers. This is documentation, not a security boundary; the recipe schema is intended to be human-readable. Cross-references give future maintainers a path back to authoritative source. |
| T-22b-09-03 | Denial of Service | Pathological regex in event_log_regex.<kind> string value | accept | The schema validates that event_log_regex values are EITHER string OR null; it does NOT compile or execute the regex. The watcher_service compiles regexes at runtime — any bad regex would surface there as a watcher_failed log + a non-fatal Plan 22b-04 lifecycle event. ReDoS hardening is out of 22b scope. |
| T-22b-09-04 | Spoofing | Recipe declares a direct_interface.kind not in enum | mitigate | The oneOf with `kind: { const: "<value>" }` gates exhaustively to {docker_exec_cli, http_chat_completions}. A recipe declaring kind=execute_arbitrary_shell would be rejected at lint time — TestLintBrokenRecipes can be extended in a future plan to add this regression. |
</threat_model>

<verification>
- `python3 -c "import json; s=json.load(open('tools/ap.recipe.schema.json')); print(sorted(s['\$defs'].keys()))"` includes `direct_interface_block` and `event_source_fallback`
- All 5 recipes lint clean: the Task 1 verify automated command exits 0
- TestLintRealRecipes 7 tests green
- Full tools/tests/ suite (including the 12 broken-recipe negative tests + the minimal_valid positive test) green: `cd tools && pytest tests/ -q 2>&1 | tail -3`
- The api_server lint endpoint (which also loads tools/ap.recipe.schema.json per services/lint_service.py:80) is unaffected — no api_server tests touched in this plan; future api_server lint tests inherit the extended schema for free
- The Go-side legacy schemas at agents/schemas/ + api/internal/recipes/schema/ are explicitly NOT modified (verifiable by `git diff` returning empty for those paths)
- File size sanity: tools/ap.recipe.schema.json grew from 1356 → ~1480 lines
</verification>

<success_criteria>
1. tools/ap.recipe.schema.json $defs gains `direct_interface_block` + `event_source_fallback` definitions matching the 5 committed recipes' shapes verbatim
2. tools/ap.recipe.schema.json $defs.v0_2.properties gains `direct_interface` reference; $defs.channel_entry.properties gains `event_log_regex` + `event_source_fallback` references
3. All 5 committed recipes (hermes, picoclaw, nullclaw, nanobot, openclaw) lint clean against the extended schema
4. The 12 broken recipes in tools/tests/broken_recipes/ STILL fail lint (no regression in TestLintBrokenRecipes)
5. The minimal_valid_recipe fixture STILL passes lint (no regression in TestLintPositive)
6. New TestLintRealRecipes class with 5 parametrized + 2 sanity tests asserts the regression guard
7. Go-side legacy schemas at agents/schemas/ + api/internal/recipes/schema/ are untouched (separate tech-debt concern)
</success_criteria>

<output>
After completion, create `.planning/phases/22b-agent-event-stream/22b-09-SUMMARY.md` with:
- Exact diff stats for `tools/ap.recipe.schema.json` (lines added per change; total file size before/after)
- The 3 new $defs/property declarations summarized (direct_interface_block oneOf shape; event_source_fallback oneOf shape; event_log_regex propertyNames + value union)
- Per-recipe lint-error count BEFORE Task 1 (each was 2 errors per planning-session reproducer) AND AFTER Task 1 (each is 0 errors)
- Test counts: TestLintPositive (1 → 1 — unchanged), TestLintBrokenRecipes (12 parametrized cases — unchanged), TestLintRealRecipes (NEW: 5 parametrized + 2 sanity)
- Honest scope notes:
  - The user prompt pointed at `agents/schemas/recipe.schema.json` and `api/internal/recipes/schema/recipe.schema.json` as the files needing edits. Empirical verification (in this plan's read_first) showed those are pre-v0.2 legacy `ap.recipe/v1` schemas (257 lines, declare ID/runtime/launch/chat_io/isolation — fields that don't exist in v0.2 recipes). They are not referenced by `test_lint.py` (which uses `tools/ap.recipe.schema.json`) and not used by api_server's lint pipeline. Editing them would NOT close gap 3.
  - Tech-debt: those 257-line legacy schemas should EITHER be deleted (if the Go API no longer needs them) OR brought up to v0.2 (if a Go-side recipe loader still depends on them). Out of 22b scope; flag for a future cleanup phase.
- Cross-reference to Plans 22b-07 + 22b-08 (which also touch recipes/openclaw.yaml + tools/, but in different sections — no merge conflicts expected since this plan only touches schema + tests, not recipes themselves)
</output>
