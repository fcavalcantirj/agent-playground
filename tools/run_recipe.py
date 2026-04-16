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
import hashlib
import json
import os
import re
import shlex
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


def run_with_timeout(
    cmd: list[str],
    *,
    timeout_s: int,
    capture: bool = True,
) -> tuple[int, str, str, bool]:
    """Wrap subprocess.run with a timeout.

    Returns (rc, stdout, stderr, timed_out). On timeout, rc == -1 and
    timed_out is True. Does NOT raise TimeoutExpired — callers classify
    the timeout themselves.

    NOTE: For `docker run` timeouts the caller MUST use `--cidfile` +
    `docker kill` to actually reap the container. This helper only kills
    the docker CLI subprocess. See RESEARCH.md §Pattern 3.
    """
    try:
        r = subprocess.run(
            cmd,
            timeout=timeout_s,
            capture_output=capture,
            text=True,
            check=False,
        )
        return r.returncode, r.stdout or "", r.stderr or "", False
    except subprocess.TimeoutExpired as exc:
        so = exc.stdout or ""
        se = exc.stderr or ""
        if isinstance(so, bytes):
            so = so.decode(errors="replace")
        if isinstance(se, bytes):
            se = se.decode(errors="replace")
        return -1, so, se, True


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

    Canonical var only. The value must be set under the exact name declared by
    the recipe in `runtime.process_env.api_key` — either in the process env or
    in `<repo_root>/.env`. Process env wins.

    No provider aliases are consulted. A recipe declaring `ANTHROPIC_API_KEY`
    must find ANTHROPIC_API_KEY — never OPENROUTER_API_KEY. Cross-provider
    aliasing is the exact anti-pattern that causes a key minted for one
    provider to be silently injected as another provider's key.

    `process_env.api_key_fallback` (schema field) documents what the agent's
    own internal code accepts; it is intentionally not consulted here.
    """
    var_name = recipe["runtime"]["process_env"]["api_key"]
    dotenv = load_dotenv(repo_root / ".env")

    val = os.environ.get(var_name) or dotenv.get(var_name)
    if val:
        return var_name, val
    raise SystemExit(
        f"ERROR: no API key — set {var_name} in process env or {repo_root}/.env"
    )


def substitute_argv(argv: list[str], prompt: str, model: str) -> list[str]:
    """Substitute $PROMPT / $MODEL in argv.

    Two contexts:
      1. Standalone element — exact match `arg == "$PROMPT"`. Docker passes it as
         its own argv entry; no shell parses it, so raw substitution is correct.
      2. Embedded in a larger string — e.g. `sh -c 'foo --prompt "$PROMPT"'`.
         A shell will parse the result, so the value MUST be shlex-quoted to
         prevent injection when the prompt contains quotes or shell metacharacters.
    """
    subs = {"$PROMPT": prompt, "$MODEL": model}
    out: list[str] = []
    for arg in argv:
        if arg in subs:
            out.append(subs[arg])
            continue
        s = arg
        for k, v in subs.items():
            if k in s:
                s = s.replace(k, shlex.quote(v))
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
) -> Verdict | None:
    """Ensure the image tag exists, either cached or freshly built/pulled.

    Returns:
        None when the image is ready.
        Verdict(Category.CLONE_FAIL | BUILD_FAIL | PULL_FAIL, detail=...) on failure.
    """
    build = recipe["build"]
    build_mode = build.get("mode", "upstream_dockerfile")
    if build_mode not in ("upstream_dockerfile", "image_pull"):
        # Lint should catch this; defensive.
        raise SystemExit(f"ERROR: unsupported build.mode: {build_mode}")

    if no_cache and image_exists(image_tag):
        log(f"  --no-cache: removing {image_tag}", quiet=quiet)
        image_remove(image_tag)

    if image_exists(image_tag):
        log(f"  image cached: {image_tag}", quiet=quiet)
        return None

    enforce_disk_guard(skip=no_disk_check, quiet=quiet)

    build_timeout_s = int(build.get("timeout_s", DEFAULT_BUILD_TIMEOUT_S))
    clone_timeout_s = int(build.get("clone_timeout_s", DEFAULT_CLONE_TIMEOUT_S))

    if build_mode == "upstream_dockerfile":
        source = recipe["source"]
        repo_url = source["repo"]
        ref = source.get("ref")
        dockerfile = build.get("dockerfile", "Dockerfile")
        context_dir = build.get("context", ".")

        clone_dir = Path(f"/tmp/ap-recipe-{recipe['name']}-clone")
        if not clone_dir.exists():
            log(f"  cloning {repo_url} → {clone_dir}", quiet=quiet)
            rc, so, se, timed_out = run_with_timeout(
                ["git", "clone", "--depth=1", repo_url, str(clone_dir)],
                timeout_s=clone_timeout_s,
            )
            if timed_out:
                return Verdict(
                    Category.CLONE_FAIL,
                    f"git clone timeout after {clone_timeout_s}s",
                )
            if rc != 0:
                tail = (se or "").strip().splitlines()[-1:] or [""]
                return Verdict(
                    Category.CLONE_FAIL,
                    f"git clone exit {rc}: {tail[0][:200]}",
                )
            if ref:
                log(f"  attempting to pin {ref[:12]}...", quiet=quiet)
                # fetch + checkout preserve soft-fail behavior from original code
                rc2, _, _, fetch_to = run_with_timeout(
                    ["git", "-C", str(clone_dir), "fetch", "--depth=1", "origin", ref],
                    timeout_s=clone_timeout_s,
                )
                if fetch_to:
                    log(
                        f"  WARN: fetch timeout after {clone_timeout_s}s — using shallow HEAD",
                        quiet=quiet,
                    )
                elif rc2 == 0:
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
        rc, so, se, timed_out = run_with_timeout(
            [
                "docker", "build",
                "--progress=plain",
                "-t", image_tag,
                "-f", str(clone_dir / dockerfile),
                str(clone_dir / context_dir),
            ],
            timeout_s=build_timeout_s,
        )
        if timed_out:
            # D-03 limitation acknowledged: BuildKit layer may finish despite CLI kill.
            # docker/cli#3375 open; accept.
            return Verdict(
                Category.BUILD_FAIL,
                f"docker build timeout after {build_timeout_s}s (BuildKit layer may complete)",
            )
        if rc != 0:
            tail = (se or "").strip().splitlines()[-1:] or [""]
            return Verdict(
                Category.BUILD_FAIL,
                f"docker build exit {rc}: {tail[0][:200]}",
            )
        return None

    # image_pull
    pull_image = build.get("image")
    if not pull_image:
        raise SystemExit("ERROR: build.mode=image_pull requires build.image")
    log(f"  pulling {pull_image} → {image_tag}", quiet=quiet)
    rc, so, se, timed_out = run_with_timeout(
        ["docker", "pull", pull_image],
        timeout_s=build_timeout_s,
    )
    if timed_out:
        return Verdict(
            Category.PULL_FAIL,
            f"docker pull timeout after {build_timeout_s}s",
        )
    if rc != 0:
        tail = (se or "").strip().splitlines()[-1:] or [""]
        return Verdict(
            Category.PULL_FAIL,
            f"docker pull exit {rc}: {tail[0][:200]}",
        )
    # tag the pulled image — if this fails, surface as PULL_FAIL (tag is part of pull step)
    rc2, _, se2, _ = run_with_timeout(
        ["docker", "tag", pull_image, image_tag],
        timeout_s=30,
    )
    if rc2 != 0:
        return Verdict(
            Category.PULL_FAIL,
            f"docker tag exit {rc2}: {(se2 or '').strip()[:200]}",
        )
    return None


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
    smoke_timeout_s: int | None = None,
) -> tuple[Verdict, dict]:
    """Run a single cell with --cidfile + docker kill timeout enforcement.

    Returns (verdict, details_dict) where details_dict carries the existing
    emit_json/emit_human-consumable fields (wall_time_s, filtered_payload,
    stderr_tail, exit_code, etc.). This preserves backwards-compat with
    the existing output formats while the authoritative verdict travels
    via the Verdict return value.
    """
    raw_argv = recipe["invoke"]["spec"]["argv"]
    argv = substitute_argv(list(raw_argv), prompt, model)

    vol = recipe["runtime"]["volumes"][0]
    container_mount = vol["container"]
    entrypoint = recipe["invoke"]["spec"].get("entrypoint")
    data_dir = Path(tempfile.mkdtemp(prefix=f"ap-recipe-{recipe['name']}-data-"))

    # Cidfile: fresh UUID path, DO NOT pre-create. Docker errors if file exists.
    # See RESEARCH.md §Pitfall 2 + docker/cli#5954.
    cidfile = Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")

    # Timeout precedence: explicit kwarg > recipe.smoke.timeout_s > default.
    smoke = recipe["smoke"]
    if smoke_timeout_s is None:
        smoke_timeout_s = int(smoke.get("timeout_s", DEFAULT_SMOKE_TIMEOUT_S))

    docker_cmd = [
        "docker", "run", "--rm",
        f"--cidfile={cidfile}",
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

    rc = -1
    stdout = ""
    stderr = ""
    timed_out = False
    timeout_reason: str | None = None

    t0 = time.time()
    try:
        try:
            result = subprocess.run(
                docker_cmd,
                timeout=smoke_timeout_s,
                capture_output=True,
                text=True,
                check=False,
            )
            rc = result.returncode
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            timeout_reason = f"exceeded smoke.timeout_s={smoke_timeout_s}s"
            # Partial output from exc; defensive decode for Python 3.10 (RESEARCH.md §Pitfall 3)
            so = exc.stdout or ""
            se = exc.stderr or ""
            if isinstance(so, bytes):
                so = so.decode(errors="replace")
            if isinstance(se, bytes):
                se = se.decode(errors="replace")
            stdout = so
            stderr = se
            # Reap the container via cidfile.
            cid: str | None = None
            try:
                if cidfile.exists() and cidfile.stat().st_size > 0:
                    cid = cidfile.read_text().strip()
            except OSError:
                cid = None
            if cid:
                # docker kill -- check=False because the container may have exited
                # on its own between TimeoutExpired and now (RESEARCH.md §Pitfall 4).
                subprocess.run(
                    ["docker", "kill", cid],
                    timeout=10, check=False, capture_output=True,
                )
                subprocess.run(
                    ["docker", "rm", "-f", cid],
                    timeout=10, check=False, capture_output=True,
                )
    finally:
        # Cleanup order: data_dir (existing), cidfile (new).
        # Both with missing_ok / best-effort — moby/moby#20766.
        if data_dir.exists():
            run(["rm", "-rf", str(data_dir)], check=False)
        try:
            cidfile.unlink(missing_ok=True)
        except OSError:
            pass

    wall = time.time() - t0

    # Classify the verdict.
    if timed_out:
        verdict_obj = Verdict(Category.TIMEOUT, timeout_reason or "")
        filtered = ""
        pass_if_str = smoke.get("pass_if", "")
    elif rc != 0:
        tail = (stderr or "").strip().splitlines()[-1:] or [""]
        detail = _redact_api_key(
            f"docker run exit {rc}: {tail[0][:200]}",
            api_key_var,
        )
        verdict_obj = Verdict(Category.INVOKE_FAIL, detail)
        filtered = stdout
        pass_if_str = smoke.get("pass_if", "")
    else:
        filtered = apply_stdout_filter(
            stdout, recipe["invoke"]["spec"].get("stdout_filter")
        )
        pass_if_str = smoke["pass_if"]
        pass_if_result = evaluate_pass_if(
            pass_if_str,
            payload=filtered,
            name=recipe["name"],
            exit_code=rc,
            smoke=smoke,
        )
        if pass_if_result == "PASS":
            verdict_obj = Verdict(Category.PASS, "")
        else:
            verdict_obj = Verdict(
                Category.ASSERT_FAIL,
                f"pass_if evaluated {pass_if_result}",
            )

    details = {
        "recipe": recipe["name"],
        "model": model,
        "prompt": prompt,
        "pass_if": pass_if_str,
        "verdict": verdict_obj.verdict,
        "category": verdict_obj.category.value,
        "detail": verdict_obj.detail,
        "exit_code": rc,
        "wall_time_s": round(wall, 2),
        "filtered_payload": filtered,
        "stderr_tail": "\n".join(
            _redact_api_key(stderr, api_key_var).splitlines()[-20:]
        ) or None,
    }
    return verdict_obj, details


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
        "--global-timeout",
        dest="global_timeout",
        type=int,
        default=None,
        help=(
            "Hard ceiling (seconds) across the entire runner invocation. "
            "Overrides per-recipe smoke.timeout_s. On expiry, the current "
            "cell returns TIMEOUT and any remaining cells are skipped."
        ),
    )
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
    # Step 1: parse args
    args = parse_args(argv if argv is not None else sys.argv[1:])

    # Step 2: --lint-all short-circuit (no docker needed)
    if args.lint_all:
        recipes_dir = Path("recipes")
        if not recipes_dir.exists():
            recipes_dir = Path.cwd() / "recipes"
        return _lint_all_recipes(recipes_dir)

    # Step 3: recipe path validation
    if args.recipe is None:
        sys.stderr.write("ERROR: recipe path is required (or use --lint-all)\n")
        return 2

    recipe_path = Path(args.recipe).resolve()
    if not recipe_path.exists():
        sys.stderr.write(f"ERROR: recipe not found: {recipe_path}\n")
        return 2

    # Step 4: --lint short-circuit (no docker needed)
    if args.lint:
        errors = _lint_single(recipe_path)
        _print_lint_result(recipe_path.name, errors)
        return 2 if errors else 0

    # Step 5: INFRA pre-flight — from here on Docker will be shelled out.
    # preflight_docker() probes the daemon via `docker version` and returns
    # Verdict(INFRA_FAIL) if it's unreachable; None otherwise.
    infra = preflight_docker()
    if infra is not None:
        emit_verdict_line(infra, recipe="(pre-flight)", model="", wall_s=0.0)
        return 1

    # Step 6: mandatory lint pre-step with LINT_FAIL emission
    if not args.no_lint:
        errors = _lint_single(recipe_path)
        if errors:
            _print_lint_result(recipe_path.name, errors)
            emit_verdict_line(
                Verdict(Category.LINT_FAIL, f"{len(errors)} schema error(s)"),
                recipe=recipe_path.name, model="", wall_s=0.0,
            )
            sys.stderr.write(
                f"\n{_RED}Lint failed{_RESET} — fix the recipe or pass --no-lint to bypass.\n"
            )
            return 2

    # Step 7: load recipe, resolve prompt + api_key
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

    # Step 8: ensure_image — emit image verdict on failure
    image_verdict = ensure_image(
        recipe,
        image_tag=image_tag,
        no_cache=args.no_cache,
        no_disk_check=args.no_disk_check,
        quiet=quiet,
    )
    if image_verdict is not None:
        emit_verdict_line(image_verdict, recipe=name, model="", wall_s=0.0)
        return 1

    # Step 9: cell loop — run_cell returns (Verdict, dict); honor --global-timeout
    # Determine the (model, expected_verdict) list.
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
    global_deadline: float | None = None
    if args.global_timeout:
        global_deadline = time.time() + args.global_timeout

    for model, expected in cells:
        log(f"\n--- cell: {name} × {model} (expected {expected}) ---", quiet=quiet)

        # Compute per-cell timeout: min(smoke.timeout_s, remaining --global-timeout budget).
        smoke_timeout = int(recipe["smoke"].get("timeout_s", DEFAULT_SMOKE_TIMEOUT_S))
        if global_deadline is not None:
            remaining = global_deadline - time.time()
            if remaining <= 0:
                # Global timeout already expired before we started this cell.
                v = Verdict(
                    Category.TIMEOUT,
                    f"exceeded --global-timeout={args.global_timeout}s (cell skipped)",
                )
                emit_verdict_line(v, recipe=name, model=model, wall_s=0.0)
                any_nonpass = True
                if v.verdict != expected:
                    any_drift = True
                continue
            smoke_timeout = min(smoke_timeout, int(remaining))

        verdict_obj, result = run_cell(
            recipe,
            image_tag=image_tag,
            prompt=prompt,
            model=model,
            api_key_var=api_key_var,
            api_key_val=api_key_val,
            quiet=quiet,
            smoke_timeout_s=smoke_timeout,
        )
        result["expected_verdict"] = expected
        result["drift"] = result["verdict"] != expected

        if args.json:
            emit_json(result)
        else:
            emit_human(result)
        emit_verdict_line(
            verdict_obj,
            recipe=name,
            model=model,
            wall_s=result["wall_time_s"],
        )

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

    # Exit code contract (D-03 / RESEARCH Open Q2):
    #   0 = all PASS; 1 = any non-PASS runtime failure; 2 = lint / usage error (handled above)
    if args.all_cells:
        return 1 if any_drift else 0
    return 1 if any_nonpass else 0


if __name__ == "__main__":
    sys.exit(main())
