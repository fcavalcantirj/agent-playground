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

---

## DI-03 — `tests/test_migration.py` calls `alembic` CLI directly (PATH-fragile)

- **File:** `api_server/tests/test_migration.py` line ~51 — `subprocess.run(["alembic", ...])`.
- **Symptom:** 8 errors `FileNotFoundError: [Errno 2] No such file or directory: 'alembic'`
  on any environment where the alembic console script is not on PATH (e.g.
  worktree-local venvs that install dependencies but don't propagate the
  console script).
- **Pre-existing:** YES — present since Phase 19 baseline; my new
  `tests/test_events_migration.py` uses the safer `[sys.executable, "-m",
  "alembic", ...]` pattern (matches `tests/conftest.py::migrated_pg`).
- **Recommended fix:** convert `test_migration.py::_alembic` to use
  `[sys.executable, "-m", "alembic", *args]` — same one-line change made in
  `conftest.py::migrated_pg`.
- **Owner:** deferred — not caused by 22b-02; my events-migration test
  isn't affected.

---

## DI-04 — `tests/test_idempotency.py::test_same_key_different_users_isolated` violates NOT NULL on `agent_instances.name`

- **File:** `api_server/tests/test_idempotency.py`
- **Symptom:** `asyncpg.exceptions.NotNullViolationError: null value in
  column "name" of relation "agent_instances"` — the test inserts an
  `agent_instances` row without supplying `name`, but migration 002
  (Phase 22 series) made `name NOT NULL`.
- **Pre-existing:** YES — `test_idempotency.py` last touched in commit
  `1c4ba36` (Phase 19-05); migration 002 landed in Phase 22-01. The test
  was not updated when the column became required.
- **Recommended fix:** add `name = 'idempotency-test-{user_id_short}'`
  (or similar) to the test's INSERT helper.
- **Owner:** deferred — not caused by 22b-02 (no Plan 22b-02 file touches
  `tests/test_idempotency.py`).

---

## DI-05 — `tests/test_roundtrip.py::test_yaml_roundtrip_is_lossless[openclaw]` fails on baseline

- **File:** `tools/tests/test_roundtrip.py`
- **Symptom:** ruamel-rt round-trip diverges at char 16336 of openclaw.yaml
  serialization. hermes/nanobot/nullclaw round-trip cleanly; only openclaw
  fails. (picoclaw also runs in the parametrize but exits early because the
  test fail-fast at openclaw — needs `--lf` continuation to confirm.)
- **Pre-existing:** YES — verified via `git stash` round-trip 2026-04-19
  during Plan 22b-09 Task 2 verification. Failure reproduces against
  HEAD~1 (before any 22b-09 schema/test changes).
- **Likely root cause:** openclaw.yaml carries the duplicate `category: PASS`
  key from DI-01 (lines 308 vs 328), which changes serialization order
  between safe-load and rt-dump. DI-01 fix would likely also unblock DI-05.
- **Owner:** deferred — out of scope for 22b-09 (which only touches
  schema + tests, not recipe files). The TestLintRealRecipes class added
  in this plan uses safe-load (not rt) and is unaffected.
