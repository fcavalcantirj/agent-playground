# Phase 24: Flutter Foundation — Pattern Map

**Mapped:** 2026-05-02
**Files analyzed:** 25 mobile files + 2 repo-root files
**Analogs found:** 18 cross-language analogs / 25 mobile files (7 are no-analog scaffold/template files)

## Cold-Start Disclaimer

`mobile/` does not exist in the repo. This is the **cold-start of the Flutter project** — there is no in-repo Dart/Flutter analog for any new file. Pattern mapping is **cross-language**:

- **Wire-shape analogs** in `api_server/src/api_server/` (Python/FastAPI) — what the Dart code must mirror byte-for-byte (cookie format, error envelope, idempotency-key shape, SSE id semantics).
- **HTTP-client structural analogs** in `frontend/lib/api.ts` + `frontend/components/playground-form.tsx` (TypeScript/Next.js) — the Dart `ApiClient` mirrors `apiGet`/`apiPost` + `Authorization: Bearer` BYOK pattern structurally.
- **Tooling analogs** in `api_server/Makefile` + `.github/workflows/test-recipes.yml` — target naming and CI shape.
- **Spike-harness analogs** in `api_server/tests/spikes/` + `api_server/tests/e2e/test_inapp_5x5_matrix.py` — markdown spike convention + e2e-report shape.
- **In-spec analogs** in `24-RESEARCH.md` Patterns 1-7 — fully-fleshed canonical Dart code for ApiClient, AuthInterceptor, sealed Result, ApiError, MessagesStream, Riverpod providers, spike harness skeleton.

**Structural divergence to respect:** The Dart code mirrors the **wire format** that backend code parses, NOT the backend code's internal language idioms. E.g., the Dart `AuthInterceptor` writes `Cookie: ap_session=<uuid>` because that is what `ApSessionMiddleware._extract_cookie` reads off the request — but the Dart code does NOT mirror Python middleware patterns (no scope/ASGI shape, no asyncpg).

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `mobile/lib/main.dart` | scaffold/entry | boot-time | `api_server/src/api_server/main.py` (lifespan factory) | role-match |
| `mobile/lib/app.dart` | scaffold/root-widget | request-response | RESEARCH §Pattern 1+6 | in-spec |
| `mobile/lib/core/env/app_env.dart` | config | boot-time validation | RESEARCH §Code Examples line 1183-1207 (`AppEnv.fromEnvironment`) | in-spec |
| `mobile/lib/core/theme/solvr_theme.dart` | theme/config | render-time | `/Users/fcavalcanti/dev/solvr/frontend/app/globals.css` (out-of-repo) + RESEARCH §Theme Skeleton line 1228-1290 | in-spec |
| `mobile/lib/core/router/app_router.dart` | router/config | request-response | RESEARCH §Architecture Patterns (go_router config; placeholder route only) | in-spec |
| `mobile/lib/core/api/result.dart` | model/utility | type-shape | `api_server/src/api_server/models/errors.py` `ErrorCode` + `ErrorEnvelope` | wire-mirror |
| `mobile/lib/core/api/api_client.dart` | service/HTTP-client | request-response | `frontend/lib/api.ts` `apiGet`/`apiPost` + RESEARCH §Pattern 1 | structural |
| `mobile/lib/core/api/auth_interceptor.dart` | middleware | request-response | `api_server/src/api_server/middleware/session.py` `SessionMiddleware` (wire shape) + RESEARCH §Pattern 2 | wire-mirror |
| `mobile/lib/core/api/messages_stream.dart` | service/SSE-client | streaming | `api_server/src/api_server/routes/agent_messages.py` SSE handler + RESEARCH §Pattern 5 | wire-mirror |
| `mobile/lib/core/api/api_endpoints.dart` | utility/constants | none | route paths in `api_server/src/api_server/routes/*.py` | wire-mirror |
| `mobile/lib/core/api/dtos.dart` | model | type-shape | Pydantic `BaseModel` types in `api_server/src/api_server/models/` | wire-mirror |
| `mobile/lib/core/api/providers.dart` | DI/factory | boot-time | RESEARCH §Pattern 6 (Riverpod codegen) | in-spec |
| `mobile/lib/core/api/log_interceptor.dart` | middleware | request-response | `api_server/src/api_server/middleware/log_redact.py` `AccessLogMiddleware` (redaction policy) | structural |
| `mobile/lib/core/storage/secure_storage.dart` | service/storage | persist-read | no in-repo analog (web uses HttpOnly cookie) | no-analog |
| `mobile/lib/core/auth/auth_event_bus.dart` | event-bus | pub-sub | no in-repo analog | no-analog |
| `mobile/lib/features/_placeholder/healthz_screen.dart` | screen | request-response | `frontend/components/playground-form.tsx` (Result-rendering shape) | structural |
| `mobile/integration_test/spike_api_roundtrip_test.dart` | test/spike | request-response + streaming | `api_server/tests/e2e/test_inapp_5x5_matrix.py` + `api_server/tests/spikes/test_respx_authlib.py` + RESEARCH §Pattern 7 | structural |
| `mobile/Makefile` | tooling | n/a | `api_server/Makefile` (target naming) | structural |
| `mobile/pubspec.yaml`, `mobile/pubspec.lock` | manifest | n/a | `api_server/pyproject.toml` + `api_server/uv.lock` (lockfile-commit discipline) | structural |
| `mobile/.fvmrc` | SDK pin | n/a | `api_server/uv.lock` (per CONTEXT D-05; no `.python-version` in repo) | structural |
| `mobile/.gitignore` | tooling | n/a | no analog; D-08 enumerates the standard Flutter set | no-analog |
| `mobile/.env.example` | tooling | n/a | no in-repo analog (D-44 documents BASE_URL/SESSION_ID/OPENROUTER_KEY) | no-analog |
| `mobile/analysis_options.yaml` | linter config | n/a | `api_server/pyproject.toml` `[tool.ruff]` (strict-from-day-1 discipline) | structural |
| `mobile/README.md` | docs | n/a | `api_server/README.md` (per-target docs convention) | structural |
| `mobile/ios/Runner/Info.plist` | native config | boot-time | RESEARCH §Code Examples line 1094-1180 | in-spec |
| `mobile/android/app/src/main/AndroidManifest.xml` | native config | boot-time | RESEARCH §Code Examples line 1144-1162 | in-spec |
| `mobile/android/app/src/debug/res/xml/network_security_config.xml` | native config | boot-time | RESEARCH §Code Examples line 1116-1142 | in-spec |
| `spikes/flutter-api-roundtrip.md` | spike artifact | n/a | RESEARCH spike artifact format (D-54) — mirrors existing `spikes/` convention; **note: `spikes/` directory does not yet exist at repo root** — Phase 24 creates it. | no-analog |
| `.github/workflows/mobile.yml` | CI | n/a | `.github/workflows/test-recipes.yml` (only existing workflow) | structural |

