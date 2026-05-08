# Phase 31 — Deferred Items (out of plan scope)

Items discovered during execution that are NOT caused by Phase 31 plan changes. Logged here per the executor SCOPE BOUNDARY rule.

## Plan 31-02 (auth rate-limit)

### Pre-existing failures in non-integration suite (confirmed unrelated)

Discovered while running `pytest -q -m "not api_integration and not e2e_money_path" --ignore=tests/spikes` for regression check on Plan 31-02:

1. `tests/recipes/test_phase30_via_proxy_invariant.py::test_all_recipes_flipped_count` — `expected 7 recipes with via_proxy: true, got 8`. New recipe added since the invariant baseline; no rate-limit code involved.
2. `tests/test_run_recipe_telegram_invariant.py::test_baseline_capture` — `RuntimeError: recipe 'openclaw' runtime.via_proxy=true requires channel='inapp' with INAPP_AUTH_TOKEN in activation_substitutions` (raised by `tools/run_recipe.py:1311`).
3. `tests/test_run_recipe_telegram_invariant.py::test_telegram_unchanged` — same root cause as #2.
4. `tests/test_run_recipe_telegram_invariant.py::test_telegram_unchanged_when_substitutions_none` — same root cause as #2.

All 4 failures live in recipe-runner code paths, not rate-limit middleware. Confirmed at HEAD before Plan 31-02's edits landed (smoke run on `f775f32` with no rate_limit changes touching them).

**Disposition:** out of Plan 31-02 scope. Owner of recipes/run_recipe.py invariants should re-baseline.
