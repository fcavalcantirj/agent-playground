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


def _import_run_recipe_module():
    """Import and cache the run_recipe module (full module, not just one callable).

    All persistent-mode runner functions (run_cell, run_cell_persistent,
    stop_persistent, exec_in_persistent) live in the same file. Caching the
    module object in ``sys.modules["run_recipe"]`` keeps ``Verdict`` /
    ``Category`` identity stable across callers (``lint_service`` +
    ``execute_run`` + ``execute_persistent_*`` all share one module object).

    ``tools/`` is NOT on ``sys.path`` in the api_server layout, so we load
    by file path (same pattern as ``services/lint_service.py``).

    Refactored from Plan 19's ``_import_run_cell`` which returned just the
    single callable. Plan 22-04 callers need siblings in the same module —
    ``run_cell_persistent`` (Plan 22-03), ``stop_persistent``,
    ``exec_in_persistent`` — so this returns the whole module and callers
    attribute-access what they need.
    """
    mod = sys.modules.get("run_recipe")
    if mod is not None and hasattr(mod, "run_cell"):
        return mod
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
    return new_mod


def _import_run_cell():
    """Back-compat shim used by ``execute_run``.

    Preserved so Plan-19-era callers and tests continue to work unchanged
    while Plan 22-04 adds the persistent-mode bridge functions that need
    the whole module.
    """
    return _import_run_recipe_module().run_cell


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


async def execute_persistent_start(
    app_state,
    recipe: dict,
    *,
    model: str,
    api_key_var: str,
    api_key_val: str,
    channel_id: str,
    channel_creds: dict[str, str],
    run_id: str,
    boot_timeout_s: int = 180,
) -> dict[str, Any]:
    """Spawn a persistent container using the same concurrency scaffold as ``execute_run``.

    Per-tag Lock serializes image builds (first call on a cold cache builds/
    pulls; subsequent concurrent starts for the same recipe share the cached
    image). Global Semaphore bounds total in-flight boots across all recipes.

    Returns the details dict half of ``run_cell_persistent``'s
    ``(Verdict, dict)`` return. On non-PASS verdict the caller (route handler
    in Plan 22-05) decides whether to raise or record the failure; this
    function returns the dict unconditionally with ``verdict`` / ``category``
    / ``detail`` string fields attached so the route layer can branch without
    introspecting the runner's bespoke ``Verdict`` namedtuple.

    Concurrency notes:
    - ``tag_lock`` is held for the full boot duration (~10-120s depending on
      recipe). Intentional: concurrent ``/start`` requests for the SAME
      recipe serialize on the image cache. DIFFERENT-recipe starts run in
      parallel, bounded only by the global semaphore.
    - ``asyncio.to_thread`` is mandatory — ``run_cell_persistent`` is a sync
      function that blocks on ``docker run -d`` + log polling; calling
      directly from an ``async def`` stalls the event loop.

    BYOK invariant: neither ``api_key_val`` nor ``channel_creds`` are logged
    or persisted by this module. Plan 22-05's route layer is responsible for
    redacting exceptions before any persistence touch.
    """
    mod = _import_run_recipe_module()
    image_tag = f"ap-recipe-{recipe['name']}"   # matches tools/run_recipe.py convention
    tag_lock = await _get_tag_lock(app_state, image_tag)
    async with tag_lock:                         # serialize SAME-tag builds
        async with app_state.run_semaphore:      # bound total concurrent boots
            result = await asyncio.to_thread(
                mod.run_cell_persistent,
                recipe,
                image_tag=image_tag,
                model=model,
                api_key_var=api_key_var,
                api_key_val=api_key_val,
                channel_id=channel_id,
                channel_creds=channel_creds,
                run_id=run_id,
                quiet=True,
                boot_timeout_s=boot_timeout_s,
            )
    # Same tuple/dict shape handling as ``execute_run`` — tests may
    # short-circuit with just the details dict (no Verdict namedtuple).
    if isinstance(result, tuple):
        verdict, details = result
        details = dict(details)
        # Attach string-typed fields so the route layer can branch without
        # importing the runner's Verdict / Category classes.
        details["verdict"] = getattr(verdict, "verdict", None) or getattr(verdict, "name", None) or str(verdict)
        cat = getattr(verdict, "category", None)
        if cat is not None:
            details["category"] = getattr(cat, "value", None) or getattr(cat, "name", None) or str(cat)
        if "detail" not in details:
            details["detail"] = getattr(verdict, "detail", "")
    else:
        details = dict(result)
        details.setdefault("verdict", "PASS")
    return details


async def execute_persistent_stop(
    container_id: str,
    *,
    graceful_shutdown_s: int = 5,
    sigterm_handled: bool = True,
    recipe_name: str | None = None,
    data_dir: str | None = None,
) -> dict[str, Any]:
    """Gracefully stop a persistent container.

    Wraps Plan 22-03's ``stop_persistent`` in ``asyncio.to_thread`` so the
    sync subprocess calls (``docker kill``, ``docker inspect``, ``docker
    rm``) don't stall the event loop.

    Concurrency:
    - NO image tag-lock — stop doesn't touch images.
    - NO semaphore — stop is cheap (<< 1 run budget) and concurrent-safe.

    Per-recipe ``sigterm_handled``: when ``False`` (nanobot's gateway
    ignores SIGTERM entirely per spike-07), ``stop_persistent`` skips the
    SIGTERM + poll phase and force-rms immediately, logging a WARNING
    (not error) with ``recipe_name``. The caller surfaces
    ``force_killed: bool`` through ``AgentStopResponse``.

    Plan 22-03's ``stop_persistent`` is expected to return
    ``(Verdict, details)`` — both shapes handled for test fixtures.
    """
    mod = _import_run_recipe_module()
    result = await asyncio.to_thread(
        mod.stop_persistent,
        container_id,
        graceful_shutdown_s=graceful_shutdown_s,
        sigterm_handled=sigterm_handled,
        recipe_name=recipe_name,
        data_dir=data_dir,
        quiet=True,
    )
    if isinstance(result, tuple):
        verdict, details = result
        details = dict(details)
        details["verdict"] = getattr(verdict, "verdict", None) or getattr(verdict, "name", None) or str(verdict)
    else:
        details = dict(result)
        details.setdefault("verdict", "PASS")
    details.setdefault("force_killed", False)
    return details


