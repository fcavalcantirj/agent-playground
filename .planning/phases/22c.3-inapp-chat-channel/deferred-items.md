# Deferred items — Phase 22c.3

Items discovered during execution that are out of scope for the
current plan + log here for a future task to pick up.

## From Plan 22c.3-08

### Pre-existing test_idempotency.py failure (not caused by Plan 22c.3-08)

`tests/test_idempotency.py::test_same_key_different_users_isolated`
fails on `main` with:

```
asyncpg.exceptions.NotNullViolationError: null value in column "name"
of relation "agent_instances" violates not-null constraint
```

The test seeds an `agent_instances` row directly without setting `name`
— but `agent_instances.name` was made NOT NULL by `alembic 002`
(`alembic/versions/002_agent_name_personality.py`). Verified pre-existing
by `git stash` + run on clean main: the failure persists.

Fix: add `name='test-agent'` to the test's INSERT. The 3 other tests in
the file (`test_same_key_returns_cache`, `test_body_mismatch_returns_422`,
`test_expired_key_re_runs`) all pass on the post-22c.3-08 middleware
and do NOT touch this code path.

Out of scope for Plan 22c.3-08 (scope: chat path additions only).

## From Plan 22c.3-13 (zeroclaw)

### Pre-existing recipe-schema lint failure across all inapp-extended recipes

`python3 tools/run_recipe.py --lint-all` reports schema FAIL for hermes,
nanobot, openclaw, and zeroclaw — and would for nullclaw if its inapp
block used the same v3 shape. Root cause: `tools/ap.recipe.schema.json`
v0.2 hard-codes a `channels.telegram`-only shape with these constraints
that conflict with the new inapp block:

  - `channels.inapp` is unknown (additionalProperties: false at channels)
  - `response_routing` enum lacks `per_session` / `per_session_id`
  - `multi_user_model` enum lacks `per_session_id`
  - inapp-only required fields like `transport` / `port` / `endpoint` /
    `contract` / `persistent_argv_override` / `activation_env` are
    rejected by the strict telegram channel shape

This is a Rule 4 architectural item (schema extension); the planning
team chose to ship inapp recipes as forward-additive YAML and let the
schema catch up in a future format-vN consolidation phase. Plans 10/11/12
shipped the same shape and the live api_server (which uses
`recipes_loader.load_all_recipes` — a permissive YAML loader, NOT
schema-validated) accepts the recipes verbatim, surfaces them via
`GET /v1/recipes/<name>`, and the InappRecipeIndex parser extracts the
required fields cleanly.

Work to do whenever the schema phase lands:
  1. Extend `tools/ap.recipe.schema.json` with a `channels.inapp` branch
     mirroring the field shape used by all 5 inapp recipes today
  2. Add `per_session` / `per_session_id` to `response_routing` enum
  3. Add `per_session_id` to `multi_user_model` enum
  4. Re-run `python3 tools/run_recipe.py --lint-all` — must PASS for all
     5 inapp recipes

Out of scope for Plan 22c.3-13 (recipe authoring only; schema work was
not in the plan must_haves and would block 4 plans retroactively).

### Plan verify cmd #3 references non-existent --list-recipes flag

Plan 22c.3-13 <verify> step 3 reads:

```bash
python3 tools/run_recipe.py --list-recipes 2>&1 | grep -q zeroclaw
```

`tools/run_recipe.py` has no `--list-recipes` flag — confirmed by reading
its argparse setup (lines 1470-1579). Closest existing flag is `--lint-all`
which iterates `recipes/*.yaml` but reports lint verdicts (not a name list).

Substituted equivalent: `curl -s http://localhost:8000/v1/recipes` against
the live api_server returns the recipe registry, and zeroclaw appears
with `channels_supported=['inapp']` — proves both load-side parse success
AND that the api_server registry sees the new recipe. Same load-bearing
property the original verify intended to assert (runner accepts the file
shape).

Rule 3 deviation; documented in 22c.3-13 SUMMARY.

