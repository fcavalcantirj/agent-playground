# Phase 10: error-taxonomy-timeout-enforcement — Pattern Map

**Mapped:** 2026-04-16
**Files analyzed:** 10 (2 modified Python/JSON, 5 migrated YAML, 1 new test module, 1 optional new script, 1 doc stub)
**Analogs found:** 10 / 10 (all in-repo; no foreign reference needed)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tools/run_recipe.py` (MODIFY) | runner / script | request-response + file-I/O | itself (extend existing functions) | exact (self-extension) |
| `tools/ap.recipe.schema.json` (MODIFY) | schema / config | declarative validation | itself (extend existing schema) | exact (self-extension) |
| `recipes/hermes.yaml` (MODIFY) | data / recipe YAML | batch / data-at-rest | itself + other 4 recipes | exact (self-migration) |
| `recipes/openclaw.yaml` (MODIFY) | data / recipe YAML | batch / data-at-rest | itself + hermes | exact |
| `recipes/picoclaw.yaml` (MODIFY) | data / recipe YAML | batch / data-at-rest | itself + hermes | exact |
| `recipes/nullclaw.yaml` (MODIFY) | data / recipe YAML | batch / data-at-rest | itself + hermes | exact |
| `recipes/nanobot.yaml` (MODIFY) | data / recipe YAML | batch / data-at-rest | itself + hermes | exact |
| `tools/tests/test_categories.py` (CREATE) | test module | unit tests + mock-subprocess | `tools/tests/test_pass_if.py` | exact |
| `tools/tests/conftest.py` (MODIFY — extend fixture) | test fixture | mock injection | itself (extend `mock_subprocess`) | exact (self-extension) |
| `scripts/migrate_recipes_phase10.py` (CREATE — optional one-shot) | migration / script | file-I/O (YAML round-trip) | `tools/run_recipe.py::writeback_cell` | role-match |
| `docs/RECIPE-SCHEMA.md` (MODIFY — placeholder banner) | docs | declarative reference | itself (extend §6.3) | exact |

## Pattern Assignments

### `tools/run_recipe.py` (runner, request-response + file-I/O)

**Analog:** itself — this phase extends the existing module. Every new code path has a local template.

#### Imports pattern (lines 11-26) — extend, do NOT reshuffle

```python
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
```

**Phase 10 adds:** `import uuid` (cidfile name), `from dataclasses import dataclass`, `from enum import Enum`. Keep them in the stdlib alphabetical block with the existing `argparse…time` group; do not regroup. `uuid` goes right after `tempfile` (matches existing alpha ordering).

#### Module-level constants pattern (lines 41-49)

```python
DISK_GUARD_FLOOR_GB = 5.0

_SCHEMA_PATH = Path(__file__).parent / "ap.recipe.schema.json"

# ANSI colors for lint output (D-08)
_RED = "\033[31m"
_GREEN = "\033[32m"
_BOLD = "\033[1m"
_RESET = "\033[0m"
```

**Phase 10 adds** (same band, before `# ANSI colors`):
- `DEFAULT_SMOKE_TIMEOUT_S = 180`
- `DEFAULT_BUILD_TIMEOUT_S = 900`
- `DEFAULT_CLONE_TIMEOUT_S = 300`
- `DOCKER_DAEMON_PROBE_TIMEOUT_S = 5`

And the `Category(str, Enum)` + `@dataclass(frozen=True) Verdict` per RESEARCH.md §Pattern 1–2.

#### Importable-API section header pattern (lines 52-58)

```python
# ---------- importable API ----------


def _load_schema() -> dict:
    """Load the JSON Schema from the co-located schema file."""
    return json.loads(_SCHEMA_PATH.read_text())
```

**Phase 10 adds:** a new `# ---------- category taxonomy ----------` section header between `# ---------- importable API ----------` and the `_load_schema` function. `Category` and `Verdict` live there — they're imported by `tools/tests/test_categories.py`, so they're part of the public importable API alongside `load_recipe`, `lint_recipe`, and `evaluate_pass_if`.

