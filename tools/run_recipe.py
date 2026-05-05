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
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# Phase 22c.3.1 (D-14): activation-time placeholder substitution helper —
# lifted from api_server/tests/e2e/_helpers.py. Lives next to run_recipe.py
# in tools/ so both files can share it.
#
# Robust import: when run_recipe.py is loaded by api_server.services.runner_bridge
# via importlib.util.spec_from_file_location("run_recipe", <path>), tools/ is NOT
# on sys.path. Insert this file's parent directory (tools/) onto sys.path so the
# sibling _placeholders module resolves regardless of caller. tools/tests/conftest.py
# does this dance too — same pattern.
_TOOLS_DIR = str(Path(__file__).resolve().parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
from _placeholders import render_placeholders  # noqa: E402

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

# Phase 22c.3.1 (D-25, B-4 fix): pre_start_command timeout. Module-level so
# tests can monkey-patch via ``tools.run_recipe.PRE_START_COMMAND_TIMEOUT_S``
# without rewriting the function signature.
PRE_START_COMMAND_TIMEOUT_S = 120

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

    WR-01 (v0.2): the root is now `oneOf: [v0_1, v0_2]` so top-level errors
    arrive as an opaque 'is not valid under any of the given schemas' message.
    The deep error paths live under `e.context` — the list of sub-errors from
    each `oneOf` branch. We walk `context` recursively to surface the deepest
    path, preserving the pre-v0.2 error message shape (e.g. 'source.ref: ...').
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
    messages: list[str] = []
    for e in errors:
        if e.validator == "oneOf" and e.context:
            # Drill into the branch sub-errors. Pick the v0_N branch that the
            # recipe was trying to be (matched apiVersion const) so the user
            # sees errors scoped to the right version. If apiVersion can't be
            # resolved, surface all sub-errors — redundant but strictly more
            # informative than the opaque top-level message.
            api_version = normalized.get("apiVersion") if isinstance(normalized, dict) else None
            branch_errors = _select_oneof_branch_errors(e.context, api_version)
            for sub in sorted(branch_errors, key=lambda x: list(x.absolute_path)):
                sub_path = ".".join(str(p) for p in sub.absolute_path) or "(root)"
                messages.append(f"{sub_path}: {sub.message}")
            if not branch_errors:
                # Fallback: emit the top-level oneOf message so the consumer at
                # least knows something failed.
                path = ".".join(str(p) for p in e.absolute_path) or "(root)"
                messages.append(f"{path}: {e.message}")
        else:
            path = ".".join(str(p) for p in e.absolute_path) or "(root)"
            messages.append(f"{path}: {e.message}")
    return messages


def _select_oneof_branch_errors(context_errors, api_version):
    """Pick the oneOf sub-errors that belong to the branch the recipe was
    trying to match (determined by its apiVersion const). Returns a flat list
    of jsonschema ValidationError objects.

    Filters out:
    - apiVersion-const sub-errors (signal that this is the wrong branch, not
      a substantive content error).
    - Branch-wide 'additionalProperties' collapses for the wrong branch —
      these are noise when the apiVersion const already identifies the right
      branch (a v0.1 recipe hitting the v0.2 branch produces an extra
      'additionalProperties are not allowed' at root that duplicates v0.1-
      branch's own per-field errors).

    Deduplicates by (absolute_path, message) — oneOf branches often report
    the same per-field required/type violation once per branch; the user only
    needs to see each real problem once.
    """
    # Pick the branch index whose apiVersion const matches the recipe's
    # declared apiVersion, so we can prefer that branch's sub-errors.
    target_branch: int | None = None
    if isinstance(api_version, str):
        for sub in context_errors:
            spath = list(sub.absolute_schema_path)
            if (
                len(spath) >= 3
                and spath[-1] == "const"
                and "apiVersion" in spath
                and len(spath) >= 2
                and isinstance(spath[1], int)
            ):
                # spath looks like ['oneOf', <branch_idx>, 'properties',
                # 'apiVersion', 'const']. The branch whose const DID NOT match
                # is the "wrong" branch for this apiVersion; we want the OTHER.
                wrong_branch = spath[1]
                # If there are exactly 2 branches (v0_1, v0_2), the "right"
                # branch is 1 - wrong_branch.
                target_branch = 1 - wrong_branch

    substantive: list = []
    seen: set[tuple] = set()
    for sub in context_errors:
        spath = list(sub.absolute_schema_path)
        # Drop apiVersion-const mismatch noise.
        if len(spath) >= 3 and spath[-1] == "const" and "apiVersion" in spath:
            continue
        # Prefer the target branch's errors when resolvable. If target_branch
        # is None, keep everything.
        if target_branch is not None and len(spath) >= 2 and isinstance(spath[1], int):
            if spath[1] != target_branch:
                continue
        key = (tuple(sub.absolute_path), sub.message)
        if key in seen:
            continue
        seen.add(key)
        substantive.append(sub)
    return substantive


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


AWK_FILTER_TIMEOUT_S = 30


def apply_stdout_filter(raw: str, spec: Any) -> str:
    if spec is None:
        return raw
    engine = spec.get("engine")
    if engine is None:
        return raw
    if engine != "awk":
        raise SystemExit(f"ERROR: unsupported stdout_filter.engine: {engine}")
    program = spec["program"]
    try:
        proc = subprocess.run(
            ["awk", program],
            input=raw,
            capture_output=True,
            text=True,
            timeout=AWK_FILTER_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        # Pathological awk program (infinite loop, runaway regex backtracking).
        # Fail-open to raw payload so the pass_if gate can still run — an empty
        # return would mask all downstream verdicts.
        return raw
    return proc.stdout


def evaluate_pass_if(
    rule: str,
    *,
    payload: str,
    name: str,
    exit_code: int,
    smoke: dict,
    agent_name: str | None = None,
) -> str:
    case_insensitive = bool(smoke.get("case_insensitive", False))

    def _contains(needle: str) -> bool:
        if not needle:
            return False
        hay = payload
        n = needle
        if case_insensitive:
            hay = hay.lower()
            n = n.lower()
        return n in hay

    if rule == "response_contains_name":
        # Phase 22c.1: PASS if the bot's reply contains EITHER the recipe's
        # canonical name OR the user's chosen agent_name. Recipe-name match
        # preserves backward compat with verified_cells; agent_name match
        # honors the user's identity choice once it's plumbed end-to-end.
        return "PASS" if (_contains(name) or _contains(agent_name or "")) else "FAIL"
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
    if rule == "replied_ok":
        # Phase 22c.1: container exited cleanly AND produced a non-empty
        # reply. Used when personality presets override the recipe's smoke
        # prompt — the recipe's name-eliciting contract no longer holds, so
        # the smoke check degrades to "did the (recipe + model + key)
        # combination actually function?". The agent's reply is the proof
        # of work; pass_if doesn't second-guess the content.
        return "PASS" if (exit_code == 0 and len((payload or "").strip()) > 0) else "FAIL"
    return f"UNKNOWN(pass_if={rule})"


# ---------- phase 10 helpers ----------


def _redact_api_key(text: str, api_key_var: str, api_key_val: str | None = None) -> str:
    """Replace every <api_key_var>=<non-space-value> substring with <api_key_var>=<REDACTED>.

    When ``api_key_val`` is provided AND is at least 8 characters long, ALSO replace every
    literal occurrence of the key value with ``<REDACTED>``. This protects against stderr
    lines that leak the key without the ``VAR=`` prefix (e.g. API error messages that
    echo the key, logger output from the agent that prints the token body-first).

    Backward-compatible: callers that pass only two positional arguments see identical
    behavior to the pre-widening implementation. Added 2026-04-16 per Phase 19 CONTEXT.md D-02.

    Applied to all ``detail`` strings derived from subprocess stderr per D-02 + V7/V8 of
    RESEARCH.md §Security Domain.
    """
    if not text:
        return ""
    out = re.sub(
        rf"{re.escape(api_key_var)}=\S+",
        f"{api_key_var}=<REDACTED>",
        text,
    )
    if api_key_val and len(api_key_val) >= 8:
        out = out.replace(api_key_val, "<REDACTED>")
    return out


def _clone_dir_for(name: str, ref: str | None) -> Path:
    """Derive a clone cache path keyed on both recipe name and source.ref.

    `/tmp/ap-recipe-<name>-<sha256(ref)[:12]>-clone`. Any ref change creates
    a new cache dir, so recipes that update `source.ref` get a fresh clone
    instead of silently running against the stale pin.

    When `ref` is None (no ref declared — shallow HEAD), a stable sentinel
    hash is used so the path is still deterministic and doesn't alias with
    any real ref.
    """
    ref_value = ref if ref is not None else "__noref__"
    digest = hashlib.sha256(ref_value.encode()).hexdigest()[:12]
    return Path(f"/tmp/ap-recipe-{name}-{digest}-clone")


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

        clone_dir = _clone_dir_for(recipe["name"], ref)
        if no_cache:
            # Wipe any stale clone dirs for this recipe name — across all refs.
            # Defense against leftover orphans from prior ref values.
            import glob
            for stale in glob.glob(f"/tmp/ap-recipe-{recipe['name']}-*-clone"):
                run(["rm", "-rf", stale], check=False)
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
                    rc3, _, se3, co_to = run_with_timeout(
                        ["git", "-C", str(clone_dir), "checkout", "FETCH_HEAD"],
                        timeout_s=60,
                    )
                    if co_to:
                        log(
                            "  WARN: checkout FETCH_HEAD timeout — using shallow HEAD",
                            quiet=quiet,
                        )
                    elif rc3 != 0:
                        tail = (se3 or "").strip().splitlines()[-1:] or [""]
                        log(
                            f"  WARN: checkout FETCH_HEAD failed (rc={rc3}): {tail[0][:200]} — using shallow HEAD",
                            quiet=quiet,
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
    agent_name: str | None = None,
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

    # Env file: keys delivered via `docker run -e KEY=VAL` leak to the kernel
    # process listing (ps / /proc/*/cmdline). `--env-file` reads at docker CLI
    # time and sets the var in the container without exposing the value on
    # the argv. Chmod 600, unlinked in finally below.
    env_file = Path(f"/tmp/ap-env-{uuid.uuid4().hex}")
    env_file.write_text(f"{api_key_var}={api_key_val}\n")
    try:
        env_file.chmod(0o600)
    except OSError:
        pass

    # Timeout precedence: explicit kwarg > recipe.smoke.timeout_s > default.
    smoke = recipe["smoke"]
    if smoke_timeout_s is None:
        smoke_timeout_s = int(smoke.get("timeout_s", DEFAULT_SMOKE_TIMEOUT_S))

    docker_cmd = [
        "docker", "run", "--rm",
        f"--cidfile={cidfile}",
        "--env-file", str(env_file),
        "-v", f"{data_dir}:{container_mount}",
    ]
    if entrypoint:
        docker_cmd += ["--entrypoint", entrypoint]
    docker_cmd += [image_tag] + argv

    log(f"  $ {' '.join(docker_cmd)}", quiet=quiet)

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
        # Cleanup order: data_dir, cidfile, env_file. All best-effort.
        if data_dir.exists():
            run(["rm", "-rf", str(data_dir)], check=False)
        try:
            cidfile.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            env_file.unlink(missing_ok=True)
        except OSError:
            pass

    wall = time.time() - t0

    # Classify the verdict.
    if timed_out:
        verdict_obj = Verdict(Category.TIMEOUT, timeout_reason or "")
        filtered = ""
        pass_if_str = smoke.get("pass_if", "")
    elif rc != 0:
        # Fix B (debug `hermes-invoke-fail-silent-stderr`, 2026-04-17):
        # Some agent CLIs suppress upstream-error output at their default log
        # level. If stderr is empty on a non-zero exit, fall back to the tail
        # of stdout so the user sees *something* instead of "docker run exit 1: ".
        stderr_stripped = (stderr or "").strip()
        if stderr_stripped:
            tail_line = stderr_stripped.splitlines()[-1]
            source = "stderr"
        else:
            stdout_lines = (stdout or "").strip().splitlines()
            tail_line = stdout_lines[-1] if stdout_lines else ""
            source = "stdout(tail)" if tail_line else "no output"
        detail = _redact_api_key(
            f"docker run exit {rc} [{source}]: {tail_line[:200]}",
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
            agent_name=agent_name,
        )
        if pass_if_result == "PASS":
            verdict_obj = Verdict(Category.PASS, "")
        else:
            verdict_obj = Verdict(
                Category.ASSERT_FAIL,
                f"pass_if evaluated {pass_if_result}",
            )

    # Fix B: if stderr is empty and we failed, surface stdout tail instead so
    # the RunResultCard accordion shows something useful to the user.
    if rc != 0 and not (stderr or "").strip():
        stderr_tail_src = (stdout or "")
        stderr_tail_prefix = "[stdout tail — stderr was empty]\n"
    else:
        stderr_tail_src = (stderr or "")
        stderr_tail_prefix = ""
    stderr_tail_lines = _redact_api_key(stderr_tail_src, api_key_var).splitlines()[-20:]
    stderr_tail_out = (stderr_tail_prefix + "\n".join(stderr_tail_lines)) or None

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
        "stderr_tail": stderr_tail_out,
    }
    return verdict_obj, details


# ---------- persistent-mode helpers (Phase 22) ----------


def _cleanup(env_file: Path, data_dir: Path) -> None:
    """Best-effort teardown of env-file + tempdir on failure paths."""
    try:
        env_file.unlink(missing_ok=True)
    except OSError:
        pass
    if data_dir.exists():
        subprocess.run(["rm", "-rf", str(data_dir)], check=False)


def _force_remove(container_id: str) -> None:
    """Best-effort `docker rm -f`. Swallows errors."""
    subprocess.run(
        ["docker", "rm", "-f", container_id],
        timeout=10, check=False, capture_output=True,
    )


def _redact_channel_creds(
    text: str,
    api_key_var: str,
    api_key_val: str,
    required_inputs: list,
    optional_inputs: list,
    channel_creds: dict[str, str],
    extra_secrets: tuple[str, ...] | list[str] = (),
) -> str:
    """Apply _redact_api_key for the API key + every secret channel cred.

    Covers both the `VAR=value` prefix form and (when the value is >= 8 chars)
    bare-value occurrences. Non-secret inputs are still redacted via the
    `VAR=` regex pass so stderr lines like `TELEGRAM_ALLOWED_USER=152099202`
    don't leak the numeric id.

    Phase 22c.3.1 (D-26 + RESEARCH §Risks §7): ``extra_secrets`` carries
    activation_substitutions values (e.g. ``INAPP_AUTH_TOKEN``,
    ``INAPP_PROVIDER_KEY``) that aren't in ``channel_creds`` but flow into
    the env-file. Each value with len ≥ 8 gets bare-substring replaced.
    Backwards-compat: defaults to empty tuple — existing callers unchanged.
    """
    out = _redact_api_key(text, api_key_var, api_key_val)
    for entry in (required_inputs or []) + (optional_inputs or []):
        var = entry.get("env")
        if not var:
            continue
        val = channel_creds.get(var)
        out = _redact_api_key(out, var, val if entry.get("secret") else None)
    # D-26: redact activation-time secrets (INAPP_AUTH_TOKEN, provider key).
    for s in (extra_secrets or ()):
        if s and len(s) >= 8:
            out = out.replace(s, "<REDACTED>")
    return out


def _build_env_file_content(
    api_key_var: str,
    api_key_val: str,
    required_inputs: list,
    optional_inputs: list,
    channel_creds: dict[str, str],
    rendered_activation_env: dict[str, str] | None = None,
) -> str:
    """Pure-function env-file builder (Phase 22c.3.1 — B-6 fix).

    Returns the env-file content as a single string (newline-terminated lines).
    Single source of truth for env-file shape — used by both the legacy
    code path (rendered_activation_env=None — D-27 byte-identical) AND the
    new override path (rendered_activation_env=<rendered dict> — D-24 overlay).

    Order:
      1. ``api_key_var=api_key_val``                (legacy first line)
      2. required_inputs + optional_inputs in order, with prefix_required
      3. rendered_activation_env entries (D-24 — last lines win on collision)

    Per docker ``--env-file`` semantics, later lines win for duplicate keys,
    so activation_env values OVERRIDE any colliding api_key/cred values.
    Do NOT deduplicate — duplicates are how the overlay works.
    """
    lines = [f"{api_key_var}={api_key_val}"]
    for entry in (required_inputs or []) + (optional_inputs or []):
        var = entry.get("env")
        if not var:
            continue
        val = channel_creds.get(var)
        if val is None or val == "":
            continue
        prefix = entry.get("prefix_required") or ""
        lines.append(f"{var}={prefix}{val}")
    if rendered_activation_env:
        for k, v in rendered_activation_env.items():
            lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n"


def run_cell_persistent(
    recipe: dict,
    *,
    image_tag: str,
    model: str,
    api_key_var: str,
    api_key_val: str,
    channel_id: str,
    channel_creds: dict[str, str],
    run_id: str,
    quiet: bool = True,
    boot_timeout_s: int = 180,
    activation_substitutions: dict[str, str] | None = None,
) -> tuple[Verdict, dict]:
    """Spawn a persistent container, poll readiness, return (Verdict, details).

    Delta from run_cell():
      - `docker run -d --name ap-agent-<run_id>` (NOT --rm)
      - argv sourced from recipe["persistent"]["spec"]["argv"]
      - env-file contains BOTH api_key_var=api_key_val AND every
        channel_creds entry (plus prefix_required transforms)
      - polls `docker logs <cid>` for persistent.spec.ready_log_regex
        within boot_timeout_s
      - once ready, runs health_check probe (process_alive or http)
      - returns container_id + ready_at + boot_wall_s in details dict

    Phase 22c.3.1 (D-04..D-08, D-12..D-15, D-24, D-25, D-27, D-31, D-32, D-34
    + AMD-37): when ``channels[channel_id].persistent_argv_override`` is
    declared AND ``activation_substitutions`` is non-None, switch to the
    "channel-aware override" code path:
      * read override.entrypoint / argv / pre_start_commands / user_override
      * render placeholders (${VAR}, $VAR, {key}) in argv + entrypoint +
        activation_env using activation_substitutions
      * allocate data_dir + env_file UPFRONT (D-34); env-file content built
        via _build_env_file_content with rendered_activation_env overlay
        (D-24 — last lines win)
      * run pre_start_commands as `docker run --rm` per command (D-04..D-08),
        with --cidfile + PRE_START_COMMAND_TIMEOUT_S timeout (D-25, D-32)
      * reset boot timeout budget after pre_start (D-31 — Risks §8)
      * docker run -d the daemon with rendered argv + entrypoint
      * details["pre_start_wall_s"] + details["boot_wall_s"] = sum (D-31)

    When the gate is closed (override absent OR activation_substitutions=None),
    fall through to the legacy code path — D-27 byte-identical invariant
    enforced via the `test_run_recipe_telegram_invariant.py` snapshot test.

    The caller (runner_bridge in Plan 22-04) is responsible for persisting
    the container_id to the agent_containers table and for invoking
    stop_persistent() with the matching graceful_shutdown_s + sigterm_handled
    values on teardown.
    """
    # 1. Validate recipe has persistent + channel blocks.
    persistent = recipe.get("persistent")
    if not persistent:
        raise RuntimeError(f"recipe {recipe['name']!r} has no persistent block")
    spec = persistent.get("spec") or {}
    if not spec.get("argv"):
        raise RuntimeError(
            f"recipe {recipe['name']!r} persistent.spec.argv is required"
        )
    if not spec.get("ready_log_regex"):
        raise RuntimeError(
            f"recipe {recipe['name']!r} persistent.spec.ready_log_regex is required"
        )
    if not spec.get("health_check"):
        raise RuntimeError(
            f"recipe {recipe['name']!r} persistent.spec.health_check is required"
        )
    channels = recipe.get("channels") or {}
    channel = channels.get(channel_id)
    if not channel:
        raise RuntimeError(
            f"recipe {recipe['name']!r} does not support channel {channel_id!r}"
        )

    required_inputs = list(channel.get("required_user_input") or [])
    optional_inputs = list(channel.get("optional_user_input") or [])

    # Validate all REQUIRED entries are present in channel_creds.
    missing = [e["env"] for e in required_inputs if e["env"] not in channel_creds
               or channel_creds.get(e["env"]) in (None, "")]
    if missing:
        raise RuntimeError(
            f"channel {channel_id} missing required inputs: {missing}"
        )

    # AMD-37 + D-27: gate the new path. Original AMD-37 said both
    # `persistent_argv_override is not None` AND `activation_substitutions
    # is not None` must hold. EXTENSION (Rule-1 fix discovered during
    # Task 3 e2e gate): hermes inapp declares `activation_env` but NO
    # `persistent_argv_override`. The legacy code path drops activation_env
    # on the floor → the daemon never gets `API_SERVER_ENABLED=true` →
    # ready_log never matches → 240s timeout. To make the e2e gate work
    # for ALL 5 recipes (including hermes), the gate now opens when EITHER
    # `persistent_argv_override` OR `activation_env` is declared (in
    # addition to the activation_substitutions conjunct). Telegram still
    # falls through (no override + no activation_env in the telegram
    # block) — D-27 byte-identical invariant preserved (verified by
    # `test_run_recipe_telegram_invariant.py::test_telegram_unchanged*`).
    override_raw = channel.get("persistent_argv_override")
    activation_env_decl = channel.get("activation_env")
    channel_ready_log = channel.get("ready_log_regex")
    has_override_argv = bool(
        override_raw
        and isinstance(override_raw, dict)
        and override_raw.get("argv")
    )
    has_activation_env = bool(
        activation_env_decl
        and isinstance(activation_env_decl, dict)
    )
    gate_open = bool(
        activation_substitutions is not None
        and (has_override_argv or has_activation_env)
    )

    # Common: per-recipe volume mount target.
    vol = recipe["runtime"]["volumes"][0]
    container_mount = vol["container"]
    container_name = f"ap-agent-{run_id}"
    image_default_user = spec.get("user_override")  # may be overridden below

    # Common: secrets list for redaction (D-26 + RESEARCH §Risks §7).
    extra_secrets: tuple[str, ...] = ()
    if activation_substitutions:
        extra_secrets = tuple(
            v for v in activation_substitutions.values()
            if isinstance(v, str) and len(v) >= 8
        )

    if gate_open:
        # ===================================================================
        # NEW PATH — channel-aware override + activation_env overlay +
        # pre_start_commands loop with cidfile cleanup (Phase 22c.3.1).
        # When persistent_argv_override is declared, it sources argv +
        # entrypoint + pre_start_commands. When ONLY activation_env is
        # declared (e.g. hermes inapp), argv + entrypoint fall back to
        # `recipe.persistent.spec.*` and pre_start_specs is empty.
        # ===================================================================
        if has_override_argv:
            override = override_raw
            entrypoint = override.get("entrypoint")
            argv_raw = list(override.get("argv") or [])
            pre_start_specs = list(override.get("pre_start_commands") or [])
            user_override = override.get("user_override") or image_default_user
        else:
            # activation_env-only path (hermes shape) — keep legacy argv/
            # entrypoint, just inject the activation_env overlay into the
            # env-file. No pre_start_commands.
            entrypoint = spec.get("entrypoint")
            argv_raw = list(spec.get("argv") or [])
            pre_start_specs = []
            user_override = image_default_user
        activation_env_raw = activation_env_decl or {}
        if not isinstance(activation_env_raw, dict):
            activation_env_raw = {}

        # 2. Render placeholders.
        if has_override_argv:
            # Recipe authors who declare an override are responsible for
            # using activation-time placeholder syntax (${VAR}/$VAR/{key}).
            argv = [
                str(render_placeholders(a, activation_substitutions))
                for a in argv_raw
            ]
        else:
            # Legacy argv comes from persistent.spec.argv; substitute_argv
            # handles its $PROMPT/$MODEL shape (D-27 byte-identical for
            # this slice of behavior).
            argv = substitute_argv(list(argv_raw), prompt="", model=model)
        if entrypoint:
            entrypoint = str(
                render_placeholders(entrypoint, activation_substitutions)
            )
        rendered_env: dict[str, str] = {
            str(k): str(render_placeholders(v, activation_substitutions))
            for k, v in activation_env_raw.items()
        }

        # 3. Allocate data_dir + env_file UPFRONT (D-34 — pre_start needs
        # both volumes mounted, so they MUST exist before the loop).
        data_dir = Path(
            tempfile.mkdtemp(prefix=f"ap-recipe-{recipe['name']}-data-")
        )
        env_file = Path(f"/tmp/ap-env-{uuid.uuid4().hex}")
        env_file.write_text(_build_env_file_content(
            api_key_var, api_key_val,
            required_inputs, optional_inputs,
            channel_creds,
            rendered_activation_env=rendered_env,
        ))
        try:
            env_file.chmod(0o600)
        except OSError:
            pass

        # 4. Pre-start loop. Each command runs as `docker run --rm` with
        # --cidfile + PRE_START_COMMAND_TIMEOUT_S timeout. State accumulates
        # in data_dir.
        pre_start_t0 = time.time()
        for pre in pre_start_specs:
            pre_argv_raw = pre.get("argv") if isinstance(pre, dict) else None
            if not pre_argv_raw:
                continue
            pre_argv_rendered = [
                str(render_placeholders(a, activation_substitutions))
                for a in pre_argv_raw
            ]
            if not pre_argv_rendered:
                continue
            pre_entry = pre_argv_rendered[0]
            pre_args = pre_argv_rendered[1:]
            pre_cidfile = Path(f"/tmp/ap-pre-cid-{uuid.uuid4().hex}.cid")
            pre_cmd = [
                "docker", "run", "--rm",
                f"--cidfile={pre_cidfile}",
                "--env-file", str(env_file),
                "-v", f"{data_dir}:{container_mount}",
                "--entrypoint", pre_entry,
            ]
            if user_override:
                pre_cmd += ["--user", str(user_override)]
            pre_cmd += [image_tag, *pre_args]
            log(
                f"  $ docker run --rm pre_start [argv elided]",
                quiet=quiet,
            )
            try:
                ex = subprocess.run(
                    pre_cmd,
                    timeout=PRE_START_COMMAND_TIMEOUT_S,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                # D-32: cidfile-kill the hung container.
                try:
                    cid = pre_cidfile.read_text().strip()
                    if cid:
                        subprocess.run(
                            ["docker", "kill", cid],
                            timeout=10, check=False, capture_output=True,
                        )
                        subprocess.run(
                            ["docker", "rm", "-f", cid],
                            timeout=10, check=False, capture_output=True,
                        )
                except OSError:
                    pass
                try:
                    pre_cidfile.unlink(missing_ok=True)
                except OSError:
                    pass
                _cleanup(env_file, data_dir)
                raise RuntimeError(
                    f"pre_start_command timed out after "
                    f"{PRE_START_COMMAND_TIMEOUT_S}s: {pre_entry} "
                    f"{' '.join(pre_args)[:100]}"
                )
            finally:
                try:
                    pre_cidfile.unlink(missing_ok=True)
                except OSError:
                    pass

            if ex.returncode != 0:
                tail = _redact_channel_creds(
                    ex.stderr or "",
                    api_key_var, api_key_val,
                    required_inputs, optional_inputs, channel_creds,
                    extra_secrets=extra_secrets,
                )
                _cleanup(env_file, data_dir)
                raise RuntimeError(
                    f"pre_start_command failed rc={ex.returncode}: "
                    f"{pre_entry} {' '.join(pre_args)[:50]} "
                    f"stderr={tail[-200:]}"
                )
        pre_start_wall_s = round(time.time() - pre_start_t0, 2)

        # 5. Build daemon docker run command. Reset t0 (D-31 — boot_timeout_s
        # applies only to the persistent container's ready-poll budget, NOT
        # to the pre_start loop total).
        # AP_DOCKER_NETWORK: pin the spawned container onto the same docker
        # network as api_server (default deploy_default). Without this the
        # container lands on the host's default bridge (172.17.x) and the
        # api_server's inapp_dispatcher cannot resolve its IP for HTTP
        # forwarding (Networks[<docker_network_name>].IPAddress is empty).
        docker_network = os.environ.get("AP_DOCKER_NETWORK", "").strip()
        docker_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--env-file", str(env_file),
            "-v", f"{data_dir}:{container_mount}",
        ]
        if docker_network:
            docker_cmd += ["--network", docker_network]
        if user_override:
            docker_cmd += ["--user", str(user_override)]
        if entrypoint:
            docker_cmd += ["--entrypoint", entrypoint]
        docker_cmd += [image_tag] + argv

        log(
            f"  $ docker run -d --name {container_name} "
            f"{'--network ' + docker_network + ' ' if docker_network else ''}"
            f"... {image_tag} [argv elided]",
            quiet=quiet,
        )

        t0 = time.time()
        try:
            result = subprocess.run(
                docker_cmd, timeout=30, capture_output=True, text=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            _cleanup(env_file, data_dir)
            raise RuntimeError("docker run -d timed out after 30s")
    else:
        # ===================================================================
        # LEGACY PATH — D-27 byte-identical invariant. Steps verbatim from
        # pre-Phase-22c.3.1 main HEAD, with the env-file write routed through
        # _build_env_file_content (rendered_activation_env=None) per B-6 fix
        # so there's a single source of truth for env-file shape. The Wave 0
        # snapshot test enforces byte-identical output for this branch.
        # ===================================================================
        pre_start_wall_s = 0.0

        # 2. Assemble argv with model substitution (no $PROMPT in persistent mode).
        raw_argv = spec["argv"]
        argv = substitute_argv(list(raw_argv), prompt="", model=model)

        # 3. Build env-file via the shared helper (rendered_activation_env=None
        # so output is byte-identical to the legacy direct-write).
        env_file = Path(f"/tmp/ap-env-{uuid.uuid4().hex}")
        env_file.write_text(_build_env_file_content(
            api_key_var, api_key_val,
            required_inputs, optional_inputs,
            channel_creds,
            rendered_activation_env=None,
        ))
        try:
            env_file.chmod(0o600)
        except OSError:
            pass

        # 4. Build docker run command — DETACHED + NAMED + no --rm.
        entrypoint = spec.get("entrypoint")
        user_override = image_default_user
        data_dir = Path(
            tempfile.mkdtemp(prefix=f"ap-recipe-{recipe['name']}-data-")
        )

        # AP_DOCKER_NETWORK: same fix as the channel-aware path above.
        docker_network = os.environ.get("AP_DOCKER_NETWORK", "").strip()
        docker_cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--env-file", str(env_file),
            "-v", f"{data_dir}:{container_mount}",
        ]
        if docker_network:
            docker_cmd += ["--network", docker_network]
        if user_override:
            docker_cmd += ["--user", user_override]
        if entrypoint:
            docker_cmd += ["--entrypoint", entrypoint]
        docker_cmd += [image_tag] + argv

        log(
            f"  $ docker run -d --name {container_name} "
            f"{'--network ' + docker_network + ' ' if docker_network else ''}"
            f"... {image_tag} [argv elided]",
            quiet=quiet,
        )

        # 5. Execute `docker run -d`, capture container_id from stdout.
        t0 = time.time()
        try:
            result = subprocess.run(
                docker_cmd, timeout=30, capture_output=True, text=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            _cleanup(env_file, data_dir)
            raise RuntimeError("docker run -d timed out after 30s")

    if result.returncode != 0:
        _cleanup(env_file, data_dir)
        stderr = _redact_channel_creds(
            result.stderr or "", api_key_var, api_key_val,
            required_inputs, optional_inputs, channel_creds,
            extra_secrets=extra_secrets,
        )
        persistent_wall = round(time.time() - t0, 2)
        return Verdict(
            Category.INVOKE_FAIL,
            f"docker run -d exit {result.returncode}: {stderr[:200]}",
        ), {
            "recipe": recipe["name"],
            "model": model,
            "channel": channel_id,
            "container_name": container_name,
            "boot_wall_s": round(pre_start_wall_s + persistent_wall, 2),
            "pre_start_wall_s": pre_start_wall_s,
        }

    container_id = (result.stdout or "").strip()
    if not container_id:
        _cleanup(env_file, data_dir)
        raise RuntimeError("docker run -d produced empty container id")

    # 6. Poll `docker logs <container_id>` for ready_log_regex.
    # When the new path is active (gate_open) and the channel block declares
    # its own ready_log_regex, use it — recipes layer it on the inapp channel
    # so the runner waits for the inapp daemon's "listening" line, not the
    # default (telegram-shaped) spec line. Telegram path keeps spec value:
    # gate_open=False there, so byte-identical behavior preserved (D-27).
    ready_log_pattern = (
        channel_ready_log if (gate_open and channel_ready_log)
        else spec["ready_log_regex"]
    )
    ready_regex = re.compile(ready_log_pattern)
    deadline = t0 + boot_timeout_s
    ready = False
    while time.time() < deadline:
        logs_result = subprocess.run(
            ["docker", "logs", "--tail", "200", container_id],
            timeout=10, capture_output=True, text=True, check=False,
        )
        combined = (logs_result.stdout or "") + "\n" + (logs_result.stderr or "")
        if ready_regex.search(combined):
            ready = True
            break
        # Fail fast if container exited before ready_log matched.
        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
            timeout=5, capture_output=True, text=True, check=False,
        )
        if (inspect.stdout or "").strip() != "true":
            exit_code_res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.ExitCode}}", container_id],
                timeout=5, capture_output=True, text=True, check=False,
            )
            try:
                exit_code = int((exit_code_res.stdout or "").strip())
            except ValueError:
                exit_code = -1
            _force_remove(container_id)
            _cleanup(env_file, data_dir)
            redacted_logs = _redact_channel_creds(
                combined[-500:], api_key_var, api_key_val,
                required_inputs, optional_inputs, channel_creds,
                extra_secrets=extra_secrets,
            )
            persistent_wall = round(time.time() - t0, 2)
            return Verdict(
                Category.INVOKE_FAIL,
                f"container exited (code={exit_code}) before ready: "
                f"{redacted_logs[-200:]}",
            ), {
                "recipe": recipe["name"],
                "model": model,
                "channel": channel_id,
                "container_id": container_id,
                "container_name": container_name,
                "boot_wall_s": round(pre_start_wall_s + persistent_wall, 2),
                "pre_start_wall_s": pre_start_wall_s,
                "exit_code": exit_code,
            }
        time.sleep(2)

    if not ready:
        _force_remove(container_id)
        _cleanup(env_file, data_dir)
        persistent_wall = round(time.time() - t0, 2)
        return Verdict(
            Category.TIMEOUT,
            f"ready_log_regex not matched within {boot_timeout_s}s",
        ), {
            "recipe": recipe["name"],
            "model": model,
            "channel": channel_id,
            "container_id": container_id,
            "container_name": container_name,
            "boot_wall_s": round(pre_start_wall_s + persistent_wall, 2),
            "pre_start_wall_s": pre_start_wall_s,
        }

    # 7. Health check probe (log-match already proves readiness; HC is
    #    a secondary signal for the status endpoint).
    hc = spec["health_check"]
    hc_ok = False
    if hc["kind"] == "process_alive":
        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
            timeout=5, capture_output=True, text=True, check=False,
        )
        hc_ok = (inspect.stdout or "").strip() == "true"
    elif hc["kind"] == "http":
        port = hc["port"]
        path = hc.get("path") or "/"
        url = f"http://127.0.0.1:{port}{path}"
        # Alpine-based images may lack curl; fall back to wget.
        probe = subprocess.run(
            ["docker", "exec", container_id, "sh", "-c",
             f"curl -fsS -m 5 {shlex.quote(url)} "
             f"|| wget -q -O- --timeout=5 {shlex.quote(url)}"],
            timeout=15, capture_output=True, text=True, check=False,
        )
        hc_ok = probe.returncode == 0
    else:
        # Do not fail the boot on unknown health_check kind — log match wins.
        log(f"  WARN: unknown health_check kind: {hc['kind']!r}", quiet=quiet)
        hc_ok = False

    # 8. Return success details. Env-file is safe to unlink NOW — docker CLI
    #    has already read it and delivered env vars to the container's kernel
    #    namespace. data_dir stays until stop (container references its mount).
    #
    # D-31: boot_wall_s is the SUM of pre_start_wall_s + persistent ready
    # poll wall — operators see end-to-end latency. pre_start_wall_s is
    # exposed as a sub-field for diagnostics.
    ready_at = datetime.now(timezone.utc)
    persistent_wall = round(time.time() - t0, 2)
    boot_wall_s = round(pre_start_wall_s + persistent_wall, 2)
    try:
        env_file.unlink(missing_ok=True)
    except OSError:
        pass

    details = {
        "recipe": recipe["name"],
        "model": model,
        "channel": channel_id,
        "container_id": container_id,
        "container_name": container_name,
        "ready_at": ready_at.isoformat(),
        "boot_wall_s": boot_wall_s,
        "pre_start_wall_s": pre_start_wall_s,
        "ready_log_matched": True,
        "health_check_ok": hc_ok,
        "health_check_kind": hc["kind"],
        "data_dir": str(data_dir),
    }
    return Verdict(Category.PASS, ""), details


