---
phase: 10-error-taxonomy-timeout-enforcement
reviewed: 2026-04-16T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - recipes/hermes.yaml
  - recipes/nanobot.yaml
  - recipes/nullclaw.yaml
  - recipes/openclaw.yaml
  - recipes/picoclaw.yaml
  - scripts/migrate_recipes_phase10.py
  - tools/ap.recipe.schema.json
  - tools/run_recipe.py
  - tools/tests/conftest.py
  - tools/tests/test_categories.py
  - tools/tests/test_phase10_primitives.py
  - tools/tests/test_phase10_runner.py
findings:
  critical: 0
  warning: 5
  info: 9
  total: 14
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-04-16
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 10 introduces a 9-live + 2-reserved category taxonomy, `--cidfile`-based
timeout enforcement, a `preflight_docker` probe, and a one-shot migration of
the 5 committed recipes to carry `category`/`detail` per cell. The implementation
is well-structured and test coverage is strong — every live category has at
least one test, the `docker kill` reap path has a load-bearing regression test
with pre-populated cidfile, and redaction is asserted. No Critical issues.

Five Warnings concern:

1. `resolve_api_key`'s hardcoded OpenRouter alias fallback contradicts its own
   docstring about avoiding cross-provider key bleed.
2. `ensure_image`'s cached clone directory is never re-checked-out when the
   recipe's `source.ref` changes, silently pinning users to stale refs.
3. `git checkout FETCH_HEAD` ignores non-zero exit without logging, so a
   failed checkout falls through to an unpinned HEAD silently.
4. Prompt substitution into sh-entrypoint recipes (picoclaw, nullclaw,
   nanobot) has no shell escaping — a prompt containing `"` or `$` will
   break the container command line.
5. The `schema.json` `known_incompatible_cells.items.verdict` field lacks
   the `enum: ["PASS","FAIL"]` constraint that `verified_cells.items.verdict`
   has, making the two sibling arrays inconsistent.

The rest are Info items: minor duplication, dead parameters, a non-atomic
write-back, and some recipe-file documentation tightening.

## Warnings

### WR-01: `resolve_api_key` hardcoded OpenRouter aliases contradict the documented anti-bleed rationale

**File:** `tools/run_recipe.py:254-282`
**Issue:** The docstring explicitly states the function does NOT consult
`process_env.api_key_fallback` because mixing those concerns "causes
cross-provider key bleed (e.g. an OpenAI direct key in the host env being
injected as an OpenRouter key)." The implementation immediately below then
hardcodes a two-alias fallback chain:

```python
aliases = [var_name, "OPENROUTER_API_KEY", "OPEN_ROUTER_API_TOKEN"]
```

For a recipe whose canonical `api_key` is `ANTHROPIC_API_KEY` (or
`OPENAI_API_KEY`), this will inject an `OPENROUTER_API_KEY` value from
process env as the Anthropic/OpenAI key — exactly the bleed the docstring
warns against, just with OpenRouter as the source instead of the destination.
Today every committed recipe uses `OPENROUTER_API_KEY` as its canonical var,
so the bug is latent, but it will fire the moment Phase 11+ recipes for
Anthropic/OpenAI-direct land.

**Fix:** Drop the OpenRouter aliases entirely and rely solely on `var_name`
plus the repo-root `.env`. If a "dev convenience" alias list is wanted,
key it off the recipe's `runtime.provider` field (e.g. only add the
OpenRouter aliases when `provider == "openrouter"`) so it cannot bleed
across providers:

```python
var_name = recipe["runtime"]["process_env"]["api_key"]
provider = recipe["runtime"].get("provider", "")
dotenv = load_dotenv(repo_root / ".env")

aliases = [var_name]
if provider == "openrouter":
    aliases += ["OPENROUTER_API_KEY", "OPEN_ROUTER_API_TOKEN"]

# dedupe preserving order
seen: set[str] = set()
ordered = [a for a in aliases if not (a in seen or seen.add(a))]
for alias in ordered:
    val = os.environ.get(alias) or dotenv.get(alias)
    if val:
        return var_name, val
```

