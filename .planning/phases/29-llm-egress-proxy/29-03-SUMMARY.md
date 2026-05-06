---
phase: 29
plan: 03
subsystem: llm-egress-proxy
tags: [provider-dispatch, byok, openrouter, anthropic, openai, ssrf-defense, frozen-dataclass, pure-function]
dependency_graph:
  requires:
    - 29-CONTEXT.md (D-09 closed-set provider enum, D-17 single source of truth)
    - 29-PATTERNS.md (lines 316-359, exact UpstreamSpec + PROVIDERS shape)
    - spikes/PROBE-VAL-04.md (auth-swap empirical verification)
    - api_server/src/api_server/services/recipes_loader.py (existing _ENV_TO_PROVIDER mirror)
  provides:
    - "UpstreamSpec frozen dataclass — immutable per-provider upstream descriptor"
    - "PROVIDERS dict — closed enum of 3 entries (openrouter / openai / anthropic) with empirically-verified auth shapes"
    - "ENV_TO_PROVIDER dict — recipe env-var → provider string mapping"
    - "derive_provider() helper — raises ValueError on unknown env var (closed-enum SSRF defense)"
  affects:
    - "Plan 04 (proxy router) — imports PROVIDERS keyed on agent_containers.upstream_provider"
    - "Plan 05 (deploy handler) — calls derive_provider(env_var) at deploy time to materialize agent_containers.upstream_provider"
    - "Plan 06 (record_usage) — imports PROVIDERS for sse_format dispatch in stream parser"
    - "Plan 07 (backfill activity) — imports PROVIDERS for OpenRouter post-hoc /generation lookup"
tech_stack:
  added: []
  patterns:
    - "Frozen dataclass — mirrors services/inapp_recipe_index.InappChannelConfig:51-99"
    - "Module-level const dict — mirrors services/recipes_loader._ENV_TO_PROVIDER:55-61"
    - "Closed-enum dispatch — KeyError → ValueError on unknown input (SSRF defense)"
key_files:
  created:
    - api_server/src/api_server/services/proxy_dispatcher.py
    - api_server/tests/services/test_proxy_dispatcher.py
  modified: []
decisions:
  - "ENV_TO_PROVIDER duplicated rather than imported from recipes_loader — avoids import cycles when recipes_loader later wants to consume from proxy_dispatcher; parity test (Test 10) prevents drift"
  - "PROVIDERS keys exactly 3 — no aliases (no 'or' → 'openrouter'); a 4th provider is a deliberate dict-entry addition tested explicitly"
  - "derive_provider raises ValueError (not KeyError) — call sites can catch a single domain error type with a contextual message naming the bad env var"
  - "Test marker omitted — pytest registered markers are 'api_integration' and 'spike'; plan-suggested 'unit' marker is unregistered and would emit warnings; pure-function tests run by default with no marker"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-05-06"
  tasks_completed: "2/2"
  test_count: "10 functions / 14 parametrized items"
  lines_of_code: "77 (impl) + 168 (tests) = 245"
---

# Phase 29 Plan 03: Provider Dispatch Table Summary

**One-liner:** Closed-enum `PROVIDERS` dict (frozen `UpstreamSpec` per openrouter/openai/anthropic) + `derive_provider()` helper as the single source of truth for upstream URLs and auth shapes — consumed by Plans 04, 05, 06, 07.

## What Was Built

A pure-function service module — no I/O, no Postgres, no Docker, no upstream HTTP. The module exports four symbols:

| Symbol | Type | Purpose |
|---|---|---|
| `UpstreamSpec` | `@dataclass(frozen=True)` | Immutable per-provider upstream descriptor (5 fields) |
| `PROVIDERS` | `dict[str, UpstreamSpec]` | Closed enum — exactly 3 entries (openrouter/openai/anthropic) |
| `ENV_TO_PROVIDER` | `dict[str, str]` | Recipe env-var → provider string (mirrors `recipes_loader._ENV_TO_PROVIDER`) |
| `derive_provider` | `(str) -> str` | Raises `ValueError` on unknown env var (closed-enum SSRF defense) |

### `UpstreamSpec` fields

```python
@dataclass(frozen=True)
class UpstreamSpec:
    base_url: str
    auth_header_name: str
    auth_value_template: str   # "Bearer {key}" or "{key}"
    extra_headers: dict[str, str]
    sse_format: str            # "openai" | "anthropic"
```

### `PROVIDERS` shapes (mirror PROBE-VAL-04 evidence)

| Key | base_url | auth_header_name | auth_value_template | extra_headers | sse_format |
|---|---|---|---|---|---|
| `openrouter` | `https://openrouter.ai/api/v1` | `Authorization` | `Bearer {key}` | `{HTTP-Referer, X-Title}` | `openai` |
| `openai` | `https://api.openai.com/v1` | `Authorization` | `Bearer {key}` | `{}` | `openai` |
| `anthropic` | `https://api.anthropic.com` | `x-api-key` | `{key}` | `{anthropic-version: 2023-06-01}` | `anthropic` |

PROBE-VAL-04 sub-probe (b) confirms Anthropic returns 401 `invalid_bearer_token` when given a `Bearer` prefix — that empirical finding is the reason Anthropic's `auth_value_template` is bare `{key}` and not `Bearer {key}`.

### `ENV_TO_PROVIDER` mapping

```python
{
    "OPENROUTER_API_KEY": "openrouter",
    "ANTHROPIC_API_KEY":  "anthropic",
    "OPENAI_API_KEY":     "openai",
}
```

Test 10 asserts equality with `services.recipes_loader._ENV_TO_PROVIDER` so the two dicts cannot drift.

### `derive_provider()` semantics

