# Phase 9: Spec lint + test harness foundations - Research

**Researched:** 2026-04-15
**Domain:** JSON Schema validation, pytest test harness, Python packaging, recipe YAML lint
**Confidence:** HIGH

## Summary

Phase 9 adds structural validation (lint) and a test harness to the recipe runner. The core deliverables are: (1) a hand-written JSON Schema (`ap.recipe.schema.json`) that validates v0.1 recipes including cross-field invariants, (2) a `--lint` subcommand integrated as a mandatory pre-step, (3) a `pytest` suite covering pass_if verbs, lint negatives, and YAML round-trip, and (4) Python packaging via `pyproject.toml` with Makefile targets and a minimal GitHub Actions CI workflow.

All three key Python libraries (`jsonschema`, `ruamel.yaml`, `pytest`) are verified available, actively maintained, and compatible. The `jsonschema` library's `Draft202012Validator` fully supports `if/then` conditionals for cross-field invariants and `additionalProperties: false` for strict mode -- both verified empirically during this research. The `ruamel.yaml` round-trip preserves exact formatting for all 5 committed recipes when using the runner's existing YAML configuration (null representer + indent settings).

**Primary recommendation:** Use JSON Schema Draft 2020-12, `jsonschema>=4.23` (supports all needed features), `pytest>=8.0`, and `ruamel.yaml>=0.17.21` (already in use). Extract `evaluate_pass_if()`, `load_recipe()`, and a new `lint_recipe()` into importable functions with no global state. Keep the rest of `run_recipe.py` as-is per D-16.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** JSON Schema (`ap.recipe.schema.json`) hand-written to match `docs/RECIPE-SCHEMA.md` field tables. Not auto-generated.
- **D-02:** Schema uses JSON Schema conditionals (if/then) for cross-field invariants.
- **D-03:** `additionalProperties: false` everywhere -- strict schema, rejects unknown keys.
- **D-04:** v0 apiVersion support dropped entirely. Schema validates `ap.recipe/v0.1` only. Remove v0 compat code from runner.
- **D-05:** Schema lives at `tools/ap.recipe.schema.json`.
- **D-06:** Lint is a subcommand: `run_recipe.py --lint <recipe>` and `--lint-all`.
- **D-07:** Lint runs automatically as mandatory pre-step. `--no-lint` to bypass.
- **D-08:** Lint output is human-readable colored text. No `--json` lint flag in Phase 9.
- **D-09:** Exit codes: 0 = PASS, 1 = runtime FAIL, 2 = LINT_FAIL.
- **D-10:** `make lint-recipes` target for CI.
- **D-11:** Three test pillars: (1) pass_if verb unit tests, (2) >=10 lint negative tests, (3) ruamel round-trip tests.
- **D-12:** Docker mocking via `pytest monkeypatch` on `subprocess.run`.
- **D-13:** Broken recipe fragments in `tools/tests/broken_recipes/`.
- **D-14:** Parametrized regression test over `recipes/*.yaml`.
- **D-15:** Test suite completes in <10 seconds.
- **D-16:** Minimal extraction: `evaluate_pass_if()`, `load_recipe()`, lint function. Keep the rest as-is.
- **D-17:** `tools/pyproject.toml` with runtime deps `ruamel.yaml`, `jsonschema`; dev dep `pytest`.
- **D-18:** Tests at `tools/tests/`.
- **D-19:** Python 3.12+.
- **D-20:** Makefile targets: `install-tools`, `test`, `lint-recipes`, `check`.
- **D-21:** GitHub Actions workflow `.github/workflows/test-recipes.yml`.

### Claude's Discretion
- Test directory structure within `tools/tests/` (flat vs nested)
- `conftest.py` fixture design
- Schema Draft version (2020-12 vs 2019-09)
- Lint output formatting details