### WR-02: Cached clone directory is never updated when `source.ref` changes

**File:** `tools/run_recipe.py:496-537`
**Issue:** `ensure_image` reuses `/tmp/ap-recipe-<name>-clone` across
invocations whenever it exists:

```python
clone_dir = Path(f"/tmp/ap-recipe-{recipe['name']}-clone")
if not clone_dir.exists():
    log(...)
    run_with_timeout(["git", "clone", ...])
    ...
    if ref:
        # fetch + checkout FETCH_HEAD
else:
    log(f"  clone cached: {clone_dir}", quiet=quiet)
```

The `else` branch is a no-op — no `git fetch` + `git checkout` runs when
the clone is cached, so any ref change in the YAML is ignored. `--no-cache`
removes the Docker image tag but does NOT delete `/tmp/ap-recipe-<name>-clone`,
so even a forced rebuild compiles the wrong ref. This violates D-03's
"docker build respects the pinned ref" contract and will silently produce
non-reproducible builds.

**Fix:** Either blow away the clone dir on `--no-cache`, or always fetch+checkout
the ref in the cached branch. Minimal fix:

```python
if no_cache and clone_dir.exists():
    shutil.rmtree(clone_dir, ignore_errors=True)

if not clone_dir.exists():
    # existing clone + fetch + checkout path
    ...
else:
    log(f"  clone cached: {clone_dir}", quiet=quiet)
    if ref:
        # always resync to the pinned ref
        rc2, _, _, fetch_to = run_with_timeout(
            ["git", "-C", str(clone_dir), "fetch", "--depth=1", "origin", ref],
            timeout_s=clone_timeout_s,
        )
        if not fetch_to and rc2 == 0:
            run(["git", "-C", str(clone_dir), "checkout", "FETCH_HEAD"], check=False)
        else:
            log(f"  WARN: cached clone may be stale (ref {ref} not refreshed)", quiet=quiet)
```

### WR-03: `git checkout FETCH_HEAD` silently falls through on failure

**File:** `tools/run_recipe.py:527-530`
**Issue:**

```python
elif rc2 == 0:
    run(
        ["git", "-C", str(clone_dir), "checkout", "FETCH_HEAD"],
        check=False,
    )
```

`run(..., check=False)` swallows any non-zero exit without logging. If the
fetch succeeded but the checkout fails (e.g. merge conflicts from a dirty
cached clone, detached-HEAD refusal), the build proceeds at whatever HEAD
happens to be, with no warning emitted. The adjacent fetch-timeout and
fetch-failure branches DO log warnings, so this is an asymmetric hole.

**Fix:** Capture and check the checkout result:

```python
elif rc2 == 0:
    rc3, _, se3 = run(
        ["git", "-C", str(clone_dir), "checkout", "FETCH_HEAD"],
        check=False, capture=True,
    )
    if rc3 != 0:
        log(
            f"  WARN: git checkout FETCH_HEAD failed (rc={rc3}): "
            f"{(se3 or '').strip().splitlines()[-1:] or ['']}",
            quiet=quiet,
        )
```

### WR-04: Sh-entrypoint recipes break on prompts containing `"` or `$`

**File:** `recipes/picoclaw.yaml:109`, `recipes/nullclaw.yaml:101`, `recipes/nanobot.yaml:117`; interacts with `tools/run_recipe.py:285-296`
**Issue:** `substitute_argv` performs literal text substitution of `$PROMPT`
into argv elements. For sh-entrypoint recipes, the substituted prompt ends
up inside a double-quoted string that sh parses:

```yaml
# picoclaw.yaml
argv:
  - -c
  - |
    ...
    picoclaw agent -m "$PROMPT"
```