---

## Pattern Assignments

### Group 1 — Scaffold & Build (no in-repo analog beyond CONTEXT/RESEARCH)

#### `mobile/pubspec.yaml`, `mobile/pubspec.lock`, `mobile/.fvmrc`, `mobile/.gitignore`, `mobile/.env.example`, `mobile/analysis_options.yaml`, `mobile/README.md`

**Analog:** `api_server/pyproject.toml` + `api_server/uv.lock` (lockfile-commit + strict-lints discipline mirrored).

**Lockfile discipline analog (`api_server/uv.lock`):**
```
# api_server/uv.lock — committed to repo, locks transitive deps
# Mirrors CONTEXT D-08: commit pubspec.lock to match no-mocks/reproducibility ethos.
```
**Strict lints analog:** `api_server`'s strict `ruff` posture is mirrored by D-23 locking `very_good_analysis` (Phase 24's `flutter_lints` equivalent).
**SDK pin analog:** `api_server/uv.lock` ↔ `mobile/.fvmrc` (both pin the language SDK at project level). **Note:** there is NO `.python-version` file in `api_server/`; lockfile-driven pinning is the actual analog.
**Pubspec content:** RESEARCH §Standard Stack lines 165-191 lists the canonical pubspec dependencies; planner copies that list verbatim.

**`mobile/.env.example`** — D-44/D-49/D-51 enumerate the three vars: `BASE_URL`, `SESSION_ID`, `OPENROUTER_KEY`. No in-repo analog (the api_server has no `.env.example`).

**`mobile/.gitignore`** — no in-repo analog. CONTEXT D-08 lists the standard Flutter exclusions; planner uses `flutter create`'s default + appends `mobile/.fvm/flutter_sdk`.

**`mobile/README.md`** — analog: `api_server/README.md`. Per-target BASE_URL table (iOS Simulator localhost / Android Emulator 10.0.2.2 / device LAN IP / ngrok) per CONTEXT D-44 lines 97-102.

---

### Group 2 — Native Platform Config (specs in RESEARCH)

#### `mobile/ios/Runner/Info.plist`

**Analog:** RESEARCH §Code Examples lines 1094-1114 (NSAppTransportSecurity) + lines 1164-1180 (CFBundleURLTypes).

**ATS exemption (D-12) — copy from RESEARCH lines 1099-1113:**
```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsLocalNetworking</key>
    <true/>
    <key>NSExceptionDomains</key>
    <dict>
        <key>localhost</key>
        <dict>
            <key>NSIncludesSubdomains</key>
            <false/>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
        </dict>
    </dict>
</dict>
```

**URL scheme (D-04) — copy from RESEARCH lines 1169-1180:**
```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleTypeRole</key>
        <string>Editor</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>solvrlabs</string>
        </array>
    </dict>
</array>
```

**Orientation (D-14):** add `UISupportedInterfaceOrientations` = portrait-only.

#### `mobile/android/app/src/main/AndroidManifest.xml`

**Analog:** RESEARCH §Code Examples lines 1144-1162 (intent-filter for `solvrlabs://oauth/github`).

**Intent-filter (D-04) — copy from RESEARCH lines 1149-1161:**
```xml
<activity
    android:name="net.openid.appauth.RedirectUriReceiverActivity"
    android:theme="@style/Theme.AppCompat.Translucent.NoTitleBar"
    android:exported="true"
    tools:node="replace">
    <intent-filter>
        <action android:name="android.intent.action.VIEW"/>
        <category android:name="android.intent.category.DEFAULT"/>
        <category android:name="android.intent.category.BROWSABLE"/>
        <data android:scheme="solvrlabs"
              android:host="oauth/github"/>
    </intent-filter>
</activity>
```

**Orientation (D-14):** `android:screenOrientation="portrait"` on the main activity.

#### `mobile/android/app/src/debug/res/xml/network_security_config.xml`

**Analog:** RESEARCH §Code Examples lines 1116-1142 (debug-scoped cleartext config).

**Cleartext config (D-13) — copy from RESEARCH lines 1121-1135:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">localhost</domain>
        <domain includeSubdomains="false">127.0.0.1</domain>
        <domain includeSubdomains="false">10.0.2.2</domain>
        <domain includeSubdomains="false">10.0.3.2</domain>
    </domain-config>
</network-security-config>
```

**Reference from `mobile/android/app/src/debug/AndroidManifest.xml` (debug-only override):** RESEARCH lines 1138-1142.

**Structural divergence:** The release `AndroidManifest.xml` at `src/main/` MUST NOT reference this file — production retains `cleartextTrafficPermitted="false"` (default).

---

### Group 3 — Theme

#### `mobile/lib/core/theme/solvr_theme.dart`

**Analog (out-of-repo, authoritative):** `/Users/fcavalcanti/dev/solvr/frontend/app/globals.css` `:root` block lines 6-39 (per CONTEXT line 195 + D-22 carry-forward APP-02).

**In-spec analog:** RESEARCH §Theme Skeleton lines 1228-1290 + Token Conversion Table lines 1213-1225.

**Color tokens — copy from RESEARCH lines 1236-1243:**
```dart
class SolvrColors {
  static const background = Color(0xFFFAFAF7);
  static const foreground = Color(0xFF1F1F1F);
  static const muted = Color(0xFFEFEFEC);
  static const mutedForeground = Color(0xFF6B6B6B);
  static const border = Color(0xFFDEDEDA);
  static const destructive = Color(0xFFD9333A);
}
```

**ThemeData skeleton — copy from RESEARCH lines 1245-1290:**
```dart
ThemeData solvrTheme() {
  final base = ThemeData.light(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: SolvrColors.background,
    colorScheme: const ColorScheme.light(
      surface: SolvrColors.background,
      onSurface: SolvrColors.foreground,
      primary: SolvrColors.foreground,
      onPrimary: SolvrColors.background,
      // ...
    ),
    textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
      bodyColor: SolvrColors.foreground,
      displayColor: SolvrColors.foreground,
    ),
    cardTheme: const CardTheme(
      color: SolvrColors.background,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.zero),
    ),
    // ...
  );
}
```

**Structural divergence:** CONTEXT line 139 hard-codes `#1F1F1F` and `#FAFAF7` — those are AUTHORITATIVE. RESEARCH's other rows in the conversion table are best-effort OKLCH→sRGB conversions; planner cross-checks if a Solvr Labs token export becomes available.