def stop_persistent(
    container_id: str,
    *,
    graceful_shutdown_s: int,
    sigterm_handled: bool = True,
    recipe_name: str | None = None,
    data_dir: str | None = None,
    quiet: bool = True,
) -> tuple[Verdict, dict]:
    """Gracefully stop a persistent container.

    When sigterm_handled=False (e.g. nanobot — spike-07), skip the SIGTERM +
    poll phase and go directly to `docker rm -f`. This is the documented
    normal path for that recipe; log as a warning, not an error. Returns
    with force_killed=True.

    Steps:
      1. If sigterm_handled: `docker kill -s TERM <cid>`
      2. Poll `docker inspect State.Running` every 500ms until either False
         or graceful_shutdown_s elapsed
      3. Always `docker rm -f <cid>` (idempotent — removes whether already
         exited or still running)
      4. rm -rf data_dir if provided
    """
    t0 = time.time()
    stopped_gracefully = False
    force_killed = False

    if not sigterm_handled:
        # Recipe explicitly opts out of graceful shutdown (e.g. nanobot).
        # This IS the normal path for that recipe — warning, not error.
        if not quiet:
            print(
                f"WARN graceful shutdown skipped for recipe={recipe_name or '?'};"
                f" force-killed per recipe flag"
            )
        force_killed = True
    else:
        # Step 1: SIGTERM
        subprocess.run(
            ["docker", "kill", "-s", "TERM", container_id],
            timeout=10, capture_output=True, check=False,
        )
        # Step 2: poll for graceful exit.
        deadline = t0 + graceful_shutdown_s
        while time.time() < deadline:
            inspect = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_id],
                timeout=5, capture_output=True, text=True, check=False,
            )
            if (inspect.stdout or "").strip() != "true":
                stopped_gracefully = True
                break
            time.sleep(0.5)
        if not stopped_gracefully:
            force_killed = True

    # Step 3: capture exit code then force remove (idempotent — works whether
    # the container exited cleanly or is still running).
    exit_code_res = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.ExitCode}}", container_id],
        timeout=5, capture_output=True, text=True, check=False,
    )
    try:
        exit_code = int((exit_code_res.stdout or "").strip())
    except ValueError:
        exit_code = -1
    subprocess.run(
        ["docker", "rm", "-f", container_id],
        timeout=10, capture_output=True, check=False,
    )
    # Step 4: cleanup data_dir.
    if data_dir:
        p = Path(data_dir)
        if p.exists():
            subprocess.run(["rm", "-rf", str(p)], check=False)

    stop_wall_s = round(time.time() - t0, 2)
    return Verdict(Category.PASS, ""), {
        "container_id": container_id,
        "exit_code": exit_code,
        "stopped_gracefully": stopped_gracefully,
        "force_killed": force_killed,
        "stop_wall_s": stop_wall_s,
    }