If the runner substitutes `$PROMPT` with a value containing a `"`, `` ` ``,
or `$`, sh parsing breaks — the agent either receives a truncated prompt
or the container exits with a shell syntax error (currently classified as
`INVOKE_FAIL` with no clear diagnostic). Picoclaw's comment at line 102-103
acknowledges this ("v0 smoke is 'who are you?' which is safe"), but nothing
in the runner enforces the constraint.

This is acceptable for the committed `smoke.prompt` values in v0.1, but the
runner also accepts a prompt from positional CLI argument (`args.prompt`)
and the migration banner promises Phase 10 hardens the error path — a
user-supplied prompt with a `"` will produce a confusing `INVOKE_FAIL`.

**Fix (choose one):**

1. Add a prompt-validation step in `run_cell` that rejects (or shell-escapes)
   prompts with `"`, `` ` ``, `$`, or `\` for sh-entrypoint recipes:

   ```python
   entrypoint = recipe["invoke"]["spec"].get("entrypoint")
   if entrypoint == "sh":
       forbidden = set('"`$\\')
       bad = forbidden & set(prompt)
       if bad:
           raise SystemExit(
               f"ERROR: prompt contains shell-unsafe chars {sorted(bad)}; "
               f"sh-entrypoint recipes require escape-free prompts in v0.1"
           )
   ```

2. Or document the limitation in `docs/RECIPE-SCHEMA.md` and keep the
   current runtime behavior (acceptable for v0.1 given the comment in
   `picoclaw.yaml:102-103`).

### WR-05: Schema inconsistency — `known_incompatible_cells.items.verdict` lacks enum constraint

**File:** `tools/ap.recipe.schema.json:367-369` vs `:320-324`
**Issue:** `verified_cells.items.verdict` is:

```json
"verdict": {
  "type": "string",
  "enum": ["PASS", "FAIL"],
  ...
}
```

but `known_incompatible_cells.items.verdict` is:

```json
"verdict": {
  "type": "string"
}
```

No enum, so any string value passes validation. The migration script at
`scripts/migrate_recipes_phase10.py:60` explicitly remaps
`verdict: STOCHASTIC` → `verdict: FAIL` for parity, which is only meaningful
if the schema enforces PASS|FAIL. Today a typo like `verdict: FAL` or
`verdict: pass` would pass lint silently.

**Fix:** Mirror the `verified_cells` constraint:

```json
"verdict": {
  "type": "string",
  "enum": ["PASS", "FAIL"]
}
```

If STOCHASTIC re-enters the enum in Phase 15, update both fields together.

## Info

### IN-01: `run()` helper has an unused `quiet` parameter

**File:** `tools/run_recipe.py:191`
**Issue:** `def run(cmd, check=True, capture=False, quiet=False):` never
references `quiet` in its body. Dead parameter.
**Fix:** Remove it from the signature, or actually use it to suppress the
`sys.stderr.write(...)` on failure when the caller asks for quiet.

### IN-02: `run_cell` duplicates `run_with_timeout` logic inline

**File:** `tools/run_recipe.py:660-700`
**Issue:** `run_cell` calls `subprocess.run(..., timeout=smoke_timeout_s)`
directly and re-implements the bytes-decoding and timeout-classification
logic that `run_with_timeout` already owns (lines 220-237). The two copies
must be kept in lock-step.
**Fix:** Refactor `run_cell` to call `run_with_timeout`, and move the
cidfile-reap-on-timeout path into a small helper that's composable. Defer
if the diff risk outweighs the DRY benefit this phase.

### IN-03: Cleanup uses `rm -rf` subprocess instead of `shutil.rmtree`

**File:** `tools/run_recipe.py:705`
**Issue:** `run(["rm", "-rf", str(data_dir)], check=False)` shells out for
a trivial directory removal. `shutil.rmtree(data_dir, ignore_errors=True)`
is stdlib and portable (Windows CI, when it arrives).
**Fix:** `shutil.rmtree(data_dir, ignore_errors=True)`.

### IN-04: `--write-back` defaults to True; reader may not expect mutation

**File:** `tools/run_recipe.py:894-898`
**Issue:** `--write-back` is `default=True`, so invoking `run_recipe.py
recipes/hermes.yaml --all-cells` silently mutates the YAML file. The
`writeback_cell` write is also non-atomic (no temp+rename), so a process
kill mid-write could corrupt the recipe.
**Fix:** (a) Document the default in the help text (currently only says
"default"), and (b) write via temp-file + `os.replace` for atomicity:

```python
tmp = recipe_path.with_suffix(recipe_path.suffix + ".tmp")
with tmp.open("w") as f:
    _yaml.dump(data, f)