**`BorderRadius.zero` everywhere** is non-negotiable (D-22 carry-forward APP-02; `--radius: 0rem` from globals.css).

---

### Group 4 — API Client (the load-bearing layer)

#### `mobile/lib/core/api/result.dart` (sealed `Result<T>` + `ApiError` + `ErrorCode`)

**Analog 1 — wire shape:** `api_server/src/api_server/models/errors.py` lines 31-58 (`ErrorCode` constants) + lines 87-97 (`ErrorBody` + `ErrorEnvelope`).

**Backend ErrorCode constants (mirror exactly in Dart enum) — `api_server/src/api_server/models/errors.py:39-58`:**
```python
class ErrorCode:
    INVALID_REQUEST = "INVALID_REQUEST"
    RECIPE_NOT_FOUND = "RECIPE_NOT_FOUND"
    SCHEMA_NOT_FOUND = "SCHEMA_NOT_FOUND"
    LINT_FAIL = "LINT_FAIL"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    RATE_LIMITED = "RATE_LIMITED"
    IDEMPOTENCY_BODY_MISMATCH = "IDEMPOTENCY_BODY_MISMATCH"
    UNAUTHORIZED = "UNAUTHORIZED"
    INTERNAL = "INTERNAL"
    RUNNER_TIMEOUT = "RUNNER_TIMEOUT"
    INFRA_UNAVAILABLE = "INFRA_UNAVAILABLE"
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_NOT_RUNNING = "AGENT_NOT_RUNNING"
    AGENT_ALREADY_RUNNING = "AGENT_ALREADY_RUNNING"
    CHANNEL_NOT_CONFIGURED = "CHANNEL_NOT_CONFIGURED"
    CHANNEL_INPUTS_INVALID = "CHANNEL_INPUTS_INVALID"
    CONCURRENT_POLL_LIMIT = "CONCURRENT_POLL_LIMIT"
    EVENT_STREAM_UNAVAILABLE = "EVENT_STREAM_UNAVAILABLE"
```

**Backend error envelope shape (Dart `ApiError.fromDioException` parses this) — `api_server/src/api_server/models/errors.py:87-147`:**
```python
class ErrorBody(BaseModel):
    type: str          # e.g. "not_found", "rate_limit_error"
    code: str          # e.g. "RECIPE_NOT_FOUND" — the ErrorCode constants
    category: str | None = None
    message: str
    param: str | None = None
    request_id: str    # pulled from asgi-correlation-id contextvar

class ErrorEnvelope(BaseModel):
    error: ErrorBody

# Wire JSON: {"error": {"type": "...", "code": "...", "message": "...",
#                       "param": "...", "request_id": "..."}}
```

**Analog 2 — in-spec Dart code:** RESEARCH §Pattern 3 lines 460-486 (sealed Result) + §Pattern 4 lines 488-595 (ApiError + ErrorCode enum + `_parseCode` switch + `fromDioException` factory).

**Sealed Result — copy from RESEARCH lines 464-478:**
```dart
sealed class Result<T> {
  const Result();
  const factory Result.ok(T value) = Ok<T>;
  const factory Result.err(ApiError error) = Err<T>;
}
final class Ok<T> extends Result<T> {
  const Ok(this.value);
  final T value;
}
final class Err<T> extends Result<T> {
  const Err(this.error);
  final ApiError error;
}
```

**`ApiError.fromDioException` — copy from RESEARCH lines 536-569:** The `body['error']` extraction reads exactly the shape `make_error_envelope` emits at `api_server/src/api_server/models/errors.py:124-147`.

**Structural divergence:** Dart enum names are camelCase (`invalidRequest`); backend constants are SCREAMING_SNAKE (`INVALID_REQUEST`). The `_parseCode` switch (RESEARCH lines 574-594) translates wire→enum.

**Extra Dart-only enum values** (no backend equivalent — RESEARCH lines 517-520):
```dart
network,        // dio threw before getting a response
timeout,        // dio sendTimeout / receiveTimeout / connectionTimeout
unknownServer,  // 5xx with no parseable envelope
```

#### `mobile/lib/core/api/api_endpoints.dart`

**Analog:** Route paths declared in `api_server/src/api_server/routes/*.py`.

| Mobile constant | Backend route file | Path |
|-----------------|---------------------|------|
| `healthz` | `routes/health.py:78` | `GET /healthz` |
| `runs` | `routes/runs.py` | `POST /v1/runs` |
| `agentStart` | `routes/agent_lifecycle.py` | `POST /v1/agents/{id}/start` |
| `agentStop` | `routes/agent_lifecycle.py` | `POST /v1/agents/{id}/stop` |
| `agentMessages` | `routes/agent_messages.py:45+` | `POST /v1/agents/{id}/messages` |
| `agentMessagesHistory` | `routes/agent_messages.py` | `GET /v1/agents/{id}/messages?limit=N` |
| `agentMessagesStream` | `routes/agent_messages.py` | `GET /v1/agents/{id}/messages/stream` |
| `agentsList` | `routes/agents.py` | `GET /v1/agents` |
| `recipes` | `routes/recipes.py` | `GET /v1/recipes` |
| `models` | `routes/models.py` | `GET /v1/models` |
| `usersMe` | `routes/users.py` | `GET /v1/users/me` |
| `authGoogleMobile` | `routes/auth.py` | `POST /v1/auth/google/mobile` |
| `authGithubMobile` | `routes/auth.py` | `POST /v1/auth/github/mobile` |