#### Subprocess invocation pattern (lines 139-150)

```python
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
```

**Phase 10:** this helper is the existing subprocess wrapper — **do not replace it**. The TIMEOUT path needs direct `subprocess.run(..., timeout=…)` with cidfile handling, which is a different shape. Implement `run_cell_with_timeout()` as a new sibling helper, leaving `run()` alone for all non-container invocations (`docker build`, `docker pull`, `git clone`, `rm -rf`, `awk`, `docker image inspect`).

Pattern to copy for `run()`-style call sites that need a timeout but no cidfile (`docker build`, `git clone`):

```python
# Phase 10 pattern — add timeout kwarg to existing run() call sites via new helper
def run_with_timeout(cmd, *, timeout_s: int, capture: bool = True) -> tuple[int, str, str, bool]:
    """Wrap subprocess.run with a timeout. Returns (rc, stdout, stderr, timed_out)."""
    try:
        r = subprocess.run(cmd, timeout=timeout_s, capture_output=capture, text=True, check=False)
        return r.returncode, r.stdout or "", r.stderr or "", False
    except subprocess.TimeoutExpired as exc:
        so = exc.stdout or ""
        se = exc.stderr or ""
        if isinstance(so, bytes): so = so.decode(errors="replace")
        if isinstance(se, bytes): se = se.decode(errors="replace")
        return -1, so, se, True
```

#### API-key redaction pattern (lines 402-406)

```python
safe_cmd = [
    a if not a.startswith(f"{api_key_var}=") else f"{api_key_var}=<REDACTED>"
    for a in docker_cmd
]
log(f"  $ {' '.join(safe_cmd)}", quiet=quiet)
```

**Phase 10 MUST apply this same redaction** to any `detail` string derived from subprocess stderr. Add a helper:

```python
def _redact_api_key(text: str, api_key_var: str) -> str:
    """Replace any <api_key_var>=<value> in text with <api_key_var>=<REDACTED>."""
    import re as _re
    return _re.sub(rf"{_re.escape(api_key_var)}=\S+", f"{api_key_var}=<REDACTED>", text)
```

Apply before building `Verdict(Category.X, detail=…)` whenever `detail` is derived from stderr. Maps to RESEARCH.md §Security Domain "API key leak via stderr".

#### `run_cell()` existing shape (lines 375-439) — this is the primary target

```python
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
    # ...
    docker_cmd = [
        "docker", "run", "--rm",
        "-e", f"{api_key_var}={api_key_val}",
        "-v", f"{data_dir}:{container_mount}",
    ]
    # ...
    t0 = time.time()
    try:
        rc, stdout, stderr = run(docker_cmd, check=False, capture=True)
    finally:
        if data_dir.exists():
            run(["rm", "-rf", str(data_dir)], check=False)
    wall = time.time() - t0
    # ...
    return {
        "recipe": recipe["name"],
        "model": model,
        # ...
        "verdict": verdict,
        "exit_code": rc,
        "wall_time_s": round(wall, 2),
        # ...
    }
```

