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