### Deferred Ideas (OUT OF SCOPE)
- JSON output from lint (`--json` flag)
- Auto-generation of schema from RECIPE-SCHEMA.md
- Full runner refactor into modules
- Schema publication to schemastore.org
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `jsonschema` | >=4.23,<5 | JSON Schema validation | Official Python JSON Schema implementation, supports Draft 2020-12, if/then conditionals, additionalProperties. 4.26.0 is latest. [VERIFIED: pip3 index] |
| `ruamel.yaml` | >=0.17.21 | YAML round-trip parsing | Already used by `run_recipe.py`. Preserves comments, ordering, quotes. 0.19.1 is latest but 0.17.21 already installed and working. [VERIFIED: pip3 index + empirical round-trip test] |
| `pytest` | >=8.0 | Test framework | Standard Python test framework. 8.4.1 installed, 9.0.3 is latest. [VERIFIED: pip3 index] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `jsonschema[format-nonfunctional]` | (bundled) | Format annotation support without validation | Install extra to silence format warnings; optional since we don't use format-based validation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `jsonschema` Draft 2020-12 | Draft 2019-09 | 2019-09 also supports if/then. 2020-12 is newer and the `$schema` URI is cleaner. No functional difference for our use case. **Recommend 2020-12** since it's the latest stable draft. |
| `jsonschema` | `pydantic` / `yamale` | Pydantic validates Python objects, not YAML/JSON docs against a standalone schema file. yamale is YAML-only, no JSON Schema standard. jsonschema is the only choice for a `.json` schema artifact. |
| `pytest` | `unittest` | pytest has better parametrize, fixtures, and `monkeypatch`. No reason to use unittest for a new test suite. |
| `pytest monkeypatch` | `unittest.mock.patch` | Both work. monkeypatch is idiomatic pytest and scoped to test functions automatically. |

**Installation:**
```bash
pip install -e "tools/[dev]"
```

**Version verification:**
- jsonschema: 4.26.0 latest on PyPI (2026 release) [VERIFIED: pip3 index]
- ruamel.yaml: 0.19.1 latest on PyPI [VERIFIED: pip3 index]
- pytest: 9.0.3 latest on PyPI [VERIFIED: pip3 index]

## Architecture Patterns

### Recommended Project Structure
```
tools/
  run_recipe.py            # existing runner (579 lines, minimal extraction)
  ap.recipe.schema.json    # NEW: hand-written JSON Schema (D-05)
  pyproject.toml           # NEW: Python packaging (D-17)
  tests/
    __init__.py
    conftest.py            # shared fixtures: temp recipe builder, mock subprocess
    test_pass_if.py        # pass_if verb unit tests (Pillar 1)
    test_lint.py           # lint positive/negative tests (Pillar 2)
    test_roundtrip.py      # ruamel YAML round-trip tests (Pillar 3)
    test_recipe_regression.py  # parametrized regression over recipes/*.yaml (D-14)
    broken_recipes/        # deliberately broken YAML fragments (D-13)
      missing_api_version.yaml
      wrong_api_version.yaml
      missing_name.yaml
      invalid_name_chars.yaml
      missing_build_mode.yaml
      unknown_build_mode.yaml
      missing_needle.yaml          # pass_if: response_contains_string without needle
      missing_regex.yaml           # pass_if: response_regex without regex
      unknown_top_level_key.yaml
      missing_smoke_prompt.yaml
      missing_verified_cells.yaml  # at least one cell required
      extra_build_property.yaml    # additionalProperties: false catches this
```

### Pattern 1: Function Extraction for Testability (D-16)
**What:** Extract 3 functions from `run_recipe.py` into importable form -- no globals, no side effects at import time.
**When to use:** When the runner script needs to be both a CLI tool and importable by tests.
**Example:**
```python
# In run_recipe.py -- extracted functions with clear signatures

def load_recipe(path: Path) -> dict:
    """Load and parse a recipe YAML file. Returns the parsed dict."""
    text = path.read_text()
    return _yaml.load(text)

def lint_recipe(recipe: dict, schema: dict) -> list[str]:
    """Validate recipe against JSON Schema. Returns list of error messages."""
    from jsonschema import Draft202012Validator
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(recipe), key=lambda e: list(e.absolute_path))
    return [_format_error(e) for e in errors]

def evaluate_pass_if(rule, *, payload, name, exit_code, smoke) -> str:
    # Already exists -- just ensure it has no global dependencies
    ...
```

