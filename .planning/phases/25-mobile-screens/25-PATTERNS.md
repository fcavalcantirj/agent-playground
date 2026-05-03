# Phase 25: Mobile Screens — Pattern Map

**Mapped:** 2026-05-03
**Files analyzed:** ~38 new + ~8 extended
**Analogs found:** 38/38 (100% — Phase 24 shipped a complete substrate; every Phase 25 file has a precedent)

> Phase 25's job is "fill the empty `lib/features/` dirs and add `lib/shared/` + `lib/core/auth/`."
> The substrate (typed `ApiClient`, `Result<T>`, `MessagesStream`, `AuthInterceptor`,
> `SecureStorage`, `solvrTheme`, `AppEnv`, `go_router` skeleton, integration_test harness,
> Makefile) is already shipped at commits `ccdb184` (CONTEXT) → `9038a97` (Phase 24 ship).
> **Every new Phase 25 file has at least one strong analog in `mobile/lib/` or `mobile/integration_test/`.**

---

## File Classification

### Wave 1 — Shared widgets, AuthService, Login, cold-start (D-61, D-04..D-07, D-01..D-03)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mobile/lib/shared/status_dot.dart` | shared-widget (stateless) | render-only | `mobile/lib/features/_placeholder/healthz_screen.dart` (theme consumer) + `mobile/lib/core/theme/solvr_theme.dart` (color tokens) | role-match (no widget-package precedent yet) |
| `mobile/lib/shared/empty_state_scaffold.dart` | shared-widget (stateless) | render-only | `healthz_screen.dart` `Scaffold` + `Column` shape | role-match |
| `mobile/lib/shared/ascii_agent_banner.dart` | shared-widget (`ConsumerWidget`) | stream-driven | `healthz_screen.dart` (Riverpod `ref.watch`) + `MessagesStream` (stream consumption) | role-match (first Stream-watching widget) |
| `mobile/lib/shared/retry_banner.dart` | shared-widget (stateless) | render + tap-callback | `healthz_screen.dart` `ElevatedButton(onPressed:)` | role-match |
| `mobile/lib/shared/skeleton_row.dart` | shared-widget (stateless) | render-only | (no skeleton precedent — stateless `Container` shape) `solvr_theme.dart` muted color | role-match |
| `mobile/lib/shared/typing_dots.dart` | shared-widget (stateful — `AnimationController`) | tick-driven | (no animation precedent — first `AnimationController` in repo) | new pattern |
| `mobile/lib/shared/failed_bubble.dart` | shared-widget (stateless) | render + tap-callback | (precedes any chat-bubble — pure render) | role-match |
| `mobile/lib/shared/restart_banner.dart` | shared-widget (stateless) | render + tap-callback | same as `retry_banner.dart` | role-match (sister widget) |
| `mobile/lib/shared/confirm_dialog.dart` | shared-widget (utility class — static `show()`) | future-returning | (first `AlertDialog` wrapper) | new pattern |
| `mobile/lib/core/auth/auth_service.dart` | service-interface (abstract class) | seam | `mobile/lib/core/api/result.dart` (sealed-class with `factory`) + `mobile/lib/core/api/messages_stream.dart` (`SseSubscribe` typedef = test seam) | exact (D-66 explicitly mirrors the test-seam shape) |
| `mobile/lib/core/auth/auth_service_real.dart` | service-impl (real OAuth) | request-response | `mobile/lib/core/api/api_client.dart` `authGoogleMobile` / `authGithubMobile` methods | exact |
| `mobile/lib/core/auth/auth_service_test_seam.dart` | service-impl (test) | env-driven | `mobile/integration_test/spike_api_roundtrip_test.dart` (`String.fromEnvironment` SESSION_ID injection lines 42-44) | exact |
| `mobile/lib/core/auth/providers.dart` (or fold into existing `core/api/providers.dart`) | provider-config | DI | `mobile/lib/core/api/providers.dart` `@Riverpod(keepAlive: true)` shape | exact |
| `mobile/lib/features/login/login_screen.dart` | screen-widget (`ConsumerStatefulWidget`) | request-response (OAuth) | `healthz_screen.dart` (StatefulWidget pattern + `_loading` flag + `setState` on Result) | exact (closest mirror — same shape) |
| `mobile/lib/features/login/login_state.dart` (planner-discretion: may fold into screen file) | wizard-scope provider | DI | `core/api/providers.dart` | exact |
| `mobile/lib/core/storage/secure_storage.dart` | EXTENDED — add per-provider BYOK methods | persistence | itself (existing `readSessionId/writeSessionId/clearSessionId` shape — D-33 extends with `readByokKey(provider)/writeByokKey(provider, key)`) | exact (extending its own shape) |
| `mobile/lib/main.dart` | EXTENDED — cold-start /users/me + initial route resolution | boot | itself (Phase 24 boot sequence) | exact (extending its own shape) |
| `mobile/lib/core/router/app_router.dart` | EXTENDED — fill 7 routes | navigation | itself (Phase 24 single-route skeleton, line 1-16) | exact |
| `mobile/lib/app.dart` | EXTENDED — keep router; replace initial-route logic | render | itself | exact |
| `mobile/lib/features/_placeholder/healthz_screen.dart` | DELETED (Wave 1) | — | — | — |
| `mobile/pubspec.yaml` | EXTENDED — version bump + deps | config | itself (Phase 24 dep block lines 11-23) | exact |

### Wave 2 — Dashboard (D-08..D-20)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mobile/lib/features/dashboard/dashboard_screen.dart` | screen-widget (`ConsumerStatefulWidget`) | request-response + lifecycle (foreground refetch) | `healthz_screen.dart` (Result-switch + initState refetch + setState on result) | exact |
| `mobile/lib/features/dashboard/dashboard_providers.dart` (planner-discretion) | provider-config | DI | `core/api/providers.dart` `apiClient(Ref ref)` | exact |
| `mobile/lib/features/dashboard/agent_row.dart` (planner-discretion split) | leaf-widget | render-only | `healthz_screen.dart` Row/Column shape | role-match |

### Wave 3 — New Agent wizard + ModelPicker + Telegram (D-21..D-34, D-54..D-60)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mobile/lib/features/new_agent/wizard_scope.dart` (or `wizard_state.dart`) | scoped-provider | DI (route-keyed) | `core/api/providers.dart` `@Riverpod(keepAlive: true)` (without keepAlive) | role-match (first NON-keepAlive provider in repo) |
| `mobile/lib/features/new_agent/clone_step.dart` | screen-widget (`ConsumerStatefulWidget`) | request-response (`recipes()`) | `healthz_screen.dart` + `playground-form.tsx` recipe-card pattern (cross-platform) | exact |
| `mobile/lib/features/new_agent/model_step.dart` | screen-widget | request-response (BYOK input) | `healthz_screen.dart` + `playground-form.tsx` lines 627-635 (BYOK label-swap from server metadata) | exact |
| `mobile/lib/features/new_agent/model_picker_screen.dart` | screen-widget (`ConsumerStatefulWidget`) | request-response (`models()` + virtualized search) | `api_client.dart::models()` method + `healthz_screen.dart` Result-switch shape | exact |
| `mobile/lib/features/new_agent/deploy_step.dart` | screen-widget | request-response (deploy sequence — 1 + N calls) | `playground-form.tsx` lines 316-360 (CANONICAL — see "Pattern Assignments §Wave 3") + `healthz_screen.dart` Result-switch | exact (cross-platform mirror) |
| `mobile/lib/features/new_agent/channel_inputs.dart` | leaf-widget | render-from-metadata | `playground-form.tsx` lines 638-689 (CANONICAL — dynamic field render-loop from `recipe.channels.<id>.required_user_input`) | exact (cross-platform mirror) |
| `mobile/lib/core/api/dtos.dart` | EXTENDED — add `RecipeDetail`, `ChannelUserInput`, `RecipeChannelMeta` | DTO | itself (existing `Recipe.fromJson` shape lines 183-199) | exact (extending its own shape) |
| `mobile/lib/core/api/api_client.dart` | EXTENDED — add `recipeDetail(name)` method | request-response | itself (existing `recipes()` method lines 206-220) | exact |
| `mobile/lib/core/api/api_endpoints.dart` | EXTENDED — add `recipeDetail(name)` path constant | config | itself (existing `agentMessages(id)` lines 16-22) | exact |