- Returns the provider string for a known env var.
- Raises `ValueError` with a message containing the bad env var name AND the sorted list of known names — so the failure mode names exactly what went wrong.
- Closed enum: this is the SSRF defense — user-controlled data cannot influence the upstream URL because the only writers of `agent_containers.upstream_provider` are server-side code paths that call `derive_provider()` with a recipe-declared env-var name (not user input).

## Acceptance Gates

| Gate | Result |
|---|---|
| `set(PROVIDERS.keys()) == {"openrouter", "openai", "anthropic"}` | PASS |
| Each entry is a frozen `UpstreamSpec` | PASS — Test 5 confirms `FrozenInstanceError` on assignment |
| `auth_value_template.format(key="abc")` correct per provider | PASS — Test 6 |
| `derive_provider("OPENROUTER_API_KEY") == "openrouter"` etc. | PASS |
| `derive_provider("BOGUS_KEY")` raises `ValueError` containing "BOGUS_KEY" + "unknown" | PASS — Test 9 |
| Parity with `recipes_loader._ENV_TO_PROVIDER` | PASS — Test 10 |
| `python -c "from api_server.services.proxy_dispatcher import …; assert set(PROVIDERS) == {'openrouter','openai','anthropic'}; assert derive_provider('OPENROUTER_API_KEY') == 'openrouter'"` | PASS — verification one-liner from PLAN |

## Test Status

```
======================== 14 passed, 1 warning in 0.30s =========================
```

10 `def test_` functions; pytest collected 14 items because three are parametrized over the 3 known env vars.

## Decisions Made

1. **ENV_TO_PROVIDER duplicated, not imported.** The proxy subsystem owns its own copy to avoid an import cycle when `recipes_loader` (or Plan 04's `llm_proxy.py`) later wants to import from `proxy_dispatcher`. A parity test (Test 10) keeps the two copies in lockstep — drift surfaces as a test failure.
2. **`PROVIDERS` is exactly 3 keys.** Test 1 asserts `set(...) == {"openrouter", "openai", "anthropic"}` (not `set(...) >= {…}`). Adding a 4th provider deliberately requires updating both the dict AND the test — the test breaks if anyone aliases (e.g. adds `"or": …`) without explicitly widening the closed enum.
3. **`derive_provider` raises `ValueError`, not `KeyError`.** A single domain error type with a contextual message ("unknown api_key env var: 'BOGUS'; expected one of [...]") is easier to catch than `KeyError` at call sites that need to translate to HTTP 4xx.
4. **No pytest marker on the test module.** The pyproject.toml registers `api_integration` and `spike` only. Adding `pytestmark = pytest.mark.unit` would emit `PytestUnknownMarkWarning`. Pure-function tests run by default with no marker — that matches the existing `test_inapp_recipe_index.py` pattern.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking issue] Plan suggested `pytestmark = pytest.mark.unit`; that marker is not registered**

- **Found during:** Task 1 (writing the test file)
- **Issue:** PLAN line 114 says "with `pytestmark = pytest.mark.unit`" but `api_server/pyproject.toml` only registers `api_integration` and `spike` markers. Adding `pytest.mark.unit` would emit `PytestUnknownMarkWarning` on every pytest invocation.
- **Fix:** Omitted the `pytestmark` line. Pure-function tests run by default (no marker filter). This matches the pattern in `tests/services/test_inapp_recipe_index.py` which also has no `pytestmark`.
- **Files modified:** `api_server/tests/services/test_proxy_dispatcher.py`
- **Commit:** `4e1924a`

### Test count clarification

The plan calls for "10 test functions" (grep-checkable: `grep -cE "^def test_" outputs 10`). The file has exactly 10 `def test_` functions, but pytest collects **14 items** because two of those 10 are parametrized over the 3 known env vars (`test_env_to_provider_mapping[…]` and `test_derive_provider_happy_path[…]`). The grep gate passes; the parametrization is purely a readability win recommended by the plan ("Use parametrize where it improves readability").

## Commits

| Commit | Type | Message |
|---|---|---|
| `4e1924a` | test | `test(29-03): add failing tests for proxy_dispatcher (RED)` |
| `3f7e3fe` | feat | `feat(29-03): implement proxy_dispatcher provider table (GREEN)` |

TDD gate sequence verified: `test(...)` precedes `feat(...)`. No `refactor(...)` needed (the const-dict pattern is the simplest possible shape).

## Files Touched

### Created

- `api_server/src/api_server/services/proxy_dispatcher.py` (77 lines) — module-under-test
- `api_server/tests/services/test_proxy_dispatcher.py` (168 lines) — 10 pure-function tests

### Modified

(none)

### Deleted

(none — verified via `git diff --diff-filter=D --name-only HEAD~2 HEAD` returning empty)

## Threat-Model Mitigations

| Threat ID | Mitigation realized |
|---|---|
| T-29-03 (SSRF via PROVIDERS dict) | Closed enum: `PROVIDERS` has exactly 3 hard-coded keys. Plan 04 will look up `PROVIDERS[provider]` where `provider` comes from `agent_containers.upstream_provider` — a TEXT column the runner writes at deploy time via `derive_provider(env_var_name)`. The `KeyError` on lookup (and `ValueError` from `derive_provider`) is the SSRF defense — user-supplied data cannot influence the upstream URL because the only writers of `upstream_provider` are server-side paths consuming recipe-declared env-var names. |

## Threat Flags

(none — pure-function module; no new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries)

## Self-Check: PASSED

- File `api_server/src/api_server/services/proxy_dispatcher.py` exists: FOUND
- File `api_server/tests/services/test_proxy_dispatcher.py` exists: FOUND
- Commit `4e1924a` exists: FOUND
- Commit `3f7e3fe` exists: FOUND
- Acceptance one-liner from `<verification>`: PASSED (`verification OK`)
- 14 pytest items pass: PASSED