### Pattern 2: JSON Schema Cross-Field Invariants (D-02)
**What:** Use `allOf` with `if/then` blocks to enforce that `pass_if: response_contains_string` requires `needle`, etc.
**When to use:** Whenever one field's value constrains which other fields are required.
**Example:**
```json
{
  "allOf": [
    {
      "if": {
        "properties": {
          "smoke": {
            "properties": { "pass_if": { "const": "response_contains_string" } }
          }
        }
      },
      "then": {
        "properties": {
          "smoke": { "required": ["needle"] }
        }
      }
    }
  ]
}
```
[VERIFIED: empirical test confirmed jsonschema Draft202012Validator handles this correctly]

### Pattern 3: Pytest Monkeypatch for Docker Mocking (D-12)
**What:** Monkeypatch `subprocess.run` to return canned results per test case, avoiding real Docker.
**When to use:** Testing `evaluate_pass_if()` and `run_cell()` without Docker.
**Example:**
```python
# conftest.py
@pytest.fixture
def mock_docker_run(monkeypatch):
    """Factory fixture: returns a function that sets up subprocess.run mock."""
    def _setup(stdout="", exit_code=0, stderr=""):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd, returncode=exit_code,
                stdout=stdout if kwargs.get("capture_output") else None,
                stderr=stderr if kwargs.get("capture_output") else None,
            )
        monkeypatch.setattr(subprocess, "run", fake_run)
    return _setup
```

### Pattern 4: Parametrized Recipe Regression (D-14)
**What:** Single test function parametrized over all `recipes/*.yaml` files.
**When to use:** Catch regressions when schema evolves.
**Example:**
```python
import glob
import pytest

RECIPE_FILES = sorted(glob.glob("recipes/*.yaml"))

@pytest.mark.parametrize("recipe_path", RECIPE_FILES, ids=lambda p: Path(p).stem)
def test_committed_recipe_passes_lint(recipe_path):
    recipe = load_recipe(Path(recipe_path))
    errors = lint_recipe(recipe, schema)
    assert errors == [], f"Lint errors in {recipe_path}: {errors}"
```

### Anti-Patterns to Avoid
- **Importing `run_recipe.py` at module level with side effects:** The script currently has no module-level side effects (all logic is in `main()`), which is good. Keep it that way -- `if __name__ == "__main__"` guard is already present.
- **Mocking at too high a level:** Mock `subprocess.run`, not `run_cell`. Tests should exercise the real evaluation logic.
- **Putting the schema in a Python dict:** The schema must be a standalone `.json` file consumable by any tooling. Python loads it at runtime via `json.load()`.
- **Hand-rolled validation alongside JSON Schema:** Once the schema exists, all structural validation should go through `jsonschema.validate()`. No parallel `if recipe.get("build", {}).get("mode") not in (...)` checks.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Recipe field validation | Custom `if/elif` chain checking each field | `jsonschema.Draft202012Validator` | 50+ validation rules including cross-field invariants; hand-rolling is error-prone and hard to maintain |
| YAML parsing with comment preservation | PyYAML + manual comment tracking | `ruamel.yaml` typ="rt" | Runner already uses it; round-trip proven for all 5 recipes |
| Test parametrization | Manual loops in test functions | `pytest.mark.parametrize` | Built-in pytest feature, cleaner test output, automatic test ID generation |
| Colored terminal output | ANSI escape sequences manually | Basic ANSI codes (no dependency) | Phase 9 lint output is simple enough (red/green/bold) that a few `\033[...m` constants suffice -- no need for `colorama` or `rich` as a dependency |

