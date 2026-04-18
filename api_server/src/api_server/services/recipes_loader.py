"""Recipe YAML loading with PER-CALL YAML() instances (ruamel ticket #367).

Server-consumed paths MUST use a fresh ``YAML()`` per parse. The runner
(``tools/run_recipe.py``) keeps a module-level singleton ``_yaml`` — that
singleton is not thread-safe under FastAPI's async concurrency (ruamel
ticket #367 documents race-condition corruption). The api_server is
always a concurrent consumer, so the singleton is banned here.

Public API:

- ``load_recipe(path)`` — parse one file into a dict.
- ``load_all_recipes(dir_path)`` — parse every ``*.yaml`` in a directory,
  keyed by ``recipe["name"]``. Raises on missing name or duplicate name.
- ``to_summary(recipe)`` — project a recipe dict into ``RecipeSummary``
  with field-name translation (``source.repo`` → ``source_repo`` etc).
"""
from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from ..models.recipes import RecipeSummary


def _fresh_yaml() -> YAML:
    """Build a fresh ``YAML()`` instance.

    CRITICAL: never share a ``YAML()`` across coroutines. Ruamel ticket
    #367 documents race-condition corruption when a single instance is
    used from multiple threads / tasks in parallel. Plan 19-02 wires
    server paths to this helper; ``tools/run_recipe.py``'s CLI path keeps
    its module singleton (CLI is single-threaded, safe).

    The indentation knobs mirror the runner's singleton so round-tripped
    output is structurally identical when a downstream plan writes a
    recipe back (none does in 19-03 — read-only).
    """
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def load_recipe(path: Path) -> dict:
    """Parse a single recipe YAML file into a dict."""
    return _fresh_yaml().load(path.read_text())


def load_all_recipes(dir_path: Path) -> dict[str, dict]:
    """Load every ``*.yaml`` file in ``dir_path`` into a name-keyed dict.

    Raises ``ValueError`` if any file is missing the ``name`` field or if
    two files share a name. Called at app startup; app boot refuses to
    complete on malformed or duplicate recipes (fail-loud).
    """
    result: dict[str, dict] = {}
    for yaml_path in sorted(dir_path.glob("*.yaml")):
        recipe = load_recipe(yaml_path)
        if not isinstance(recipe, dict):
            raise ValueError(
                f"{yaml_path}: recipe must parse to a mapping, got {type(recipe).__name__}"
            )
        name = recipe.get("name")
        if not name:
            raise ValueError(f"{yaml_path}: recipe missing 'name' field")
        if name in result:
            raise ValueError(f"duplicate recipe name {name!r} in {yaml_path}")
        result[name] = recipe
    return result


def to_summary(recipe: dict) -> RecipeSummary:
    """Project a recipe dict into a ``RecipeSummary``.

    Safe ``.get()`` access throughout — any missing sub-dict yields a
    ``None`` on the summary field rather than raising. Uses the canonical
    ``ap.recipe/v0.1`` field names (``source.repo``, ``runtime.provider``,
    ``smoke.pass_if``, ``metadata.license``, ``metadata.maintainer``).

    ``smoke.pass_if`` may be either a string (``"response_contains_name"``)
    or a dict keyed by verb (``{"response_contains_string": "..."}``). The
    summary returns the string name of the verb in both cases so the
    surface is stable.
    """
    source = recipe.get("source") or {}
    runtime = recipe.get("runtime") or {}
    smoke = recipe.get("smoke") or {}
    metadata = recipe.get("metadata") or {}

    pass_if_val = smoke.get("pass_if")
    if isinstance(pass_if_val, dict):
        # Schema v0.1 only has the bare string form, but v0.1.1 + future
        # v0.2 additions may expose verb-keyed objects. Keep the summary
        # field a string either way.
        pass_if_val = next(iter(pass_if_val.keys()), None)
    elif pass_if_val is not None:
        pass_if_val = str(pass_if_val)

    build = recipe.get("build") or {}
    observed = build.get("observed") or {}

    verified_cells = smoke.get("verified_cells") or []
    verified_models: list[str] = []
    for cell in verified_cells:
        if not isinstance(cell, dict):
            continue
        if cell.get("verdict") != "PASS":
            continue
        m = cell.get("model")
        if isinstance(m, str) and m and m not in verified_models:
            verified_models.append(m)

    # v0.2 channels metadata — added in Phase 22 plan 22-01. Surfaces the
    # recipe's persistent + channels blocks so the frontend can gate
    # deploy-form Step 2.5 without a second detail fetch.
    persistent_block = recipe.get("persistent") or {}
    persistent_mode_available = bool(persistent_block)

    channels_raw = recipe.get("channels") or {}
    # isinstance(dict) is defensive — ruamel's CommentedMap is a dict subclass
    # so this still accepts round-tripped recipes.
    channels_supported: list[str] = (
        list(channels_raw.keys()) if isinstance(channels_raw, dict) else []
    )

    channel_provider_compat: dict[str, dict[str, list[str]]] | None = None
    if isinstance(channels_raw, dict):
        compat_map: dict[str, dict[str, list[str]]] = {}
        for cid, cinfo in channels_raw.items():
            if not isinstance(cinfo, dict):
                continue
            pc = cinfo.get("provider_compat")
            if not isinstance(pc, dict):
                continue
            # Normalize to plain list[str] in case ruamel returns
            # CommentedSeq. Clamp to the two known keys we expose on the API.
            supported = [str(s) for s in (pc.get("supported") or [])]
            deferred = [str(s) for s in (pc.get("deferred") or [])]
            compat_map[str(cid)] = {"supported": supported, "deferred": deferred}
        if compat_map:
            channel_provider_compat = compat_map

    # maintainer in v0.1.1 is a {name, url?} object. RecipeSummary.maintainer
    # is typed ``str | None`` on the public wire (per the pre-existing
    # docstring: maps metadata.maintainer). Project to the name when present
    # so the Pydantic validator accepts the value; detail response keeps the
    # full object via the dict passthrough.
    maintainer_raw = metadata.get("maintainer")
    if isinstance(maintainer_raw, dict):
        maintainer_val = maintainer_raw.get("name")
        maintainer_val = str(maintainer_val) if maintainer_val is not None else None
    elif maintainer_raw is None:
        maintainer_val = None
    else:
        maintainer_val = str(maintainer_raw)

    return RecipeSummary(
        name=recipe["name"],
        apiVersion=recipe.get("apiVersion", "ap.recipe/v0.1"),
        display_name=recipe.get("display_name"),
        description=str(recipe["description"]).strip() if recipe.get("description") else None,
        upstream_version=str(source["upstream_version"]).strip() if source.get("upstream_version") else None,
        image_size_gb=float(observed["image_size_gb"]) if observed.get("image_size_gb") is not None else None,
        expected_runtime_seconds=float(observed["wall_time_s"]) if observed.get("wall_time_s") is not None else None,
        source_repo=source.get("repo"),
        source_ref=str(source.get("ref")) if source.get("ref") is not None else None,
        provider=runtime.get("provider"),
        pass_if=pass_if_val,
        license=metadata.get("license"),
        maintainer=maintainer_val,
        persistent_mode_available=persistent_mode_available,
        channels_supported=channels_supported,
        channel_provider_compat=channel_provider_compat,
        verified_models=verified_models,
    )