os.replace(tmp, recipe_path)
```

### IN-05: `repo_root` derivation is brittle

**File:** `tools/run_recipe.py:958`
**Issue:** `repo_root = recipe_path.parent.parent` assumes recipes live at
`<root>/recipes/<name>.yaml`. Recipes nested one level deeper (e.g. for a
future multi-provider layout) would resolve `.env` from the wrong directory.
**Fix:** Walk upward looking for `.git/` or `pyproject.toml` as the repo-root
sentinel, or require `--repo-root` as an explicit flag.

### IN-06: `apply_stdout_filter` awk subprocess has no timeout

**File:** `tools/run_recipe.py:308-311`
**Issue:** `subprocess.run(["awk", program], input=raw, ...)` has no timeout.
Awk is well-behaved, but a pathological program (unbounded loop) would hang
the runner indefinitely, bypassing the smoke timeout that already fired
for the docker run step.
**Fix:** Add a small timeout, e.g. 30s:

```python
proc = subprocess.run(
    ["awk", program], input=raw, capture_output=True, text=True, timeout=30,
)
```

### IN-07: Migration script has no guard against accidentally re-running post-delete

**File:** `scripts/migrate_recipes_phase10.py:73-76`
**Issue:** The docstring says "Commit the result, then delete this script."
The script itself is idempotent (uses `setdefault`), but if someone copies
it into CI by mistake or re-runs it on a future recipe that uses
`STOCHASTIC` legitimately (Phase 15), it will silently coerce verdict to
FAIL without warning.
**Fix:** Either delete the script after the migration commits (per docstring),
or add a top-of-file sentinel like:

```python
# After the one-shot Phase 10 migration commit, this file should be deleted.
# Keeping it in tree risks clobbering Phase 15's restored STOCHASTIC semantics.
if __name__ == "__main__":
    print("ERROR: one-shot migration; delete this script.", file=sys.stderr)
    sys.exit(1)
```

### IN-08: Recipe YAML comments reference `response_contains_name` substring semantics that are schema-silent

**File:** `recipes/hermes.yaml:128`, `recipes/picoclaw.yaml:134`, etc.; `tools/ap.recipe.schema.json:290`
**Issue:** The schema documents `response_contains_name` as a pass_if verb,
but does not document that the "name" is drawn from the top-level `name`
field (implemented in `evaluate_pass_if` line 332-333). Downstream authors
reading only the schema will miss the link. The recipes implicitly rely
on `name: picoclaw` → match-needle `"picoclaw"`.
**Fix:** Extend the schema description for `response_contains_name`:

```json
"pass_if": {
  "type": "string",
  "enum": [...],
  "description": "Verdict verb. `response_contains_name` uses the recipe's
    top-level `name` field as the needle; other string-matching verbs require
    `needle` or `regex`. See docs/RECIPE-SCHEMA.md."
}
```

### IN-09: Secret is visible in `-e KEY=VAL` on the `docker run` command line

**File:** `tools/run_recipe.py:639`
**Issue:** `-e {api_key_var}={api_key_val}` exposes the key in
`/proc/<pid>/cmdline` for the brief docker-run subprocess lifetime. The log
output is redacted (line 646-649), but the live process listing is not.
This is a well-known Docker CLI trade-off and not a Phase 10 regression,
but deserves a note.
**Fix (deferred):** In a later phase, switch to `--env-file` backed by a
`tempfile.NamedTemporaryFile` with 0600 perms, or `--env {KEY}` which reads
from the docker-cli process env (which itself is still visible, but one
layer deeper). Not blocking for v0.1.

---

_Reviewed: 2026-04-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