**Key insight:** The JSON Schema IS the validation logic. Once it exists, all lint checking is `jsonschema.validate(recipe, schema)`. The runner code becomes thinner, not fatter.

## Common Pitfalls

### Pitfall 1: additionalProperties + if/then Interaction
**What goes wrong:** Properties declared only in `if/then` blocks (not in the main `properties` key) are rejected by `additionalProperties: false`.
**Why it happens:** JSON Schema evaluates `additionalProperties` against the `properties` defined at the same object level. Properties introduced by `if/then` are in a different subschema scope.
**How to avoid:** Declare ALL property names in the main `properties` block (even if only conditionally required). Use `if/then` only for conditional `required` constraints, not to introduce new property names.
**Warning signs:** Lint rejects a valid recipe saying "additional properties not allowed" for a field that should be fine.
[VERIFIED: empirical test confirmed this behavior with Draft202012Validator]

### Pitfall 2: Recipes Still Declare v0, Not v0.1
**What goes wrong:** D-04 says "All 5 committed recipes already declare v0.1" but they actually all declare `apiVersion: ap.recipe/v0`.
**Why it happens:** The CONTEXT.md was written with the expectation that Phase 3 consolidation would bump them, but on disk they are still v0.
**How to avoid:** Phase 9 must include a task to update all 5 recipes from `ap.recipe/v0` to `ap.recipe/v0.1` before the lint gate can enforce v0.1-only. This is a prerequisite for D-04.
**Warning signs:** `--lint` rejects all 5 committed recipes on first run because apiVersion is wrong.
[VERIFIED: `grep apiVersion recipes/*.yaml` shows all say `ap.recipe/v0`]

### Pitfall 3: Python 3.12+ Minimum vs Installed Python
**What goes wrong:** D-19 requires Python 3.12+, but the system Python is 3.10.10.
**Why it happens:** macOS ships older Python; the dev machine uses miniconda with 3.10.
**How to avoid:** `pyproject.toml` should declare `requires-python = ">=3.12"` but CI will need to install Python 3.12+. Local dev can use any Python 3.10+ (jsonschema, ruamel, pytest all work on 3.10). The `>=3.12` requirement in pyproject.toml is for forward compatibility (type syntax), not for library compatibility.
**Warning signs:** `pip install -e tools/[dev]` fails on the dev machine because of the Python version constraint.
[VERIFIED: python3 --version shows 3.10.10]

### Pitfall 4: Null Representation in YAML Round-Trip
**What goes wrong:** `ruamel.yaml` defaults to emitting `null` as a bare empty value (`base_url:` instead of `base_url: null`), breaking byte-exact round-trip.
**Why it happens:** Default null representation in ruamel.yaml.
**How to avoid:** The runner already handles this with `_represent_none` that emits explicit `null`. Tests must use the same YAML configuration as the runner (the same `_yaml` instance or same config).
**Warning signs:** Round-trip tests fail with whitespace differences on null fields.
[VERIFIED: without the representer, hermes.yaml has 79 line diffs; with it, exact match]

### Pitfall 5: Schema Scope Mismatch
**What goes wrong:** Confusing `tools/ap.recipe.schema.json` (v0.1 lint schema for the Python runner) with `agents/schemas/recipe.schema.json` (v1 platform schema for the Go loader).
**Why it happens:** Two different schemas exist for different purposes at different API versions.
**How to avoid:** D-05 explicitly places the new schema at `tools/ap.recipe.schema.json`. The CONTEXT.md canonical_refs section says "Do NOT modify or reuse" the agents/schemas one. Keep them strictly separate.
**Warning signs:** Accidentally modifying the wrong schema file.

## Code Examples

### Loading Schema and Validating
```python
# Source: verified empirically during research
import json
from pathlib import Path
from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent / "ap.recipe.schema.json"

def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())

def lint_recipe(recipe: dict) -> list[str]:
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(recipe),
        key=lambda e: list(e.absolute_path)
    )
    messages = []
    for e in errors:
        path = ".".join(str(p) for p in e.absolute_path) or "(root)"
        messages.append(f"{path}: {e.message}")
    return messages
```

