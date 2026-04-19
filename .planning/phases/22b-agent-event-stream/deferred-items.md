# Phase 22b — Deferred Items (out-of-scope findings)

Items discovered during Plan 22b-01 execution that are **pre-existing** issues
unrelated to the current task's changes. Logged per CLAUDE.md SCOPE BOUNDARY
rule — out-of-scope items are documented, not fixed.

---

## DI-01 — openclaw.yaml has a duplicate YAML key (`category: PASS`)

- **File:** `recipes/openclaw.yaml`
- **Symptom:** `ruamel.yaml.constructor.DuplicateKeyError` at lines 308 vs 328
  (`found duplicate key "category" with value "PASS"`).
- **Impact:** `tests/test_schemas.py::test_list_schemas`,
  `tests/test_schemas.py::test_get_schema_doc`, `tests/test_schemas.py::test_unknown_schema_404`,
  `tests/test_runs.py::test_agent_instance_dedupes_across_runs`, and any
  route-level tests that load the recipes directory all error at recipe-load
  time when ruamel.yaml's strict-duplicate mode is active.
- **Pre-existing:** YES — reproduces against HEAD before 22b-01 Task 1/2
  changes (verified via `git stash` round-trip 2026-04-19).
- **Introduced by:** commit `a7cf64e` (spike(22b): 10/10 spikes complete …) or
  earlier. Not caused by Phase 22b-01.
- **Recommended fix:** collapse the duplicate `category:` entry under the
  2026-04-17 CHANNEL_PASS_LLM_FAIL verified_cells block, OR relax ruamel.yaml's
  strict-duplicate-key checker in `api_server.recipes.loader` via
  `YAML(typ='rt').allow_duplicate_keys = True` if the duplication is semantic
  (both entries describe the same cell).
- **Owner:** deferred to a follow-up chore PR — not in scope for 22b-01.

---

## DI-02 — api_server venv missing Phase 22-02 deps on fresh clone

- **Symptom:** `ModuleNotFoundError: pyrage` and `cryptography` in the
  api_server/.venv on a fresh `pip install -e '.[dev]'` run.
- **Cause:** Phase 22-02 added `pyrage>=1.2` and `cryptography>=42` to
  pyproject.toml but the project's CI-equivalent (Makefile / docs) does not
  force a re-install on branch swap.
- **Recommended fix:** document in `api_server/README.md` (or Makefile) that
  `pip install -e '.[dev]'` must be re-run when the dependency list changes,
  OR add a `make bootstrap` target that runs it.
- **Owner:** deferred — observed during 22b-01 Task 1 verification, worked
  around in-place by running the install once in the venv.