### Wave 4 — Chat (D-35..D-53)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mobile/lib/features/chat/chat_screen.dart` | screen-widget (`ConsumerStatefulWidget` + `WidgetsBindingObserver`) | streaming + request-response | `healthz_screen.dart` (lifecycle hooks) + `spike_api_roundtrip_test.dart` (CANONICAL — full GET history + SSE connect + post + dedupe + Last-Event-Id resume sequence in lines 121-244) | exact |
| `mobile/lib/features/chat/chat_state.dart` (planner-discretion: family scope) | scoped-family-provider | DI (per-agent) | `core/api/providers.dart` shape (without keepAlive — family) | role-match |
| `mobile/lib/features/chat/bubble_widget.dart` | leaf-widget | render-only | `failed_bubble.dart` (sister widget — same role-aligned bubble layout) | role-match (Wave 1 lands first) |
| `mobile/lib/features/chat/input_bar.dart` | leaf-widget | text-input | `healthz_screen.dart` `ElevatedButton` callback shape | role-match |

### Wave 5 — Tests + spike + artifact (D-65, D-66)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mobile/integration_test/screens_e2e_test.dart` | integration-test (`testWidgets` + `WidgetTester`) | live-API end-to-end | `mobile/integration_test/spike_api_roundtrip_test.dart` (CANONICAL — same harness, same `String.fromEnvironment` env-injection, same `IntegrationTestWidgetsFlutterBinding`) | exact |
| `mobile/integration_test/screens_e2e_helpers.dart` (planner-discretion) | test-helper | utility | `mobile/integration_test/spike_helpers.dart` (`expectOk`, `waitForOutbound`, `shortRandHex`, `extractAssistantContent`) | exact |
| `mobile/test/golden/login_golden_test.dart` | widget-test (golden) | snapshot | `mobile/test/smoke_test.dart` (`testWidgets` + `pumpWidget` + `pumpAndSettle` + `_RejectingAdapter` for blocking dio) | role-match (first golden_toolkit test) |
| `mobile/test/golden/dashboard_empty_golden_test.dart` | widget-test (golden) | snapshot | same | role-match |
| `mobile/test/golden/dashboard_populated_golden_test.dart` | widget-test (golden) | snapshot | same | role-match |
| `mobile/test/golden/chat_markdown_golden_test.dart` | widget-test (golden) | snapshot | same | role-match |
| `mobile/test/flutter_test_config.dart` (golden_toolkit boot — REQUIRED for `goldenToolkit`) | test-config | utility | (no precedent — first `flutter_test_config.dart`) | new pattern |
| `mobile/test/features/<screen>/<screen>_test.dart` (planner-discretion coverage matrix) | widget-unit | render | `test/api/api_client_test.dart` (`http_mock_adapter` seam), `test/api/messages_stream_test.dart` (in-process StreamController seam) | exact |
| `mobile/Makefile` | EXTENDED — add `make screens-e2e` | tooling | itself (existing `make spike` target lines 23-31 — same env-var preflight + curl healthcheck + `--dart-define` shape) | exact |
| `mobile/README.md` | EXTENDED — add screens-spike docs | docs | itself | exact |
| `spikes/flutter-screens-roundtrip.md` | spike artifact | doc | `spikes/flutter-api-roundtrip.md` (Phase 24 sibling) | exact |

### Out-of-tree (spec amendments per AMD-01..AMD-03)

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `.planning/REQUIREMENTS.md` (UI-02 rewrite) | spec amendment | doc | (Phase 23 D-32 amended REQUIREMENTS.md in its commit chain — same precedent) | role-match |
| `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-CONTEXT.md` (D-28 amendment paragraph) | spec amendment | doc | same | role-match |

---

## Pattern Assignments

> Every excerpt below is read-tested as of commit `9038a97` (Phase 24 ship + Pods scaffold).
> Line numbers are stable; copy-paste targets (excerpt + path + line range) are what the planner drops into each task's `read_first` block.

---

### Wave 1 — Shared widgets, AuthService, Login, cold-start

#### `mobile/lib/shared/status_dot.dart` (D-14, D-37)

**Analog:** `mobile/lib/core/theme/solvr_theme.dart` (color tokens) + `mobile/lib/features/_placeholder/healthz_screen.dart` (theme consumer)

**Color tokens to consume** (`solvr_theme.dart` lines 23-33):
```dart
abstract final class SolvrColors {
  SolvrColors._();
  // LOCKED (CONTEXT line 139)
  static const Color background = Color(0xFFFAFAF7); // --background
  static const Color foreground = Color(0xFF1F1F1F); // --foreground

  // OKLCH-derived (best-effort sRGB conversion; may revise)
  static const Color card = Color(0xFFFFFFFF); // --card
  static const Color muted = Color(0xFFEFEFEC);
  static const Color mutedForeground = Color(0xFF6B6B6B);
  static const Color border = Color(0xFFDEDEDA);
  static const Color destructive = Color(0xFFD9333A);
}
```

**Phase 25 task action — ADD `SolvrColors.success` (D-14 running green):**
```dart
// NEW — Phase 25 D-14 — running-state status dot.
static const Color success = Color(0xFF22C55E);
```

**Imports pattern** (mirror `healthz_screen.dart` lines 7-12):
```dart
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:flutter/material.dart';
```

---

#### `mobile/lib/shared/empty_state_scaffold.dart` (D-17, D-38, UI-SPEC §Component 2)

**Analog:** `mobile/lib/features/_placeholder/healthz_screen.dart`

**Scaffold + centered Column shape** (`healthz_screen.dart` lines 62-80):
```dart
return Scaffold(
  appBar: AppBar(title: const Text('>_ SOLVR_LABS')),
  body: Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          body,
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: _loading ? null : _refresh,
            child: const Text('Retry'),
          ),
        ],
      ),
    ),
  ),
);
```

> Phase 25's `EmptyStateScaffold` widget is the same shape generalized into a reusable widget with required `heading` + optional `banner`/`body`/`primaryAction` per UI-SPEC §Component 2 lines 280-296.

---

#### `mobile/lib/shared/ascii_agent_banner.dart` (D-17, UI-SPEC §Component 3)

**Analog:** `mobile/lib/core/api/messages_stream.dart` (Stream consumption) + `mobile/lib/features/_placeholder/healthz_screen.dart` (Riverpod `ref.watch`)

**ConsumerWidget Riverpod-stream pattern — extract from `healthz_screen.dart` lines 14-36 + `messages_stream.dart` `Stream<SseEvent> get events`:**

The pattern: a `ConsumerWidget` (or `ConsumerStatefulWidget`) that `ref.watch`es a Riverpod-supplied `Stream`, then renders one item at a time with `AnimatedSwitcher`. Phase 25's `recipesProvider` (UI-SPEC §State Management Contract line 671) supplies the names; the banner widget itself is pure (decoupled from data source — D-Discretion line 524).

**Mono text style — call this from the new widget:**
```dart
// solvr_theme.dart lines 49-55
static TextStyle mono({double? fontSize, FontWeight? fontWeight}) =>
    GoogleFonts.jetBrainsMono(
      fontSize: fontSize,
      fontWeight: fontWeight,
      color: SolvrColors.foreground,
    );
```

---

#### `mobile/lib/shared/retry_banner.dart`, `restart_banner.dart` (D-19, D-49, D-50)

