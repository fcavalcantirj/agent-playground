---
phase: 09-spec-lint-test-harness-foundations
reviewed: 2026-04-16T00:30:00Z
depth: standard
files_reviewed: 16
files_reviewed_list:
  - .github/workflows/test-recipes.yml
  - .gitignore
  - Makefile
  - recipes/hermes.yaml
  - recipes/nanobot.yaml
  - recipes/nullclaw.yaml
  - recipes/openclaw.yaml
  - recipes/picoclaw.yaml
  - tools/ap.recipe.schema.json
  - tools/pyproject.toml
  - tools/run_recipe.py
  - tools/tests/__init__.py
  - tools/tests/conftest.py
  - tools/tests/test_lint.py
  - tools/tests/test_pass_if.py
  - tools/tests/test_recipe_regression.py
  - tools/tests/test_roundtrip.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 09: Code Review Report

**Reviewed:** 2026-04-16T00:30:00Z
**Depth:** standard
**Files Reviewed:** 16
**Status:** issues_found

## Summary

Phase 09 delivers a JSON Schema (`tools/ap.recipe.schema.json`), a recipe linter and runner (`tools/run_recipe.py`), a CI workflow (`.github/workflows/test-recipes.yml`), and a well-structured pytest harness with 4 test modules. The code is clean, well-documented, and follows consistent patterns throughout. No hardcoded secrets, no dangerous functions, no debug artifacts.

The codebase is solid overall. Three warnings found: (1) a silent failure on `git checkout` that could cause builds against an unintended commit, (2) whitespace-only API key values passing validation, and (3) a missing `--no-lint` guard on path-derived values from the recipe name. Three informational items address code quality: redundant path logic, an unused import, and a missing `awk` error check.

## Warnings

### WR-01: Silent failure on `git checkout FETCH_HEAD` could build wrong ref

**File:** `tools/run_recipe.py:342-345`
**Issue:** When `ensure_image` fetches a pinned ref and the fetch succeeds (`rc == 0`), the subsequent `git checkout FETCH_HEAD` is called with `check=False`. If the checkout fails (e.g., dirty worktree in the cached clone, or filesystem issue), the error is silently swallowed and the build proceeds on whatever ref the clone currently has checked out (likely `main` HEAD). This means the container image could be built from a different commit than the recipe's `source.ref` specifies, with no warning emitted.

**Fix:** Check the return code of the checkout and either abort or log a warning:
```python
rc_checkout = run(
    ["git", "-C", str(clone_dir), "checkout", "FETCH_HEAD"],
    check=False,
)
if rc_checkout != 0:
    log(
        f"  WARN: checkout of FETCH_HEAD failed (rc={rc_checkout}), "
        f"build may use wrong ref",
        quiet=quiet,
    )
```

### WR-02: Whitespace-only API key values accepted as valid

**File:** `tools/run_recipe.py:188-191`
**Issue:** In `resolve_api_key`, the truthiness check `if val:` on line 191 rejects empty strings but accepts whitespace-only strings (e.g., `OPENROUTER_API_KEY="   "`). A whitespace-only value would be passed to the Docker container as the API key, causing a cryptic authentication failure at the LLM provider instead of a clear runner error.

**Fix:** Strip whitespace before the truthiness check:
```python
for alias in ordered:
    val = (os.environ.get(alias) or dotenv.get(alias, "")).strip()
    if val:
        return var_name, val
```

### WR-03: Recipe `name` used in filesystem paths without validation when `--no-lint` bypasses schema check

**File:** `tools/run_recipe.py:331,391`
**Issue:** The recipe `name` field is used directly in filesystem paths: `/tmp/ap-recipe-{name}-clone` (line 331) and `ap-recipe-{name}-data-` (line 391). The JSON Schema constrains `name` to `^[a-z0-9_-]+$`, but this validation only runs during lint. When `--no-lint` is passed, a crafted recipe with `name: "../../etc"` could cause the clone directory to resolve outside `/tmp/`. Similarly, the `dockerfile` and `context` fields from the recipe are joined with the clone path (lines 359-360) without any containment check, allowing a path traversal to point Docker at directories outside the clone.

In practice, recipes are committed source code so this is a defense-in-depth concern, not an active exploit. But the `--no-lint` bypass removes the only guard.

**Fix:** Validate `name` with a regex before using it in paths, independent of the lint flag:
```python
import re
name = recipe["name"]
if not re.fullmatch(r"[a-z0-9_-]+", name):
    raise SystemExit(f"ERROR: invalid recipe name: {name!r}")
```

For `dockerfile` and `context`, verify the resolved path stays inside the clone directory:
```python
full_path = (clone_dir / context_dir).resolve()
if not str(full_path).startswith(str(clone_dir.resolve())):
    raise SystemExit(f"ERROR: context path escapes clone directory: {context_dir}")
```

## Info

### IN-01: Redundant path fallback in `_lint_all_recipes`

**File:** `tools/run_recipe.py:579-582`
**Issue:** The fallback `Path.cwd() / "recipes"` on line 581 is redundant because `Path("recipes")` is already a relative path that resolves against `cwd()`. The `.exists()` check on line 580 and the fallback will always point to the same directory.

**Fix:** Remove the fallback branch:
```python
if args.lint_all:
    recipes_dir = Path("recipes")
    return _lint_all_recipes(recipes_dir)
```

### IN-02: `subprocess` import in conftest.py imported but only used by fixture

**File:** `tools/tests/conftest.py:2,12`
**Issue:** `conftest.py` imports `load_recipe`, `lint_recipe`, and `evaluate_pass_if` at module level (line 12) but these are only used to make them available for test files that import from `run_recipe` directly anyway (test files already do `from run_recipe import ...`). The `conftest.py` imports are not consumed by any fixture. This is not a bug -- it ensures `sys.path` is set up before any test file imports `run_recipe` -- but the explicit imports on line 12 are unnecessary since the `sys.path.insert` on line 10 is the only load-bearing side effect.

**Fix:** Replace line 12 with a comment explaining the intent:
```python
# sys.path.insert above ensures run_recipe is importable by test modules
```

### IN-03: `apply_stdout_filter` does not check awk exit code

**File:** `tools/run_recipe.py:221-224`
**Issue:** The `awk` subprocess is called without checking its return code. If the awk program is syntactically invalid (e.g., a recipe author makes a typo in the stdout_filter program), awk will exit non-zero and return empty stdout. The empty string silently becomes the filtered payload, causing `evaluate_pass_if` to return FAIL. The root cause (broken awk program) would not appear in any output.

**Fix:** Check the awk return code and surface the error:
```python
proc = subprocess.run(
    ["awk", program], input=raw, capture_output=True, text=True
)
if proc.returncode != 0:
    sys.stderr.write(
        f"WARN: awk filter exited {proc.returncode}: {proc.stderr.strip()}\n"
    )
return proc.stdout
```

---

_Reviewed: 2026-04-16T00:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