**Phase 10 change:**
1. Change return type from `dict` → `Verdict` (or `dict` augmented with `category` + `detail` — planner's call; RESEARCH.md recommends `Verdict` dataclass with a `to_cell_dict()` adapter for the existing JSON emission).
2. Inject `--cidfile` into `docker_cmd` immediately after `--rm`:
   ```python
   cidfile = Path(f"/tmp/ap-cid-{uuid.uuid4().hex}.cid")
   docker_cmd = [
       "docker", "run", "--rm", f"--cidfile={cidfile}",
       "-e", f"{api_key_var}={api_key_val}", ...
   ]
   ```
3. Replace the `run(docker_cmd, check=False, capture=True)` call with the timeout-aware body from RESEARCH.md §Pattern 3. The existing `try/finally` that cleans `data_dir` stays; add `cidfile.unlink(missing_ok=True)` to the same `finally`.
4. On `TimeoutExpired`: reap via `docker kill <cid>` + `docker rm -f <cid>`, return `Verdict(Category.TIMEOUT, detail=f"exceeded smoke.timeout_s={timeout_s}s")`.
5. On `rc != 0` with no timeout: return `Verdict(Category.INVOKE_FAIL, detail=redact(stderr_tail))`.
6. On `rc == 0`: keep existing `evaluate_pass_if()` call; map PASS → `Verdict(Category.PASS, "")`, FAIL → `Verdict(Category.ASSERT_FAIL, "pass_if evaluated FAIL")`.

#### `ensure_image()` existing shape (lines 301-370) — produces BUILD_FAIL / PULL_FAIL / CLONE_FAIL

Currently raises `SystemExit` on any subprocess failure (via `run(…, check=True)` defaults). Phase 10 must convert this to return a `Verdict | None` so the outer loop can emit a categorized failure instead of an uncaught exit.

Pattern: wrap each `run([...])` call site with a category classification:

| Current call site | Line | Phase 10 category |
|---|---|---|
| `run(["git", "clone", "--depth=1", repo_url, str(clone_dir)])` | 334 | `CLONE_FAIL` (wrap with `build.clone_timeout_s`) |
| `run(["git", "-C", str(clone_dir), "fetch", ...])` | 338 | soft-fail (existing `check=False` — no category change) |
| `run(["docker", "build", ...])` | 355 | `BUILD_FAIL` (wrap with `build.timeout_s`) |
| `run(["docker", "pull", pull_image])` | 369 | `PULL_FAIL` |

Signature change: `def ensure_image(...) -> Verdict | None:` — `None` means image is ready (same as today's implicit success), `Verdict` is a terminal failure.

#### `emit_human()` + `emit_json()` shape (lines 444-465)

```python
def emit_human(result: dict) -> None:
    print()
    print("=" * 70)
    print(f"  VERDICT: {result['verdict']}")
    # ...
```

**Phase 10 adds** a new one-liner `emit_verdict()` per D-05 format:

```python
def emit_verdict_line(verdict: Verdict, *, recipe: str, model: str, wall_s: float) -> None:
    # D-05 format: <CATEGORY pad 10>  <recipe> (<model>) <wall>s — <detail>
    cat = verdict.category.value.ljust(10)
    color = _GREEN if verdict.category is Category.PASS else _RED
    line = f"{color}{cat}{_RESET} {recipe} ({model}) {wall_s:.2f}s"
    if verdict.detail:
        line += f" — {verdict.detail}"
    print(line)
```

The existing `emit_human()` stays for single-cell banner mode; `emit_verdict_line()` is the per-cell summary used under `--all-cells` and for category-producing failures outside the cell loop.

Existing JSON emission (`emit_json` at line 444) consumes a plain dict. Keep it — the planner adds `result["category"]` and `result["detail"]` to the dict before `emit_json(result)`; no format migration of `emit_json()` itself required.

#### `main()` existing shape (lines 574-702) — 128 lines, refactor candidate

Current ordering: lint-all short-circuit → arg validation → lint pre-step → `load_recipe` → prompt resolution → `resolve_api_key` → `ensure_image` → cell loop → exit code. Drift detection handled in the loop (lines 659-695).

**Phase 10 inserts three new sections** (per RESEARCH.md §Code Examples "Minimal main() refactor sketch"):

1. **Pre-flight INFRA check** — at the very top of `main()` before anything else (except `parse_args`):
   ```python
   infra = preflight_docker()  # returns Verdict | None
   if infra is not None:
       emit_verdict_line(infra, recipe="(pre-flight)", model="", wall_s=0.0)
       return 1
   ```
2. **LINT_FAIL emission** at the existing lint pre-step (lines 601-608): wrap the existing error return with an `emit_verdict_line(Verdict(Category.LINT_FAIL, f"{len(errors)} schema error(s)"), ...)` call.
3. **BUILD/PULL/CLONE verdict handling** after `ensure_image()` (line 633): if `ensure_image()` returns a `Verdict`, emit it and `return 1`.

Discretion call (D-03): planner may break `main()` into `_run_preflight() / _run_lint() / _run_ensure() / _run_cells()` sub-functions if the added branching pushes `main()` past ~150 lines. Lean YES per CONTEXT.md D-05.

#### Argparse pattern (lines 513-571)

```python
p.add_argument("--json", action="store_true", help="Emit structured JSON verdict(s).")
p.add_argument(
    "--no-cache",
    action="store_true",
    help="Remove the tagged image before build/pull.",
)
```

**Phase 10 adds** `--global-timeout`:
```python
p.add_argument(
    "--global-timeout",
    type=int,
    default=None,
    help="Hard ceiling (seconds) across the entire runner invocation. "
         "Overrides per-recipe timeouts. On expiry, current cell returns TIMEOUT "
         "and remaining cells are skipped.",
)
```

Optional per CONTEXT.md Claude's Discretion: `--timeout-override` (nice-to-have).

---

### `tools/ap.recipe.schema.json` (schema / declarative validation)

**Analog:** itself — this phase extends an existing schema.

#### Enum-addition pattern (lines 65-68, lines 271-279)

Existing enum declarations:
```json
"mode": {
  "type": "string",
  "enum": ["upstream_dockerfile", "image_pull"]
},
```
```json
"pass_if": {
  "type": "string",
  "enum": [
    "response_contains_name",
    "response_contains_string",
    "response_regex",
    "response_not_contains",
    "exit_zero"
  ],
  "description": "Verdict verb."
},
```

**Phase 10 adds** a new 11-value `category` enum property (per RESEARCH.md §Example 3) under `smoke.verified_cells.items.properties`:
```json
"category": {
  "type": "string",
  "enum": [
    "PASS", "ASSERT_FAIL", "INVOKE_FAIL",
    "BUILD_FAIL", "PULL_FAIL", "CLONE_FAIL",
    "TIMEOUT", "LINT_FAIL", "INFRA_FAIL",
    "STOCHASTIC", "SKIP"
  ],
  "description": "Authoritative failure category (9 live, 2 reserved for later phases)."
},
"detail": {
  "type": "string",
  "description": "Single-line reason for the category. Empty string when category=PASS."
}
```

Same additions to `smoke.known_incompatible_cells.items.properties`.

**CRITICAL ORDERING** (RESEARCH.md §Pitfall 1): these two fields are added as **OPTIONAL** first (step A), then recipes migrate (step B), then they become **REQUIRED** (step C). The schema's existing `"additionalProperties": false` at line 303 / 331 means step A is non-optional — skipping it makes migration fail lint.

Existing required-fields pattern (line 303):
```json
"required": ["model", "verdict"],
```

Step C tightens to:
```json
"required": ["model", "verdict", "category", "detail"],
```

#### Top-level `smoke` new field pattern (lines 261-297)

Existing:
```json
"timeout_s": {
  "type": "integer",
  "minimum": 1,
  "description": "Max wall time for the container run. Default 180."
},
```

**Phase 10 adds** to `build` block (mirror this shape):
```json
"timeout_s": {
  "type": "integer",
  "minimum": 1,
  "description": "Max wall time for docker build. Default 900."
},
"clone_timeout_s": {
  "type": "integer",
  "minimum": 1,
  "description": "Max wall time for git clone + checkout. Default 300."
}
```

`smoke.timeout_s` already exists — do not duplicate. Copy the `minimum: 1` + description convention exactly.

---

### `recipes/hermes.yaml` (recipe YAML, batch data-at-rest)

**Analog:** itself — field additions mirror the existing `verified_cells[]` entry shape at lines 131-154.

#### Existing cell shape (hermes.yaml lines 131-139)
```yaml
verified_cells:
  - model: anthropic/claude-haiku-4-5
    verdict: PASS
    wall_time_s: 12.86
    notes: Adopts persona cleanly. Response duplicated in stdout (Rich + plain).
  - model: openai/gpt-4o-mini
    verdict: PASS
    wall_time_s: 12.69
    notes: Adopts persona cleanly. Single-copy output.
```

**Phase 10 migrated shape:**
```yaml
verified_cells:
  - model: anthropic/claude-haiku-4-5
    verdict: PASS
    category: PASS
    detail: ""
    wall_time_s: 12.86
    notes: Adopts persona cleanly. Response duplicated in stdout (Rich + plain).
```

Insertion order: `category` and `detail` go **after `verdict`** and **before `wall_time_s`** to keep the primary-to-auxiliary ordering the recipes already use. ruamel.yaml round-trip preserves insertion order via `CommentedMap` — the migration script must `insert()` at the right key index (see migration script section below).

#### Existing `known_incompatible_cells` (hermes.yaml lines 140-154)
```yaml
known_incompatible_cells:
  - model: google/gemini-2.5-flash
    verdict: STOCHASTIC
    notes: |
      Initial recon (2026-04-15) observed a deterministic FAIL:
      ...
```

**Phase 10 migrated** (STOCHASTIC → ASSERT_FAIL temporarily per D-04):
```yaml
known_incompatible_cells:
  - model: google/gemini-2.5-flash
    verdict: FAIL                         # was STOCHASTIC; STOCHASTIC not a verdict enum value
    category: ASSERT_FAIL                 # temporary — phase 15 will map to STOCHASTIC
    detail: "flapping verdict — see notes"
    notes: |
      ...
```

Note: the existing schema at lines 330-346 defines `known_incompatible_cells.items.verdict` as plain `"type": "string"` (not enum-constrained), which is why `verdict: STOCHASTIC` passes today. Phase 10 does not tighten that — STOCHASTIC stays in the `notes` body as the user-facing explanation; `verdict` becomes `FAIL` for internal consistency. Re-read CONTEXT.md D-04 for the mapping nuance.

---

### `recipes/openclaw.yaml` / `picoclaw.yaml` / `nullclaw.yaml` / `nanobot.yaml` (same pattern as hermes)

Each receives the same two-field insertion after `verdict` for every `verified_cells[]` entry and every `known_incompatible_cells[]` entry. openclaw has one `known_incompatible_cells` entry with `verdict: FAIL` (not STOCHASTIC) at lines 144-154 — that one maps to `category: ASSERT_FAIL` straightforwardly, no STOCHASTIC nuance.

Only hermes has a STOCHASTIC entry per Grep results. All other known_incompatible_cells are `verdict: FAIL`.

---

### `tools/tests/test_categories.py` (CREATE — test module, unit tests)

**Analog:** `tools/tests/test_pass_if.py` (199 lines, 7 test classes, pure-function fixtures)

#### Imports pattern (test_pass_if.py lines 1-7)

```python
"""Unit tests for all 5 pass_if verbs in evaluate_pass_if.

Pillar 1 (D-11a, D-12): each verb has at least one PASS and one FAIL test.
No Docker, no network — pure function tests against canned payloads.
"""
import pytest
from run_recipe import evaluate_pass_if
```

**Phase 10 copy:**
```python
"""Unit tests for all 9 live categories in the Phase 10 taxonomy.

Per D-01/D-03: each live category has at least one fixture exercising the
code path that emits it. No live Docker — all subprocess calls mocked.
"""
import subprocess
import pytest
from run_recipe import run_cell, ensure_image, preflight_docker, Category, Verdict
```

#### Test class / method shape (test_pass_if.py lines 10-29)

```python
class TestResponseContainsName:
    def test_pass_when_name_present(self):
        result = evaluate_pass_if(
            "response_contains_name",
            payload="I am hermes, an AI assistant.",
            name="hermes",
            exit_code=0,
            smoke={},
        )
        assert result == "PASS"
```

**Phase 10 copy** (one class per live category, per RESEARCH.md §Example 2):
```python
class TestTimeoutCategory:
    def test_timeout_produces_TIMEOUT_verdict(self, monkeypatch, minimal_valid_recipe):
        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "run"]:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=1, stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)

        verdict = run_cell(
            minimal_valid_recipe, image_tag="ap-recipe-test", prompt="hi",
            model="test/model", api_key_var="X", api_key_val="y", quiet=True,
        )
        assert verdict.category is Category.TIMEOUT
        assert "timeout" in verdict.detail.lower()
        assert verdict.verdict == "FAIL"
```

One `TestXxxCategory` class per live category: `TestPassCategory`, `TestAssertFailCategory`, `TestInvokeFailCategory`, `TestBuildFailCategory`, `TestPullFailCategory`, `TestCloneFailCategory`, `TestTimeoutCategory`, `TestLintFailCategory`, `TestInfraFailCategory`. Plus `TestCategoryEnum` (validates the 11-value enum directly) and `TestVerdictShape` (validates derived `verdict` property).

#### Fixture reuse from conftest.py

`minimal_valid_recipe` fixture (conftest.py lines 55-103) and `mock_subprocess` fixture (conftest.py lines 37-52) are the two workhorses. `test_categories.py` consumes both directly — no new conftest-level fixtures required **unless** the TIMEOUT-raising variant is hoisted up (see next section).

---

### `tools/tests/conftest.py` (MODIFY — extend `mock_subprocess` fixture)

**Analog:** itself — the existing `mock_subprocess` fixture at lines 37-52.

#### Existing fixture shape

```python
@pytest.fixture
def mock_subprocess(monkeypatch):
    """Factory: configure subprocess.run to return canned output."""

    def _configure(stdout="", returncode=0, stderr=""):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=returncode,
                stdout=stdout if kwargs.get("capture_output") else None,
                stderr=stderr if kwargs.get("capture_output") else None,
            )

        monkeypatch.setattr(subprocess, "run", fake_run)

    return _configure
```

**Phase 10 extension** (per RESEARCH.md §Pitfall 5):
```python
@pytest.fixture
def mock_subprocess_timeout(monkeypatch):
    """Factory: configure subprocess.run to raise TimeoutExpired on docker run."""

    def _configure(timeout_s: int = 1):
        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "run"]:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout_s, stderr="")
            # cleanup calls (docker kill, docker rm) return success
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", fake_run)

    return _configure
```

Add as a sibling of `mock_subprocess` (after line 52, before `minimal_valid_recipe`). Keeps the factory-fixture pattern intact.

Alternative: extend existing `mock_subprocess` with a `raise_timeout_on_docker_run=False` kwarg. Either approach works — planner's call. The hoisted sibling fixture is more readable; inline extension is more compact.

---

### `scripts/migrate_recipes_phase10.py` (CREATE — optional one-shot migration)

**Analog:** `tools/run_recipe.py::writeback_cell` (lines 470-490) — the only existing ruamel round-trip writer.

#### Existing round-trip write pattern

```python
def writeback_cell(recipe_path: Path, model: str, wall_time_s: float) -> None:
    """Round-trip update of verified_cells[].wall_time_s for <model>.
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
```

**Phase 10 copy** (one-shot script — per RESEARCH.md §Example 4):
```python
#!/usr/bin/env python3
"""ONE-SHOT migration: add {category, detail} to every cell across the 5
committed recipes. Commit the result, then delete this script. Phase 10 D-04.
"""
from pathlib import Path
from ruamel.yaml import YAML

_y = YAML(typ="rt")
_y.preserve_quotes = True
_y.width = 4096
_y.indent(mapping=2, sequence=4, offset=2)


def _represent_none(dumper, _data):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "null")


_y.representer.add_representer(type(None), _represent_none)


def migrate(recipe_path: Path) -> None:
    data = _y.load(recipe_path.read_text())
    smoke = data.get("smoke", {})

    for cell in smoke.get("verified_cells", []) or []:
        cell.setdefault("category", "PASS" if cell.get("verdict") == "PASS" else "ASSERT_FAIL")
        cell.setdefault("detail", "")

    for cell in smoke.get("known_incompatible_cells", []) or []:
        if cell.get("verdict") == "STOCHASTIC":
            cell["verdict"] = "FAIL"
            cell.setdefault("category", "ASSERT_FAIL")
            cell.setdefault("detail", "flapping verdict — see notes")
        else:
            cell.setdefault("category", "ASSERT_FAIL")
            notes = cell.get("notes", "")
            cell.setdefault("detail", notes.split(".")[0][:120] if notes else "")

    with recipe_path.open("w") as f:
        _y.dump(data, f)


if __name__ == "__main__":
    for p in sorted(Path("recipes").glob("*.yaml")):
        print(f"migrating {p.name}")
        migrate(p)
```

**CRITICAL:** the YAML instance configuration (lines 1-7 above) must be **byte-identical** to `tools/run_recipe.py` lines 27-39, otherwise `test_roundtrip.py` (which asserts byte-identical round-trip) fails after migration. Copy the ruamel block verbatim.

Discretion (CONTEXT.md §specifics + RESEARCH.md Open Q 3): planner may instead do Edit-by-hand on 5 recipes — 10 cells total, <30 edits. Given the STOCHASTIC nuance in hermes, a script is safer than hand-edits. Recommendation: ship the script, commit, delete in same commit or follow-up.

---

### `docs/RECIPE-SCHEMA.md` (MODIFY — minimal sync, §6.3 extension)

**Analog:** itself — the existing §6.3 "Cell matrices" at lines 200-211.

#### Existing table pattern (line 206)

```markdown
| `smoke.verified_cells[]` | list of maps | yes | At least one cell must be present. Keys: `model` (required), `verdict` (required, `PASS` or `FAIL`), `wall_time_s` (optional float), `notes` (optional, multi-line). Cells with `verdict: PASS` are the canonical "this works" matrix. |
```

**Phase 10 updates** this row to list `category` (required) and `detail` (required) alongside `model` and `verdict`. Add a new subsection §6.4 "Category taxonomy" listing all 11 enum values with their meaning (mirror CONTEXT.md D-01 table verbatim). Mark STOCHASTIC and SKIP with `# reserved — phase 15` / `# reserved — later UX phase`.

Phase 17 (doc-runner sync) is the long-term owner of keeping this doc honest; phase 10 just needs to prevent drift, not solve it for good.

---

## Shared Patterns

### Pattern A: ruamel.yaml round-trip configuration

**Source:** `tools/run_recipe.py` lines 27-39
**Apply to:** `scripts/migrate_recipes_phase10.py` (MUST be byte-identical to pass `test_roundtrip.py`)

```python
_yaml = YAML(typ="rt")
_yaml.preserve_quotes = True
_yaml.width = 4096
_yaml.indent(mapping=2, sequence=4, offset=2)


def _represent_none(dumper, _data):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "null")


_yaml.representer.add_representer(type(None), _represent_none)
```

Also mirrored in `conftest.py::yaml_rt` fixture (lines 16-27) — any third consumer in this phase should use the conftest fixture, not a re-declaration.

### Pattern B: API-key redaction before logging / emission

**Source:** `tools/run_recipe.py` lines 402-406
**Apply to:** All `detail` strings derived from subprocess stderr in `run_cell()` and `ensure_image()`

```python
safe_cmd = [
    a if not a.startswith(f"{api_key_var}=") else f"{api_key_var}=<REDACTED>"
    for a in docker_cmd
]
```

Phase 10 generalization (new helper):
```python
def _redact_api_key(text: str, api_key_var: str) -> str:
    import re as _re
    return _re.sub(rf"{_re.escape(api_key_var)}=\S+", f"{api_key_var}=<REDACTED>", text)
```

Applied in every `Verdict(Category.X, detail=_redact_api_key(stderr_tail, api_key_var))` call site.

### Pattern C: ANSI-color output for stdout

**Source:** `tools/run_recipe.py` lines 46-49, 100-105
**Apply to:** `emit_verdict_line()` for the new D-05 CLI format

```python
_RED = "\033[31m"
_GREEN = "\033[32m"
_RESET = "\033[0m"

# Usage (lines 100-105)
if not errors:
    print(f"{_GREEN}PASS{_RESET} {name}")
else:
    print(f"{_RED}FAIL{_RESET} {name} ({len(errors)} error{'s' if len(errors) != 1 else ''})")
```

Phase 10 extends the same pattern: green for `Category.PASS`, red for every other category.

### Pattern D: jsonschema Draft 2020-12 validation via `lint_recipe()`

**Source:** `tools/run_recipe.py` lines 65-92
**Apply to:** New schema fields — no Python code change; the declarative `enum` + `required` additions in `ap.recipe.schema.json` flow automatically through `Draft202012Validator`.

```python
validator = Draft202012Validator(schema)
errors = sorted(
    validator.iter_errors(normalized),
    key=lambda e: list(e.absolute_path),
)
```

Phase 10 adds zero Python in the validator path. `LINT_FAIL` emission is just a caller-side classification of existing `_lint_single()` output (lines 108-114).

### Pattern E: pytest monkeypatch-subprocess for docker-free unit tests

**Source:** `tools/tests/conftest.py` lines 37-52
**Apply to:** Every test class in `test_categories.py`

```python
@pytest.fixture
def mock_subprocess(monkeypatch):
    def _configure(stdout="", returncode=0, stderr=""):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd, returncode=returncode,
                stdout=stdout if kwargs.get("capture_output") else None,
                stderr=stderr if kwargs.get("capture_output") else None,
            )
        monkeypatch.setattr(subprocess, "run", fake_run)
    return _configure
```

Every category test is mock-only per RESEARCH.md §Pitfall 6. Real Docker only in manual QA phase gate.

### Pattern F: sys.path injection for test imports

**Source:** `tools/tests/conftest.py` lines 9-12
**Apply to:** `test_categories.py` implicitly (conftest already does this for all test files in the same dir)

```python
# Add tools/ to sys.path so tests can import run_recipe
sys.path.insert(0, str(Path(__file__).parent.parent))

from run_recipe import load_recipe, lint_recipe, evaluate_pass_if
```

Phase 10: extend the import line in conftest to also export Category and Verdict? No — `test_categories.py` does its own `from run_recipe import …` like `test_pass_if.py` does. conftest's import exists to fail fast if the module is broken; leave it alone.

---

## No Analog Found

None. Every file in scope has a direct in-repo analog.

The nominal candidate for "no analog" was a pre-flight Docker health check (`preflight_docker()`), but the pattern is a direct descendant of the existing `image_exists()` helper (lines 290-294) — same `subprocess.run(["docker", "image", "inspect", tag], check=False, capture=True)` shape, differs only in which `docker` subcommand is invoked. Use `image_exists()` as the structural analog.

---

## Metadata

**Analog search scope:**
- `/Users/fcavalcanti/dev/agent-playground/tools/` — 7 files (runner, schema, pyproject, 4 test files + conftest + broken_recipes fixtures dir)
- `/Users/fcavalcanti/dev/agent-playground/recipes/` — 5 YAML files + BACKLOG + README
- `/Users/fcavalcanti/dev/agent-playground/scripts/` — 1 bash file (smoke-e2e.sh — not a Python analog)
- `/Users/fcavalcanti/dev/agent-playground/docs/` — 1 file (RECIPE-SCHEMA.md)
- `/Users/fcavalcanti/dev/agent-playground/.planning/FRAMEWORK-MATURITY-ROADMAP.md` — confirmed P05 scope

**Files scanned:** 18

**Key architectural pattern identified:**
- Every Phase 10 change is **additive self-extension** — the runner, schema, and recipes all have existing shapes that the new category/detail/timeout fields slot into without structural refactor. The one genuinely new artifact is `test_categories.py`, and its template (`test_pass_if.py`) is near-isomorphic.

**Critical sequencing constraint** (Pitfall 1, non-negotiable):
1. Schema — add `category`/`detail` as OPTIONAL
2. Migrate 5 YAMLs
3. Schema — tighten to REQUIRED
4. Runner — emit `Verdict` objects
5. Tests — add `test_categories.py`

Commits at every boundary must keep `pytest -x` green on the 5 committed recipes.

**Pattern extraction date:** 2026-04-16