**Structural divergence:** Endpoint constants are bare paths (no scheme/host); the dio `BaseOptions(baseUrl: ...)` from `app_env.dart` does the prepending.

#### `mobile/lib/core/api/dtos.dart`

**Analog:** Pydantic models in `api_server/src/api_server/models/`. Each Dart DTO mirrors one backend Pydantic class with a `fromJson` / `toJson` per D-34 (no codegen).

DTOs the spike + placeholder need:
- `HealthOk` — mirrors `routes/health.py:79` `{"ok": true}` return shape.
- `RunRequest` / `RunResponse` — mirror `models/runs.py`.
- `MessagePostAck` (`{message_id}`) — mirrors the 202 body from `routes/agent_messages.py`.
- `MessagesPage` — mirrors history GET response.
- `AgentInstance`, `Recipe`, `OpenRouterModel`, `User` — for `/v1/agents`, `/v1/recipes`, `/v1/models`, `/v1/users/me`.

**Structural divergence:** Backend uses `snake_case` JSON keys; Dart classes expose `camelCase` fields with the JSON name passed through `fromJson`/`toJson` explicitly. **No `freezed`, no `build_runner`** (D-34 LOCKED).

#### `mobile/lib/core/api/api_client.dart`

**Analog 1 — structural shape:** `frontend/lib/api.ts` lines 28-77 (`apiGet`/`apiPost`/`apiDelete` wrapper).

**`apiPost` shape (mirror in Dart `ApiClient` methods) — `frontend/lib/api.ts:61-73`:**
```typescript
export function apiPost<T = unknown>(
  path: string,
  body?: unknown,
  headers?: HeadersInit,    // BYOK header carried in
  opts?: ApiCallOptions,    // AbortSignal
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
    headers,
    signal: opts?.signal,
  });
}
```

**BYOK header injection pattern (carry to Dart `runs(...)` and `start(...)` per D-40) — `frontend/components/playground-form.tsx:324-359`:**
```typescript
const smokeRes = await apiPost<RunResponse>(
  "/api/v1/runs",
  { recipe_name: recipe, model, agent_name: trimmedName, personality },
  { Authorization: `Bearer ${byok}` },     // ← BYOK header on /runs only
);
// ...
const startRes = await apiPost<AgentStartResponse>(
  `/api/v1/agents/${agentId}/start`,
  startBody,
  { Authorization: `Bearer ${byok}` },     // ← AND on /start
);
```

**Analog 2 — in-spec Dart code:** RESEARCH §Pattern 1 lines 318-407 (`ApiClient` class with typed methods returning `Future<Result<T>>`).

**Per-method skeleton — copy from RESEARCH lines 333-365 (covers healthz + runs):**
```dart
class ApiClient {
  ApiClient(this._dio);
  final Dio _dio;

  Future<Result<HealthOk>> healthz({CancelToken? cancelToken}) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '/healthz',
        cancelToken: cancelToken,
      );
      return Result.ok(HealthOk.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<RunResponse>> runs({
    required RunRequest body,
    String? byokOpenRouterKey,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '/v1/runs',
        data: body.toJson(),
        cancelToken: cancelToken,
        options: Options(
          headers: byokOpenRouterKey == null
              ? null
              : {'Authorization': 'Bearer $byokOpenRouterKey'},
        ),
      );
      return Result.ok(RunResponse.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }
  // ...postMessage (with Idempotency-Key header), messagesHistory, etc.
}
```

**`postMessage` with Idempotency-Key — copy from RESEARCH lines 367-384.** The `Idempotency-Key` header is REQUIRED on `POST /v1/agents/:id/messages` per Phase 23 D-09; backend enforces via `api_server/src/api_server/middleware/idempotency.py:58-73` (`_AGENT_MESSAGES_PATTERN`).

**Structural divergence from frontend/lib/api.ts:**
- TypeScript throws `ApiError`; Dart returns `Result.err(ApiError)` (D-32 — sealed Result, never throws).
- TypeScript uses `credentials: "include"` to ride the browser cookie jar; Dart manually injects `Cookie:` via `AuthInterceptor` (D-35).
- TypeScript `apiGet` is generic; Dart has one method per endpoint (typed return) — D-31.

#### `mobile/lib/core/api/auth_interceptor.dart`

**Analog 1 — wire shape:** `api_server/src/api_server/middleware/session.py:37-98`. The Dart interceptor writes the EXACT cookie format `_extract_cookie` reads.

**Backend cookie parser (Dart writes what this reads) — `api_server/src/api_server/middleware/session.py:90-98`:**
```python
def _extract_cookie(scope: Scope, name: str) -> str | None:
    """Minimal Cookie header parser — returns the first value matching ``name`` or None."""
    for h_name, h_val in scope.get("headers", []):
        if h_name == b"cookie":
            for piece in h_val.decode("latin-1", errors="ignore").split(";"):
                k, _, v = piece.strip().partition("=")
                if k == name and v:
                    return v
    return None
```

**Backend cookie name constant (must match exactly) — `api_server/src/api_server/middleware/session.py:37`:**
```python
SESSION_COOKIE_NAME = "ap_session"
```

**Backend 401 trigger (Dart 401 handler clears + emits in response) — `api_server/src/api_server/auth/deps.py:49-58`:**
```python
def require_user(request: Request) -> JSONResponse | UUID:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return JSONResponse(
            status_code=401,
            content=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "Authentication required",
                param="ap_session",
            ),
        )
    # ...
```

**Analog 2 — in-spec Dart code:** RESEARCH §Pattern 2 lines 422-451 + §Code Examples lines 1027-1048.

**Interceptor skeleton — copy from RESEARCH lines 422-451:**
```dart
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._storage, this._authEvents);
  final SecureStorage _storage;
  final StreamController<AuthRequired> _authEvents;

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final sessionId = await _storage.readSessionId();
    if (sessionId != null) {
      options.headers['Cookie'] = 'ap_session=$sessionId';   // ← exact wire format
    }
    handler.next(options);
  }

  @override
  void onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode == 401) {
      await _storage.clearSessionId();
      _authEvents.add(const AuthRequired());
    }
    handler.next(err);
  }
}
```

