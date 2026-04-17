"""Bridge between FastAPI handler and ``tools/run_recipe.py::run_cell``.

Implements RESEARCH.md **Pattern 2** (per-image-tag ``asyncio.Lock`` —
Pitfall 1 safe via ``app.state.locks_mutex`` — + global
``asyncio.Semaphore(N)`` + ``asyncio.to_thread`` wrap).

Why every primitive:

- **``locks_mutex``** guards mutations to the ``image_tag_locks`` dict
  (Pitfall 1: two coroutines racing on ``dict.setdefault`` can end up
  holding different Lock objects for the same key; the mutex makes the
  lookup-or-create pair atomic).
- **Per-tag ``Lock``** serializes BUILDS of the same image tag (two
  concurrent requests for the same recipe share the lock → ``ensure_image``
  runs once, second request waits, pulls the cached image).
- **Global ``Semaphore(N)``** bounds total concurrent ``run_cell`` calls
  across ALL tags (keeps docker from exploding when 100 different recipes
  are requested at once).
- **``asyncio.to_thread``** is MANDATORY — ``run_cell`` is sync and blocks
  10-200s; calling it directly from an ``async def`` stalls the entire
  event loop.

BYOK invariant: ``api_key_val`` flows as a kwarg into ``run_cell`` which
uses the ``--env-file`` code path. This module NEVER logs the key and
NEVER persists it. See ``routes/runs.py`` for the full data-side
enforcement; see Plan 19-06 for the log-side (``_redact_api_key`` widening
+ AccessLogMiddleware allowlist).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any


def _import_run_cell():
    """Import ``run_recipe.run_cell`` by file path + cache in ``sys.modules``.

    ``tools/`` is NOT on ``sys.path`` in the api_server layout, so we load
    by file path (same pattern as ``services/lint_service.py``). Cached in
    ``sys.modules["run_recipe"]`` so subsequent calls share the module
    object — important because ``lint_service`` may have already loaded it
    and both paths need the same ``Category`` definition in memory.
    """
    mod = sys.modules.get("run_recipe")
    if mod is not None and hasattr(mod, "run_cell"):
        return mod.run_cell
    repo_root = Path(__file__).resolve().parents[4]
    runner_path = repo_root / "tools" / "run_recipe.py"
    if not runner_path.exists():
        raise RuntimeError(f"runner not found at {runner_path}")
    spec = importlib.util.spec_from_file_location("run_recipe", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to build import spec for {runner_path}")
    new_mod = importlib.util.module_from_spec(spec)
    sys.modules["run_recipe"] = new_mod
    spec.loader.exec_module(new_mod)
    return new_mod.run_cell


async def _get_tag_lock(app_state, image_tag: str) -> asyncio.Lock:
    """Return (creating if needed) the ``asyncio.Lock`` for ``image_tag``.

    Pitfall 1 safe: mutations to ``image_tag_locks`` happen under
    ``locks_mutex`` so a race between two coroutines can't leave them
    holding different Lock objects for the same tag.
    """
    async with app_state.locks_mutex:
        lock = app_state.image_tag_locks.get(image_tag)
        if lock is None:
            lock = asyncio.Lock()
            app_state.image_tag_locks[image_tag] = lock
    return lock


async def execute_run(
    app_state,
    recipe: dict,
    *,
    prompt: str,
    model: str,
    api_key_var: str,
    api_key_val: str,
) -> dict[str, Any]:
    """Execute ``run_cell`` with Pattern 2 concurrency primitives.

    Returns the ``details`` dict half of ``run_cell``'s ``(Verdict, dict)``
    tuple. The tuple Verdict is not consumed — the dict carries everything
    the response model needs (``verdict`` string, ``category``, etc.).

    The image tag convention ``ap-recipe-{name}`` matches
    ``tools/run_recipe.py`` line 1024 (``image_tag`` default derivation);
    changing either side without the other would cause Docker tag misses
    and redundant builds.
    """
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
    # ``run_cell`` returns ``(Verdict, details_dict)``; test fixtures
    # (``mock_run_cell`` in conftest) short-circuit with just the details
    # dict. Handle both shapes so tests don't have to fabricate a Verdict.
    if isinstance(result, tuple):
        _verdict, details = result
    else:
        details = result
    return details