### Colored Lint Output (No Dependencies)
```python
# Source: standard ANSI escape codes
RED = "\033[31m"
GREEN = "\033[32m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_lint_result(recipe_name: str, errors: list[str]) -> None:
    if not errors:
        print(f"{GREEN}PASS{RESET} {recipe_name}")
    else:
        print(f"{RED}FAIL{RESET} {recipe_name} ({len(errors)} errors)")
        for msg in errors:
            print(f"  {RED}-{RESET} {msg}")
```

### Pytest conftest.py Pattern
```python
# Source: pytest documentation patterns + project-specific needs
import pytest
import json
import subprocess
from pathlib import Path
from ruamel.yaml import YAML

@pytest.fixture
def yaml_rt():
    """Pre-configured ruamel YAML instance matching runner's config."""
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    def _represent_none(dumper, _data):
        return dumper.represent_scalar("tag:yaml.org,2002:null", "null")
    y.representer.add_representer(type(None), _represent_none)
    return y

@pytest.fixture
def schema():
    """Load the JSON Schema for recipe validation."""
    schema_path = Path(__file__).parent.parent / "ap.recipe.schema.json"
    return json.loads(schema_path.read_text())

@pytest.fixture
def mock_subprocess(monkeypatch):
    """Factory: configure subprocess.run to return canned output."""
    def _configure(stdout="", returncode=0, stderr=""):
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                args=cmd, returncode=returncode,
                stdout=stdout if kwargs.get("capture_output") else None,
                stderr=stderr if kwargs.get("capture_output") else None,
            )
        monkeypatch.setattr(subprocess, "run", fake_run)
    return _configure

@pytest.fixture
def minimal_valid_recipe():
    """A minimal recipe dict that passes lint."""
    return {
        "apiVersion": "ap.recipe/v0.1",
        "name": "test-agent",
        "display_name": "Test Agent",
        "description": "A test recipe for unit testing.",
        "source": {
            "repo": "https://github.com/test/test",
            "ref": "abc123",
        },
        "build": {
            "mode": "upstream_dockerfile",
        },
        "runtime": {
            "provider": "openrouter",
            "process_env": {
                "api_key": "OPENROUTER_API_KEY",
                "base_url": None,
                "model": None,
            },
            "volumes": [{
                "name": "test_vol",
                "host": "per_session_tmpdir",
                "container": "/data",
            }],
        },
        "invoke": {
            "mode": "cli-passthrough",
            "spec": {
                "argv": ["echo", "$PROMPT"],
            },
        },
        "smoke": {
            "prompt": "hello",
            "pass_if": "exit_zero",
            "verified_cells": [
                {"model": "test/model", "verdict": "PASS"},
            ],
        },
        "metadata": {
            "recon_date": "2026-04-15",
            "recon_by": "test",
            "source_citations": ["test"],
        },
    }
```

### Broken Recipe Fragment Example
```yaml
# tools/tests/broken_recipes/missing_needle.yaml
# Targets: D-02 cross-field invariant — pass_if: response_contains_string requires needle
apiVersion: ap.recipe/v0.1
name: broken-needle
display_name: Broken Needle Test
description: This recipe should fail lint because needle is missing.
source:
  repo: https://github.com/test/test
  ref: abc123
build:
  mode: upstream_dockerfile
runtime:
  provider: openrouter
  process_env:
    api_key: OPENROUTER_API_KEY
    base_url: null
    model: null
  volumes:
    - name: vol
      host: per_session_tmpdir
      container: /data
invoke:
  mode: cli-passthrough
  spec:
    argv: ["echo", "hello"]
smoke:
  prompt: "hello"
  pass_if: response_contains_string
  # needle is MISSING -- lint should catch this
  verified_cells:
    - model: test/model
      verdict: PASS
metadata:
  recon_date: "2026-04-15"
  recon_by: test
  source_citations: ["test"]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| PyYAML for YAML parsing | ruamel.yaml round-trip | Pre-project | Comment preservation, exact round-trip |
| jsonschema Draft 7 | Draft 2020-12 | 2020 | `$schema` URI is `https://json-schema.org/draft/2020-12/schema`, cleaner vocabulary system |
| pytest <8 | pytest 8.x/9.x | 2024 | Better parametrize, improved error output, native `tmp_path` |
| `jsonschema.validate()` (simple call) | `Draft202012Validator.iter_errors()` | Current best practice | `iter_errors()` collects ALL errors in one pass instead of raising on the first one -- essential for a lint tool |

