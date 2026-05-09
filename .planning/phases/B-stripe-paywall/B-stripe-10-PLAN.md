---
phase: B-stripe
plan: 10
type: execute
wave: 5
depends_on: [B-stripe-03, B-stripe-05]
files_modified:
  - mobile/lib/features/billing/billing_models.dart
  - mobile/lib/features/billing/billing_api.dart
  - mobile/lib/features/billing/billing_providers.dart
  - mobile/lib/core/api/api_endpoints.dart
  - mobile/lib/core/api/api_client.dart
  - mobile/lib/core/router/app_router.dart
  - mobile/test/features/billing/billing_models_test.dart
  - mobile/test/features/billing/billing_providers_test.dart
autonomous: true
gap_closure: false
requirements_addressed:
  - D-06 (mobile fetches packs from /v1/billing/packs — NO hardcoded catalog)
  - D-21 (mobile billing surfaces; balance polling)
  - APP-03 (typed API client)
must_haves:
  truths:
    - "billing_models.dart exposes Pack, Balance, Transaction DTOs with hand-written fromJson per D-34"
    - "billing_api.dart adds 5 new typed methods: billingPacks, billingBalance, createCheckoutSession, createSubscription, billingTransactions"
    - "billing_providers.dart Riverpod hub mirrors usage_providers.dart shape (CancelToken + appLifecycleProvider listen)"
    - "app_router adds 3 new routes (/billing/topup, /billing/checkout, /billing/transactions)"
    - "Mobile NEVER hardcodes pack data — every render path goes through GET /v1/billing/packs"
  artifacts:
    - path: "mobile/lib/features/billing/billing_models.dart"
      provides: "Pack, Balance, Transaction DTOs"
    - path: "mobile/lib/features/billing/billing_api.dart"
      provides: "5 typed API methods returning Result envelopes"
    - path: "mobile/lib/features/billing/billing_providers.dart"
      provides: "BalanceNotifier, PacksNotifier, TransactionsNotifier"
  key_links:
    - from: "mobile/lib/features/billing/billing_api.dart"
      to: "GET /v1/billing/packs"
      via: "Dio client + ApiEndpoints.billingPacks"
      pattern: "billingPacks"
    - from: "mobile/lib/core/router/app_router.dart"
      to: "billing screens (Plan 11)"
      via: "GoRoute entries"
      pattern: "/billing/topup|/billing/checkout|/billing/transactions"
---

<objective>
Mobile data plumbing for Phase B billing. DTOs + API client methods + Riverpod providers + router entries. Screens come in Plan 11; this plan is the substrate they bind to.

Purpose: The "dumb client" rule forbids hardcoding the catalog or doing client-side aggregation. This plan establishes the typed pipes from api_server endpoints to mobile state.
Output: 3 new files in `mobile/lib/features/billing/` + extensions to api_endpoints/api_client/app_router + tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/B-stripe-paywall/CONTEXT.md
@.planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md
@.planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md
@mobile/lib/features/usage/usage_models.dart
@mobile/lib/features/usage/usage_providers.dart
@mobile/lib/core/api/api_endpoints.dart
@mobile/lib/core/api/api_client.dart
@mobile/lib/core/router/app_router.dart

<interfaces>
From api_server (Plans 03 + 05) — endpoint contracts:
- GET /v1/billing/packs → {"packs": [{id, label, usd_amount_cents:int, credit_cents:int}, ...]}
- GET /v1/billing/balance → {tier:str, balance_cents:int, display_balance_cents:int, is_negative:bool}
- GET /v1/billing/transactions?limit=N&before=ISO → {transactions:[{id, kind, amount_cents, reference_id?, reference_type?, created_at}], next_before?}
- POST /v1/billing/checkout {pack_id} → {checkout_url}
- POST /v1/billing/subscription {} → {checkout_url}

From mobile/lib/features/usage/usage_models.dart (Phase 27 — D-34 contract):
- Hand-written fromJson, defensive defaults; USD as String; no json_serializable codegen

From mobile/lib/features/usage/usage_providers.dart (template):
- @riverpod class with CancelToken + appLifecycleProvider listen + Result switch

From mobile/lib/core/api/api_client.dart (Dio + Result envelope):
- Future<Result<T>> shape, DioException → Result.err
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: billing_models.dart + api_endpoints.dart + api_client.dart + tests</name>
  <files>mobile/lib/features/billing/billing_models.dart, mobile/lib/core/api/api_endpoints.dart, mobile/lib/core/api/api_client.dart, mobile/lib/features/billing/billing_api.dart, mobile/test/features/billing/billing_models_test.dart</files>
  <read_first>
    - mobile/lib/features/usage/usage_models.dart (FULL — D-34 hand-written fromJson template)
    - mobile/lib/core/api/api_endpoints.dart (FULL)
    - mobile/lib/core/api/api_client.dart:407-440 (Dio.get/post → Result.ok/err pattern)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"Mobile" sections — full templates)
  </read_first>
  <behavior>
    Tests written FIRST (Dart):
    - test_pack_fromJson_parses_complete_object
    - test_pack_fromJson_handles_missing_int_fields_with_defaults
    - test_balance_fromJson_parses_negative_balance
    - test_transaction_fromJson_handles_null_reference_fields
    - test_transactions_response_with_next_before
  </behavior>
  <action>
