---
phase: 25-mobile-screens
plan: 05
subsystem: ui
tags: [flutter, new-agent, wizard, riverpod-scoped, model-picker, dtos, byok, ui-02]

# Dependency graph
requires:
  - phase: 25-mobile-screens (Wave 1, plan 25-02)
    provides: go_router /new-agent/clone /new-agent/model /new-agent/model/picker stub routes; wizard_*_screen stub files; ConfirmDialog
  - phase: 25-mobile-screens (Wave 1, plan 25-03)
    provides: SkeletonRow (reused for clone-card loading vocabulary)
  - phase: 25-mobile-screens (Wave 2, plan 25-04)
    provides: recipesProvider (cached AsyncValue<List<Recipe>>); Recipe DTO with optional description; secureStorageProvider override path; auth substrate
  - phase: 24-flutter-foundation
    provides: Typed ApiClient + Result<T> + ApiError; OpenRouterModel DTO; SolvrTheme; secureStorage.{readByokKey, writeByokKey}; http_mock_adapter dev_dep
  - phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
    provides: GET /v1/recipes/{name} response shape ({"recipe": {...full yaml dict...}})

provides:
  - RecipeDetail / ChannelUserInput / RecipeChannelMeta / ChannelProviderCompat DTOs (mobile/lib/core/api/dtos.dart) — hand-written fromJson per Phase 24 D-34
  - ApiEndpoints.recipeDetail(name) static URL builder (T-25-05-03 mitigation note)
  - ApiClient.recipeDetail(name) returning Result<RecipeDetail>
  - wizardScopeProvider + WizardScopeState (Pitfall #10 Pattern A; selectedRecipe, selectedModel, byokKey, agentName, telegramEnabled, telegramInputs, isDirty/clear)
  - modelsProvider (cached AsyncValue<List<OpenRouterModel>>) — D-26 source for picker
  - WizardShell (X close + 3-dot stepper + body slot; D-31 cancel UX with ConfirmDialog when dirty)
  - CloneStep (horizontal recipe cards from recipesProvider per D-25; selection upgrades summary→detail via api.recipeDetail())
  - ModelStep (D-26 push picker; D-32 BYOK label-swap from channelProviderCompat[inapp].deferred; D-33 auto-fill from secureStorage; D-34 obscureText + eye-toggle)
  - ModelPickerScreen (full-screen MaterialPageRoute; virtualized ListView.builder; search + empty caption)

affects:
  - 25-mobile-screens (Wave 3 plan 25-06) — DeployStep reads wizardScope.{selectedRecipe, selectedModel, byokKey, agentName, telegramEnabled, telegramInputs}; calls wizardScope.clear() on Deploy success per D-60
  - 25-mobile-screens (Wave 5 spike) — exit-gate test drives the full Login → Dashboard → CloneStep → ModelStep → ModelPicker → DeployStep flow

# Tech tracking
tech-stack:
  added: []  # Reuses existing Phase 24/25 substrate; no pubspec changes
  patterns:
    - "Pitfall #10 Pattern A — single Notifier for wizard scope, manually invalidated on close (D-31) and Deploy success (D-60). No autoDispose — there is only one wizard at a time, so explicit invalidation is simpler than ProviderScope override + ShellRoute (Pattern B)."
    - "DTO subclassing for upgrade paths — RecipeDetail extends Recipe so wizardScope.selectedRecipe can hold either the list-summary or the detail without re-architecting the field type after upgrade fetch."
    - "Wire-shape unwrap in fromJson — RecipeDetail.fromJson accepts both {\"recipe\": {...}} (live API) and the inner dict (test convenience); single factory handles both."
    - "Server-derived flag synthesis — channelProviderCompat is computed by walking channels.<id>.provider_compat in the detail dict (recipes_loader.py:128-143 mirror) instead of reading a flat top-level field. Mobile self-contained; no need to merge summary+detail at the wizardScope layer."
    - "MaterialPageRoute push for the model picker — bypasses go_router so Navigator.pop(picked) returns the selection to the awaiting context.push<OpenRouterModel>() in ModelStep. Simpler than wiring a result-channel through go_router state."
    - "Deferred postFrameCallback hydration — _hydrateFromStorage runs once per provider key in postFrameCallback so ref.read of secureStorageProvider doesn't trip the build-phase assertion. Provider-key change (e.g. user goes back to step 1 and switches recipe) re-hydrates."

key-files:
  created:
    - mobile/lib/features/new_agent/wizard_providers.dart
    - mobile/lib/features/new_agent/wizard_providers.g.dart  # riverpod_generator output
    - mobile/lib/features/new_agent/wizard_shell.dart
    - mobile/test/core/api/dtos_recipe_detail_test.dart
    - mobile/test/core/api/api_client_recipe_detail_test.dart
    - mobile/test/features/new_agent/wizard_scope_test.dart
    - mobile/test/features/new_agent/wizard_shell_test.dart
    - mobile/test/features/new_agent/clone_step_test.dart
    - mobile/test/features/new_agent/model_step_test.dart
    - mobile/test/features/new_agent/byok_label_test.dart
    - mobile/test/features/new_agent/model_picker_screen_test.dart
  modified:
    - mobile/lib/core/api/dtos.dart  # +ChannelUserInput, RecipeChannelMeta, ChannelProviderCompat, RecipeDetail
    - mobile/lib/core/api/api_endpoints.dart  # +recipeDetail(name)
    - mobile/lib/core/api/api_client.dart  # +recipeDetail() method
    - mobile/lib/features/new_agent/clone_step.dart  # Wave 1 stub replaced
    - mobile/lib/features/new_agent/model_step.dart  # Wave 1 stub replaced
    - mobile/lib/features/new_agent/model_picker_screen.dart  # Wave 1 stub replaced
    - mobile/lib/features/dashboard/dashboard_providers.g.dart  # codegen hash drift only (regenerated by build_runner alongside wizard_providers.g.dart)

key-decisions:
  - "RecipeDetail.fromJson unwraps {\"recipe\": ...} envelope inside the DTO instead of in ApiClient.recipeDetail(). Reason: keeps the wire-shape contract co-located with the parser, and tests can pass the inner dict directly without constructing the wrapper. (Plan example assumed flat shape — corrected to mirror the actual api_server.routes.recipes.RecipeDetailResponse passthrough.)"
  - "channelProviderCompat synthesized by walking channels.<id>.provider_compat in the detail response rather than expecting a flat channel_provider_compat top-level field. Reason: the flat field exists ONLY in RecipeSummary (list endpoint); the detail endpoint passes through the raw recipe YAML which has provider_compat scoped per channel. Mirrors recipes_loader.py:128-143 server-side derivation; keeps mobile self-contained with one fetch per recipe selection."
  - "Pattern A (single keepAlive Notifier + manual clear()) over Pattern B (ProviderScope override + ShellRoute) for wizardScopeProvider per Pitfall #10. Reason: only one wizard at a time; Pattern B's elegance is overkill for the cardinality."
  - "Hand-written WidgetsBinding.addPostFrameCallback for BYOK auto-fill instead of initState because ModelStep's storageProvider key depends on the recipe (which lands AFTER initState — set in CloneStep, observed via ref.watch). The _hydratedFor field gates re-hydration so subsequent rebuilds don't double-write."
  - "MaterialPageRoute (Navigator.push) for ModelPickerScreen instead of context.push via go_router. Reason: go_router's push works for screen state but the awaited return value flow (`final picked = await context.push<OpenRouterModel>(...)`) needs the picker's pop(value) to surface back through the same go_router call — testing that across multiple screens is fragile. The picker is a pure modal-style screen; MaterialPageRoute is the simpler primitive. The go_router /new-agent/model/picker route is preserved (still wired in app_router.dart) for deep-link compatibility, but production flow uses Navigator.push."

patterns-established:
  - "Permissive defensive parser for wire shapes that may grow — every new optional recipe-yaml field defaults to null/empty in the Dart fromJson; additive backend changes don't crash the wizard (Open Question #3 from 25-RESEARCH)."
  - "Sub-class-on-upgrade for DTOs — list summary → detail via subclass, so the same field can hold either form without `as` casts everywhere. Reusable for any future endpoint pair where the detail is a strict superset of the summary."
  - "Server-driven label flips: read recipe metadata in the build method, NEVER `if recipe.name == 'X'`. The dedicated byok_label_test.dart is a Golden-Rule-#2 regression gate: a future contributor can't sneak in a Dart-side recipe-name branch without breaking that test (the fixture varies ONLY in channelProviderCompat — the recipe.name is the same `fixture` in both cases)."

requirements-completed: [UI-02]

# Metrics
duration: ~19min
completed: 2026-05-03
---

# Phase 25 Plan 05: New Agent Wizard — Clone + Model + ModelPicker + RecipeDetail DTOs Summary

**Wave 3 wizard scaffolding ships the BYOK label-swap gate — a server-driven, pattern-tested guard against the Golden Rule #2 anti-pattern (`if recipe == 'hermes'`). Three step screens, four DTOs, one Riverpod scope, one shared chrome widget; 43 new tests.**

## Performance

- **Duration:** ~19 min (start 2026-05-03T17:48:38Z; end 2026-05-03T18:07:14Z)
- **Tasks:** 3 (all committed atomically)
- **Files created:** 11 (3 lib + 8 test) + 1 generated output (.g.dart)
- **Files modified:** 7 (3 core/api lib + 3 features/new_agent lib stubs replaced + 1 dashboard codegen drift)

## Accomplishments
- 4 new DTO classes (ChannelUserInput / RecipeChannelMeta / ChannelProviderCompat / RecipeDetail) with hand-written `fromJson` per Phase 24 D-34. RecipeDetail extends Recipe (drop-in subtype after upgrade fetch).
- ApiEndpoints.recipeDetail(name) static URL builder + ApiClient.recipeDetail() method mirroring the recipes() shape; both 200/404 paths covered by http_mock_adapter tests.
- wizardScopeProvider implemented as Pitfall #10 Pattern A — single Notifier + clear(); WizardScopeState carries every wizard field (selectedRecipe, selectedModel, byokKey, agentName, telegramEnabled, telegramInputs) with isDirty derivation.
- modelsProvider (D-26 picker source) lives in wizard_providers.dart for cohesion.
- WizardShell renders the X close + 3-dot stepper + caption labels + body slot; D-31 cancel UX raises ConfirmDialog when isDirty, pops immediately when not.
- CloneStep — horizontal recipe-card row from recipesProvider per D-25; tap upgrades summary to detail via api.recipeDetail(name) and stores in wizardScope; Next gated on selection.
- ModelStep — D-26 push picker (MaterialPageRoute), D-32 BYOK label-swap from channelProviderCompat[inapp].deferred (server-driven, NEVER Dart-branched), D-33 auto-fill from secureStorage, D-34 obscureText + eye-toggle, autocorrect/enableSuggestions = false.
- ModelPickerScreen — full-screen scaffold with search TextField + virtualized ListView.builder + tap-row-pops-with-selection; empty filter caption per UI-SPEC line 199.
- 43 new tests across 8 test files; mobile suite total 213/213 + 2 skipped (was 170 + 2). All tests use real dio + http_mock_adapter (no service mocks per Golden Rule #1).
- `flutter analyze` exits 0 on every Plan 25-05 file.

## Task Commits

1. **Task 1: DTOs + ApiEndpoints + ApiClient.recipeDetail** — `4a295a7` (feat)
   - 4 new classes in dtos.dart; recipeDetail(name) static fn in api_endpoints.dart; recipeDetail() method in api_client.dart.
   - 13 new tests (11 DTO unit + 2 ApiClient http_mock_adapter). Mobile total 183/183 + 2 skipped.

2. **Task 2: wizardScopeProvider + WizardShell** — `775340a` (feat)
   - wizard_providers.dart (WizardScopeState + WizardScope Notifier + modelsProvider), wizard_shell.dart (chrome + cancel UX).
   - 11 new tests (5 scope ProviderContainer + 6 shell widget). Mobile total 194/194 + 2 skipped. dashboard_providers.g.dart hash drift (codegen regen alongside wizard_providers.g.dart).

3. **Task 3: CloneStep + ModelStep + ModelPickerScreen** — `9b9fbaa` (feat)
   - 3 step screens replace Wave 1 stubs. CloneStep horizontal cards from recipesProvider; ModelStep BYOK + label-swap; ModelPickerScreen virtualized search.
   - 19 new tests (5 clone + 6 model_step + 3 byok_label + 5 model_picker). Mobile total 213/213 + 2 skipped.

_Note: Each task implemented TDD-style (RED → GREEN → small REFACTOR for analyze lints). build_runner is invoked once after writing wizard_providers.dart; the .g.dart commits per existing repo convention._

## Files Created/Modified

### Created (lib)
- `mobile/lib/features/new_agent/wizard_providers.dart` — wizardScopeProvider (Pattern A) + modelsProvider; WizardScopeState (selectedRecipe, selectedModel, byokKey, agentName, telegramEnabled, telegramInputs, isDirty, clear).
- `mobile/lib/features/new_agent/wizard_providers.g.dart` — riverpod_generator output (committed per repo convention).
- `mobile/lib/features/new_agent/wizard_shell.dart` — common chrome (X close + 3-dot stepper + body slot); D-31 cancel UX.

### Created (tests)
- `mobile/test/core/api/dtos_recipe_detail_test.dart` — 11 tests (ChannelUserInput, RecipeChannelMeta, ChannelProviderCompat, RecipeDetail wrapped/unwrapped/empty/subtype).
- `mobile/test/core/api/api_client_recipe_detail_test.dart` — 2 tests (200/404).
- `mobile/test/features/new_agent/wizard_scope_test.dart` — 5 tests (default, every setter, clear).
- `mobile/test/features/new_agent/wizard_shell_test.dart` — 6 tests (step 1 chrome, step 2 chrome, !isDirty close, isDirty Cancel, isDirty Discard, back-arrow preserves state).
- `mobile/test/features/new_agent/clone_step_test.dart` — 5 tests (renders cards, Next disabled, tap-upgrades-to-detail, Next routes, horizontal scroll axis).
- `mobile/test/features/new_agent/model_step_test.dart` — 6 tests (Pick a model push, selected model card + Change, obscureText/autocorrect, eye-toggle, auto-fill from secureStorage, onChanged persist + Next gate).
- `mobile/test/features/new_agent/byok_label_test.dart` — 3 tests (OpenRouter default, Anthropic when deferred contains openrouter, defensive default no-recipe).
- `mobile/test/features/new_agent/model_picker_screen_test.dart` — 5 tests (renders ListView + search, query filters, empty caption, tap pops with selection — `_PushHost` harness for the MaterialPageRoute return value).

### Modified
- `mobile/lib/core/api/dtos.dart` — +ChannelUserInput / RecipeChannelMeta / ChannelProviderCompat / RecipeDetail classes.
- `mobile/lib/core/api/api_endpoints.dart` — +recipeDetail(name) with T-25-05-03 mitigation note (recipe-name regex precludes path traversal).
- `mobile/lib/core/api/api_client.dart` — +recipeDetail() method between recipes() and models().
- `mobile/lib/features/new_agent/clone_step.dart` — Wave 1 stub replaced with full UI-01 ConsumerWidget.
- `mobile/lib/features/new_agent/model_step.dart` — Wave 1 stub replaced; ConsumerStatefulWidget owning controller + obscureText + hydrated flag.
- `mobile/lib/features/new_agent/model_picker_screen.dart` — Wave 1 stub replaced; ConsumerStatefulWidget with search controller + virtualized list.
- `mobile/lib/features/dashboard/dashboard_providers.g.dart` — codegen hash drift only (recomputed by build_runner alongside wizard_providers.g.dart). Functional content unchanged.

## Decisions Made
- **Wire-shape unwrap inside RecipeDetail.fromJson**: the live API returns `{"recipe": {...}}` (RecipeDetailResponse.model_dump). RecipeDetail.fromJson handles both wrapped and unwrapped input — co-locates the contract with the parser; tests can pass the inner dict directly without re-wrapping. This was a plan-illustrative correction: the plan's example assumed flat shape.
- **Synthesize channelProviderCompat from channels.<id>.provider_compat** (recipes_loader.py:128-143 mirror) instead of reading a flat top-level field that exists ONLY in RecipeSummary (list endpoint). Keeps mobile self-contained: one detail fetch per recipe selection, no need to merge summary+detail in wizardScope. The plan's example used the flat field; corrected to match actual wire shape.
- **Pitfall #10 Pattern A** for wizardScopeProvider — single keepAlive Notifier with explicit `.clear()` calls. Pattern B's ProviderScope+ShellRoute is over-engineered for a single-instance wizard and harder to test (would require additional ProviderScope wiring in widget tests).
- **MaterialPageRoute for the model picker** rather than go_router context.push. Reason: tests need to assert the picker pops with a typed return value back to ModelStep's `await context.push<OpenRouterModel>()`. MaterialPageRoute makes the return-value flow explicit at one widget; go_router's typed push works but couples the picker to the router config. The /new-agent/model/picker GoRoute still exists in app_router.dart (Wave 1 carry-forward) for deep-link consistency.
- **postFrameCallback for BYOK auto-fill** instead of initState — the storageProvider key depends on `selectedRecipe.channelProviderCompat[inapp].deferred`, which is set in step 1, observed in step 2 via ref.watch. initState would read the Provider before it stabilizes. _hydratedFor flag gates per-provider single-shot hydration so a recipe switch (e.g. user goes back to step 1, picks hermes after openclaw) re-hydrates with the anthropic key, not the openrouter one.
- **byok_label_test.dart as Golden-Rule-#2 regression gate** — fixture recipes vary ONLY in channelProviderCompat; recipe.name is `fixture` in both cases. A future contributor sneaking in `if recipe.name == 'hermes'` would break the test on the Anthropic-label assertion. The pattern-matching server-driven flag is the contract under test, not the recipe name.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's RecipeDetail.fromJson assumed flat top-level `channel_provider_compat` field**
- **Found during:** Task 1 (writing the Read-first analysis of api_server.models.recipes)
- **Issue:** The plan example (lines 313-321) read `json['channel_provider_compat']` as if it existed at the detail-response top level. Inspection of `api_server/src/api_server/models/recipes.py:75-84` showed `RecipeDetailResponse` is a passthrough of the raw recipe YAML wrapped under a `recipe` key — `channel_provider_compat` exists ONLY in `RecipeSummary` (the list endpoint). The detail YAML has `provider_compat` scoped per channel at `channels.<id>.provider_compat`.
- **Fix:** RecipeDetail.fromJson unwraps `{"recipe": {...}}` and synthesizes `channelProviderCompat` by walking `channels.<id>.provider_compat` (recipes_loader.py:128-143 server-side derivation mirror). DTO contract is unchanged from the plan's surface (still exposes a `Map<String, ChannelProviderCompat>`); only the parser logic differs.
- **Files modified:** mobile/lib/core/api/dtos.dart, mobile/test/core/api/dtos_recipe_detail_test.dart (test fixture uses the actual wire shape with provider_compat nested under channels).
- **Verification:** test/core/api/dtos_recipe_detail_test.dart `parses an inapp+telegram recipe (wrapped {"recipe": ...} form)` asserts the synthesis works against an openclaw-shaped fixture.
- **Committed in:** `4a295a7` (Task 1 commit)

**2. [Rule 1 - Bug] Plan example used `final Map<String, dynamic> r =` (omit_local_variable_types lint)**
- **Found during:** Task 1 GREEN analyze pass
- **Issue:** Plan code style violated very_good_analysis `omit_local_variable_types`.
- **Fix:** `final r = ...` (type inferred from the conditional expression).
- **Committed in:** `4a295a7` (Task 1 commit)

**3. [Rule 1 - Bug] Plan example put `super.description` between two required params (always_put_required_named_parameters_first lint)**
- **Found during:** Task 1 GREEN analyze pass
- **Issue:** RecipeDetail constructor had `required super.name, required super.channelsSupported, super.description, required this.channels, required this.channelProviderCompat`. The optional `super.description` between required params violates the lint.
- **Fix:** Reordered to put all 4 required first, optional last.
- **Committed in:** `4a295a7` (Task 1 commit)

**4. [Rule 1 - Bug] Plan example imported flutter_riverpod alongside riverpod_annotation in wizard_providers.dart (unnecessary_import lint)**
- **Found during:** Task 2 GREEN analyze pass
- **Issue:** All used elements come from riverpod_annotation; flutter_riverpod import was redundant.
- **Fix:** Removed the flutter_riverpod import.
- **Committed in:** `775340a` (Task 2 commit)

**5. [Rule 3 - Blocking] context.push<OpenRouterModel>() return-value flow couldn't reliably round-trip the typed value back to ModelStep through go_router config**
- **Found during:** Task 3 implementation
- **Issue:** Plan example used `context.push<OpenRouterModel>('/new-agent/model/picker')`. go_router's typed result flow is ambiguous when the picker pops with `Navigator.of(context).pop(filtered[i])` because the GoRoute defines no `result` typing. Tests would have needed extra fixture ceremony to assert the round-trip.
- **Fix:** ModelPickerScreen is pushed via `Navigator.push(MaterialPageRoute<OpenRouterModel>(builder: (_) => const ModelPickerScreen()))` from ModelStep, and `Navigator.pop(model)` returns the typed value to the awaiting future. Tests use a `_PushHost` widget that demonstrates the round-trip in isolation. The GoRoute /new-agent/model/picker still exists in app_router.dart for deep-link consistency.
- **Files modified:** mobile/lib/features/new_agent/model_step.dart (`Navigator.push` instead of `context.push`), mobile/test/features/new_agent/model_picker_screen_test.dart (`_PushHost` harness asserts the typed pop value).
- **Verification:** model_picker_screen_test.dart `tap row pops with the selection` test asserts the host widget receives `PICKED:<id>` after the pop.
- **Committed in:** `9b9fbaa` (Task 3 commit)

**6. [Rule 1 - Bug] Plan example used `WidgetsBinding.instance.addPostFrameCallback` to call `_hydrateFromStorage` — without `unawaited()` triggers discarded_futures lint, and called bare callback function with no argument inside the ref.read closure**
- **Found during:** Task 3 GREEN analyze pass
- **Issue:** discarded_futures lint flagged the bare `_hydrateFromStorage(...)` invocation inside the postFrameCallback. The future is correctly fire-and-forget but the lint requires explicit acknowledgment.
- **Fix:** `unawaited(_hydrateFromStorage(cfg.storageProvider))` + added `dart:async` import. Comment documents that the future owns its own mounted-check + per-provider single-shot guard.
- **Committed in:** `9b9fbaa` (Task 3 commit)

**7. [Rule 1 - Bug] Plan tests used non-cascade `final adapter = DioAdapter(dio: dio); adapter.onGet(...)` (cascade_invocations lint)**
- **Found during:** Task 3 GREEN analyze pass
- **Issue:** Three test fixture builder functions had the same pattern. Lint surfaced the redundant receiver.
- **Fix:** `DioAdapter(dio: dio).onGet('/v1/models', (s) => s.reply(...))` chained directly. The adapter holds a reference internally to dio so the side-effect outlives the expression.
- **Files modified:** test/features/new_agent/byok_label_test.dart, test/features/new_agent/model_picker_screen_test.dart, test/features/new_agent/model_step_test.dart.
- **Committed in:** `9b9fbaa` (Task 3 commit)

**8. [Rule 1 - Bug] clone_step_test.dart `_summary` builder used `if (description != null) 'description': description` (use_null_aware_elements lint)**
- **Found during:** Task 3 GREEN analyze pass
- **Issue:** Lint flagged the if-conditional map entry as preferable to a null-aware value spread.
- **Fix:** `'description': ?description` — Dart 3 null-aware-value syntax keeps the entry only when the value is non-null. (First attempt used `?'description': description` — wrong: the `?` annotates the value, not the key. Re-read the lint output to correct the syntax.)
- **Committed in:** `9b9fbaa` (Task 3 commit)

**9. [Rule 1 - Bug] WizardScope's `setTelegramEnabled(bool v)` triggers avoid_positional_boolean_parameters lint**
- **Found during:** Task 2 GREEN analyze pass
- **Issue:** very_good_analysis flags positional bool params. But the rest of the WizardScope setter API is symmetric `setX(value)` shape; named-param wrapping for one setter would add ceremony at every callsite.
- **Fix:** `// ignore: avoid_positional_boolean_parameters` with a documentation comment explaining the symmetry rationale. document_ignores lint then surfaces — added the doc comment to satisfy.
- **Committed in:** `775340a` (Task 2 commit)

---

**Total deviations:** 9 auto-fixed (5 plan-illustrative-code corrections + 3 lint cleanups + 1 architectural-pivot from go_router push to MaterialPageRoute). All deviations preserve the plan's contract surface; no architectural changes that would affect Plan 25-06 (which reads wizardScope).

## Issues Encountered

- **api_server detail-response shape research.** Initial reading of the plan's RecipeDetail.fromJson example assumed flat shape; ~5 min of cross-referencing api_server.routes.recipes + api_server.services.recipes_loader + recipes/openclaw.yaml established the actual wire shape (wrapped under "recipe" key; provider_compat nested per channel). Documented in the dtos.dart class doc and dtos_recipe_detail_test.dart fixtures.
- **go_router typed return-value uncertainty.** Initial Task 3 plan example used `await context.push<OpenRouterModel>()`. Spent ~3 min checking go_router's docs + the existing dashboard's Navigator usage before pivoting to MaterialPageRoute (cleaner contract for the typed return; still keeps the GoRoute for deep-link consistency).
- **build_runner regen drift on dashboard_providers.g.dart.** The codegen run for wizard_providers.dart also recomputed the AgentsList hash for dashboard_providers.g.dart (content-based). The diff is just one line (the hash string) — committed alongside the wizard codegen, no functional change.

[Note: Deviations from Plan documents unplanned work that was handled automatically. Issues Encountered documents debugging during planned work.]

## User Setup Required

None — no external service configuration. The plan adds Dart-only code; existing pubspec dependencies (riverpod_annotation, riverpod_generator, http_mock_adapter, flutter_secure_storage, dio, go_router) cover every test path.

## Next Phase Readiness

- **Wave 3 plan 25-06 (DeployStep)**: wizardScope ships with every field DeployStep needs (selectedRecipe, selectedModel, byokKey, agentName, telegramEnabled, telegramInputs). The plan's `clear()` is the canonical exit hook (D-60 — call after Deploy success); D-31 cancel-X already calls it via WizardShell.
- **RecipeDetail in wizardScope** means DeployStep can read `selectedRecipe.channels.telegram.allInputs` directly for the dynamic Telegram fields (D-54) without an additional fetch — wizardScope already holds the detail.
- **modelsProvider** is keepAlive — Plan 25-06 doesn't refetch; the picker selection persists across step transitions per D-26.
- **BYOK key persistence** is handled — DeployStep reads `wizardScope.byokKey` for the Authorization Bearer header on /runs and /start; secureStorage.readByokKey() is the recovery path on next-wizard-open per D-33.

### Known Gaps (deferred)

- **CloneStep error UX**: when api.recipeDetail() fails (404 / 500 / network) the selection silently no-ops. Plan 25-06 may add an inline error banner; Wave 5 spike validates that recipes from `GET /v1/recipes` always have a corresponding detail (the API is the source of truth — orphan summaries shouldn't exist).
- **Picker price/context-length captions**: UI-SPEC line 579 mentions `{ctx_len/1000}k · ${price}/1M` caption right-aligned per row. OpenRouterModel DTO doesn't currently expose those fields (Phase 24 carry-forward); Plan 25-06 or Wave 5 polish will extend the DTO + parser if/when the visual contract demands it.
- **Loading vocabulary for clone cards**: `_LoadingCards` uses 3 SkeletonRow widgets in horizontal layout — the SkeletonRow primitive is row-shaped, so the 200×160 cards render with horizontally-stretched skeletons. Visually acceptable; a CloneCardSkeleton primitive could ship in Wave 5 polish if needed.

## Self-Check: PASSED

Verified files exist:
- FOUND: mobile/lib/core/api/dtos.dart (extended with 4 new classes)
- FOUND: mobile/lib/core/api/api_endpoints.dart (extended with recipeDetail(name))
- FOUND: mobile/lib/core/api/api_client.dart (extended with recipeDetail())
- FOUND: mobile/lib/features/new_agent/wizard_providers.dart
- FOUND: mobile/lib/features/new_agent/wizard_providers.g.dart
- FOUND: mobile/lib/features/new_agent/wizard_shell.dart
- FOUND: mobile/lib/features/new_agent/clone_step.dart (Wave 1 stub replaced)
- FOUND: mobile/lib/features/new_agent/model_step.dart (Wave 1 stub replaced)
- FOUND: mobile/lib/features/new_agent/model_picker_screen.dart (Wave 1 stub replaced)
- FOUND: mobile/test/core/api/dtos_recipe_detail_test.dart
- FOUND: mobile/test/core/api/api_client_recipe_detail_test.dart
- FOUND: mobile/test/features/new_agent/wizard_scope_test.dart
- FOUND: mobile/test/features/new_agent/wizard_shell_test.dart
- FOUND: mobile/test/features/new_agent/clone_step_test.dart
- FOUND: mobile/test/features/new_agent/model_step_test.dart
- FOUND: mobile/test/features/new_agent/byok_label_test.dart
- FOUND: mobile/test/features/new_agent/model_picker_screen_test.dart

Verified commits exist:
- FOUND: 4a295a7 (Task 1 — RecipeDetail DTOs + ApiClient.recipeDetail)
- FOUND: 775340a (Task 2 — wizardScopeProvider + WizardShell)
- FOUND: 9b9fbaa (Task 3 — Clone + Model + ModelPicker step screens)

Test count: baseline 170 + 2 skipped → 213 + 2 skipped (43 new tests; no prior tests regressed; no new skips). flutter analyze clean on every Plan 25-05 file.

deploy_step.dart: untouched (Plan 25-06 territory) — verified via `git diff HEAD~3 -- mobile/lib/features/new_agent/deploy_step.dart` (empty diff).
chat/, dashboard_screen.dart, dashboard_providers.dart: untouched — verified via `git status --short` showing only the 4 expected lib paths + 1 codegen drift.

---
*Phase: 25-mobile-screens*
*Completed: 2026-05-03*