**Deprecated/outdated:**
- `jsonschema.Draft4Validator`: still works but Draft 2020-12 is the current standard
- `PyYAML` for round-trip: use ruamel.yaml instead (PyYAML destroys comments and ordering)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 |
| Config file | `tools/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tools/tests/ -x --tb=short` |
| Full suite command | `pytest tools/tests/ -v` |

### Phase Requirements to Test Map

Since this phase has no specific requirement IDs, tests map to the decision IDs from CONTEXT.md:

| Decision | Behavior | Test Type | Automated Command | File Exists? |
|----------|----------|-----------|-------------------|-------------|
| D-02 | Cross-field invariant (pass_if + needle/regex) | unit | `pytest tools/tests/test_lint.py -k invariant -x` | Wave 0 |
| D-03 | additionalProperties rejects unknown keys | unit | `pytest tools/tests/test_lint.py -k unknown -x` | Wave 0 |
| D-04 | v0 apiVersion rejected, v0.1 accepted | unit | `pytest tools/tests/test_lint.py -k apiversion -x` | Wave 0 |
| D-11a | pass_if verb unit tests (5 verbs) | unit | `pytest tools/tests/test_pass_if.py -x` | Wave 0 |
| D-11b | >=10 lint negative tests | unit | `pytest tools/tests/test_lint.py -k broken -x` | Wave 0 |
| D-11c | ruamel round-trip over all 5 recipes | unit | `pytest tools/tests/test_roundtrip.py -x` | Wave 0 |
| D-14 | All 5 committed recipes pass lint | regression | `pytest tools/tests/test_recipe_regression.py -x` | Wave 0 |
| D-15 | Suite completes in <10 seconds | timing | `pytest tools/tests/ --timeout=10` (or wall-clock check) | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tools/tests/ -x --tb=short`
- **Per wave merge:** `pytest tools/tests/ -v`
- **Phase gate:** Full suite green + all 5 recipes pass `--lint` + `make check` green

### Wave 0 Gaps
- [ ] `tools/tests/__init__.py` -- package marker
- [ ] `tools/tests/conftest.py` -- shared fixtures
- [ ] `tools/tests/test_pass_if.py` -- covers D-11a
- [ ] `tools/tests/test_lint.py` -- covers D-02, D-03, D-04, D-11b
- [ ] `tools/tests/test_roundtrip.py` -- covers D-11c
- [ ] `tools/tests/test_recipe_regression.py` -- covers D-14
- [ ] `tools/tests/broken_recipes/` -- >=10 broken YAML files (D-13)
- [ ] `tools/pyproject.toml` -- Python packaging (D-17)
- [ ] `tools/ap.recipe.schema.json` -- JSON Schema (D-01)

## Schema Design Notes

### Draft Selection: 2020-12
**Recommendation:** Use Draft 2020-12. [VERIFIED: `Draft202012Validator` works on the installed jsonschema 4.25.0]

The existing `agents/schemas/recipe.schema.json` (v1 platform schema, separate concern) uses Draft 2019-09. Using 2020-12 for the v0.1 lint schema creates no conflict since they are entirely separate files for different purposes. 2020-12 is the latest stable draft and has the cleanest `$schema` URI.

### Cross-Field Invariants to Encode
Based on the 5 committed recipes and `docs/RECIPE-SCHEMA.md`:

| Condition | Then Requires | Where in Schema |
|-----------|---------------|-----------------|
| `smoke.pass_if == "response_contains_string"` | `smoke.needle` | Top-level `allOf` with `if/then` |
| `smoke.pass_if == "response_not_contains"` | `smoke.needle` | Same |
| `smoke.pass_if == "response_regex"` | `smoke.regex` | Same |
| `build.mode == "upstream_dockerfile"` | `source.repo`, `source.ref` | `build` object `allOf` |
| `build.mode == "image_pull"` | `build.image` | `build` object `allOf` |
| `invoke.mode == "cli-passthrough"` | `invoke.spec.argv` | `invoke` object |

### Required Top-Level Fields
From RECIPE-SCHEMA.md: `apiVersion`, `name`, `display_name`, `description`, `build`, `runtime`, `invoke`, `smoke`, `metadata`. The `source` block is conditionally required (only when `build.mode == upstream_dockerfile`).

### Enum Values to Lock
| Field | Allowed Values |
|-------|---------------|
| `apiVersion` | `ap.recipe/v0.1` only (D-04) |
| `build.mode` | `upstream_dockerfile`, `image_pull` |
| `invoke.mode` | `cli-passthrough` (only one implemented) |
| `smoke.pass_if` | `response_contains_name`, `response_contains_string`, `response_regex`, `response_not_contains`, `exit_zero` |
| `stdout_filter.engine` | `awk` |
| `session_id_capture.engine` | `awk`, `none` |
| `volumes[].mode` | `rw`, `ro` |

## Broken Recipe Catalog (D-13)

At least 10 broken fragments are required. Here is the recommended set (12 fragments, each targeting a specific schema violation):

| # | Filename | Violation | Schema Feature |
|---|----------|-----------|----------------|
| 1 | `missing_api_version.yaml` | Missing `apiVersion` | required |
| 2 | `wrong_api_version.yaml` | `apiVersion: ap.recipe/v0` | const |
| 3 | `missing_name.yaml` | Missing `name` | required |
| 4 | `invalid_name_chars.yaml` | `name: "Not Valid!"` | pattern |
| 5 | `missing_build_mode.yaml` | `build` present but no `mode` | required |
| 6 | `unknown_build_mode.yaml` | `build.mode: "magic"` | enum |
| 7 | `missing_needle.yaml` | `pass_if: response_contains_string` without `needle` | if/then |
| 8 | `missing_regex.yaml` | `pass_if: response_regex` without `regex` | if/then |
| 9 | `unknown_top_level_key.yaml` | Extra key `foo: bar` at root | additionalProperties |
| 10 | `missing_smoke_prompt.yaml` | Smoke block without `prompt` | required |
| 11 | `missing_verified_cells.yaml` | Smoke without `verified_cells` | required (minItems: 1) |
| 12 | `image_pull_no_image.yaml` | `build.mode: image_pull` without `build.image` | if/then |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | Runner + tests | Yes | 3.10.10 | See Pitfall 3: D-19 says 3.12+ but 3.10 works for all libraries |
| pip | Package install | Yes | 25.2 | -- |
| jsonschema | Lint validation | Yes (installed) | 4.25.0 | -- |
| ruamel.yaml | YAML parsing | Yes (installed) | 0.17.21 | -- |
| pytest | Test runner | Yes (installed) | 8.4.1 | -- |
| make | Build targets | Yes | 3.81 | -- |
| Docker | NOT needed for Phase 9 tests | N/A | N/A | Tests mock subprocess.run |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:**
- Python 3.12+: D-19 requires 3.12+, but the dev machine has 3.10.10. All libraries work on 3.10. CI (GitHub Actions) should use 3.12+. For local dev, consider relaxing `requires-python` to `>=3.10` or documenting that CI is the enforcement point.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | -- |
| V3 Session Management | No | -- |
| V4 Access Control | No | -- |
| V5 Input Validation | Yes | JSON Schema validation rejects invalid recipe structure before Docker invocation |
| V6 Cryptography | No | -- |

### Known Threat Patterns for Recipe Lint

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed YAML injection | Tampering | JSON Schema `additionalProperties: false` + strict enum/pattern validation |
| Recipe with unexpected shell commands | Elevation of Privilege | Out of scope for Phase 9 (Phase 14 handles isolation) -- but lint prevents structurally invalid recipes from reaching Docker |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | D-19's Python 3.12+ can be relaxed to 3.10+ for local dev | Environment | Low -- only CI enforcement matters; all libraries work on 3.10 |
| A2 | All 5 recipes need apiVersion bumped from v0 to v0.1 as part of this phase | Pitfall 2 | Medium -- if this step is missed, the lint gate rejects all recipes on first run |
| A3 | Draft 2020-12 chosen over 2019-09 for the schema | Schema Design | Low -- both work identically for our use case |
| A4 | Flat test directory structure (no subdirectories under `tools/tests/`) | Architecture | Low -- can reorganize later |

## Open Questions (RESOLVED)

1. **Python 3.12+ vs 3.10 for local dev** — RESOLVED: User approved relaxing D-19 to `>=3.10` in pyproject.toml. CI enforces 3.12+. All libraries work on 3.10.

2. **Recipes v0 to v0.1 bump -- is it this phase's job?** — RESOLVED: Yes. Phase 9 Plan 01 bumps all 5 recipes from `ap.recipe/v0` to `ap.recipe/v0.1` as a prerequisite for the lint gate.

## Sources

### Primary (HIGH confidence)
- [jsonschema PyPI](https://pypi.org/project/jsonschema/) -- version 4.26.0 latest, verified via `pip3 index` [VERIFIED: pip3 index]
- [jsonschema docs](https://python-jsonschema.readthedocs.io/en/stable/validate/) -- Draft202012Validator, iter_errors [CITED: docs]
- [JSON Schema conditionals](https://json-schema.org/understanding-json-schema/reference/conditionals) -- if/then/else specification [CITED: json-schema.org]
- [ruamel.yaml PyPI](https://pypi.org/project/ruamel.yaml/) -- version 0.19.1 latest [VERIFIED: pip3 index]
- [pytest PyPI](https://pypi.org/project/pytest/) -- version 9.0.3 latest [VERIFIED: pip3 index]
- Empirical tests during research: Draft202012Validator if/then, additionalProperties interaction, cross-field invariants, YAML round-trip for all 5 recipes [VERIFIED: local Python execution]
- `tools/run_recipe.py` -- current runner source (579 lines), extraction targets identified [VERIFIED: file read]
- `docs/RECIPE-SCHEMA.md` -- canonical v0.1 spec, all field tables [VERIFIED: file read]
- `recipes/*.yaml` -- all 5 committed recipes read and analyzed [VERIFIED: file read]
- `agents/schemas/recipe.schema.json` -- existing v1 platform schema (separate concern, Draft 2019-09) [VERIFIED: file read]

### Secondary (MEDIUM confidence)
- `.planning/FRAMEWORK-MATURITY-ROADMAP.md` Phase 04 section -- steal-from-prior-art patterns [VERIFIED: file read]
- `recon/prior-art-research.md` -- METR, Cog, devcontainer patterns [VERIFIED: file read]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all three libraries verified installed, version-checked, and empirically tested
- Architecture: HIGH -- extraction pattern is minimal (D-16), test structure is straightforward
- Pitfalls: HIGH -- all 5 pitfalls verified empirically (YAML round-trip, additionalProperties+if/then, recipe apiVersion mismatch, Python version, schema file confusion)
- Schema design: HIGH -- cross-field invariants verified working with Draft202012Validator

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable domain, no fast-moving dependencies)
