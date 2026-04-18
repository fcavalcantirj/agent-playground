# Spike 09 — `_import_run_recipe_module` parents[4] in api container

**Date:** 2026-04-18
**Plan affected:** 22-04 (runner_bridge wrappers)
**Verdict:** PASS

## Probe

Inside `deploy-api_server-1`:
```python
from pathlib import Path
p = Path('/app/api_server/src/api_server/services/runner_bridge.py')
print(p.resolve().parents[4])              # → /app
print((p.resolve().parents[4] / 'tools' / 'run_recipe.py').exists())  # → True
```

## Actual output
```
parents[4]: /app
tools/run_recipe.py exists?: True
```

## Verdict: PASS

Plan 22-04's `_import_run_recipe_module` using `parents[4]` resolves to `/app` in the api_server image, and `tools/run_recipe.py` exists there. No plan delta.