**Analog:** `mobile/lib/features/_placeholder/healthz_screen.dart` `ElevatedButton(onPressed: ..., child: ...)` shape

**Tone discriminator (UI-SPEC §Component 4 line 335):**
```dart
enum RetryBannerTone { muted, warning }
```

> Same widget-shape as `restart_banner.dart` and the `RetryBanner` extension surface for D-50 (Telegram-failed). Both consume `SolvrColors.muted` as bg + `SolvrColors.foreground` as fg + the new `⚠` glyph (UI-SPEC line 173 — only emoji allowed).

---

#### `mobile/lib/shared/typing_dots.dart` (D-41, UI-SPEC §Component 6)

**Analog:** None in repo — first `AnimationController`. Use UI-SPEC contract (lines 370-380):

```dart
// 3 dots, each 6 px diameter, color fill, 4 px horizontal gap.
// AnimatedBuilder + 1200ms AnimationController.
// Each dot fades 0.3 → 1.0 → 0.3, staggered 0/400/800ms.
```

> No deps added (D-Discretion line 502 resolved: `AnimatedBuilder`, NOT Lottie). Use `with TickerProviderStateMixin` on `_TypingDotsState`.

---

#### `mobile/lib/shared/confirm_dialog.dart` (D-07, D-28, D-31, UI-SPEC §Component 9)

**Analog:** None in repo (first `AlertDialog`). UI-SPEC §Component 9 (lines 432-450) is canonical:
```dart
class ConfirmDialog {
  static Future<ConfirmDialogResult> show(
    BuildContext context, {
    required String title,
    String? body,
    String cancelLabel = 'Cancel',
    required String confirmLabel,
    bool destructive = true,
    String? thirdButtonLabel,        // optional (for D-28 "Rename" path)
  });
}
enum ConfirmDialogResult { cancel, confirm, third }
```

> `barrierDismissible: false`. Confirm button uses `SolvrColors.destructive` text (NOT background — UI-SPEC line 138).

---

#### `mobile/lib/core/auth/auth_service.dart` + `_real.dart` + `_test_seam.dart` (D-66)

**Analog 1 (interface shape):** `mobile/lib/core/api/result.dart` (sealed-class with factory) lines 17-21:
```dart
sealed class Result<T> {
  const Result();
  const factory Result.ok(T value) = Ok<T>;
  const factory Result.err(ApiError error) = Err<T>;
}
```

**Analog 2 (test seam typedef):** `mobile/lib/core/api/messages_stream.dart` lines 37-41:
```dart
typedef SseSubscribe = Stream<SSEModel> Function({
  required String url,
  required Map<String, String> headers,
});
```

> The same seam discipline applies: `AuthService` is an `abstract interface class`, two impls (real OAuth via google_sign_in/flutter_appauth; test seam reads `--dart-define SESSION_ID`). Riverpod overrides swap impls in tests.

**Analog 3 (real-impl HTTP call):** `mobile/lib/core/api/api_client.dart::authGoogleMobile` lines 271-285:
```dart
Future<Result<SessionUser>> authGoogleMobile({
  required String idToken,
  CancelToken? cancelToken,
}) async {
  try {
    final res = await _dio.post<Map<String, dynamic>>(
      ApiEndpoints.authGoogleMobile,
      data: {'id_token': idToken},
      cancelToken: cancelToken,
    );
    return Result.ok(SessionUser.fromJson(res.data!));
  } on DioException catch (e) {
    return Result.err(ApiError.fromDioException(e));
  }
}
```

**Analog 4 (test-seam env injection):** `mobile/integration_test/spike_api_roundtrip_test.dart` lines 42-67:
```dart
const _baseUrl = String.fromEnvironment('BASE_URL');
const _sessionId = String.fromEnvironment('SESSION_ID');
const _byokKey = String.fromEnvironment('OPENROUTER_KEY');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('...', (tester) async {
    expect(_baseUrl, isNotEmpty, reason: 'BASE_URL not set...');
    expect(_sessionId, isNotEmpty, reason: 'SESSION_ID not set...');
    // ...
  });
}
```

> **D-66 contract:** `AuthService` test impl reads `String.fromEnvironment('SESSION_ID')`, calls `secureStorage.writeSessionId(...)`, returns `Ok(SessionUser)` synthesized from the cookie — never touches the native sheet. Real impl uses `google_sign_in` / `flutter_appauth`, then calls `apiClient.authGoogleMobile(idToken: ...)`.

---

#### `mobile/lib/core/auth/providers.dart` (or fold into existing `core/api/providers.dart`)

**Analog:** `mobile/lib/core/api/providers.dart` lines 20-55:

**Riverpod provider shape (D-66, UI-SPEC §State Management):**
```dart
@Riverpod(keepAlive: true)
AppEnv appEnv(Ref ref) => AppEnv.fromEnvironment();

@Riverpod(keepAlive: true)
SecureStorage secureStorage(Ref ref) => SecureStorage();

@Riverpod(keepAlive: true)
AuthEventBus authEventBus(Ref ref) {
  final bus = AuthEventBus();
  ref.onDispose(bus.dispose);
  return bus;
}

@Riverpod(keepAlive: true)
ApiClient apiClient(Ref ref) => ApiClient(ref.watch(dioProvider));
```

**Phase 25 ADDs (UI-SPEC lines 668-675):**
```dart
@Riverpod(keepAlive: true)
AuthService authService(Ref ref) => AuthServiceReal(
      apiClient: ref.watch(apiClientProvider),
      storage: ref.watch(secureStorageProvider),
    );

@riverpod
class CurrentUser extends _$CurrentUser {
  @override
  Future<SessionUser?> build() async => /* GET /v1/users/me; null on 401 */;
}

@riverpod
Future<List<Recipe>> recipes(Ref ref) async => /* api.recipes() */;
```

> **Generator note (Phase 24 Plan 06 line 5-7 of `providers.dart`):** Phase 24 carry-forward — `riverpod_generator` IS allowed; only `build_runner` for JSON codegen is forbidden by D-34. Use `@riverpod` annotations + `riverpod_generator`; commit `*.g.dart` files.

---

#### `mobile/lib/features/login/login_screen.dart` (D-04..D-06)

**Analog:** `mobile/lib/features/_placeholder/healthz_screen.dart` (closest existing screen — same `ConsumerStatefulWidget` + `Result<T>` switch + `_loading` flag pattern)

**Stateful Riverpod consumer pattern** (`healthz_screen.dart` lines 14-82 — full file is the canonical screen shape):
```dart
class HealthzScreen extends ConsumerStatefulWidget {
  const HealthzScreen({super.key});

  @override
  ConsumerState<HealthzScreen> createState() => _HealthzScreenState();
}

class _HealthzScreenState extends ConsumerState<HealthzScreen> {
  Result<HealthOk>? _result;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  Future<void> _refresh() async {
    if (_loading) return;
    setState(() => _loading = true);
    final api = ref.read(apiClientProvider);
    final r = await api.healthz();
    if (!mounted) return;
    setState(() {
      _result = r;
      _loading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = _result;
    Widget body;
    if (_loading || state == null) {
      body = const CircularProgressIndicator();
    } else {
      body = switch (state) {
        Ok(:final value) => Text(value.ok ? 'OK' : 'NOT OK', /* ... */),
        Err(:final error) => Text('ERROR: ${error.code.name} — ${error.message}', /* ... */),
      };
    }
    return Scaffold(/* ... */);
  }
}
```

> **Login screen wiring (D-04..D-06):** mirror this exact shape; replace `apiClient.healthz()` with `authService.signInWithGoogle()` / `signInWithGithub()`. The pending state (D-05) replaces the button label with `CircularProgressIndicator(strokeWidth: 2)`. The error caption (D-06) renders an inline `Text` with `SolvrColors.destructive` foreground when `_result is Err`.

---

#### `mobile/lib/core/storage/secure_storage.dart` — EXTEND (D-33)

