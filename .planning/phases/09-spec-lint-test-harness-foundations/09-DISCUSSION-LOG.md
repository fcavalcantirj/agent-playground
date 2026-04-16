# Phase 9: Spec lint + test harness foundations — Discussion Log

**Date:** 2026-04-15
**Mode:** Interactive (discuss)

## Areas Selected

All 4 initial areas + 3 additional: Schema source of truth, Lint integration mode, Test harness scope & structure, Python packaging, Runner refactoring scope, Schema file location, CI pipeline.

## Q&A Log

### Schema source of truth

| # | Question | Options Presented | User Selected |
|---|----------|-------------------|---------------|
| 1 | Where should the lint schema come from? | Generate from RECIPE-SCHEMA.md (Rec), Write standalone, Adapt v1 schema | Generate from RECIPE-SCHEMA.md |
| 2 | Cross-field invariants in schema or runner? | Cross-field in schema (Rec), Schema for structure only | Cross-field in schema |
| 3 | Schema versioning: v0 vs v0.1? | v0.1-only + migrate (Rec), Accept both, v0.1-only + runner compat | v0.1-only (after clarifying why v0 existed — vestigial, all recipes already v0.1) |
| 4 | Reject unknown keys or allow forward-compat? | Reject unknown (Rec), Allow extra | Reject unknown (strict) |
| 5 | Schema generation automated or hand-written? | Hand-written + Phase 17 sync (Rec), Auto-generated from doc | Hand-written |
| 6 | Where should schema file live? | tools/, docs/, root | "your discretion" → later revisited, chose tools/ap.recipe.schema.json |

### Lint integration mode

| # | Question | Options Presented | User Selected |
|---|----------|-------------------|---------------|
| 1 | How should --lint integrate? | Subcommand in run_recipe.py (Rec), Standalone script, Library function | Subcommand in run_recipe.py |
| 2 | Lint error output format? | Structured JSON, Human-readable (Rec), Both modes | Human-readable text |
| 3 | Exit code for lint failures? | Exit 2 for lint (Rec), Exit 1 for all, You decide | Exit 2 |
| 4 | --lint-all flag + make target? | --lint-all + make (Rec), Separate make only, pytest does it | --lint-all + make target |

### Test harness scope & structure

| # | Question | Options Presented | User Selected |
|---|----------|-------------------|---------------|
| 1 | Test suite scope priority? | All three pillars (Rec), pass_if + lint only, Minimal lint only | All three pillars |
| 2 | How to mock Docker? | monkeypatch subprocess.run (Rec), Docker-in-Docker, Abstract interface | monkeypatch subprocess.run |
| 3 | Broken recipe fragment location? | tests/broken_recipes/ (Rec), Inline in test code, Both | tests/broken_recipes/ |
| 4 | Regression test over committed recipes? | Parametrized (Rec), No (--lint-all covers it), Separate file | Parametrized |
| 5 | Test execution time budget? | <10s (Rec), <30s, No budget | <10s |
| 6 | Test dir structure, conftest fixtures? | (3 options) | "Skip these, move to packaging" — Claude's discretion |

### Python packaging

| # | Question | Options Presented | User Selected |
|---|----------|-------------------|---------------|
| 1 | Dependency management structure? | pyproject.toml (Rec), requirements.txt split, Single requirements.txt | pyproject.toml |
| 2 | Where should pyproject.toml live? | Repo root (Rec), tools/ | tools/ (user challenged root placement: "put something on root that belongs to an inner folder?") |
| 3 | Layout confirmation: tools/pyproject.toml + tools/tests/? | tools/pyproject.toml + tools/tests/, tools/pyproject.toml + tests/ at root | tools/pyproject.toml + tools/tests/ |
| 4 | Minimum Python version? | 3.10+ (Rec), 3.12+, 3.8+ | 3.12+ (user: "why not latest?") |
| 5 | Makefile targets? | Full set (Rec), Minimal, You decide | Full set |

### Runner refactoring scope

| # | Question | Options Presented | User Selected |
|---|----------|-------------------|---------------|
| 1 | Refactor runner for testability? | Minimal extraction (Rec), Full refactor, No refactor | Minimal extraction |

### Schema file location (revisit)

| # | Question | Options Presented | User Selected |
|---|----------|-------------------|---------------|
| 1 | Schema location? | tools/ap.recipe.schema.json, docs/ap.recipe.schema.json | tools/ap.recipe.schema.json |

### CI pipeline

| # | Question | Options Presented | User Selected |
|---|----------|-------------------|---------------|
| 1 | Add GitHub Actions or defer to Phase 7? | Minimal CI now (Rec), Defer, Makefile only | Minimal CI now |

## User Notes

- "we need a mature specification and a runner, validator, etc" — emphasis on maturity and rigor
- "0 and 0.1? why we have two?" — led to explaining the vestigial v0 format and deciding to drop it
- "put something on root that belongs to an inner folder?" — challenged root pyproject.toml, led to tools/ scoping
- "why not latest?" — challenged conservative Python version, led to 3.12+
- "overall goal and deliverables and north star of this phase is?" — led to explicit north star framing

## Deferred Ideas

- JSON output from lint (later phase)
- Auto-generation of schema from RECIPE-SCHEMA.md (rejected, Phase 17 sync test instead)
- Full runner modularization (later if needed)
- Schema on schemastore.org (Phase 7 OSS scope)

---
*Discussion completed: 2026-04-15*