**Structural divergence:**
- Backend middleware reads `Cookie: ap_session=<uuid>` from the request scope; Dart interceptor WRITES that exact string. Cookie parsing is single-use (one cookie name) — no need for `cookie_jar`.
- Backend uses `latin-1` decoding for the Cookie header; Dart uses UTF-8 by default. UUIDs are ASCII, so this is safe — but planner must ensure no non-ASCII session_ids are ever stored.
- Backend's `require_user` returns 401 with envelope `{"error": {"code": "UNAUTHORIZED", "param": "ap_session", ...}}`; the Dart interceptor's 401 handler triggers BEFORE `ApiError.fromDioException` parses the envelope — both fire (one clears storage + emits event, the other surfaces the typed error to the caller).

#### `mobile/lib/core/api/messages_stream.dart`

**Analog 1 — wire shape:** `api_server/src/api_server/routes/agent_messages.py` SSE handler emits `id:<seq>` on every event (per Phase 22c.3 D-09/D-34). The Dart wrapper tracks `_lastEventId` from the `id:` field on each event.

**Backend SSE event shape (whitelisted kinds) — `api_server/src/api_server/routes/agent_messages.py:52-56`:**
```python
INAPP_KINDS: tuple[str, ...] = (
    "inapp_inbound",
    "inapp_outbound",
    "inapp_outbound_failed",
)
```

**Analog 2 — in-spec Dart code:** RESEARCH §Pattern 5 lines 598-676.

**MessagesStream skeleton — copy from RESEARCH lines 609-676** (full class with `connect()`, `disconnect()` preserving cursor, `resetCursor()`, `dispose()`):
```dart
class MessagesStream {
  // ...
  Future<void> connect() async {
    final cookie = await cookieProvider();
    final headers = <String, String>{
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
      if (cookie != null) 'Cookie': 'ap_session=$cookie',
      if (_lastEventId != null) 'Last-Event-Id': _lastEventId!,
    };
    final stream = SSEClient.subscribeToSSE(
      method: SSERequestType.GET,
      url: _baseUrl.resolve('/v1/agents/$agentId/messages/stream').toString(),
      header: headers,
    );
    _sub = stream.listen((SSEModel m) {
      if (m.id != null && m.id!.isNotEmpty) {
        _lastEventId = m.id;
      }
      _events.add(SseEvent(id: m.id, kind: m.event ?? 'unknown', data: m.data ?? ''));
    }, onError: (Object e, StackTrace s) => _events.addError(e, s));
  }
  // ...
}
```

**Structural divergence:** `flutter_client_sse` does NOT auto-track or auto-resume (RESEARCH §Anti-Patterns line 837). The wrapper IS the workaround. Caller is responsible for re-passing `Last-Event-Id` on every reconnect — `disconnect()` deliberately preserves the cursor.

#### `mobile/lib/core/api/log_interceptor.dart`

**Analog (structural):** `api_server/src/api_server/middleware/log_redact.py` (`AccessLogMiddleware`).

**Redaction policy:** the Dart log interceptor MUST redact `Cookie:` and `Authorization:` headers in dev-mode logs (truncate to last 8 chars). Mirrors `api_server`'s log-redaction posture (CONTEXT line 122 / D-52). Planner reads the existing `middleware/log_redact.py` for the exact redaction patterns to mirror.

**Structural divergence:** Backend redaction runs ASGI-level; Dart redaction runs at dio-interceptor level. Same redacted output shape, different source pipeline.

#### `mobile/lib/core/api/providers.dart`

**Analog:** RESEARCH §Pattern 6 lines 685-712 (Riverpod codegen) + §Code Examples lines 1066-1077.

**`@Riverpod(keepAlive: true) Dio dio(Ref ref)` — copy from RESEARCH lines 692-709:**
```dart
@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final baseUrl = ref.watch(appEnvProvider).baseUrl;
  final storage = ref.watch(secureStorageProvider);
  final authEvents = ref.watch(authEventBusProvider);

  final dio = Dio(BaseOptions(
    baseUrl: baseUrl.toString(),
    connectTimeout: const Duration(seconds: 10),  // D-37
    receiveTimeout: const Duration(seconds: 30),  // D-37
  ));
  dio.interceptors.addAll([
    AuthInterceptor(storage, authEvents),
    if (kDebugMode) RedactingLogInterceptor(),
  ]);
  ref.onDispose(dio.close);
  return dio;
}

@riverpod
ApiClient apiClient(Ref ref) => ApiClient(ref.watch(dioProvider));
```

**Note:** `riverpod_annotation` + `riverpod_generator` codegen via `build_runner` — under "Claude's Discretion" per CONTEXT line 145. Hand-written Riverpod 3 providers also valid. Planner picks; codegen is community standard.

---

### Group 5 — Env Config

#### `mobile/lib/core/env/app_env.dart`

**Analog:** RESEARCH §Code Examples lines 1183-1207 (`AppEnv.fromEnvironment` with boot validation).

**Skeleton — copy from RESEARCH lines 1187-1206:**
```dart
class AppEnv {
  AppEnv({required this.baseUrl});
  final Uri baseUrl;

  static AppEnv fromEnvironment() {
    const raw = String.fromEnvironment('BASE_URL', defaultValue: 'http://localhost:8000');
    if (raw.isEmpty) {
      throw StateError(
        'BASE_URL is empty. Pass --dart-define=BASE_URL=http://... at flutter run.'
      );
    }
    final uri = Uri.tryParse(raw);
    if (uri == null || !uri.hasScheme || (!uri.isScheme('http') && !uri.isScheme('https'))) {
      throw StateError(
        'BASE_URL is malformed: "$raw". Must be http(s)://host[:port].'
      );
    }
    return AppEnv(baseUrl: uri);
  }
}
```

**No in-repo analog.** This is greenfield. The `String.fromEnvironment` pattern is Dart stdlib; the StateError fail-loud discipline mirrors CONTEXT's "no silent fallback" ethos (D-43).

**Structural divergence:** `--dart-define BASE_URL=...` is BAKED at compile time, NOT read at runtime. Per-target switching happens at `flutter run` invocation, not at runtime. CONTEXT D-44 enumerates per-target values.