**Analog:** Itself (existing session_id methods). Phase 25 adds per-provider BYOK keys mirroring the same shape.

**Existing pattern** (`secure_storage.dart` lines 13-41):
```dart
class SecureStorage {
  SecureStorage([FlutterSecureStorage? backend])
      : _backend = backend ?? const FlutterSecureStorage();

  static const String _kSessionId = 'session_id';

  final FlutterSecureStorage _backend;
  String? _cached;
  bool _hydrated = false;

  Future<String?> readSessionId() async {
    if (_hydrated) return _cached;
    _cached = await _backend.read(key: _kSessionId);
    _hydrated = true;
    return _cached;
  }

  Future<void> writeSessionId(String id) async {
    await _backend.write(key: _kSessionId, value: id);
    _cached = id;
    _hydrated = true;
  }

  Future<void> clearSessionId() async {
    await _backend.delete(key: _kSessionId);
    _cached = null;
    _hydrated = true;
  }
}
```

**Phase 25 ADDs (D-33 — BYOK key methods, NOT cleared on logout per D-25 + D-33):**
```dart
// NEW — Phase 25 D-33 — per-provider BYOK keys (NOT cleared on logout).
static const String _kByokKeyPrefix = 'byok_key_'; // byok_key_openrouter, byok_key_anthropic

Future<String?> readByokKey(String provider) =>
    _backend.read(key: '$_kByokKeyPrefix$provider');

Future<void> writeByokKey(String provider, String key) =>
    _backend.write(key: '$_kByokKeyPrefix$provider', value: key);

Future<void> clearByokKey(String provider) =>
    _backend.delete(key: '$_kByokKeyPrefix$provider');
```

> **Cache discipline:** the existing `_cached`/`_hydrated` discipline applies ONLY to session_id (hot-path on every dio request). BYOK keys are read once per Wizard mount — the platform-channel cost is negligible; no cache needed.

---

#### `mobile/lib/main.dart` — EXTEND (D-01)

**Analog:** Itself (Phase 24 boot sequence lines 1-34).

**Phase 25 cold-start /users/me + initial-route resolution (D-01..D-03):** insert between line 22 (`AppEnv.fromEnvironment();`) and line 28 (`SystemChrome.setPreferredOrientations`):
```dart
// NEW — Phase 25 D-01: native splash holds; we resolve the session, then
// runApp routes to /dashboard or /login. On 5xx/timeout, route to a retry
// screen (D-02). Native splash hides on first frame after runApp().
final authResult = await _resolveCurrentUser();
final initialRoute = switch (authResult) {
  Ok() => '/dashboard',
  Err(:final error) when error.code == ErrorCode.unauthorized => '/login',
  Err() => '/retry-bootstrap',  // D-02
};
```