def exec_in_persistent(
    container_id: str,
    argv: list[str],
    *,
    timeout_s: int = 30,
) -> tuple[Verdict, dict]:
    """Run a command inside a running persistent container via `docker exec`.

    First caller is POST /v1/agents/:id/channels/:cid/pair with argv
    ["openclaw", "pairing", "approve", "telegram", "<CODE>"]. Output is NOT
    redacted here — the caller (runner_bridge / route) owns key/token
    redaction in responses. Typical callers pass short non-sensitive codes.
    """
    t0 = time.time()
    try:
        result = subprocess.run(
            ["docker", "exec", container_id] + argv,
            timeout=timeout_s, capture_output=True, text=True, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        wall = round(time.time() - t0, 2)
        so = exc.stdout or b""
        se = exc.stderr or b""
        if isinstance(so, bytes):
            so = so.decode(errors="replace")
        if isinstance(se, bytes):
            se = se.decode(errors="replace")
        return Verdict(Category.TIMEOUT, f"exec exceeded {timeout_s}s"), {
            "container_id": container_id,
            "exit_code": -1,
            "stdout_tail": so[-500:],
            "stderr_tail": se[-500:],
            "wall_time_s": wall,
        }
    wall = round(time.time() - t0, 2)
    verdict = Verdict(
        Category.PASS if result.returncode == 0 else Category.INVOKE_FAIL,
        "" if result.returncode == 0 else f"exec exit {result.returncode}",
    )
    return verdict, {
        "container_id": container_id,
        "exit_code": result.returncode,
        "stdout_tail": (result.stdout or "")[-500:],
        "stderr_tail": (result.stderr or "")[-500:],
        "wall_time_s": wall,
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
    # Phase 22 persistent-mode flags (manual testing seam; API runner_bridge
    # is the primary interface).
    p.add_argument(
        "--mode",
        choices=["smoke", "persistent"],
        default="smoke",
        help="smoke runs the one-shot; persistent spawns a long-lived container.",
    )
    p.add_argument(
        "--channel",
        default="telegram",
        help="channel id for --mode persistent (default: telegram).",
    )
    p.add_argument(
        "--channel-creds-env-prefix",
        default="AP_CHANNEL_",
        help=(
            "In --mode persistent, channel creds are read from env vars matching"
            " this prefix (e.g. AP_CHANNEL_TELEGRAM_BOT_TOKEN -> TELEGRAM_BOT_TOKEN)."
            " Keeps shell history free of secrets and avoids fragile quoting."
        ),
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="Container name suffix (default: fresh uuid4 hex). Container name"
             " becomes ap-agent-<run_id>.",
    )
    p.add_argument(
        "--boot-timeout-s",
        type=int,
        default=180,
        help="Seconds to wait for persistent.spec.ready_log_regex to match.",
    )
    p.add_argument(
        "--stop",
        metavar="CONTAINER_ID",
        default=None,
        help="Stop a persistent container gracefully (SIGTERM -> wait -> rm -f).",
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

    # Step 2.5: --stop short-circuit (Phase 22 persistent mode teardown).
    # Does not need a recipe — the container_id is self-describing. We pass
    # graceful_shutdown_s=10 as a safe upper bound; the runner_bridge caller
    # in Plan 22-04 threads the recipe's actual value.
    if args.stop:
        infra = preflight_docker()
        if infra is not None:
            emit_verdict_line(infra, recipe="(pre-flight)", model="", wall_s=0.0)
            return 1
        verdict, details = stop_persistent(args.stop, graceful_shutdown_s=10)
        print(json.dumps({"verdict": verdict.verdict, **details}, indent=2))
        return 0 if verdict.verdict == "PASS" else 1

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

    # Step 8.5: --mode persistent dispatch (Phase 22 manual-testing seam).
    # The API runner_bridge (Plan 22-04) is the primary caller of
    # run_cell_persistent; this path lets developers exercise the primitive
    # from a shell without the API in the loop.
    if args.mode == "persistent":
        if args.all_cells:
            sys.stderr.write(
                "--all-cells is incompatible with --mode persistent "
                "(persistent is not a cell sweep)\n"
            )
            return 2
        channel_id = args.channel
        channel_block = (recipe.get("channels") or {}).get(channel_id) or {}
        if not channel_block:
            sys.stderr.write(
                f"recipe {name} has no channels.{channel_id} block\n"
            )
            return 2
        required = channel_block.get("required_user_input") or []
        optional = channel_block.get("optional_user_input") or []
        creds: dict[str, str] = {}
        for entry in required + optional:
            env_key = f"{args.channel_creds_env_prefix}{entry['env']}"
            val = os.environ.get(env_key)
            if val:
                creds[entry["env"]] = val
        missing = [e["env"] for e in required if e["env"] not in creds]
        if missing:
            sys.stderr.write(
                f"missing required channel creds (env "
                f"{args.channel_creds_env_prefix}*): {missing}\n"
            )
            return 2
        # Model: CLI positional arg wins; else first PASS cell.
        model = args.model or first_pass_cell_model(recipe)
        if model is None:
            sys.stderr.write(
                "ERROR: no model on CLI and no PASS verified_cell to fall back on\n"
            )
            return 2
        run_id = args.run_id or uuid.uuid4().hex[:12]
        log(f"\n--- persistent: {name} × {model} × {channel_id} "
            f"(run_id={run_id}) ---", quiet=quiet)
        verdict_obj, details = run_cell_persistent(
            recipe,
            image_tag=image_tag,
            model=model,
            api_key_var=api_key_var,
            api_key_val=api_key_val,
            channel_id=channel_id,
            channel_creds=creds,
            run_id=run_id,
            quiet=quiet,
            boot_timeout_s=args.boot_timeout_s,
        )
        out = {
            "verdict": verdict_obj.verdict,
            "category": verdict_obj.category.value,
            "detail": verdict_obj.detail,
            **details,
        }
        print(json.dumps(out, indent=2))
        if verdict_obj.verdict != "PASS":
            return 1
        print(f"\ncontainer is running. To stop it:")
        print(f"  python tools/run_recipe.py --stop {details['container_id']}")
        return 0

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