---

### Group 6 — Router

#### `mobile/lib/core/router/app_router.dart`

**Analog:** RESEARCH §Architecture Patterns lines 213-217 (router config diagram) + Project Structure lines 283-284 ("placeholder route only in P24").

**No code excerpt** in RESEARCH for this file specifically — go_router config is Claude's Discretion (CONTEXT line 144). Planner writes a minimal config with one route → `HealthzScreen`. Phase 25 fills in `/dashboard`, `/new-agent`, `/chat/:id`.

**Structural divergence:** `go_router` mandated by APP-01 carry-forward; no `Navigator 1.0`, no `auto_route` (RESEARCH §Anti-Patterns line 839).

---

### Group 7 — Placeholder Screen

#### `mobile/lib/features/_placeholder/healthz_screen.dart`

**Analog 1 — Result-rendering shape:** `frontend/components/playground-form.tsx:300-397` (`onDeploy` async handler with try/catch error → typed error state → render branches).

**Analog 2 — exhaustive switch on `Result<T>`:** RESEARCH §Pattern 3 lines 481-486.

**Switch pattern — copy from RESEARCH lines 481-486:**
```dart
final r = await api.healthz();
final widget = switch (r) {
  Ok(:final value) => Text('ok: ${value.ok}'),
  Err(:final error) => Text('error: ${error.message}'),
};
```

**Structural divergence (CRITICAL — D-44 / CONTEXT line 19-22):**
- **NO debug menu.** No env banner. No URL switcher. No developer chrome of any kind.
- The screen is a single `Scaffold` calling `/healthz` through the real interceptor chain + real theme + real router.
- `dart:developer log()` is the only logging facility (D-25); `print()` is linter-flagged.
- Renders "OK" via the real `ThemeData` — NOT a stub `Container(color: Colors.red)`.

This is the production-shape foundation; Phase 25 just adds more screens to it.

---

### Group 8 — Storage / Auth Event Bus (no in-repo analog)

#### `mobile/lib/core/storage/secure_storage.dart`

**No in-repo analog.** Web frontend uses HttpOnly cookies (`frontend/lib/api.ts:34` `credentials: "include"`); the browser owns storage. Mobile MUST own it explicitly.

