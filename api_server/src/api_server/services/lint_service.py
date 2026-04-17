"""Lint service — wraps ``tools/run_recipe.py::lint_recipe`` verbatim.

Three responsibilities:

1. Enforce the 256 KiB body cap (``LINT_BODY_MAX_BYTES``) — V5 mitigation
   against YAML-bomb DoS. Oversize bodies raise ``LintBodyTooLargeError``
   BEFORE the YAML parser ever sees them.
2. Parse the body with a FRESH ``YAML()`` instance (ruamel ticket #367).
   The runner's module-level singleton is deliberately NOT reused here.
3. Delegate validation to the runner's ``lint_recipe`` function via
   ``importlib`` (the ``tools/`` directory is not on ``sys.path`` in the
   api_server layout, so we load the module by file path).

Exposes ``get_runner_schema()`` for the ``GET /v1/schemas/{version}``
route — loads the JSON Schema dict from ``tools/ap.recipe.schema.json``
via the runner's ``_load_schema`` helper.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ..models.errors import LintError, LintResponse

# 256 KiB hard cap — CONTEXT.md §Carried-forward decisions. Threat model
# T-19-03-01: a YAML bomb can blow up memory in microseconds; the cap
# rejects before we even attempt a parse.
LINT_BODY_MAX_BYTES = 262144


class LintBodyTooLargeError(ValueError):
    """Raised when request body exceeds ``LINT_BODY_MAX_BYTES``."""


def _runner_module_path() -> Path:
    """Resolve ``tools/run_recipe.py`` relative to this file.

    Layout: ``api_server/src/api_server/services/lint_service.py`` →
    ``parents[4]`` is the repo root. Raises if the runner is missing
    (should never happen in a well-formed checkout).
    """
    repo_root = Path(__file__).resolve().parents[4]
    runner_path = repo_root / "tools" / "run_recipe.py"
    if not runner_path.exists():
        raise RuntimeError(f"runner not found at {runner_path}")
    return runner_path


def _import_runner_module():
    """Import ``run_recipe`` by file path + cache in ``sys.modules``.

    ``tools/`` is not on ``sys.path`` in the api_server layout, so we use
    ``importlib.util.spec_from_file_location`` to load it by path. Cached
    in ``sys.modules`` so subsequent calls return the same module object
    (required for the schema + lint helpers to share state).
    """
    mod_name = "run_recipe"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    runner_path = _runner_module_path()
    spec = importlib.util.spec_from_file_location(mod_name, runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to build import spec for {runner_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _lint_recipe_fn():
    """Return the runner's ``lint_recipe`` function."""
    return _import_runner_module().lint_recipe


def get_runner_schema() -> dict:
    """Return the JSON Schema dict from ``tools/ap.recipe.schema.json``.

    Shared with ``routes/schemas.py`` so both paths go through the runner's
    canonical ``_load_schema`` helper — no schema-file-path duplication.
    """
    return _import_runner_module()._load_schema()


def _parse_error_to_lint(err: YAMLError) -> LintError:
    """Convert a ruamel parse error into a ``LintError``.

    ruamel error messages are multi-line with context; keep the first line
    and cap at 500 chars so a pathological input can't blow up the error
    body.
    """
    return LintError(path="(yaml)", message=str(err).splitlines()[0][:500])


def lint_yaml_bytes(body: bytes) -> LintResponse:
    """Lint a YAML body against the recipe schema.

    Flow:

    1. Size-cap guard (raises ``LintBodyTooLargeError`` → 413 in the route).
    2. Fresh ``YAML(typ="rt")`` parse. Parse errors become a single
       ``LintError`` with ``valid=False`` (200 response, not 400 — parse
       failures are lint failures, same category).
    3. Non-mapping payloads (lists, scalars) short-circuit to a single
       ``(root)`` error.
    4. Delegate to ``run_recipe.lint_recipe``. Each returned message has
       shape ``"path: text"``; split on the first ``": "`` to populate
       the ``LintError`` fields.
    """
    if len(body) > LINT_BODY_MAX_BYTES:
        raise LintBodyTooLargeError(
            f"request body {len(body)}B exceeds {LINT_BODY_MAX_BYTES}B cap"
        )
    yaml = YAML(typ="rt")  # fresh per call — S-2 pattern (ruamel #367)
    try:
        parsed = yaml.load(body)
    except YAMLError as e:
        return LintResponse(valid=False, errors=[_parse_error_to_lint(e)])

    if not isinstance(parsed, dict):
        return LintResponse(
            valid=False,
            errors=[LintError(path="(root)", message="recipe must be a YAML mapping")],
        )

    msgs = _lint_recipe_fn()(parsed)
    errors: list[LintError] = []
    for msg in msgs:
        if ": " in msg:
            path, text = msg.split(": ", 1)
        else:
            path, text = "(root)", msg
        errors.append(LintError(path=path, message=text))
    return LintResponse(valid=(len(errors) == 0), errors=errors)
