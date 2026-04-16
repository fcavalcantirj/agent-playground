#!/usr/bin/env python3
"""Agent Playground recipe runner — ap.recipe/v0.1.

Loads a recipe, produces the container image (upstream_dockerfile build or
image_pull), runs the agent against a single prompt/model cell (or sweeps
every verified cell), applies the stdout filter, evaluates the smoke
pass_if rule, and reports a verdict.

Contract: see docs/RECIPE-SCHEMA.md.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_yaml = YAML(typ="rt")
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def _represent_none(dumper, _data):
    # Emit `null` explicitly instead of a bare empty value so round-trip
    # write-back does not turn `base_url: null` into `base_url:`.
    return dumper.represent_scalar("tag:yaml.org,2002:null", "null")


_yaml.representer.add_representer(type(None), _represent_none)

DISK_GUARD_FLOOR_GB = 5.0

_SCHEMA_PATH = Path(__file__).parent / "ap.recipe.schema.json"

# Phase 10 defaults (D-03)
DEFAULT_SMOKE_TIMEOUT_S = 180
DEFAULT_BUILD_TIMEOUT_S = 900
DEFAULT_CLONE_TIMEOUT_S = 300
DOCKER_DAEMON_PROBE_TIMEOUT_S = 5

# ANSI colors for lint output (D-08)
_RED = "\033[31m"
_GREEN = "\033[32m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


# ---------- category taxonomy (Phase 10) ----------


class Category(str, Enum):
    """Phase 10 verdict category enum (9 live + 2 reserved per D-01).

    Subclassing `str` (not `enum.StrEnum`) keeps compatibility with
    Python 3.10 per pyproject.toml `requires-python = ">=3.10"`.
    Members auto-coerce to strings for JSON emission.
    """
    # Live (9)
    PASS = "PASS"
    ASSERT_FAIL = "ASSERT_FAIL"
    INVOKE_FAIL = "INVOKE_FAIL"
    BUILD_FAIL = "BUILD_FAIL"
    PULL_FAIL = "PULL_FAIL"
    CLONE_FAIL = "CLONE_FAIL"
    TIMEOUT = "TIMEOUT"
    LINT_FAIL = "LINT_FAIL"
    INFRA_FAIL = "INFRA_FAIL"
    # Reserved (2) — schema enum only; runner never emits these in Phase 10.
    STOCHASTIC = "STOCHASTIC"   # reserved — phase 15 (multi-run determinism)
    SKIP = "SKIP"               # reserved — later UX phase (known_incompatible SKIP)


@dataclass(frozen=True)
class Verdict:
    """Phase 10 verdict record per D-02. `verdict` field is derived."""
    category: Category
    detail: str = ""

    @property
    def verdict(self) -> str:
        return "PASS" if self.category is Category.PASS else "FAIL"

    def to_cell_dict(self) -> dict:
        return {
            "category": self.category.value,
            "detail": self.detail,
            "verdict": self.verdict,
        }


# ---------- importable API ----------


def _load_schema() -> dict:
    """Load the JSON Schema from the co-located schema file."""
    return json.loads(_SCHEMA_PATH.read_text())


def load_recipe(path: Path) -> dict:
    """Load and parse a recipe YAML file. Returns the parsed dict."""
    return _yaml.load(path.read_text())


def lint_recipe(recipe: dict, schema: dict | None = None) -> list[str]:
    """Validate recipe dict against JSON Schema. Returns list of error messages (empty = valid).

    If schema is None, loads from the default location (tools/ap.recipe.schema.json).

    Normalizes the recipe through JSON round-trip before validation so that
    ruamel.yaml types (CommentedMap, datetime.date, etc.) are converted to
    plain Python dicts/strings that jsonschema can type-check correctly.
    """
    if schema is None:
        schema = _load_schema()
    from jsonschema import Draft202012Validator

    # Normalize: ruamel rt loader returns CommentedMap and may coerce
    # YAML date scalars (e.g. 2026-04-15) to datetime.date objects.
    # JSON round-trip converts everything to plain dicts/strings.
    normalized = json.loads(json.dumps(recipe, default=str))

    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(normalized),
        key=lambda e: list(e.absolute_path),
    )
    messages = []
    for e in errors:
        path = ".".join(str(p) for p in e.absolute_path) or "(root)"
        messages.append(f"{path}: {e.message}")
    return messages


# ---------- lint CLI helpers ----------


def _print_lint_result(name: str, errors: list[str]) -> None:
    """Print colored lint result for a single recipe."""
    if not errors:
        print(f"{_GREEN}PASS{_RESET} {name}")
    else:
        print(f"{_RED}FAIL{_RESET} {name} ({len(errors)} error{'s' if len(errors) != 1 else ''})")
        for msg in errors:
            print(f"  {_RED}-{_RESET} {msg}")


def _lint_single(recipe_path: Path) -> list[str]:
    """Load and lint a single recipe file. Returns error list."""
    try:
        recipe = load_recipe(recipe_path)
    except Exception as e:
        return [f"YAML parse error: {e}"]
    return lint_recipe(recipe)


def _lint_all_recipes(recipes_dir: Path) -> int:
    """Lint all *.yaml files in the recipes directory. Returns exit code."""
    yaml_files = sorted(recipes_dir.glob("*.yaml"))
    if not yaml_files:
        print(f"{_RED}ERROR{_RESET}: no *.yaml files found in {recipes_dir}")
        return 2
    any_fail = False
    for path in yaml_files:
        errors = _lint_single(path)
        _print_lint_result(path.name, errors)
        if errors:
            any_fail = True
    return 2 if any_fail else 0


# ---------- small helpers ----------

def log(msg: str, *, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


def run(cmd, check=True, capture=False, quiet=False):
    """Run a subprocess. Returns (rc, stdout, stderr) if capture else rc."""
    result = subprocess.run(cmd, check=False, capture_output=capture, text=True)
    if check and result.returncode != 0:
        if capture:
            sys.stderr.write(result.stderr or "")
        raise SystemExit(
            f"ERROR: command failed (exit {result.returncode}): {' '.join(cmd)}"
        )
    if capture:
        return result.returncode, result.stdout, result.stderr
    return result.returncode


def load_dotenv(path: Path) -> dict:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def resolve_api_key(recipe: dict, repo_root: Path) -> tuple[str, str]:
    """Find a value for the recipe's canonical api_key env var.

    Intentionally does NOT consult `process_env.api_key_fallback` — that field
    documents what the agent's own code internally accepts, not a hint about
    where the runner should source the value. Mixing those two concerns causes
    cross-provider key bleed (e.g. an OpenAI direct key in the host env being
    injected as an OpenRouter key).

    Search order for a value: the recipe's canonical `api_key` var, then the
    local-dev aliases OPENROUTER_API_KEY and OPEN_ROUTER_API_TOKEN, in that
    order. Process env wins over repo-root .env.
    """
    var_name = recipe["runtime"]["process_env"]["api_key"]
    dotenv = load_dotenv(repo_root / ".env")

    aliases = [var_name, "OPENROUTER_API_KEY", "OPEN_ROUTER_API_TOKEN"]
    # dedupe while preserving order
    seen: set[str] = set()
    ordered = [a for a in aliases if not (a in seen or seen.add(a))]

    for alias in ordered:
        val = os.environ.get(alias) or dotenv.get(alias)
        if val:
            return var_name, val
    raise SystemExit(
        f"ERROR: no API key — set {var_name} (or one of {ordered}) "
        f"in process env or {repo_root}/.env"
    )


def substitute_argv(argv: list[str], prompt: str, model: str) -> list[str]:
    subs = {"$PROMPT": prompt, "$MODEL": model}
    out: list[str] = []
    for arg in argv:
        if arg in subs:
            out.append(subs[arg])
            continue
        s = arg
        for k, v in subs.items():
            s = s.replace(k, v)
        out.append(s)
    return out


def apply_stdout_filter(raw: str, spec: Any) -> str:
    if spec is None:
        return raw
    engine = spec.get("engine")
    if engine is None:
        return raw
    if engine != "awk":
        raise SystemExit(f"ERROR: unsupported stdout_filter.engine: {engine}")
    program = spec["program"]
    proc = subprocess.run(
        ["awk", program], input=raw, capture_output=True, text=True
    )
    return proc.stdout


def evaluate_pass_if(
    rule: str,
    *,
    payload: str,
    name: str,
    exit_code: int,
    smoke: dict,
) -> str:
    case_insensitive = bool(smoke.get("case_insensitive", False))

    def _contains(needle: str) -> bool:
        hay = payload
        n = needle
        if case_insensitive:
            hay = hay.lower()
            n = n.lower()
        return n in hay

    if rule == "response_contains_name":
        return "PASS" if _contains(name) else "FAIL"
    if rule == "response_contains_string":
        needle = smoke.get("needle")
        if needle is None:
            return "ERROR(missing smoke.needle)"
        return "PASS" if _contains(needle) else "FAIL"
    if rule == "response_not_contains":
        needle = smoke.get("needle")
        if needle is None:
            return "ERROR(missing smoke.needle)"
        return "FAIL" if _contains(needle) else "PASS"
    if rule == "response_regex":
        pattern = smoke.get("regex")
        if pattern is None:
            return "ERROR(missing smoke.regex)"
        flags = re.IGNORECASE if case_insensitive else 0
        return "PASS" if re.search(pattern, payload, flags) else "FAIL"
    if rule == "exit_zero":
        return "PASS" if exit_code == 0 else "FAIL"
    return f"UNKNOWN(pass_if={rule})"


# ---------- phase 10 helpers ----------


def _redact_api_key(text: str, api_key_var: str) -> str:
    """Replace every <api_key_var>=<non-space-value> substring with <api_key_var>=<REDACTED>.

    Applied to all `detail` strings derived from subprocess stderr per D-02 + V7/V8 of
    RESEARCH.md §Security Domain.
    """
    if not text:
        return ""
    return re.sub(
        rf"{re.escape(api_key_var)}=\S+",
        f"{api_key_var}=<REDACTED>",
        text,
    )


def preflight_docker() -> Verdict | None:
    """Return INFRA_FAIL Verdict if the Docker daemon is unreachable, None if OK.

    Uses `docker version` (not `docker --version`) because it explicitly connects
    to the daemon — the client-only probe would succeed even when dockerd is down.
    """
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            timeout=DOCKER_DAEMON_PROBE_TIMEOUT_S,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            tail = (result.stderr or "").strip()[:200]
            return Verdict(
                Category.INFRA_FAIL,
                f"docker version exit {result.returncode}: {tail}",
            )
        return None
    except subprocess.TimeoutExpired:
        return Verdict(
            Category.INFRA_FAIL,
            f"docker daemon unresponsive (>{DOCKER_DAEMON_PROBE_TIMEOUT_S}s)",
        )
    except FileNotFoundError:
        return Verdict(Category.INFRA_FAIL, "docker CLI not in PATH")


def emit_verdict_line(
    verdict: Verdict,
    *,
    recipe: str,
    model: str,
    wall_s: float,
) -> None:
    """Emit the D-05 one-line human verdict format.

    Format: `<CATEGORY pad 10>  <recipe> (<model>) <wall>s[ — <detail>]`
    Green PASS / red everything else.
    """
    cat = verdict.category.value.ljust(10)
    color = _GREEN if verdict.category is Category.PASS else _RED
    line = f"{color}{cat}{_RESET} {recipe} ({model}) {wall_s:.2f}s"
    if verdict.detail:
        line += f" — {verdict.detail}"
    print(line, flush=True)


# ---------- disk guard ----------

def disk_free_gb(path: str = "/") -> float:
    usage = shutil.disk_usage(path)
    return usage.free / (1024 ** 3)


def enforce_disk_guard(*, skip: bool, quiet: bool) -> None:
    if skip:
        return
    free_gb = disk_free_gb("/")
    if free_gb < DISK_GUARD_FLOOR_GB:
        raise SystemExit(
            f"ERROR: disk guard tripped — only {free_gb:.1f} GB free on / "
            f"(floor is {DISK_GUARD_FLOOR_GB} GB). "
            f"Free space, or pass --no-disk-check to bypass."
        )
    log(f"  disk_free: {free_gb:.1f} GB (floor {DISK_GUARD_FLOOR_GB} GB)", quiet=quiet)


# ---------- image lifecycle ----------

def image_exists(tag: str) -> bool:
    rc, _, _ = run(
        ["docker", "image", "inspect", tag], check=False, capture=True
    )
    return rc == 0


def image_remove(tag: str) -> None:
    run(["docker", "image", "rm", "-f", tag], check=False, capture=True)


def ensure_image(
    recipe: dict,
    *,
    image_tag: str,
    no_cache: bool,
    no_disk_check: bool,
    quiet: bool,
) -> None:
    build = recipe["build"]
    build_mode = build.get("mode", "upstream_dockerfile")
    if build_mode not in ("upstream_dockerfile", "image_pull"):
        raise SystemExit(f"ERROR: unsupported build.mode: {build_mode}")

    if no_cache and image_exists(image_tag):
        log(f"  --no-cache: removing {image_tag}", quiet=quiet)
        image_remove(image_tag)

    if image_exists(image_tag):
        log(f"  image cached: {image_tag}", quiet=quiet)
        return

    enforce_disk_guard(skip=no_disk_check, quiet=quiet)

    if build_mode == "upstream_dockerfile":
        source = recipe["source"]
        repo_url = source["repo"]
        ref = source.get("ref")
        dockerfile = build.get("dockerfile", "Dockerfile")
        context_dir = build.get("context", ".")

        clone_dir = Path(f"/tmp/ap-recipe-{recipe['name']}-clone")
        if not clone_dir.exists():
            log(f"  cloning {repo_url} → {clone_dir}", quiet=quiet)
            run(["git", "clone", "--depth=1", repo_url, str(clone_dir)])
            if ref:
                log(f"  attempting to pin {ref[:12]}...", quiet=quiet)
                rc = run(
                    ["git", "-C", str(clone_dir), "fetch", "--depth=1", "origin", ref],
                    check=False,
                )
                if rc == 0:
                    run(
                        ["git", "-C", str(clone_dir), "checkout", "FETCH_HEAD"],
                        check=False,
                    )
                else:
                    log(
                        f"  WARN: could not fetch pinned ref {ref}, using shallow HEAD",
                        quiet=quiet,
                    )
        else:
            log(f"  clone cached: {clone_dir}", quiet=quiet)

        log(f"  building {image_tag} ...", quiet=quiet)
        run([
            "docker", "build",
            "--progress=plain",
            "-t", image_tag,
            "-f", str(clone_dir / dockerfile),
            str(clone_dir / context_dir),
        ])
        return

    # image_pull
    pull_image = build.get("image")
    if not pull_image:
        raise SystemExit("ERROR: build.mode=image_pull requires build.image")
    log(f"  pulling {pull_image} → {image_tag}", quiet=quiet)
    run(["docker", "pull", pull_image])
    run(["docker", "tag", pull_image, image_tag])


# ---------- cell execution ----------

def run_cell(
    recipe: dict,
    *,
    image_tag: str,
    prompt: str,
    model: str,
    api_key_var: str,
    api_key_val: str,
    quiet: bool,
) -> dict:
    raw_argv = recipe["invoke"]["spec"]["argv"]
    argv = substitute_argv(list(raw_argv), prompt, model)

    vol = recipe["runtime"]["volumes"][0]
    container_mount = vol["container"]
    entrypoint = recipe["invoke"]["spec"].get("entrypoint")
    data_dir = Path(tempfile.mkdtemp(prefix=f"ap-recipe-{recipe['name']}-data-"))

    docker_cmd = [
        "docker", "run", "--rm",
        "-e", f"{api_key_var}={api_key_val}",
        "-v", f"{data_dir}:{container_mount}",
    ]
    if entrypoint:
        docker_cmd += ["--entrypoint", entrypoint]
    docker_cmd += [image_tag] + argv

    safe_cmd = [
        a if not a.startswith(f"{api_key_var}=") else f"{api_key_var}=<REDACTED>"
        for a in docker_cmd
    ]
    log(f"  $ {' '.join(safe_cmd)}", quiet=quiet)

    t0 = time.time()
    try:
        rc, stdout, stderr = run(docker_cmd, check=False, capture=True)
    finally:
        if data_dir.exists():
            run(["rm", "-rf", str(data_dir)], check=False)
    wall = time.time() - t0

    filtered = apply_stdout_filter(
        stdout, recipe["invoke"]["spec"].get("stdout_filter")
    )

    smoke = recipe["smoke"]
    verdict = evaluate_pass_if(
        smoke["pass_if"],
        payload=filtered,
        name=recipe["name"],
        exit_code=rc,
        smoke=smoke,
    )

    return {
        "recipe": recipe["name"],
        "model": model,
        "prompt": prompt,
        "pass_if": smoke["pass_if"],
        "verdict": verdict,
        "exit_code": rc,
        "wall_time_s": round(wall, 2),
        "filtered_payload": filtered,
        "stderr_tail": "\n".join((stderr or "").splitlines()[-20:]) or None,
    }


# ---------- reporting ----------

def emit_json(result: dict) -> None:
    print(json.dumps(result), flush=True)


def emit_human(result: dict) -> None:
    print()
    print("=" * 70)
    print(f"  VERDICT: {result['verdict']}")
    print(f"  recipe:  {result['recipe']}")
    print(f"  model:   {result['model']}")
    print(f"  pass_if: {result['pass_if']}")
    print(f"  exit:    {result['exit_code']}")
    print(f"  wall:    {result['wall_time_s']}s")
    print("=" * 70)
    print("FILTERED PAYLOAD:")
    print(result["filtered_payload"])
    print("=" * 70)
    if result["exit_code"] != 0 or result["verdict"] != "PASS":
        if result["stderr_tail"]:
            print("RAW STDERR (last 20 lines):")
            print(result["stderr_tail"])
            print("-" * 70)


# ---------- write-back ----------

def writeback_cell(recipe_path: Path, model: str, wall_time_s: float) -> None:
    """Round-trip update of verified_cells[].wall_time_s for <model>.

    Only wall_time_s is updated. The documented `verdict` is authored by the
    recon contributor and is intentionally NOT overwritten — drift is reported
    via the process exit code, not by silently mutating the recipe.
    Uses ruamel.yaml round-trip so comments and ordering survive.
    """
    text = recipe_path.read_text()
    data = _yaml.load(text)
    cells = data.get("smoke", {}).get("verified_cells")
    if cells is None:
        return
    for cell in cells:
        if cell.get("model") == model:
            cell["wall_time_s"] = float(round(wall_time_s, 2))
            break
    else:
        return
    with recipe_path.open("w") as f:
        _yaml.dump(data, f)


# ---------- model / prompt resolution ----------

def first_pass_cell_model(recipe: dict) -> str | None:
    for cell in recipe.get("smoke", {}).get("verified_cells", []) or []:
        if cell.get("verdict") == "PASS":
            return cell.get("model")
    return None


def all_verified_cells(recipe: dict) -> list[tuple[str, str]]:
    """Return [(model, documented_verdict), ...] in recipe order."""
    out: list[tuple[str, str]] = []
    for cell in recipe.get("smoke", {}).get("verified_cells", []) or []:
        if "model" in cell:
            out.append((cell["model"], cell.get("verdict", "PASS")))
    return out


# ---------- main ----------

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="run_recipe.py",
        description="Agent Playground recipe runner (ap.recipe/v0.1)",
    )
    p.add_argument(
        "recipe",
        nargs="?",
        default=None,
        help="Path to recipe YAML (recipes/<agent>.yaml). Optional with --lint-all.",
    )
    p.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Prompt to send. Falls back to smoke.prompt in the recipe.",
    )
    p.add_argument(
        "model",
        nargs="?",
        default=None,
        help="Model to use. Falls back to first PASS verified_cell.",
    )
    p.add_argument("--lint", action="store_true",
                    help="Validate recipe against schema and exit (no Docker run).")
    p.add_argument("--lint-all", action="store_true",
                    help="Validate all recipes in recipes/ directory and exit.")
    p.add_argument("--no-lint", action="store_true",
                    help="Skip the mandatory lint pre-step before running.")
    p.add_argument("--json", action="store_true", help="Emit structured JSON verdict(s).")
    p.add_argument(
        "--all-cells",
        action="store_true",
        help="Sweep every verified_cell in the recipe.",
    )
    p.add_argument(
        "--no-cache",
        action="store_true",
        help="Remove the tagged image before build/pull.",
    )
    p.add_argument(
        "--no-disk-check",
        action="store_true",
        help="Skip the 5 GB free-space guard before build/pull.",
    )
    p.add_argument(
        "--write-back",
        dest="write_back",
        action="store_true",
        default=True,
        help="In --all-cells mode, write wall_time_s/verdict back to the recipe (default).",
    )
    p.add_argument(
        "--no-write-back",
        dest="write_back",
        action="store_false",
        help="In --all-cells mode, do not modify the recipe file.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # --lint-all mode: lint every recipe and exit (D-06)
    if args.lint_all:
        recipes_dir = Path("recipes")
        if not recipes_dir.exists():
            recipes_dir = Path.cwd() / "recipes"
        return _lint_all_recipes(recipes_dir)

    # Require recipe path for all other modes
    if args.recipe is None:
        sys.stderr.write("ERROR: recipe path is required (or use --lint-all)\n")
        return 2

    recipe_path = Path(args.recipe).resolve()
    if not recipe_path.exists():
        sys.stderr.write(f"ERROR: recipe not found: {recipe_path}\n")
        return 2

    # --lint mode: validate single recipe and exit (D-06)
    if args.lint:
        errors = _lint_single(recipe_path)
        _print_lint_result(recipe_path.name, errors)
        return 2 if errors else 0

    # Mandatory lint pre-step (D-07): runs before every Docker invocation
    if not args.no_lint:
        errors = _lint_single(recipe_path)
        if errors:
            _print_lint_result(recipe_path.name, errors)
            sys.stderr.write(
                f"\n{_RED}Lint failed{_RESET} — fix the recipe or pass --no-lint to bypass.\n"
            )
            return 2

    repo_root = recipe_path.parent.parent
    recipe = load_recipe(recipe_path)
    name = recipe["name"]
    image_tag = f"ap-recipe-{name}"

    prompt = args.prompt
    if prompt is None:
        prompt = recipe.get("smoke", {}).get("prompt")
        if not prompt:
            sys.stderr.write(
                "ERROR: no prompt provided on CLI and smoke.prompt missing from recipe\n"
            )
            return 2

    quiet = args.json  # suppress banners in JSON mode

    api_key_var, api_key_val = resolve_api_key(recipe, repo_root)

    log(f"=== ap-recipe-runner :: {name} ===", quiet=quiet)
    log(f"  recipe:   {recipe_path}", quiet=quiet)
    log(f"  image:    {image_tag}", quiet=quiet)
    log(f"  api_key:  {api_key_var}=<{len(api_key_val)} chars>", quiet=quiet)

    ensure_image(
        recipe,
        image_tag=image_tag,
        no_cache=args.no_cache,
        no_disk_check=args.no_disk_check,
        quiet=quiet,
    )

    # Determine the (model, expected_verdict) list
    if args.all_cells:
        cells = all_verified_cells(recipe)
        if not cells:
            sys.stderr.write("ERROR: --all-cells but no verified_cells in recipe\n")
            return 2
    else:
        if args.model:
            cells = [(args.model, "PASS")]
        else:
            default = first_pass_cell_model(recipe)
            if default is None:
                sys.stderr.write(
                    "ERROR: no model on CLI and no PASS verified_cell to fall back on\n"
                )
                return 2
            cells = [(default, "PASS")]

    any_drift = False
    any_nonpass = False
    for model, expected in cells:
        log(f"\n--- cell: {name} × {model} (expected {expected}) ---", quiet=quiet)
        result = run_cell(
            recipe,
            image_tag=image_tag,
            prompt=prompt,
            model=model,
            api_key_var=api_key_var,
            api_key_val=api_key_val,
            quiet=quiet,
        )
        result["expected_verdict"] = expected
        result["drift"] = result["verdict"] != expected

        if args.json:
            emit_json(result)
        else:
            emit_human(result)

        if args.all_cells and args.write_back:
            try:
                writeback_cell(
                    recipe_path,
                    model=model,
                    wall_time_s=result["wall_time_s"],
                )
            except Exception as e:
                sys.stderr.write(f"WARN: write-back failed for {model}: {e}\n")

        if result["drift"]:
            any_drift = True
            sys.stderr.write(
                f"DRIFT: {name} × {model} — expected {expected}, got {result['verdict']}\n"
            )
        if result["verdict"] != "PASS":
            any_nonpass = True

    # --all-cells: regression detector — exit non-zero ONLY on drift.
    # Single-cell: legacy behavior — exit non-zero if observed != PASS.
    if args.all_cells:
        return 1 if any_drift else 0
    return 1 if any_nonpass else 0


if __name__ == "__main__":
    sys.exit(main())