**Spec:** thin wrapper around `flutter_secure_storage` 10.0 (per RESEARCH §Don't Hand-Roll line 854). Three methods:
- `Future<String?> readSessionId()` — with in-memory cache (RESEARCH §Anti-Patterns line 843: "cache the value in memory and only re-read on logout/login").
- `Future<void> writeSessionId(String id)`.
- `Future<void> clearSessionId()`.

**Cookie name matches:** the value is the UUID portion only (no `ap_session=` prefix); the interceptor adds the prefix when injecting.

#### `mobile/lib/core/auth/auth_event_bus.dart`

**No in-repo analog.** Spec: `Stream<AuthRequired>` emitted on 401. Phase 25 listens (router redirects to OAuth screen); Phase 24 only wires the stream + verifies it doesn't crash (CONTEXT D-35: "Phase 25 wires the OAuth route per Phase 23 D-26").

**Skeleton:**
```dart
class AuthRequired { const AuthRequired(); }
// Riverpod-managed StreamController<AuthRequired> exposed via authEventBusProvider.
```

---

### Group 9 — Integration Spike

#### `mobile/integration_test/spike_api_roundtrip_test.dart`

**Analog 1 — e2e gate shape:** `api_server/tests/e2e/test_inapp_5x5_matrix.py:1-80` (real-infra e2e gate emitting JSON report).

**Real-infra discipline (mirror exactly) — `api_server/tests/e2e/test_inapp_5x5_matrix.py:13-20`:**
```python
# The dispatcher is invoked via the production ``_handle_row`` directly —
# NO respx, NO mocks. The bot HTTP client is a real ``httpx.AsyncClient``
# which posts to the recipe container's port over the test docker bridge
# network; the recipe container makes real OpenRouter calls upstream.
```

This is the SAME no-mocks discipline the Phase 24 spike must honor. The Dart spike runs against a REAL local `api_server` + REAL Docker + REAL OpenRouter. CONTEXT D-46/D-49 lock this.

**Report-emission pattern (Dart spike emits markdown not JSON, but same idea) — `api_server/tests/e2e/test_inapp_5x5_matrix.py:69-80`:**
```python
REPORT_PATH = pathlib.Path(__file__).parent / "e2e-report.json"

@pytest.fixture(scope="session")
def report_accumulator() -> dict:
    return {"passed": True, "recipes": [], "failures": []}
```

**Analog 2 — spike convention:** `api_server/tests/spikes/test_respx_authlib.py:1-14` (markdown-style docstring + PASS/FAIL criterion + "FAIL → phase goes back" framing).

**Spike header convention — `api_server/tests/spikes/test_respx_authlib.py:1-14`:**
```python
"""SPIKE A (Wave 0 gate) — respx x authlib 1.6.11 interop.

Proves that ``respx`` correctly intercepts authlib's outbound httpx calls to
Google's OAuth endpoints BEFORE any downstream test authors a real OAuth
integration test against respx stubs. Per D-22c-TEST-03 + AMD-05 + RESEARCH
Open Question 5.

PASS criterion: the stubbed Google /token endpoint fires exactly once and
authlib parses the canned payload without a network call escaping.

FAIL -> phase goes back to discuss-phase; respx + authlib combination is
not compatible and the test strategy must be revisited (pytest-httpx
fallback per RESEARCH Alternatives Considered).
"""
```

The Dart spike's docstring should follow the same pattern: state PASS criterion + FAIL consequence + reference to D-46 + D-53 (the gate).

**Analog 3 — in-spec spike skeleton:** RESEARCH §Pattern 7 lines 720-826 (full 9-step harness with `IntegrationTestWidgetsFlutterBinding`, `--dart-define` env reads, `_expectOk`/`_waitForOutbound` helpers).

**Spike skeleton — copy 9-step structure from RESEARCH lines 736-826.** Key invariants:
- `IntegrationTestWidgetsFlutterBinding.ensureInitialized()` (line 736) — required for `flutter test integration_test/`.
- All three `--dart-define` vars REQUIRED (lines 739-741) — fail loud if any missing.
- Build dio with cookie pre-injected via `InterceptorsWrapper.onRequest` (lines 748-753) — no secure_storage path during spike (D-49).
- 9 sequential steps mirroring D-46 lines 108-116.

**Structural divergence:**
- Dart spike emits a markdown artifact at `spikes/flutter-api-roundtrip.md` (D-54), NOT a JSON file at the test's sibling path. The markdown is hand-written after a green run with the YAML frontmatter (`date`, `git_sha`, `flutter_sdk_version`, `recipe`, `model`, `base_url`, `target`, `verdict: PASS`).
- The Dart spike runs locally only — NOT in CI (D-53). The Python e2e matrix runs in CI (`make e2e-inapp`); the Flutter spike does not (`make spike` — local invocation only, D-50).
- The Dart spike does NOT use `respx` or any HTTP-mocking lib — it goes straight against the live api_server (D-46 step 1-9 are all real-network).

#### `spikes/flutter-api-roundtrip.md`

**No in-repo analog at `spikes/`.** Repo root has no existing `spikes/` directory (verified: `ls /Users/fcavalcanti/dev/agent-playground/spikes/` returns no such path). CONTEXT line 229 references `tests/spikes/` (the api_server's, not the repo root's).

**Spec — RESEARCH D-54 / CONTEXT lines 122-126:** YAML frontmatter + 9-step narrative + reproducibility metadata. Hand-written after a green `make spike` run.

**Frontmatter shape (RESEARCH-locked):**
```yaml
---
date: 2026-05-XX
git_sha: <commit at run time>
flutter_sdk_version: 3.x.x
recipe: nullclaw
model: anthropic/claude-haiku-4-5
base_url: http://localhost:8000
target: ios-simulator | android-emulator | physical-device
verdict: PASS
---
```

---

### Group 10 — Tooling

#### `mobile/Makefile`

**Analog:** `api_server/Makefile` (target naming convention per CONTEXT D-22).

**Target naming pattern (mirror exactly) — `api_server/Makefile:1-12, 45`:**
```makefile
.PHONY: e2e-inapp e2e-inapp-docker

e2e-inapp:  ## Phase 22c.3 SC-03 5-recipe end-to-end inapp gate; requires OPENROUTER_API_KEY.
	@test -n "$$OPENROUTER_API_KEY" || (echo "ERROR: OPENROUTER_API_KEY not set in env" && exit 1)
	# ...

e2e-inapp-docker:  ## Phase 22c.3.1-01-AC01: dockerized 5-cell route gate (macOS parity path).
	@test -n "$$OPENROUTER_API_KEY" || (echo "ERROR: OPENROUTER_API_KEY not set in env" && exit 1)
	# ...
```

**Mobile target list per CONTEXT D-22 + D-50:**
- `make doctor` → `fvm flutter doctor`
- `make get` → `fvm flutter pub get`
- `make ios` → `fvm flutter run -d <ios-device>`
- `make android` → `fvm flutter run -d <android-device>`
- `make test` → `fvm flutter test`
- `make spike` → `fvm flutter test integration_test/spike_api_roundtrip_test.dart --dart-define BASE_URL=$BASE_URL --dart-define SESSION_ID=$SESSION_ID --dart-define OPENROUTER_KEY=$OPENROUTER_KEY` (D-50; fails loud with usage banner if any env var missing — copy `@test -n "$$VAR"` pattern from `api_server/Makefile:4`).

**`make spike` env-guard — copy api_server pattern at `api_server/Makefile:4`:**
```makefile
spike:  ## Phase 24 D-50 9-step roundtrip; requires BASE_URL, SESSION_ID, OPENROUTER_KEY.
	@test -n "$$BASE_URL" || (echo "ERROR: BASE_URL not set" && exit 1)
	@test -n "$$SESSION_ID" || (echo "ERROR: SESSION_ID not set" && exit 1)
	@test -n "$$OPENROUTER_KEY" || (echo "ERROR: OPENROUTER_KEY not set" && exit 1)
	fvm flutter test integration_test/spike_api_roundtrip_test.dart \
	  --dart-define BASE_URL=$$BASE_URL \
	  --dart-define SESSION_ID=$$SESSION_ID \
	  --dart-define OPENROUTER_KEY=$$OPENROUTER_KEY
```

---

### Group 11 — CI

#### `.github/workflows/mobile.yml`

**Analog:** `.github/workflows/test-recipes.yml` (the only existing workflow).

**Existing workflow shape (mirror structure):**
```yaml
name: Recipe lint + tests

on:
  push:
    branches: [main]
    paths:
      - 'tools/**'
      - 'recipes/**'
      - 'docs/RECIPE-SCHEMA.md'
  pull_request:
    branches: [main]
    paths:
      - 'tools/**'
      - 'recipes/**'
      - 'docs/RECIPE-SCHEMA.md'

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: make install-tools
      - name: Run lint + tests
        run: make check
```

**Mobile CI spec per CONTEXT D-27:** `fvm flutter analyze && fvm flutter test` on every push to `mobile/`. ~30 LOC. No simulator runs.

**Skeleton (mirror test-recipes.yml structure):**
```yaml
name: Mobile lint + tests

on:
  push:
    branches: [main]
    paths:
      - 'mobile/**'
  pull_request:
    branches: [main]
    paths:
      - 'mobile/**'

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Flutter via FVM
        # ... (planner picks: leoafarias/fvm-action or manual fvm install)
      - run: cd mobile && fvm flutter pub get
      - run: cd mobile && fvm flutter analyze
      - run: cd mobile && fvm flutter test
```

**Structural divergence:** The spike does NOT run in CI (CONTEXT D-53 — "Spike runs **local only** — not in CI; requires real api_server + real Docker + OpenRouter network access + iOS Simulator or Android Emulator"). Only `analyze` + `test` (unit tests).

---

## Shared Patterns (apply across all relevant files)

### Wire-Format Mirroring (cross-language)

**Source files:**
- `api_server/src/api_server/middleware/session.py:37` — `SESSION_COOKIE_NAME = "ap_session"`
- `api_server/src/api_server/middleware/idempotency.py:58` — `_AGENT_MESSAGES_PATTERN = re.compile(r"^/v1/agents/[^/]+/messages$")`
- `api_server/src/api_server/models/errors.py:39-58` — `ErrorCode` constants (mirror in Dart enum)
- `api_server/src/api_server/models/errors.py:87-97` — `ErrorBody`/`ErrorEnvelope` (mirror in Dart `ApiError.fromDioException`)

**Apply to:** `auth_interceptor.dart`, `result.dart`, `api_client.dart`, `messages_stream.dart`, `dtos.dart`.

**Rule:** the Dart code mirrors the WIRE FORMAT (HTTP header strings, JSON keys, status codes), NOT the backend's internal Python idioms (no asgi/scope, no asyncpg, no Pydantic decorators).

### No-Mocks Discipline

**Source:** `api_server/tests/e2e/test_inapp_5x5_matrix.py:13-20` — "NO respx, NO mocks. The bot HTTP client is a real `httpx.AsyncClient`."

**Apply to:** `mobile/integration_test/spike_api_roundtrip_test.dart`.

**Rule:** the spike runs against REAL local `api_server` + REAL Docker + REAL OpenRouter. No HTTP mocks, no in-memory fakes. CONTEXT D-46 + Golden Rule #1.

### Lockfile + Strict-Lints Posture

**Source:** `api_server/uv.lock` (committed) + `api_server/pyproject.toml` `[tool.ruff]` (strict).

**Apply to:** `mobile/pubspec.lock` (committed per D-08) + `mobile/analysis_options.yaml` (`include: package:very_good_analysis/analysis_options.yaml` per D-23).

**Rule:** strict-from-day-1; lockfile-driven reproducibility.

### Fail-Loud Boot Validation

**Source:** `api_server/src/api_server/auth/deps.py:50-58` (401 on missing user_id) + RESEARCH `AppEnv.fromEnvironment` `StateError` on bad BASE_URL.

**Apply to:** `mobile/lib/core/env/app_env.dart`, `mobile/Makefile` `make spike` env-guard.

**Rule:** crash points at the fix immediately. No silent fallback masking config errors.

### Redaction Policy

**Source:** `api_server/src/api_server/middleware/log_redact.py` (`AccessLogMiddleware` redaction patterns).

**Apply to:** `mobile/lib/core/api/log_interceptor.dart` + `mobile/integration_test/spike_api_roundtrip_test.dart` (D-52 failure-mode capture).

**Rule:** Cookie + Authorization headers truncated to last 8 chars in any log output.

### Dumb-Client Discipline (CONTEXT line 273-274)

**Source:** Frontend's `proxy.ts` does PRESENCE check only (lines 16-21); validity lives on the backend. Frontend never holds catalogs — recipes/models always fetched.

**Apply to:** `api_client.dart`, `dtos.dart`, all `features/` directories.

**Rule:** no hardcoded recipe lists, no hardcoded model arrays, no client-side enum of agent kinds. Every catalog comes from `/v1/recipes`, `/v1/models`, `/v1/agents`. Golden Rule #2.

---

## No Analog Found

Files with no close in-repo match (planner uses RESEARCH.md / CONTEXT.md spec only):

| File | Role | Reason | Source |
|------|------|--------|--------|
| `mobile/lib/core/storage/secure_storage.dart` | service | Web uses HttpOnly cookies; mobile must own session_id explicitly | RESEARCH §Don't Hand-Roll line 854; CONTEXT D-35 |
| `mobile/lib/core/auth/auth_event_bus.dart` | event-bus | No equivalent pattern exists (web's auth state lives in proxy.ts cookie check) | CONTEXT D-35; RESEARCH §Pattern 2 |
| `mobile/lib/core/router/app_router.dart` | router | go_router has no Python/TS equivalent | RESEARCH §Architecture Patterns lines 213-217; CONTEXT D-26 |
| `mobile/lib/core/env/app_env.dart` | config | `--dart-define` is Dart stdlib; no analog | RESEARCH §Code Examples lines 1183-1207 |
| `mobile/.fvmrc` | SDK pin | No `.python-version` exists in repo (CONTEXT line 225 was incorrect — only `uv.lock` discipline applies) | CONTEXT D-05 |
| `mobile/.env.example` | tooling | api_server has no `.env.example` | CONTEXT D-44/D-49/D-51 |
| `mobile/.gitignore` | tooling | Dart-specific exclusions list | CONTEXT D-08 (enumerated) |
| `spikes/flutter-api-roundtrip.md` | spike artifact | `spikes/` directory does not exist at repo root yet | CONTEXT D-54; existing convention is `api_server/tests/spikes/` |

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/{models,middleware,auth,routes,services}/`
- `frontend/{lib,components,proxy.ts}`
- `api_server/tests/{e2e,spikes}/`
- `api_server/Makefile`
- `.github/workflows/`
- `/Users/fcavalcanti/dev/solvr/frontend/app/globals.css` (out-of-repo, theme source)

**Files scanned for analog detection:** ~80 source files.

**Pattern extraction date:** 2026-05-02.

**Verified non-existence (CONTEXT pre-conditions):**
- `mobile/` — does not exist (cold-start confirmed).
- `spikes/` (repo root) — does not exist (Phase 24 creates it).
- `api_server/.python-version` — does not exist (lockfile-only pinning is the analog).

**RESEARCH.md sections referenced** (for in-spec analogs the planner should cite directly in plan `<read_first>` blocks):
- §Pattern 1: ApiClient (lines 318-407)
- §Pattern 2: AuthInterceptor (lines 409-451)
- §Pattern 3: Sealed Result (lines 455-486)
- §Pattern 4: ApiError (lines 488-595)
- §Pattern 5: MessagesStream (lines 598-676)
- §Pattern 6: Riverpod codegen providers (lines 679-712)
- §Pattern 7: Spike harness (lines 720-826)
- §Code Examples: AppEnv.fromEnvironment (lines 1183-1207)
- §Code Examples: iOS Info.plist ATS (lines 1094-1114)
- §Code Examples: iOS Info.plist URL types (lines 1164-1180)
- §Code Examples: Android intent-filter (lines 1144-1162)
- §Code Examples: Android network_security_config (lines 1116-1142)
- §Theme Skeleton (lines 1228-1290)
- §Token Conversion Table (lines 1213-1225)
