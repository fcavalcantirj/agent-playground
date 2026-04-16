---
phase: 9
slug: spec-lint-test-harness-foundations
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-15
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=8.0 |
| **Config file** | `tools/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tools/tests/ -x --tb=short` |
| **Full suite command** | `pytest tools/tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tools/tests/ -x --tb=short`
- **After every plan wave:** Run `pytest tools/tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Decision | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | D-01, D-02, D-03 | — | N/A | unit | `pytest tools/tests/test_lint.py -x` | Wave 0 | pending |
| 09-02-01 | 02 | 1 | D-06, D-07, D-09 | — | N/A | unit | `python tools/run_recipe.py --lint recipes/hermes.yaml` | Wave 0 | pending |
| 09-03-01 | 03 | 2 | D-11a | — | N/A | unit | `pytest tools/tests/test_pass_if.py -x` | Wave 0 | pending |
| 09-03-02 | 03 | 2 | D-11b | — | N/A | unit | `pytest tools/tests/test_lint.py -k broken -x` | Wave 0 | pending |
| 09-03-03 | 03 | 2 | D-11c | — | N/A | unit | `pytest tools/tests/test_roundtrip.py -x` | Wave 0 | pending |
| 09-03-04 | 03 | 2 | D-14 | — | N/A | regression | `pytest tools/tests/test_recipe_regression.py -x` | Wave 0 | pending |
| 09-04-01 | 04 | 3 | D-17, D-20 | — | N/A | integration | `make check` | Wave 0 | pending |
| 09-04-02 | 04 | 3 | D-21 | — | N/A | CI | `.github/workflows/test-recipes.yml` passes | Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tools/tests/__init__.py` — package marker
- [ ] `tools/tests/conftest.py` — shared fixtures (YAML instance, schema loader, mock subprocess, minimal recipe builder)
- [ ] `tools/tests/test_pass_if.py` — pass_if verb unit tests (D-11a)
- [ ] `tools/tests/test_lint.py` — lint positive/negative tests (D-02, D-03, D-04, D-11b)
- [ ] `tools/tests/test_roundtrip.py` — ruamel YAML round-trip (D-11c)
- [ ] `tools/tests/test_recipe_regression.py` — parametrized regression (D-14)
- [ ] `tools/tests/broken_recipes/` — >=10 broken YAML files (D-13)
- [ ] `tools/pyproject.toml` — Python packaging (D-17)
- [ ] `tools/ap.recipe.schema.json` — JSON Schema (D-01)

---

## Manual-Only Verifications

| Behavior | Decision | Why Manual | Test Instructions |
|----------|----------|------------|-------------------|
| Colored lint output readable | D-08 | Visual formatting | Run `python tools/run_recipe.py --lint recipes/hermes.yaml` and confirm colored output |

---

*Phase: 09-spec-lint-test-harness-foundations*
*Validation strategy created: 2026-04-15*
