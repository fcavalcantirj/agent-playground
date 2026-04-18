---
phase: 22-channels-v0.2
plan: 01
subsystem: schema
tags: [recipe-schema, jsonschema, pydantic, typescript, channels, persistent-mode, telegram, oneOf-discriminator]

# Dependency graph
requires:
  - phase: 18-schema-maturity
    provides: "$defs-based versioning seam, v0_1 branch, category enum, WR-01 error-path quality contract"
  - phase: 19-api-foundation
    provides: "RecipeSummary model, RecipeListResponse, recipes_loader.to_summary, GET /v1/recipes endpoint"
provides:
  - "ap.recipe/v0.2 schema branch with persistent + channels + health_check + channel_category $defs"
  - "5 recipes now declare apiVersion: ap.recipe/v0.2 and parse cleanly under the new oneOf discriminator"
  - "RecipeSummary surfaces channels_supported, persistent_mode_available, channel_provider_compat"
  - "Frontend TS RecipeSummary mirrors the new server fields (no client-side catalog)"
  - "lint_recipe drills into oneOf e.context so WR-01 error-path quality survives the oneOf flip"
affects: [22-02-runner-persistent, 22-03-api-endpoints, 22-04-frontend-step-2.5, 22-05-e2e-telegram, 22-06-openclaw-pairing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "oneOf discriminator keyed on apiVersion const (Kubernetes CRD idiom) now live"
    - "Channel-scoped $defs ($defs.channel_category, $defs.channel_verified_cell) kept distinct from smoke-scoped $defs to prevent enum leak"
    - "sigterm_handled documentation flag + graceful_shutdown_s=0 sentinel for daemons that ignore SIGTERM"
    - "optional_user_input shares user_input_entry schema with secret optional (hermes-pattern support)"

key-files:
  created:
    - ".planning/phases/22-channels-v0.2/22-01-SUMMARY.md"
    - ".planning/phases/22-channels-v0.2/deferred-items.md"
  modified:
    - "docs/RECIPE-SCHEMA.md"
    - "tools/ap.recipe.schema.json"
    - "tools/run_recipe.py"
    - "api_server/src/api_server/models/recipes.py"
    - "api_server/src/api_server/services/recipes_loader.py"
    - "frontend/lib/api-types.ts"
    - "recipes/hermes.yaml"
    - "recipes/nanobot.yaml"
    - "recipes/nullclaw.yaml"
    - "recipes/openclaw.yaml"
    - "recipes/picoclaw.yaml"

key-decisions:
  - "Bump the 5 existing recipes' apiVersion to ap.recipe/v0.2 in this plan. Plan did not list recipes/*.yaml in files_modified, but SC-01 requires the 5 recipes to validate under the v0.2 oneOf. Single-field edit (apiVersion header line); v0.1 content untouched; alternative (anyOf root or apiVersion-enum on v0_2) broke the 'const-based branch discrimination' pattern the plan explicitly prescribed."
  - "Move persistent.argv_note / persistent.lifecycle_note to top-level of persistent: (not inside spec:) — plan spec placed them inside spec but every committed recipe has them at the persistent: top level."
  - "graceful_shutdown_s min 1→0 to admit nanobot's documented 'ignore SIGTERM — go straight to docker rm -f' sentinel. sigterm_handled:false companion flag added."
  - "user_input_entry.secret demoted from required to optional so hermes's operational-only optional_user_input entries (TELEGRAM_HOME_CHANNEL, TELEGRAM_HOME_CHANNEL_NAME) validate without fabricating a secret field."
  - "lint_recipe now drills into e.context on oneOf root errors and prefers the target branch (via apiVersion const). Preserves WR-01 error-path quality contract from Phase 18 after the oneOf flip."
  - "channel_category = category enum + BLOCKED_UPSTREAM. Kept as separate $defs so BLOCKED_UPSTREAM can't leak into smoke-level cells."

patterns-established:
  - "oneOf discriminator live: any v0.N branch is a structural clone of v0_1 with const-bumped apiVersion + additive optional properties"
  - "CommentedMap-safe .get() or {} idiom preserved in to_summary for all new v0.2 reads"
  - "Channel metadata is BYOK discipline: secret:true fields in required_user_input flow through request only (frontend Step 2.5 contract from plan 22-06)"

requirements-completed: [SC-01]

# Metrics
duration: 11min
completed: 2026-04-18
---

# Phase 22 Plan 01: Recipe Schema v0.2 + Channels Summary

**v0.2 schema branch live with persistent: + channels: + health_check + channel_category $defs; 5 recipes bumped + RecipeSummary surfaces channel metadata to frontend — zero runtime regressions, WR-01 error-path quality preserved via oneOf.context drill-in.**

## Performance

- **Duration:** ~11 min
- **Tasks:** 3/3 complete
- **Files modified:** 11 (8 in scope from plan + 3 recipe apiVersion bumps)
- **Existing tests:** 170 pass (1 pre-existing roundtrip failure for picoclaw unicode, logged to deferred-items.md)

## Accomplishments

- **Schema v0.2 branch live** — `tools/ap.recipe.schema.json` root flips from `$ref: v0_1` to `oneOf: [v0_1, v0_2]`. Added 8 new `$defs`: `v0_2`, `persistent_block`, `channels_block`, `channel_entry`, `channel_verified_cell`, `user_input_entry`, `health_check`, `channel_category`. Every subschema declares `additionalProperties: false` except the channels_block root (which uses a constrained `propertyNames` pattern).
- **Docs v0.2 shipped** — `docs/RECIPE-SCHEMA.md` now documents §10.2 (persistent) + §11 (channels) + §10 retitled to "Out of scope for v0.2", §12 (annotations) renumbered. All v0.1.1 content preserved; diff is purely additive.
- **5 recipes validate** — hermes, nanobot, nullclaw, openclaw, picoclaw all parse cleanly under v0.2 oneOf. apiVersion bumped on each; v0.1 section content untouched.
- **Frontend gate-ready** — `RecipeSummary` now surfaces `persistent_mode_available`, `channels_supported`, `channel_provider_compat`. `frontend/lib/api-types.ts` mirrors. Step 2.5 deploy-form in plan 22-06 can gate on these without a second fetch (dumb-client golden rule #2 preserved).
- **WR-01 preserved** — `lint_recipe` drills into `e.context` on oneOf root errors and prefers the target branch by apiVersion const. All 9 Phase-18 WR-01/WR-02/WR-04 hardening tests still pass.

## Task Commits

Each task was committed atomically:

1. **Task 1: Draft docs/RECIPE-SCHEMA.md v0.2 additions** — `e0775ab` (docs)
2. **Task 2: Extend tools/ap.recipe.schema.json with v0_2 branch + bump 5 recipes + lint_recipe fix + deferred-items** — `b744a82` (feat)
3. **Task 3: Extend RecipeSummary + to_summary + TS mirror** — `9b70e09` (feat)

## Files Created/Modified

### Created
- `.planning/phases/22-channels-v0.2/22-01-SUMMARY.md` — this file
- `.planning/phases/22-channels-v0.2/deferred-items.md` — pre-existing picoclaw roundtrip test failure logged out-of-scope

### Modified
- `docs/RECIPE-SCHEMA.md` — title bumped to v0.2; preamble Version policy paragraph expanded; §1 apiVersion field now accepts v0.1 OR v0.2; §9 compatibility note covers both branches; §10 retitled "Out of scope for v0.2"; §10.1 versioning-seam text updated (oneOf live); **§10.2 NEW** persistent block spec with `graceful_shutdown_s [0, 600]` range + 0-sentinel docs + health_check oneOf; **§11 NEW** channels block spec; §12 renumbered from §11 (annotations, unchanged content).

  **Quoted key paragraphs:**

  **(§ preamble)**
  > `ap.recipe/v0.2` is **additive over `ap.recipe/v0.1.1`**: every field in a valid v0.1/v0.1.1 recipe remains valid unchanged; recipes opt in to the new blocks by declaring `apiVersion: ap.recipe/v0.2` and appending the two new top-level sections — §10.2 `persistent:` and §11 `channels:` — below the existing `metadata:` block.

  **(§10.2 health_check row)**
  > The health check is a strict `oneOf` union keyed on `kind`: `process_alive` (no extra fields — used by hermes + nullclaw) or `http` with `port: int [1, 65535]` + `path: string (must start with "/")` — used by picoclaw, nanobot, openclaw.

  **(§11.1 channels row)**
  > `provider_compat` — `{supported: [...], deferred: [...]}` listing LLM-provider IDs known to work/not-work for this channel path. Openclaw-only today: `{supported: [anthropic], deferred: [openrouter]}` because of the isolated openrouter-provider-plugin silent-fail bug.

- `tools/ap.recipe.schema.json` — Full rewrite maintaining the v0_1 branch byte-for-byte and adding the v0_2 branch + 6 new reusable `$defs`.

  **JSON Schema diff (structural):**
  - **Before:** root = `"$ref": "#/$defs/v0_1"`; `$defs` = 2 entries (`category`, `v0_1`).
  - **After:** root = `"oneOf": [{"$ref": "#/$defs/v0_1"}, {"$ref": "#/$defs/v0_2"}]`; `$defs` = **10 entries** — `category`, `channel_category`, `channel_entry`, `channel_verified_cell`, `channels_block`, `health_check`, `persistent_block`, `user_input_entry`, `v0_1` (unchanged), `v0_2`.

- `tools/run_recipe.py::lint_recipe` + `_select_oneof_branch_errors` — when a root oneOf error arrives (opaque "is not valid under any of the given schemas"), we drill into `e.context`, filter out apiVersion-const mismatch noise, prefer the target branch (1 − wrong_branch where wrong_branch is the one whose apiVersion const failed), and dedup by `(absolute_path, message)` so WR-01 per-field error paths (`source.ref`, `owner_uid`) survive.

- `api_server/src/api_server/models/recipes.py::RecipeSummary` — **3 new fields** with safe defaults:
  - `persistent_mode_available: bool = False`
  - `channels_supported: list[str] = Field(default_factory=list)`
  - `channel_provider_compat: dict[str, dict[str, list[str]]] | None = None`

- `api_server/src/api_server/services/recipes_loader.py::to_summary` — now extracts persistent + channels + provider_compat via `.get() or {}` (CommentedMap-safe), normalizes nested sequences to plain `list[str]`, and conditionally populates `channel_provider_compat` only when at least one channel declares it. Also fixes a **Rule 1 bug**: the existing `maintainer=metadata.get("maintainer")` was passing a dict (v0.1.1 `{name, url?}` shape) to a `str | None` field; the code now projects to `.name` when the value is a dict.

- `frontend/lib/api-types.ts::RecipeSummary` — mirrors the 3 new server fields with optional-with-null semantics.

- `recipes/{hermes,nanobot,nullclaw,openclaw,picoclaw}.yaml` — single-line edit per file: `apiVersion: ap.recipe/v0.1` → `apiVersion: ap.recipe/v0.2`. No other content touched.

## Validator Confirmation

```
=== SC-01: schema v0.2 additive, all 5 recipes parse ===
  PASS hermes.yaml (apiVersion=ap.recipe/v0.2)
  PASS nanobot.yaml (apiVersion=ap.recipe/v0.2)
  PASS nullclaw.yaml (apiVersion=ap.recipe/v0.2)
  PASS openclaw.yaml (apiVersion=ap.recipe/v0.2)
  PASS picoclaw.yaml (apiVersion=ap.recipe/v0.2)

=== RecipeSummary v0.2 surface ===
  hermes: persistent_mode=True channels=['telegram']
  nanobot: persistent_mode=True channels=['telegram']
  nullclaw: persistent_mode=True channels=['telegram']
  openclaw: persistent_mode=True channels=['telegram']
  picoclaw: persistent_mode=True channels=['telegram']
openclaw channel_provider_compat:
  {'telegram': {'supported': ['anthropic'], 'deferred': ['openrouter']}}
```

Discriminator edge cases (synthetic probes):
- v0.1 minimal (no persistent/channels) → 0 errors (passes v0_1 branch).
- apiVersion=v9.9 → fails both branches (correct).
- v0.2 with BAD CHANNEL ID key (uppercase+space) → 1 error (propertyNames pattern).
- v0.2 apiVersion but no persistent/channels → 0 errors (both optional even under v0.2).
- v0.1 recipe with persistent block (without apiVersion bump) → fails (correct — must opt in via apiVersion).

## Decisions Made

- **Bump 5 recipes' apiVersion** rather than relax v0_2 to accept v0.1. The plan's chosen pattern (oneOf with apiVersion const discrimination) only works if recipes declare their target branch. A single-header edit per recipe preserves all v0.1 content and satisfies SC-01 cleanly.
- **persistent.argv_note / lifecycle_note at persistent top-level** (not in spec) to match every committed recipe's actual shape. Plan spec was slightly wrong; empirical data won.
- **graceful_shutdown_s=0 as valid sentinel** so nanobot's documented ignore-SIGTERM pattern can declare real data rather than a misleading "1 second" value.
- **Loosen `secret` to optional** on `user_input_entry` since hermes's `optional_user_input` carries operational-only entries without a secret flag.
- **Separate `channel_category` $defs** (not a mutation of `category`) so `BLOCKED_UPSTREAM` stays out of v0.1 semantic space. Future v0.3 can merge if needed; defensive choice today.
- **lint_recipe drill-into-context** rather than accept opaque root errors — preserves Phase 18 WR-01 error-path quality contract that Phase 22 would otherwise regress.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Bumped apiVersion on 5 recipes to ap.recipe/v0.2**
- **Found during:** Task 2 verification
- **Issue:** Plan SC-01 requires all 5 recipes to validate under v0.2 oneOf, but recipes currently carry `apiVersion: ap.recipe/v0.1` + drafted persistent/channels blocks. Under strict oneOf discrimination, they match neither v0_1 (additionalProperties rejects persistent/channels) nor v0_2 (apiVersion const mismatch).
- **Fix:** Bumped each recipe's `apiVersion:` header line from `ap.recipe/v0.1` → `ap.recipe/v0.2`. No v0.1 content modified. Plan `files_modified` did not list recipes but SC-01 is unattainable without this edit.
- **Files modified:** recipes/{hermes,nanobot,nullclaw,openclaw,picoclaw}.yaml
- **Verification:** all 5 recipes pass `jsonschema.validate()` under v0.2 oneOf
- **Committed in:** `b744a82`

**2. [Rule 3 - Blocking] Relaxed graceful_shutdown_s minimum from 1 to 0**
- **Found during:** Task 2 verification (nanobot failure)
- **Issue:** Plan specified `graceful_shutdown_s: {minimum: 1}` but nanobot.yaml declares `graceful_shutdown_s: 0` as a deliberate sentinel meaning "skip SIGTERM — go straight to docker rm -f" (paired with `sigterm_handled: false`). Spike-07 documented this upstream.
- **Fix:** minimum=0 + docstring explaining the 0-sentinel semantic.
- **Files modified:** tools/ap.recipe.schema.json, docs/RECIPE-SCHEMA.md
- **Verification:** nanobot validates; other recipes unaffected
- **Committed in:** `b744a82`

**3. [Rule 3 - Blocking] `user_input_entry.secret` demoted to optional**
- **Found during:** Task 2 verification (hermes failure)
- **Issue:** Plan specified `secret: {required}` but hermes's `optional_user_input` entries (TELEGRAM_HOME_CHANNEL, TELEGRAM_HOME_CHANNEL_NAME) lack a `secret` field — they are operational-only non-secret config.
- **Fix:** Made `secret` optional on the shared user_input_entry schema; docstring explains convention (required_user_input entries should declare it true/false; optional_user_input typically omits).
- **Files modified:** tools/ap.recipe.schema.json
- **Verification:** hermes validates
- **Committed in:** `b744a82`

**4. [Rule 3 - Blocking] Moved `argv_note` / `lifecycle_note` from spec to top-level of persistent**
- **Found during:** Task 2 verification
- **Issue:** Plan spec put `argv_note` + `lifecycle_note` inside `persistent.spec`, but every committed recipe has them at `persistent.<top-level>` (peers of `mode` and `spec`).
- **Fix:** Schema `persistent_block` now has `argv_note` + `lifecycle_note` at top level (not in `spec`).
- **Files modified:** tools/ap.recipe.schema.json
- **Verification:** hermes/nanobot/nullclaw/openclaw/picoclaw all validate
- **Committed in:** `b744a82`

**5. [Rule 2 - Missing critical] Added `sigterm_handled` optional bool to persistent.spec**
- **Found during:** Task 2 empirical recipe survey
- **Issue:** All 5 recipes declare `sigterm_handled: true|false` inside `persistent.spec`. Plan's schema spec did not mention this field — would have forced every committed recipe to fail `additionalProperties: false`.
- **Fix:** Added as optional bool in persistent_block.spec with documentation.
- **Files modified:** tools/ap.recipe.schema.json
- **Verification:** 5 recipes validate
- **Committed in:** `b744a82`

**6. [Rule 1 - Bug] `lint_recipe` lost per-field error paths after oneOf flip**
- **Found during:** Task 2 regression test sweep (test_hardening_schema_review.py WR-01)
- **Issue:** My oneOf schema flip caused jsonschema to emit an opaque top-level error ("is not valid under any of the given schemas"), destroying the per-field path info (`source.ref`, `owner_uid`) that Phase 18 WR-01 hardening tests explicitly verify. Same problem the pre-plan `$comment` flagged.
- **Fix:** `lint_recipe` now drills into `e.context` for oneOf errors, filters apiVersion-const mismatch noise, prefers the target branch, and dedups messages. New `_select_oneof_branch_errors` helper.
- **Files modified:** tools/run_recipe.py
- **Verification:** 9 WR-01/WR-02/WR-04 hardening tests + 3 schema-selfcheck tests all pass; test_lint.py broken-recipes tests pass (dedup works)
- **Committed in:** `b744a82`

**7. [Rule 1 - Bug] maintainer projection in to_summary was passing dict to `str | None`**
- **Found during:** Task 3 dev
- **Issue:** `RecipeSummary.maintainer: str | None` but `metadata.get("maintainer")` returns a dict (v0.1.1 `{name, url?}` shape). The pre-plan code was technically already incorrect against v0.1.1 recipes that used the object maintainer shape — they would have raised a Pydantic validation error if tested.
- **Fix:** Project to the `.name` string when the value is a dict.
- **Files modified:** api_server/src/api_server/services/recipes_loader.py
- **Verification:** all 5 recipes serialize through RecipeListResponse; no Pydantic errors
- **Committed in:** `9b70e09`

---

**Total deviations:** 7 auto-fixed (3× Rule 3 blocking, 2× Rule 2 missing, 2× Rule 1 bug)
**Impact on plan:** All deviations necessary for correctness. No scope creep — every fix was either (a) required to make SC-01's validator run clean against the 5 committed recipes, (b) required to keep Phase 18's WR-01 error-path contract valid, or (c) a latent bug in the existing RecipeSummary maintainer projection that the new recipes would trip. Plan intent preserved; plan letter slightly exceeded.

## Issues Encountered

- **Pre-existing `test_roundtrip.py::test_yaml_roundtrip_is_lossless[picoclaw]` failure.** ruamel emits `\U0001F44B` for `👋` in picoclaw's `reply_sample` text field, losing emoji round-trip fidelity. Confirmed pre-existing via `git stash`+test-run on HEAD=2ea0118 (before any plan-22-01 edits). Logged to `.planning/phases/22-channels-v0.2/deferred-items.md`; fix is a one-liner (`allow_unicode=True` on the dumper) but is out of plan-22-01 scope — neither the plan's files_modified nor the task-2 `files_modified` cite picoclaw.yaml content changes or the run_recipe.py YAML dumper.

## User Setup Required

None — no external service configuration required. All BYOK secrets (telegram bot tokens, anthropic/openrouter keys) continue to flow through request body only (golden rule #2: dumb client, intelligence in the API).

## Next Phase Readiness

**Ready for:**
- Plan 22-02 (runner `--mode persistent`): can read `recipe["persistent"]` with confidence; schema guarantees shape. `health_check.kind` discriminator is live for the polling-branch logic.
- Plan 22-03 (API /v1/agents/:id/{start,stop,status,pair}): `RecipeSummary.persistent_mode_available` + `channels_supported` + `channel_provider_compat` are the gate fields. Agents.py can refuse `/start` for recipes where `persistent_mode_available == False` without parsing raw YAML.
- Plan 22-06 (frontend Step 2.5): TS type is updated; UI can read `channels_supported` and `channel_provider_compat` directly from the existing `GET /v1/recipes` payload — no new endpoint needed for gate logic. The openclaw "use Anthropic direct" copy switch is driven by `channel_provider_compat.telegram.deferred.includes("openrouter")`.

**Blockers or concerns:**
- None for the channels-v0.2 track. ap.recipe/v0.3 might want to merge `category` and `channel_category` once `BLOCKED_UPSTREAM` becomes relevant to smoke cells too; deferred.
- Pre-existing picoclaw roundtrip test failure remains; logged.

## Threat Flags

No new network endpoints, auth paths, file-access patterns, or schema changes at trust boundaries were introduced. Plan added fields to an existing internal contract (RecipeSummary) and an existing schema file. No new threat surface.

## Self-Check: PASSED

### Artifact existence

```
FOUND: docs/RECIPE-SCHEMA.md
FOUND: tools/ap.recipe.schema.json
FOUND: tools/run_recipe.py
FOUND: api_server/src/api_server/models/recipes.py
FOUND: api_server/src/api_server/services/recipes_loader.py
FOUND: frontend/lib/api-types.ts
FOUND: recipes/hermes.yaml
FOUND: recipes/nanobot.yaml
FOUND: recipes/nullclaw.yaml
FOUND: recipes/openclaw.yaml
FOUND: recipes/picoclaw.yaml
FOUND: .planning/phases/22-channels-v0.2/deferred-items.md
```

### Commit existence

```
FOUND: e0775ab (Task 1)
FOUND: b744a82 (Task 2)
FOUND: 9b70e09 (Task 3)
```

### SC confirmation

- SC-01 ✅ — `jsonschema.Draft202012Validator(schema).iter_errors(recipe)` returns zero errors for all 5 committed recipes under the v0.2 oneOf branch.

---
*Phase: 22-channels-v0.2*
*Completed: 2026-04-18*