## From Plan 22c.3-15 (SC-03 e2e gate)

### Production runner-side wiring (the 5-plan-flagged gap)

Plans 22c.3-{10,11,12,13,14} each flagged this in their SUMMARYs.
Plan 22c.3-15 took Route B (test-fixture-side replication) per the
plan's `key_links` line 60. The production runner-side wiring is now
explicitly filed for a follow-up plan:

1. `tools/run_recipe.py::run_cell_persistent` — extend the function
   signature with a `channel_id` parameter and read
   `recipe.channels.inapp.persistent_argv_override` when
   `channel_id == "inapp"`. Read `channels.inapp.activation_env` and
   merge it into the env-file. Render `${INAPP_AUTH_TOKEN}` /
   `${INAPP_PROVIDER_KEY}` / `{agent_name}` / `{agent_url}` /
   `${MODEL}` placeholders before docker-run.
2. `api_server/src/api_server/routes/agent_lifecycle.py::start_persistent`
   — when `body.channel == "inapp"`, mint a per-session opaque UUID
   `inapp_auth_token`, pass it to `execute_persistent_start` so
   `run_cell_persistent` can substitute the placeholder. After
   `write_agent_container_running`, `UPDATE agent_containers SET
   inapp_auth_token = $1 WHERE id = $2`.
3. `api_server/src/api_server/main.py` lifespan — wire
   `app.state.recipe_index = InappRecipeIndex(recipes_dir,
   docker.from_env(), settings.docker_network_name)` at boot. The
   dispatcher reads `state.recipe_index` (already coded that way in
   Plan 22c.3-05); without this wiring `_handle_row` would
   AttributeError on first call in production.
4. Reference implementation: the substitution + minting discipline is
   already encoded in `api_server/tests/e2e/conftest.py::_factory`.
   Copy the substitution dict + render_placeholders + INAPP_AUTH_TOKEN
   minting verbatim into the production handler.

Estimate: ~150 lines across the 3 files. Single follow-up plan.

### Dispatcher fallback to row['model'] when contract_model_name is "agent"

Surfaced during Plan 22c.3-15 nanobot cell. The dispatcher's
openai_compat adapter sends `inapp.contract_model_name or "agent"` as
the `model` field. Some bots (nanobot) only accept the literal
configured model id and 400 on the placeholder. Recommended dispatcher
patch:

```python
case "openai_compat":
    body: dict[str, Any] = {
        "model": (
            inapp.contract_model_name
            if inapp.contract_model_name and inapp.contract_model_name != "agent"
            else (row.get("model") if isinstance(row, dict) else (row["model"] if "model" in row.keys() else "agent"))
        ),
        ...
```

This requires `fetch_pending_for_dispatch` to also return
`agent_instances.model` in its JOIN. The Plan 22c.3-15 test fixture
substitutes the model via the recipe_index wrapper instead.

### oauth_sessions schema variance defensiveness

The `oauth_user_with_openrouter_key` fixture in
`api_server/tests/e2e/conftest.py` defensively try/except's the
`INSERT INTO oauth_sessions` because the schema's column shape may
have evolved across phases (provider, access_token, etc.). Plan 22c
(OAuth) landed earlier; the schema reference should be re-verified.
The gate currently injects the same key as env into the recipe
container, so the OAuth-row-only path is documented but not
exclusively exercised. Future hardening: ensure the recipe container's
`OPENROUTER_API_KEY` is sourced *only* from the oauth_sessions row
once the production runner-side wiring lands (item 1 above).

### Per-recipe model id format normalization

openclaw's anthropic plugin only accepts `anthropic/claude-haiku-4-5`
(dash); other recipes accept `anthropic/claude-haiku-4.5` (dot).
Currently the matrix test selects per-recipe via a small ternary; a
robust solution is either (a) a recipe-level field
`channels.inapp.model_id_format: "dashed"` or (b) the dispatcher
normalizes when forwarding. Tracked for future schema work.