async def execute_persistent_status(
    container_id: str,
    *,
    recipe_health_check: dict | None = None,
    log_tail_lines: int = 50,
) -> dict[str, Any]:
    """Return current state of a persistent container.

    Response shape: ``{running, exit_code, log_tail, http_code?, ready?}``.
    Read-only probe — no image tag-lock, no global semaphore. Dual-branch
    per spike-11:

    - ``recipe_health_check.kind == "process_alive"`` (or omitted): probe
      via ``docker inspect -f '{{.State.Running}},{{.State.ExitCode}}'``
      only.
    - ``recipe_health_check.kind == "http"``: additionally run a
      ``docker exec <cid> sh -c 'curl ... || wget ...'`` probe against the
      container-local health port. The curl/wget fallback is mandatory
      because image toolchains vary — hermes has neither curl nor wget
      (so it's always process_alive), other images have one or both.

    Factored here (not as a new ``run_recipe`` function) because the probe
    logic is API-layer concern, not runner primitive — adding it to
    ``tools/run_recipe.py`` would be noise for a ~30-line self-contained
    probe. ``asyncio.to_thread`` is still mandatory because even a "fast"
    ``docker inspect`` can block if the daemon is slow.

    Returns ``running=False`` cleanly for non-existent containers (the
    inspect exits non-zero; we treat that as "not running" without
    raising, so ``GET /v1/agents/:id/status`` always responds 200).
    """
    def _probe() -> dict[str, Any]:
        import subprocess as _sp  # local import — not needed by the rest of the module
        running = False
        exit_code: int | None = None
        http_code: int | None = None
        ready: bool | None = None
        inspect = _sp.run(
            ["docker", "inspect", "-f", "{{.State.Running}},{{.State.ExitCode}}", container_id],
            timeout=5, capture_output=True, text=True, check=False,
        )
        if inspect.returncode == 0:
            parts = (inspect.stdout or "").strip().split(",", 1)
            running = (parts[0].strip() == "true")
            try:
                exit_code = int(parts[1].strip()) if len(parts) > 1 else None
            except ValueError:
                exit_code = None

        # G5 dual-branch: http probe only if recipe asks for it AND container running
        if running and recipe_health_check and recipe_health_check.get("kind") == "http":
            port = recipe_health_check.get("port")
            path = recipe_health_check.get("path", "/")
            # curl || wget fallback — see spike-11 for image toolchain variance.
            # Double {{ }} escapes the shell format spec past Python's f-string.
            probe_cmd = (
                f"curl -s -o /dev/null -w '%{{http_code}}' "
                f"http://127.0.0.1:{port}{path} 2>/dev/null "
                f"|| wget -qO /dev/null --server-response "
                f"http://127.0.0.1:{port}{path} 2>&1 | grep -oE 'HTTP/[0-9.]+ [0-9]+' "
                f"| grep -oE '[0-9]+$' | head -1"
            )
            probe = _sp.run(
                ["docker", "exec", container_id, "sh", "-c", probe_cmd],
                timeout=5, capture_output=True, text=True, check=False,
            )
            out = (probe.stdout or "").strip()
            if out.isdigit():
                http_code = int(out)
                ready = http_code == 200

        logs = _sp.run(
            ["docker", "logs", "--tail", str(log_tail_lines), container_id],
            timeout=10, capture_output=True, text=True, check=False,
        )
        log_tail = ((logs.stdout or "") + "\n" + (logs.stderr or "")).strip().splitlines()[-log_tail_lines:]
        return {
            "running": running,
            "exit_code": exit_code,
            "log_tail": log_tail,
            "http_code": http_code,
            "ready": ready,
        }
    return await asyncio.to_thread(_probe)


async def execute_persistent_exec(
    app_state,
    container_id: str,
    argv: list[str],
    *,
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Run a command inside a persistent container (openclaw pairing approve, etc.).

    Uses the global semaphore to avoid flooding the docker daemon with
    concurrent ``docker exec`` calls across unrelated containers. NO image
    tag-lock — exec doesn't touch images.

    First caller is POST ``/v1/agents/:id/channels/:cid/pair`` with
    argv ``["openclaw", "pairing", "approve", "telegram", "<CODE>"]`` —
    sub-second in practice but the semaphore bound protects the daemon
    against concurrent-exec storms.
    """
    mod = _import_run_recipe_module()
    async with app_state.run_semaphore:
        result = await asyncio.to_thread(
            mod.exec_in_persistent,
            container_id,
            argv,
            timeout_s=timeout_s,
        )
    if isinstance(result, tuple):
        verdict, details = result
        details = dict(details)
        details["verdict"] = getattr(verdict, "verdict", None) or getattr(verdict, "name", None) or str(verdict)
    else:
        details = dict(result)
        details.setdefault("verdict", "PASS")
    return details