**File 1 — `mobile/lib/features/billing/billing_models.dart`:**

```dart
class Pack {
  const Pack({
    required this.id,
    required this.label,
    required this.usdAmountCents,
    required this.creditCents,
  });

  factory Pack.fromJson(Map<String, dynamic> json) => Pack(
        id: json['id'] as String,
        label: json['label'] as String,
        usdAmountCents: (json['usd_amount_cents'] as int?) ?? 0,
        creditCents: (json['credit_cents'] as int?) ?? 0,
      );

  final String id;
  final String label;
  final int usdAmountCents;
  final int creditCents;
}

class Balance {
  const Balance({
    required this.tier,
    required this.balanceCents,
    required this.displayBalanceCents,
    required this.isNegative,
  });

  factory Balance.fromJson(Map<String, dynamic> json) => Balance(
        tier: (json['tier'] as String?) ?? 'free',
        balanceCents: (json['balance_cents'] as int?) ?? 0,
        displayBalanceCents: (json['display_balance_cents'] as int?) ?? 0,
        isNegative: (json['is_negative'] as bool?) ?? false,
      );

  final String tier;
  final int balanceCents;
  final int displayBalanceCents;
  final bool isNegative;
}

class Transaction {
  const Transaction({
    required this.id,
    required this.kind,
    required this.amountCents,
    required this.createdAt,
    this.referenceId,
    this.referenceType,
  });

  factory Transaction.fromJson(Map<String, dynamic> json) => Transaction(
        id: json['id'] as String,
        kind: json['kind'] as String,
        amountCents: (json['amount_cents'] as int?) ?? 0,
        referenceId: json['reference_id'] as String?,
        referenceType: json['reference_type'] as String?,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  final String id;
  final String kind;            // topup / debit / refund / tier_change / admin_writeoff
  final int amountCents;        // negative for debits
  final String? referenceId;
  final String? referenceType;
  final DateTime createdAt;
}

class TransactionsPage {
  const TransactionsPage({required this.transactions, this.nextBefore});

  factory TransactionsPage.fromJson(Map<String, dynamic> json) => TransactionsPage(
        transactions: ((json['transactions'] as List<dynamic>?) ?? const [])
            .map((e) => Transaction.fromJson(e as Map<String, dynamic>))
            .toList(growable: false),
        nextBefore: json['next_before'] != null
            ? DateTime.parse(json['next_before'] as String)
            : null,
      );

  final List<Transaction> transactions;
  final DateTime? nextBefore;
}
```

**File 2 — `mobile/lib/core/api/api_endpoints.dart` modification:** Append:

```dart
// Phase B — billing surface.
static const String billingPacks         = '/v1/billing/packs';
static const String billingBalance       = '/v1/billing/balance';
static const String billingTransactions  = '/v1/billing/transactions';
static const String billingCheckout      = '/v1/billing/checkout';
static const String billingSubscription  = '/v1/billing/subscription';
```

**File 3 — `mobile/lib/features/billing/billing_api.dart`:** New file. Mirror `lib/core/api/api_client.dart:407-440`:

```dart
import 'package:dio/dio.dart';
import '../../core/api/api_client.dart';
import '../../core/api/api_endpoints.dart';
import 'billing_models.dart';

extension BillingApi on ApiClient {
  Future<Result<List<Pack>>> billingPacks({CancelToken? cancelToken}) async {
    try {
      final res = await dio.get<Map<String, dynamic>>(
        ApiEndpoints.billingPacks,
        cancelToken: cancelToken,
      );
      final raw = (res.data!['packs'] as List<dynamic>);
      return Result.ok(raw
          .map((e) => Pack.fromJson(e as Map<String, dynamic>))
          .toList(growable: false));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<Balance>> billingBalance({CancelToken? cancelToken}) async {
    try {
      final res = await dio.get<Map<String, dynamic>>(
        ApiEndpoints.billingBalance,
        cancelToken: cancelToken,
      );
      return Result.ok(Balance.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<TransactionsPage>> billingTransactions({
    int limit = 50,
    DateTime? before,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await dio.get<Map<String, dynamic>>(
        ApiEndpoints.billingTransactions,
        queryParameters: {
          'limit': limit,
          if (before != null) 'before': before.toUtc().toIso8601String(),
        },
        cancelToken: cancelToken,
      );
      return Result.ok(TransactionsPage.fromJson(res.data!));
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<String>> createPackCheckoutSession({
    required String packId,
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await dio.post<Map<String, dynamic>>(
        ApiEndpoints.billingCheckout,
        data: {'pack_id': packId},
        cancelToken: cancelToken,
      );
      return Result.ok(res.data!['checkout_url'] as String);
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }

  Future<Result<String>> createSubscriptionCheckoutSession({
    CancelToken? cancelToken,
  }) async {
    try {
      final res = await dio.post<Map<String, dynamic>>(
        ApiEndpoints.billingSubscription,
        data: {},
        cancelToken: cancelToken,
      );
      return Result.ok(res.data!['checkout_url'] as String);
    } on DioException catch (e) {
      return Result.err(ApiError.fromDioException(e));
    }
  }
}
```

