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
    p.add_argument("recipe", help="Path to recipe YAML (recipes/<agent>.yaml)")
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

    recipe_path = Path(args.recipe).resolve()
    if not recipe_path.exists():
        sys.stderr.write(f"ERROR: recipe not found: {recipe_path}\n")
        return 2

    repo_root = recipe_path.parent.parent
    recipe = _yaml.load(recipe_path.read_text())
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
