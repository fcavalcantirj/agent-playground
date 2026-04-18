# Phase 22 — Deferred Items

Out-of-scope items discovered during plan execution. DO NOT fix in this plan.

## Plan 22-01 (executor 2026-04-18)

### test_roundtrip.py::test_yaml_roundtrip_is_lossless[picoclaw] — pre-existing
- **Pre-existing** at plan-22-01 start (verified via `git stash` + test run on HEAD=2ea0118).
- Unicode character `👋` (U+1F44B) in `channels.telegram.verified_cells[0].reply_sample` round-trips as `\U0001F44B` through ruamel's rt loader.
- Out of plan-22-01 scope (`files_modified` does not include `picoclaw.yaml` beyond the apiVersion bump nor `tools/run_recipe.py`'s YAML dumper).
- Likely fix: add `allow_unicode=True` to the dumper OR normalize the reply_sample string. Defer to a follow-up.