**Note:** This uses Dart extension methods on `ApiClient`. If the existing api_client.dart shape is methods on a `class ApiClient`, instead add the methods directly to api_client.dart (mirror lines 407-440 in-place rather than via extension). Confirm shape via `read_first` and adapt.

**File 4 — `mobile/test/features/billing/billing_models_test.dart`:** Pure Dart unit test. Cover the 5 fromJson behaviors listed.
  </action>
  <verify>
    <automated>cd mobile &amp;&amp; flutter test test/features/billing/billing_models_test.dart</automated>
  </verify>
  <done>
- All 5 model tests pass.
- `grep -c 'factory.*fromJson' mobile/lib/features/billing/billing_models.dart` ≥ 4 (Pack, Balance, Transaction, TransactionsPage).
- `grep -c 'billing' mobile/lib/core/api/api_endpoints.dart` ≥ 5.
- The 5 new ApiClient methods exist (extension OR direct).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: billing_providers.dart + app_router.dart + provider tests</name>
  <files>mobile/lib/features/billing/billing_providers.dart, mobile/lib/core/router/app_router.dart, mobile/test/features/billing/billing_providers_test.dart</files>
  <read_first>
    - mobile/lib/features/usage/usage_providers.dart (FULL — Riverpod + CancelToken + appLifecycleProvider template)
    - mobile/lib/core/router/app_router.dart (GoRoute pattern)
    - mobile/lib/features/billing/billing_api.dart (Task 1)
    - mobile/lib/features/billing/billing_models.dart (Task 1)
    - mobile/test/features/usage/ (existing provider test patterns)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_packs_notifier_loads_5_packs_via_api_client
    - test_balance_notifier_loads_balance
    - test_balance_notifier_invalidates_on_app_resume
    - test_transactions_notifier_paginates_on_load_more
    - test_balance_notifier_handles_api_error
  </behavior>
  <action>
**File 1 — `mobile/lib/features/billing/billing_providers.dart`:**

```dart
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../../core/api/api_client.dart';
import '../../core/lifecycle/app_lifecycle_provider.dart';  // existing per usage_providers.dart
import 'billing_api.dart';
import 'billing_models.dart';

part 'billing_providers.g.dart';

@riverpod
class PacksNotifier extends _$PacksNotifier {
  CancelToken? _cancel;

  @override
  Future<List<Pack>> build() async {
    _cancel?.cancel('superseded');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) cancel.cancel('disposed');
    });
    final api = ref.watch(apiClientProvider);
    final r = await api.billingPacks(cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      Err(:final error) => throw error,
    };
  }
}

@riverpod
class BalanceNotifier extends _$BalanceNotifier {
  CancelToken? _cancel;

  @override
  Future<Balance> build() async {
    _cancel?.cancel('superseded');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) cancel.cancel('disposed');
    });
    ref.listen<AppLifecycleState>(appLifecycleProvider, (prev, next) {
      if (prev != next && next == AppLifecycleState.resumed) {
        ref.invalidateSelf();
      }
    });
    final api = ref.watch(apiClientProvider);
    final r = await api.billingBalance(cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      Err(:final error) => throw error,
    };
  }
}

@riverpod
class TransactionsNotifier extends _$TransactionsNotifier {
  CancelToken? _cancel;

  @override
  Future<TransactionsPage> build() async {
    _cancel?.cancel('superseded');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) cancel.cancel('disposed');
    });
    final api = ref.watch(apiClientProvider);
    final r = await api.billingTransactions(limit: 50, cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      Err(:final error) => throw error,
    };
  }

  /// Append next page using the cursor.
  Future<void> loadMore() async {
    final current = state.value;
    if (current == null || current.nextBefore == null) return;
    final api = ref.read(apiClientProvider);
    final r = await api.billingTransactions(limit: 50, before: current.nextBefore);
    if (r case Ok(:final value)) {
      state = AsyncValue.data(TransactionsPage(
        transactions: [...current.transactions, ...value.transactions],
        nextBefore: value.nextBefore,
      ));
    }
  }
}
```