> The router itself reads `initialRoute` from a `ProviderScope.override` of an `initialLocationProvider` (planner's discretion).

---

#### `mobile/lib/core/router/app_router.dart` — EXTEND (D-21, D-26, D-60)

**Analog:** Itself (Phase 24 single-route skeleton).

**Existing skeleton** (`app_router.dart` lines 1-16):
```dart
import 'package:agent_playground/features/_placeholder/healthz_screen.dart';
import 'package:go_router/go_router.dart';

GoRouter buildRouter() => GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => const HealthzScreen(),
        ),
      ],
    );
```

**Phase 25 ADDs — per UI-SPEC §Routing Contract lines 649-657:**
```dart
GoRouter buildRouter({String initialLocation = '/'}) => GoRouter(
  initialLocation: initialLocation,
  routes: [
    GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
    GoRoute(path: '/dashboard', builder: (_, __) => const DashboardScreen()),
    GoRoute(path: '/new-agent/clone', builder: (_, __) => const CloneStep()),
    GoRoute(path: '/new-agent/model', builder: (_, __) => const ModelStep()),
    GoRoute(path: '/new-agent/model/picker', builder: (_, __) => const ModelPickerScreen()),
    GoRoute(path: '/new-agent/name-deploy', builder: (_, __) => const DeployStep()),
    GoRoute(
      path: '/chat/:agentInstanceId',
      builder: (_, state) =>
          ChatScreen(agentInstanceId: state.pathParameters['agentInstanceId']!),
    ),
  ],
);
```

> **D-60 navigation semantics:** wizard Deploy success uses `context.go('/chat/<id>')` (replace); Dashboard row tap uses `context.push('/chat/<id>')` (back returns to Dashboard). Wizard cancel-X (D-31) pops the entire `/new-agent/*` branch with `context.go('/dashboard')`.

---

#### `mobile/pubspec.yaml` — EXTEND (D-67, AMD-03, Wave-1 deps)

**Analog:** Itself.

**Existing dep block** (`pubspec.yaml` lines 4-32):
```yaml
version: 0.1.0+1
environment:
  sdk: ^3.9.0
  flutter: ">=3.41.0"
dependencies:
  dio: ^5.9.2
  flutter:
    sdk: flutter
  flutter_appauth: ^12.0.0
  flutter_client_sse: ^2.0.3
  flutter_riverpod: ^3.3.1
  flutter_secure_storage: ^10.0.0
  go_router: ^17.2.3
  google_fonts: ^8.1.0
  google_sign_in: ^7.2.0
  riverpod_annotation: ^4.0.2
  uuid: ^4.5.3
dev_dependencies:
  build_runner: ^2.4.0
  flutter_test:
    sdk: flutter
  http_mock_adapter: ^0.6.1
  integration_test:
    sdk: flutter
  riverpod_generator: ^4.0.3
  very_good_analysis: ^10.0.0
```

**Phase 25 ADDs (D-67 + AMD-03):**
```yaml
version: 0.2.0+2  # D-67 — was 0.1.0+1

dependencies:
  # ... existing ...
  flutter_markdown_plus: ^1.0.0   # AMD-03 (D-43; replaces discontinued flutter_markdown)
  url_launcher: ^6.3.0            # D-46 (markdown link tap)

dev_dependencies:
  # ... existing ...
  golden_toolkit: ^0.15.0         # D-62 (snapshot tests at textScaleFactor 1.0/1.5/2.0)
```

---

### Wave 2 — Dashboard

#### `mobile/lib/features/dashboard/dashboard_screen.dart` (D-08..D-20)

**Analog:** `mobile/lib/features/_placeholder/healthz_screen.dart`

**Same shape as Login screen (above)**: `ConsumerStatefulWidget` + `Result<List<AgentSummary>>?` state + `_loading` flag + `initState` post-frame `_refresh()` + `Result.switch` in `build()`.

**Refetch-on-resume pattern (D-12) — adds `WidgetsBindingObserver`:**
```dart
class _DashboardScreenState extends ConsumerState<DashboardScreen>
    with WidgetsBindingObserver {
  Result<List<AgentSummary>>? _result;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);  // D-12 foreground refetch
    WidgetsBinding.instance.addPostFrameCallback((_) => _refresh());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _refresh();  // D-12
  }
  // ...
}
```

**ApiClient call** — `agentsList()` (api_client.dart lines 184-201):
```dart
final r = await ref.read(apiClientProvider).agentsList();
```

**Pull-to-refresh wraps the ListView in a `RefreshIndicator` (D-12, default Material styling).**

**Skeleton row vocabulary (D-18):** show 3 `SkeletonRow()` widgets while `_result == null`.

**Empty-state vocabulary (D-17):** when `result.value.isEmpty`, render `EmptyStateScaffold(banner: AsciiAgentBanner(namesStream: ...), heading: 'No agents yet', primaryAction: (label: 'Deploy your first agent', onTap: () => context.push('/new-agent/clone')))`.

**Sort (D-13):** `result.value.sorted((a, b) => (b.lastActivity ?? '').compareTo(a.lastActivity ?? ''))`.

---

### Wave 3 — New Agent wizard + Telegram

#### `mobile/lib/features/new_agent/deploy_step.dart` (D-22, D-27..D-30, D-54..D-60) — **THE CRITICAL CROSS-PLATFORM MIRROR**

**Analog 1 (CANONICAL — deploy call sequence):** `frontend/components/playground-form.tsx` lines 316-360.

**The web playground's deploy sequence — Dart MUST mirror this verbatim:**
```typescript
// frontend/components/playground-form.tsx lines 318-372
try {
  // Step 1: always run the smoke first. (Phase 23 D-22)
  const smokeRes = await apiPost<RunResponse>(
    "/api/v1/runs",
    { recipe_name: recipe, model, agent_name: trimmedName, personality },
    { Authorization: `Bearer ${byok}` },
  );
  setVerdict(smokeRes);
  const agentId = smokeRes.agent_instance_id;

  if (deployMode === "persistent" && agentId) {
    if (smokeRes.verdict !== "PASS") {
      // D-30 — render inline error, do NOT proceed.
      setUiError({
        kind: "unknown",
        message: `Smoke ${reason} — channel start aborted. ...`,
      });
      return;
    }

    // Step 2: /start with the selected channel + channel_inputs.
    const startBody: AgentStartRequest = {
      channel: selectedChannel,
      channel_inputs: { ...channelInputs },
    };
    const startRes = await apiPost<AgentStartResponse>(
      `/api/v1/agents/${agentId}/start`,
      startBody,
      { Authorization: `Bearer ${byok}` },
    );
    // ...
    success = true;
  }
} catch (e) {
  setUiError(parseApiError(e));
}
```

**Phase 25 D-56 mobile mirror (sequential 1×/runs + 1..2×/start):**
```dart
// 1. POST /v1/runs (BYOK Bearer header).
final runRes = await api.runs(
  body: RunRequest(recipeName: recipe, model: model, agentName: trimmedName),
  byokOpenRouterKey: byok,
);
switch (runRes) {
  case Err(:final error):
    return _showSmokeFailInline(error);  // D-30
  case Ok(:final value):
    if (!value.smokeOk) return _showSmokeFailInline(/* verdict.detail */);  // D-30
    final agentId = value.agentInstanceId;

    // 2. POST /v1/agents/<id>/start with channel='inapp' (D-56 always).
    final inappRes = await api.start(
      agentId: agentId,
      body: const StartRequest(channel: 'inapp', channelInputs: {}),
      byokOpenRouterKey: byok,
    );
    if (inappRes is Err) return _showInappFailInline(inappRes.error);  // D-57

    // 3. If telegram toggled — POST /start AGAIN with channel='telegram'.
    if (telegramEnabled) {
      final tgRes = await api.start(
        agentId: agentId,
        body: StartRequest(channel: 'telegram', channelInputs: telegramInputs),
        byokOpenRouterKey: byok,
      );
      if (tgRes is Err) {
        // D-58: route to Chat anyway; failed-banner per D-50.
        context.go('/chat/$agentId', extra: TelegramFailedBanner(reason: tgRes.error.message));
        return;
      }
    }
    context.go('/chat/$agentId');  // D-60 — replace wizard route.
}
```

**Analog 2 (CANONICAL — name validation regex):** `api_server/src/api_server/models/runs.py` lines 77-82:
```python
agent_name: str | None = Field(
    None,
    min_length=1,
    max_length=64,
    pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _-]*$",
)
```

> **D-27 contract notes:** CONTEXT D-27 (line 181) says `^[a-z0-9][a-z0-9_-]*$` (lowercase only, no spaces). The actual backend regex (line 81 above) is `^[a-zA-Z0-9][a-zA-Z0-9 _-]*$` (case-insensitive + allows spaces). **Planner: pick the stricter D-27 regex** (lowercase only, no spaces) — backend will accept; client gives the cleaner UX. Mirror EXACTLY in Dart at file constant level:
```dart
// Mirror: D-27 contract (stricter than backend D-27 narrows the surface for
// "agent name" UX cleanliness). Backend accepts ^[a-zA-Z0-9][a-zA-Z0-9 _-]*$.
final RegExp kAgentNameRegex = RegExp(r'^[a-z0-9][a-z0-9_-]*$');
const int kAgentNameMaxLength = 64;
```

---

#### `mobile/lib/features/new_agent/channel_inputs.dart` (D-54) — dynamic-fields render loop

**Analog:** `frontend/components/playground-form.tsx` lines 638-689 — CANONICAL dynamic channel-inputs pattern.

**Web reference (lines 638-689):**
```tsx
{deployMode === "persistent" && allInputs.length > 0 && (
  <div className="mt-6 flex flex-col gap-5">
    {allInputs.map((input: ChannelUserInput) => {
      const isRequired = requiredInputs.some((e) => e.env === input.env);
      return (
        <div key={input.env} className="flex flex-col gap-2">
          <Label htmlFor={`ch-${input.env}`} className="...">
            <KeyRound className="size-5 text-foreground/70" />
            {input.env}
            {!isRequired && <span className="...">(optional)</span>}
          </Label>
          <Input
            id={`ch-${input.env}`}
            type={input.secret ? "password" : "text"}
            autoComplete={input.secret ? "new-password" : "off"}
            autoCorrect="off" autoCapitalize="off" spellCheck={false}
            placeholder={input.secret ? "••••••••" : "..."}
            required={isRequired}
            value={channelInputs[input.env] ?? ""}
            onChange={(e) => setChannelInputs(prev => ({ ...prev, [input.env]: e.target.value }))}
            className="h-14 max-w-2xl text-lg font-mono"
          />
          <p className="text-sm leading-relaxed text-foreground/70">
            {input.hint}
            {input.hint_url && (
              <> <a href={input.hint_url} target="_blank" rel="noopener noreferrer" className="underline ...">get one here</a></>
            )}
          </p>
        </div>
      );
    })}
  </div>
)}
```

**Dart mirror (D-54):**
```dart
// Inside DeployStep.build(), inside Wizard step 3, when telegramEnabled is true:
for (final input in recipeDetail.channels.telegram.allInputs) // required + optional
  Padding(
    padding: const EdgeInsets.only(top: 16),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Label = the `env` value verbatim — NEVER "Bot Token" / "User ID"
        // hardcoded (Golden Rule #2; UI-SPEC line 240).
        Text(input.env, style: SolvrTextStyles.mono(fontSize: 14, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        TextField(
          obscureText: input.secret,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(hintText: input.secret ? '••••••••' : '...'),
          onChanged: (v) => ref.read(wizardScopeProvider.notifier).setChannelInput(input.env, v),
        ),
        if (input.hint != null) Padding(
          padding: const EdgeInsets.only(top: 4),
          child: _HintCaption(hint: input.hint!, hintUrl: input.hintUrl),  // url_launcher (D-46)
        ),
      ],
    ),
  ),
```

**Recipe field source — `recipes/openclaw.yaml` `channels.telegram.required_user_input`:**
```yaml
channels:
  telegram:
    required_user_input:
      - env: TELEGRAM_BOT_TOKEN
        secret: true
        hint: Create via @BotFather /newbot.
      - env: TELEGRAM_ALLOWED_USER
        secret: false
        kind: telegram_numeric_id
        prefix_required: "tg:"          # runner auto-prefixes
        hint_url: https://t.me/userinfobot
        hint: Numeric Telegram user ID (no @). Runner auto-prefixes "tg:".
```

---

#### `mobile/lib/features/new_agent/model_step.dart` BYOK label-swap (D-32)

**Analog:** `frontend/components/playground-form.tsx` lines 627-635 — CANONICAL BYOK label-swap from `channel_provider_compat`:

```tsx
{deployMode === "persistent" && providerDeferredForChannel.length > 0 && (
  <Alert className="mt-4">
    <AlertTitle>Provider override required</AlertTitle>
    <AlertDescription>
      This recipe + channel combination defers {providerDeferredForChannel.join(", ")}.
      Use your {(selectedRecipe?.channel_provider_compat?.[selectedChannel]?.supported ?? ["direct"]).join(" / ")} API key instead.
    </AlertDescription>
  </Alert>
)}
```

**Dart mirror (D-32) — single field, label flipped from server metadata:**
```dart
// Default = "OpenRouter API Key". Flip to "Anthropic API Key" when the
// selected recipe+channel defers openrouter (e.g. hermes; openclaw +
// telegram). NEVER use a Dart-side `if recipe == 'hermes'` branch
// (Golden Rule #2: dumb client).
final defers = recipeDetail.channelProviderCompat[selectedChannel]?.deferred ?? [];
final useAnthropic = defers.contains('openrouter');
final label = useAnthropic ? 'Anthropic API Key' : 'OpenRouter API Key';
final storageProvider = useAnthropic ? 'anthropic' : 'openrouter';

// On change, persist via secureStorage.writeByokKey(storageProvider, value).
// Auto-fill from secureStorage.readByokKey(storageProvider) on mount.
```

---

#### `mobile/lib/core/api/dtos.dart` — EXTEND (RecipeDetail + ChannelUserInput)

**Analog:** Itself — existing `Recipe.fromJson` shape (`dtos.dart` lines 183-199):
```dart
class Recipe {
  const Recipe({required this.name, required this.channelsSupported});

  factory Recipe.fromJson(Map<String, dynamic> json) => Recipe(
        name: json['name'] as String,
        channelsSupported:
            ((json['channels_supported'] as List<dynamic>?) ?? <dynamic>[])
                .map((e) => e as String)
                .toList(growable: false),
      );

  final String name;
  final List<String> channelsSupported;
}
```

**Phase 25 ADDs** — three new classes following the same hand-written `fromJson` shape:
```dart
class ChannelUserInput {
  const ChannelUserInput({required this.env, required this.secret, this.hint, this.hintUrl, this.kind});

  factory ChannelUserInput.fromJson(Map<String, dynamic> json) => ChannelUserInput(
    env: json['env'] as String,
    secret: (json['secret'] as bool?) ?? false,
    hint: json['hint'] as String?,
    hintUrl: json['hint_url'] as String?,
    kind: json['kind'] as String?,
  );

  final String env;
  final bool secret;
  final String? hint;
  final String? hintUrl;
  final String? kind;
}

class RecipeChannelMeta {
  const RecipeChannelMeta({required this.requiredUserInput, required this.optionalUserInput});
  factory RecipeChannelMeta.fromJson(Map<String, dynamic> json) => RecipeChannelMeta(
    requiredUserInput: ((json['required_user_input'] as List<dynamic>?) ?? <dynamic>[])
        .cast<Map<String, dynamic>>().map(ChannelUserInput.fromJson).toList(growable: false),
    optionalUserInput: ((json['optional_user_input'] as List<dynamic>?) ?? <dynamic>[])
        .cast<Map<String, dynamic>>().map(ChannelUserInput.fromJson).toList(growable: false),
  );
  final List<ChannelUserInput> requiredUserInput;
  final List<ChannelUserInput> optionalUserInput;

  List<ChannelUserInput> get allInputs => [...requiredUserInput, ...optionalUserInput];
}

class RecipeDetail extends Recipe {
  const RecipeDetail({
    required super.name,
    required super.channelsSupported,
    required this.channels,
    required this.channelProviderCompat,
    this.description,
  });
  // ... fromJson reads `channels` map and channel_provider_compat ...
  final Map<String, RecipeChannelMeta> channels;
  final Map<String, ChannelProviderCompat> channelProviderCompat;
  final String? description;
}
```

---

#### `mobile/lib/core/api/api_client.dart` — EXTEND (`recipeDetail(name)`)

**Analog:** Itself (existing `recipes()` method at lines 206-220):
```dart
Future<Result<List<Recipe>>> recipes({CancelToken? cancelToken}) async {
  try {
    final res = await _dio.get<List<dynamic>>(
      ApiEndpoints.recipes,
      cancelToken: cancelToken,
    );
    final rows = (res.data ?? const <dynamic>[])
        .cast<Map<String, dynamic>>()
        .map(Recipe.fromJson)
        .toList(growable: false);
    return Result.ok(rows);
  } on DioException catch (e) {
    return Result.err(ApiError.fromDioException(e));
  }
}
```

**Phase 25 ADD** (mirror shape; single-row response):
```dart
Future<Result<RecipeDetail>> recipeDetail({
  required String name,
  CancelToken? cancelToken,
}) async {
  try {
    final res = await _dio.get<Map<String, dynamic>>(
      ApiEndpoints.recipeDetail(name),
      cancelToken: cancelToken,
    );
    return Result.ok(RecipeDetail.fromJson(res.data!));
  } on DioException catch (e) {
    return Result.err(ApiError.fromDioException(e));
  }
}
```

---

### Wave 4 — Chat

#### `mobile/lib/features/chat/chat_screen.dart` (D-35..D-53) — **MIRRORS THE SPIKE**

**Analog (CANONICAL):** `mobile/integration_test/spike_api_roundtrip_test.dart` lines 121-244 — the spike already exercises the exact load-bearing sequence Phase 25's Chat screen needs (parallel `GET /messages` + SSE connect + `POST /messages` + dedupe + `Last-Event-Id` resume).

**Spike pattern — connect SSE then post and listen** (`spike_api_roundtrip_test.dart` lines 124-167):
```dart
final stream = MessagesStream(
  baseUrl: Uri.parse(_baseUrl),
  agentId: agentId,
  cookieProvider: () async => _sessionId,
);
final received = <SseEvent>[];
final sseSub = stream.events.listen(
  received.add,
  onError: (Object e, _) => fail('SSE error in step 3+: $e'),
);
await stream.connect();
// Give SSE 2 seconds to settle the connection before posting.
await Future<void>.delayed(const Duration(seconds: 2));

final idemKey = const Uuid().v4();
final ackRes = await api.postMessage(
  agentId: agentId,
  content: 'spike roundtrip',
  idempotencyKey: idemKey,
);
final ack = expectOk(ackRes, step: 4);

// Step 5: SSE delivers an assistant reply.
final firstReply = await waitForOutbound(received);
final firstReplyText = extractAssistantContent(firstReply.data);
```

**Reconnect-on-foreground pattern (D-52)** — `spike_api_roundtrip_test.dart` lines 204-221:
```dart
// disconnect mid-stream + reconnect with Last-Event-Id
final lastSeenId = stream.lastEventId;
expect(lastSeenId, isNotNull);
final receivedCountBeforeResume = received.length;
await stream.disconnect();
// Cursor MUST survive disconnect.
expect(stream.lastEventId, lastSeenId);
await stream.connect();
await Future<void>.delayed(const Duration(seconds: 2));
```

**Phase 25 Chat-screen orchestration (D-36 + D-52):**
```dart
class _ChatScreenState extends ConsumerState<ChatScreen> with WidgetsBindingObserver {
  late final MessagesStream _stream;
  final Map<String, ChatMessage> _messagesById = {};  // D-36 dedupe
  StreamSubscription<SseEvent>? _sub;
  CancelToken? _historyToken;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _stream = MessagesStream(
      baseUrl: ref.read(appEnvProvider).baseUrl,
      agentId: widget.agentInstanceId,
      cookieProvider: () => ref.read(secureStorageProvider).readSessionId(),
    );
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    // D-36: parallel GET history + SSE connect.
    _historyToken = CancelToken();
    final historyFuture = ref.read(apiClientProvider).messagesHistory(
      agentId: widget.agentInstanceId,
      limit: 200,
      cancelToken: _historyToken,
    );
    _sub = _stream.events.listen(_onSse);
    await _stream.connect();
    final historyRes = await historyFuture;
    // D-36: dedupe — if id already in map, update status only.
    if (historyRes case Ok(:final value)) {
      for (final m in value.messages) {
        _messagesById.putIfAbsent(m.inappMessageId, () => m);
      }
    }
    setState(() {});
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // D-52: reconnect on foreground with Last-Event-Id.
    if (state == AppLifecycleState.resumed) {
      _stream.disconnect().then((_) => _stream.connect());
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _historyToken?.cancel();
    _sub?.cancel();
    _stream.dispose();
    super.dispose();
  }
  // ...
}
```

**Send pattern with `Idempotency-Key` (D-41 + D-45):**
```dart
Future<void> _send(String content) async {
  final idemKey = const Uuid().v4();  // D-45 — NEW key per Send press.
  setState(() {
    // D-41: optimistic user bubble + grey typing-dots assistant bubble.
    _messagesById['pending-$idemKey'] = ChatMessage(/* ... */);
  });
  final r = await ref.read(apiClientProvider).postMessage(
    agentId: widget.agentInstanceId,
    content: content,
    idempotencyKey: idemKey,
  );
  switch (r) {
    case Ok(): /* SSE will deliver assistant reply; replace pending placeholder */
    case Err(): _markFailed(idemKey, error);  // D-44 FailedBubble
  }
}
```

> **Send button states (D-51):** disabled when text empty/whitespace; spinner during inflight (`_inflight = true`); tap-spinner cancels via `dio.CancelToken.cancel()`. Failures render via FailedBubble path ONLY — no snackbar.

---

### Wave 5 — Tests + spike + artifact

#### `mobile/integration_test/screens_e2e_test.dart` (D-65)

**Analog:** `mobile/integration_test/spike_api_roundtrip_test.dart` (CANONICAL — same harness, env vars, binding init, timeout shape)

**Boot pattern** (`spike_api_roundtrip_test.dart` lines 42-93):
```dart
const _baseUrl = String.fromEnvironment('BASE_URL');
const _sessionId = String.fromEnvironment('SESSION_ID');
const _byokKey = String.fromEnvironment('OPENROUTER_KEY');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('9-step round-trip — D-46 (Phase 24 exit gate)', (tester) async {
    expect(_baseUrl, isNotEmpty, reason: 'BASE_URL not set...');
    expect(_sessionId, isNotEmpty, reason: 'SESSION_ID not set...');
    expect(_byokKey, isNotEmpty, reason: 'OPENROUTER_KEY not set...');

    final dio = Dio(BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
    ));
    dio.interceptors.addAll([
      InterceptorsWrapper(
        onRequest: (options, handler) {
          options.headers['Cookie'] = 'ap_session=$_sessionId';
          handler.next(options);
        },
      ),
      const RedactingLogInterceptor(),
    ]);
    final api = ApiClient(dio);
    // ... 9 steps ...
  }, timeout: const Timeout(Duration(minutes: 15)));
}
```

**Phase 25 D-65 mirror — extend with `WidgetTester.pumpWidget(SolvrLabsApp(...))` + driving the UI:**
```dart
testWidgets('Phase 25 screens e2e — D-65 exit gate', (tester) async {
  // SAME env-var preflight as spike.
  expect(_baseUrl, isNotEmpty);
  expect(_sessionId, isNotEmpty);
  expect(_byokKey, isNotEmpty);

  // AuthService test impl injected via Riverpod override (D-66).
  await tester.pumpWidget(ProviderScope(
    overrides: [
      authServiceProvider.overrideWithValue(AuthServiceTestSeam(sessionId: _sessionId)),
    ],
    child: const SolvrLabsApp(),
  ));
  await tester.pumpAndSettle();

  // 1. Login → AuthService → Dashboard appears.
  await tester.tap(find.text('Continue with Google'));
  await tester.pumpAndSettle();
  expect(find.text('No agents yet'), findsOneWidget);  // empty state OK on fresh user

  // 2. Tap FAB → wizard step 1.
  await tester.tap(find.byType(FloatingActionButton));
  await tester.pumpAndSettle();
  // ... pick recipe, model, type name, Telegram OFF, Deploy.
  // 3. Wait for /v1/runs + /v1/agents/<id>/start.
  // 4. Chat opens; type "hi"; assert assistant bubble appears.
  // 5. WidgetsBinding.instance.handleAppLifecycleStateChanged round-trip.
  // 6. Assert history visible after relaunch.
}, timeout: const Timeout(Duration(minutes: 15)));
```

---

#### `mobile/Makefile` — EXTEND (D-65 — `make screens-e2e`)

**Analog:** Itself (existing `make spike` target lines 23-31).

**Existing `make spike` target:**
```make
spike:  ## Phase 24 D-50 — 9-step roundtrip integration_test. Requires BASE_URL, SESSION_ID, OPENROUTER_KEY (D-49/D-51).
	@test -n "$$BASE_URL" || (echo "ERROR: BASE_URL not set..." && exit 1)
	@test -n "$$SESSION_ID" || (echo "ERROR: SESSION_ID not set..." && exit 1)
	@test -n "$$OPENROUTER_KEY" || (echo "ERROR: OPENROUTER_KEY not set..." && exit 1)
	@curl -fsS --max-time 5 "$$BASE_URL/healthz" >/dev/null || (echo "ERROR: api_server not healthy..." && exit 1)
	fvm flutter test integration_test/spike_api_roundtrip_test.dart \
	  --dart-define BASE_URL=$$BASE_URL \
	  --dart-define SESSION_ID=$$SESSION_ID \
	  --dart-define OPENROUTER_KEY=$$OPENROUTER_KEY
```

**Phase 25 ADD — sibling `screens-e2e` target (same env preflight, different test path):**
```make
screens-e2e:  ## Phase 25 D-65 — Login → Dashboard → Wizard → Chat round-trip.
	@test -n "$$BASE_URL" || (echo "ERROR: BASE_URL not set..." && exit 1)
	@test -n "$$SESSION_ID" || (echo "ERROR: SESSION_ID not set..." && exit 1)
	@test -n "$$OPENROUTER_KEY" || (echo "ERROR: OPENROUTER_KEY not set..." && exit 1)
	@curl -fsS --max-time 5 "$$BASE_URL/healthz" >/dev/null || (echo "ERROR: api_server not healthy..." && exit 1)
	fvm flutter test integration_test/screens_e2e_test.dart \
	  --dart-define BASE_URL=$$BASE_URL \
	  --dart-define SESSION_ID=$$SESSION_ID \
	  --dart-define OPENROUTER_KEY=$$OPENROUTER_KEY
```

> **And update `.PHONY`:** `.PHONY: doctor get test ios android spike screens-e2e clean`.

---

#### Golden tests + `mobile/test/flutter_test_config.dart` (D-62)

**Analog (testWidgets/pumpWidget shape):** `mobile/test/smoke_test.dart` lines 17-37:
```dart
void main() {
  testWidgets('SolvrLabsApp renders without throwing', (tester) async {
    final fakeDio = Dio(BaseOptions(baseUrl: 'http://test.invalid'))
      ..httpClientAdapter = _RejectingAdapter();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          dioProvider.overrideWith((ref) => fakeDio),
        ],
        child: const SolvrLabsApp(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(Scaffold), findsOneWidget);
    fakeDio.close(force: true);
  });
}
```

**`flutter_test_config.dart`** — required entrypoint for `golden_toolkit` boot (no in-repo precedent — this is the first such file):
```dart
// mobile/test/flutter_test_config.dart — D-62 golden_toolkit boot.
import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:golden_toolkit/golden_toolkit.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  return GoldenToolkit.runWithConfiguration(
    () async {
      await loadAppFonts();
      await testMain();
    },
    config: GoldenToolkitConfiguration(
      defaultDevices: const [Device.phone, Device.iphone11],
    ),
  );
}
```

> **Pinning:** the same `_RejectingAdapter` pattern from `smoke_test.dart` blocks dio in golden tests. Tests run at `textScaleFactor` 1.0 / 1.5 / 2.0 per UI-SPEC §Accessibility (lines 712-726).

---

#### `spikes/flutter-screens-roundtrip.md` (D-65 artifact)

**Analog:** `spikes/flutter-api-roundtrip.md` (Phase 24 sibling — same YAML frontmatter + step-narrative format per D-54).

> Format already canonized; planner copies the frontmatter shape (`date`, `git_sha`, `flutter_sdk_version`, `recipe`, `model`, `base_url`, `target`, `verdict: PASS`) and narrates the 6-step Phase 25 flow (Login → Dashboard → Wizard → /runs → /start × N → Chat → relaunch → history).

---

## Shared Patterns

### Auth (Cookie injection on every dio call)
**Source:** `mobile/lib/core/api/auth_interceptor.dart` lines 23-52 (already shipped).
**Apply to:** Every screen that calls `apiClient.<method>()` — the interceptor is mounted on the singleton dio (Phase 24 `core/api/providers.dart::dio` line 46) and runs implicitly. Phase 25 screens DO NOT need to think about session-cookie injection.

```dart
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._storage, this._authEvents);

  @override
  Future<void> onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final sessionId = await _storage.readSessionId();
    if (sessionId != null && sessionId.isNotEmpty) {
      options.headers['Cookie'] = 'ap_session=$sessionId';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode == 401) {
      await _storage.clearSessionId();  // D-03 + cleanup
      _authEvents.emit();                // → Phase 25 router listener
    }
    handler.next(err);
  }
}
```

> **D-03 wiring (NEW in Phase 25):** the router subscribes to `authEventBusProvider.events`; on `AuthRequired`, navigates to `/login` with the `Signed out · Sign in to continue` banner (UI-SPEC §Copy line 207).

---

### Error handling (Result switch)
**Source:** `mobile/lib/core/api/result.dart` lines 17-31 + every `apiClient` method (e.g. `dtos.dart::Recipe.fromJson` + `api_client.dart::recipes()` lines 206-220).
**Apply to:** Every screen/widget that calls an `apiClient` method — Phase 25 widgets MUST switch on `Result<T>` exhaustively (sealed-class compile-time check).

**Existing call-site (the only existing one — `healthz_screen.dart` lines 49-60):**
```dart
body = switch (state) {
  Ok(:final value) => Text(value.ok ? 'OK' : 'NOT OK', style: SolvrTextStyles.mono(fontSize: 24)),
  Err(:final error) => Text('ERROR: ${error.code.name} — ${error.message}', style: SolvrTextStyles.mono(fontSize: 16)),
};
```

> Every Phase 25 screen mirrors this exhaustive-switch shape. Loading state goes BEFORE the switch (`_loading || state == null` → `CircularProgressIndicator` / `SkeletonRow`).

---

### Idempotency-Key generation (Send press)
**Source:** `mobile/integration_test/spike_api_roundtrip_test.dart` line 141-145 + `mobile/pubspec.yaml::uuid: ^4.5.3`:
```dart
final idemKey = const Uuid().v4();
final ackRes = await api.postMessage(
  agentId: agentId,
  content: 'spike roundtrip',
  idempotencyKey: idemKey,
);
```
**Apply to:** Chat screen Send button (`chat_screen.dart`); D-45 retry generates a NEW `Uuid().v4()` (not replay).

---

### Dynamic-fields render loop (channel inputs)
**Source:** `frontend/components/playground-form.tsx` lines 638-689 (CANONICAL — see §Wave 3 above).
**Apply to:** `channel_inputs.dart` widget (D-54). NEVER hardcode "Bot Token" / "User ID" labels in Dart — labels come from `recipe.channels.<id>.required_user_input[i].env`.

---

### Deploy call sequence (1×/runs + N×/start)
**Source:** `frontend/components/playground-form.tsx` lines 316-360 (CANONICAL).
**Apply to:** `deploy_step.dart` (D-56). Same try/await sequence; mobile orchestrates 1 (inapp) or 2 (inapp+telegram) `/start` calls sequentially.

---

### Riverpod provider shape (DI)
**Source:** `mobile/lib/core/api/providers.dart` lines 20-55 (already shipped).
**Apply to:** Every NEW provider (`authServiceProvider`, `currentUserProvider`, `recipesProvider`, `modelsProvider`, `agentsListProvider`, `wizardScopeProvider`, `chatScopeProvider(agentId)` family). Use `@Riverpod(keepAlive: true)` for app-wide singletons; `@riverpod` (without keepAlive) for screen-scoped ones; `Family.autoDispose` for the wizard + chat scopes.

---

### Scaffold + theme consumption
**Source:** `mobile/lib/features/_placeholder/healthz_screen.dart` lines 62-80 + `mobile/lib/core/theme/solvr_theme.dart::solvrTheme()`.
**Apply to:** Every screen widget — wrap in `Scaffold(appBar: AppBar(...), body: ...)`; consume `Theme.of(context).textTheme.*` for typography (UI-SPEC §Typography lines 84-87) — do NOT inline `fontSize:` values.

---

### Integration-test harness (live api_server)
**Source:** `mobile/integration_test/spike_api_roundtrip_test.dart` lines 42-93 (boot) + `mobile/integration_test/spike_helpers.dart` lines 13-24 (`expectOk`).
**Apply to:** Wave 5 `screens_e2e_test.dart`. Same `String.fromEnvironment` triple, same `IntegrationTestWidgetsFlutterBinding`, same `Timeout(Duration(minutes: 15))`, same `expectOk` helper.

---

### Make-target preflight pattern
**Source:** `mobile/Makefile` lines 23-31 (`make spike`).
**Apply to:** New `make screens-e2e` target — copy preflight env var checks + `curl /healthz` + `--dart-define` triple verbatim.

---

### Hand-written DTO `fromJson` shape
**Source:** `mobile/lib/core/api/dtos.dart` (every class — e.g. `AgentSummary` lines 152-180).
**Apply to:** Every NEW DTO (`RecipeDetail`, `ChannelUserInput`, `RecipeChannelMeta`, optional `ChannelProviderCompat`). Plain Dart class, `const` ctor, named-param constructor, `factory fromJson(Map<String, dynamic>)`, defensive nullable handling, `final` fields.

---

## No Analog Found

Phase 24 shipped a complete substrate; **no Phase 25 file lacks a precedent in repo or cross-platform reference**. Three "first-of-kind" patterns DO emerge but each has a clear source-of-truth:

| File | Role | Data Flow | Reason | Source-of-truth substitute |
|------|------|-----------|--------|----------------------------|
| `mobile/lib/shared/typing_dots.dart` | First `AnimationController` | tick-driven | No animation precedent in repo | UI-SPEC §Component 6 lines 370-380 (full visual contract) |
| `mobile/lib/shared/confirm_dialog.dart` | First `AlertDialog` wrapper | future-returning | No `AlertDialog` precedent | UI-SPEC §Component 9 lines 432-450 (full signature contract) |
| `mobile/test/flutter_test_config.dart` | First golden-toolkit boot | test-config | No `flutter_test_config.dart` precedent | `golden_toolkit` README boilerplate (well-known shape) |

---

## Metadata

**Analog search scope:** `mobile/lib/`, `mobile/integration_test/`, `mobile/test/`, `mobile/Makefile`, `mobile/pubspec.yaml`, `frontend/components/playground-form.tsx`, `api_server/src/api_server/models/runs.py`, `api_server/src/api_server/routes/runs.py`, `recipes/openclaw.yaml`, `recipes/hermes.yaml`, `spikes/`.
**Files scanned:** 22 (Phase 24 substrate) + 1 (web reference) + 2 (api_server) + 2 (recipes) = 27.
**Pattern extraction date:** 2026-05-03.

---

## PATTERN MAPPING COMPLETE