Run `cd mobile && dart run build_runner build --delete-conflicting-outputs` to regenerate `billing_providers.g.dart`.

**File 2 — `mobile/lib/core/router/app_router.dart`:** Add 3 GoRoute entries. Mirror existing `GoRoute(...)` shape:

```dart
GoRoute(
  path: '/billing/topup',
  builder: (context, state) => const TopUpScreen(),
),
GoRoute(
  path: '/billing/checkout',
  builder: (context, state) {
    final url = state.uri.queryParameters['url'];
    return CheckoutWebViewScreen(checkoutUrl: url ?? '');
  },
),
GoRoute(
  path: '/billing/transactions',
  builder: (context, state) => const TransactionsScreen(),
),
```

The TopUpScreen / CheckoutWebViewScreen / TransactionsScreen widgets are added in Plan 11; for this plan, add the routes as forward references (the import lines + class names will resolve once Plan 11 lands). To keep the build green NOW (before Plan 11), add stub widget classes inline at the bottom of `app_router.dart` (or in a temporary `mobile/lib/features/billing/_stubs.dart`):

```dart
// TEMP STUBS — replaced by full screens in Plan 11.
class TopUpScreen extends StatelessWidget {
  const TopUpScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('TopUp')));
}
class CheckoutWebViewScreen extends StatelessWidget {
  const CheckoutWebViewScreen({super.key, required this.checkoutUrl});
  final String checkoutUrl;
  @override
  Widget build(BuildContext context) => Scaffold(body: Center(child: Text('Checkout: $checkoutUrl')));
}
class TransactionsScreen extends StatelessWidget {
  const TransactionsScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(body: Center(child: Text('Transactions')));
}
```

**Decision (per Plan 11 dependency):** Plan 11 will replace these stubs with real screens. Marking the stubs with a `// PHASE_B_STUB` comment so Plan 11's executor finds and replaces them.

**File 3 — `mobile/test/features/billing/billing_providers_test.dart`:** Use `ProviderContainer` + `http_mock_adapter` (existing dev dep per Phase 24). Mirror `mobile/test/features/usage/usage_providers_test.dart`:

```dart
testWidgets('packsNotifier loads 5 packs via api client', (tester) async {
  final dioAdapter = DioAdapter(dio: ...);
  dioAdapter.onGet('/v1/billing/packs', (s) => s.reply(200, {
    'packs': [
      {'id': 'pack_5', 'label': r'$5', 'usd_amount_cents': 500, 'credit_cents': 500},
      // ...4 more...
    ],
  }));
  final container = ProviderContainer(...);
  final r = await container.read(packsNotifierProvider.future);
  expect(r.length, 5);
  expect(r.first.id, 'pack_5');
});
```
  </action>
  <verify>
    <automated>cd mobile &amp;&amp; dart run build_runner build --delete-conflicting-outputs &amp;&amp; flutter test test/features/billing/billing_providers_test.dart</automated>
  </verify>
  <done>
- All 5 provider tests pass.
- `grep -c '@riverpod' mobile/lib/features/billing/billing_providers.dart` = 3.
- `grep -c '/billing/' mobile/lib/core/router/app_router.dart` ≥ 3.
- Stub screens marked with `// PHASE_B_STUB` comment so Plan 11 can find them.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Mobile → api_server | session-cookie auth via existing Dio interceptor; HTTPS in prod, HTTP localhost in dev |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-LK | InfoDisclosure | mobile billing models | mitigate | DTOs do NOT include stripe_price_id (server already filters); no Stripe key ever ships in mobile binary |
| T-B-XT | InfoDisclosure | billing_api.dart | mitigate | Dio uses request.app's session cookie via existing interceptor; cross-tenant probe defense lives at api_server |
| T-B-LOG | InfoDisclosure | mobile error logging | mitigate | DioException toString() output is not logged in plaintext to crash reports — Sentry SDK handles redaction; Phase 31 H6 wired |
</threat_model>

<verification>
- 10 mobile tests pass.
- Stubs in app_router.dart compile and route correctly.
- No new dependencies (flutter_inappwebview was added in Wave 0).
</verification>

<success_criteria>
- `cd mobile && flutter analyze` clean.
- `cd mobile && flutter test test/features/billing/` all green.
- Manual smoke (deploy stack up, real session cookie): launch app, navigate to `/billing/transactions` → see "Transactions" stub. Plan 11 replaces this with real list.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-10-SUMMARY.md` listing the DTOs, API methods, providers, and stub-marker locations for Plan 11.
</output>
