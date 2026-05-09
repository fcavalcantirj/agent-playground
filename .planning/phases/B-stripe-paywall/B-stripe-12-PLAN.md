---
phase: B-stripe
plan: 12
type: execute
wave: 5
depends_on: [B-stripe-10]
files_modified:
  - mobile/lib/features/usage/usage_models.dart
  - mobile/lib/features/usage/usage_ticker_widget.dart
  - mobile/lib/features/dashboard/dashboard_providers.dart
  - mobile/lib/features/chat/chat_providers.dart
  - mobile/lib/app.dart
  - mobile/test/features/usage/usage_ticker_widget_tier_branch_test.dart
  - mobile/test/features/chat/chat_402_handler_test.dart
autonomous: true
gap_closure: false
requirements_addressed:
  - D-02 (bimodal display — ultra users see credits, free/pro see USD)
  - D-18 (lazy tier propagation; ticker polls /v1/usage/summary regularly)
  - D-21 (chat 402 routes to InsufficientCreditsModal — NOT RetryBanner)
  - AMD-04 (Sentry user-context updates with tier on sign-in / tier flip)
must_haves:
  truths:
    - "UsageSummary mobile model adds tier (always) + balanceCents/displayBalanceCents/isNegative (when ultra)"
    - "UsageTickerWidget renders credits ('123 credits') for ultra, USD for free/pro (existing Phase A path)"
    - "When tier='ultra' AND is_negative=true, ticker shows '$0.00 ⚠' with tap-to-explain dialog"
    - "Chat provider classifies 402 separately from other errors and triggers showInsufficientCreditsModal — NOT the RetryBanner"
    - "Sentry.configureScope sets tier as user context data on sign-in AND on tier flip detected via balance polling"
  artifacts:
    - path: "mobile/lib/features/usage/usage_models.dart"
      provides: "Updated UsageSummary with tier + balance fields"
    - path: "mobile/lib/features/usage/usage_ticker_widget.dart"
      provides: "Tier-branched render"
  key_links:
    - from: "mobile/lib/features/chat/chat_providers.dart"
      to: "mobile/lib/features/billing/insufficient_credits_modal.dart"
      via: "402 status code → showInsufficientCreditsModal call"
      pattern: "showInsufficientCreditsModal"
    - from: "mobile/lib/app.dart"
      to: "Sentry.configureScope"
      via: "scope.setUser + scope.setData('tier', tier)"
      pattern: "setData\\(['\\\"]tier"
---

<objective>
Three byte-additive mobile modifications: (1) tier-branched ticker render; (2) chat 402 → modal dispatch; (3) Sentry user-context tier wiring. None of these add new screens — they extend existing surfaces with tier awareness.

Purpose: After Plan 11 ships the dedicated billing screens, the existing screens (chat + AppBar) need to react to tier appropriately. Without these, a Pro user would see the ticker showing USD (correct) but an Ultra user would also see USD (wrong). And a chat 402 would route to the H4 RetryBanner (wrong — must be modal per D-21).
Output: Modifications to 5 mobile files + 2 unit tests.
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
@.planning/phases/B-stripe-paywall/B-stripe-04-SUMMARY.md
@mobile/lib/features/usage/usage_models.dart
@mobile/lib/features/usage/usage_ticker_widget.dart
@mobile/lib/features/dashboard/dashboard_providers.dart
@mobile/lib/features/chat/chat_providers.dart
@mobile/lib/app.dart

<interfaces>
From Plan 04 — /v1/usage/summary now includes:
- tier: str (always)
- balance_cents: int? (only when tier='ultra')
- display_balance_cents: int? (only when tier='ultra')
- is_negative: bool? (only when tier='ultra')

From Plan 11 — mobile/lib/features/billing/insufficient_credits_modal.dart:
- showInsufficientCreditsModal(context: BuildContext) -> Future<void>

From mobile/lib/app.dart (Phase 31 H6 / WR-01):
- Sentry.configureScope((scope) => scope.setUser(SentryUser(id: ...))) on sign-in
- Phase B adds: scope.setData('tier', tier)

From mobile/lib/features/chat/chat_providers.dart (Phase 31 H4):
- classifyChatStreamError enum
- chatStreamErrorProvider routes errors to RetryBanner
- Phase B intercepts 402 BEFORE classifier — routes to modal instead
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: usage_models.dart + usage_ticker_widget.dart tier projection + dashboard provider passthrough</name>
  <files>mobile/lib/features/usage/usage_models.dart, mobile/lib/features/usage/usage_ticker_widget.dart, mobile/lib/features/dashboard/dashboard_providers.dart, mobile/test/features/usage/usage_ticker_widget_tier_branch_test.dart</files>
  <read_first>
    - mobile/lib/features/usage/usage_models.dart (FULL — current UsageSummary + hand-written fromJson)
    - mobile/lib/features/usage/usage_ticker_widget.dart (FULL — current render)
    - mobile/lib/features/dashboard/dashboard_providers.dart (FULL — AgentsList provider)
    - mobile/test/features/usage/usage_ticker_widget_test.dart (existing test pattern)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"Mobile: usage_ticker_widget.dart")
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_ticker_renders_usd_for_free_tier
    - test_ticker_renders_usd_for_pro_tier
    - test_ticker_renders_credits_for_ultra_tier
    - test_ticker_renders_zero_credits_with_warning_for_negative_balance_ultra
    - test_summary_fromJson_with_no_balance_fields_for_free_user
    - test_summary_fromJson_with_balance_fields_for_ultra_user
  </behavior>
  <action>
**File 1 — `mobile/lib/features/usage/usage_models.dart` modification:** Add new optional fields to `UsageSummary`:

```dart
class UsageSummary {
  const UsageSummary({
    required this.totalUsd,
    required this.byProvider,
    required this.periodStart,
    required this.periodEnd,
    this.tier = 'free',
    this.balanceCents,
    this.displayBalanceCents,
    this.isNegative,
  });

  factory UsageSummary.fromJson(Map<String, dynamic> json) => UsageSummary(
        totalUsd: (json['total_usd'] as String?) ?? '0',
        byProvider: ...existing...,
        periodStart: DateTime.parse(json['period_start'] as String),
        periodEnd: DateTime.parse(json['period_end'] as String),
        tier: (json['tier'] as String?) ?? 'free',
        balanceCents: json['balance_cents'] as int?,
        displayBalanceCents: json['display_balance_cents'] as int?,
        isNegative: json['is_negative'] as bool?,
      );

  // ...existing fields unchanged...
  final String tier;
  final int? balanceCents;
  final int? displayBalanceCents;
  final bool? isNegative;
}
```

**File 2 — `mobile/lib/features/usage/usage_ticker_widget.dart` modification:** Branch the render label on `summary.tier`:

```dart
// In the existing build method, replace the single `Text(label)` with:
Widget build(BuildContext context, WidgetRef ref) {
  final asyncSummary = ref.watch(usageSummaryProvider);
  return asyncSummary.when(
    data: (summary) {
      final isUltra = summary.tier == 'ultra';
      final isNegative = summary.isNegative ?? false;
      final label = isUltra
          ? (isNegative
              ? '\$0.00 ⚠'
              : '${summary.displayBalanceCents ?? 0} credits')
          : '\$${summary.totalUsd}';
      final widget = Text(label, style: ...existing style...);
      if (isUltra && isNegative) {
        return GestureDetector(
          onTap: () => showDialog(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('Negative balance'),
              content: const Text(
                'A refund was processed and your balance is currently negative. '
                'Top up to resume usage, or contact support for write-off review.',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('Close'),
                ),
              ],
            ),
          ),
          child: widget,
        );
      }
      return widget;
    },
    loading: () => ...existing...,
    error: (e, _) => ...existing...,
  );
}
```

**File 3 — `mobile/lib/features/dashboard/dashboard_providers.dart` modification:** No change required IF the dashboard projection already proxies the same `usageSummaryProvider`. Re-read the file to confirm. If the dashboard does NOT consume usageSummaryProvider, no change. If it does, ensure the new fields are passed through to whatever derived state it produces.

**File 4 — `mobile/test/features/usage/usage_ticker_widget_tier_branch_test.dart`:** ProviderContainer + override usageSummaryProvider with synthetic UsageSummary instances per the 4 ticker behaviors. Use `pumpWidget` + `find.text(...)`.

**Note on serialization:** Phase A's `usage_ticker_widget_test.dart` may break if it constructs `UsageSummary` without the new optional fields. Default-args make the constructor compatible. Re-run the existing tests as a regression gate.
  </action>
  <verify>
    <automated>cd mobile &amp;&amp; flutter test test/features/usage/usage_ticker_widget_tier_branch_test.dart test/features/usage/usage_ticker_widget_test.dart</automated>
  </verify>
  <done>
- All 6 new ticker tests + existing Phase A ticker tests pass.
- `grep -c 'tier' mobile/lib/features/usage/usage_models.dart` ≥ 2.
- `grep -c "tier == 'ultra'" mobile/lib/features/usage/usage_ticker_widget.dart` ≥ 1.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: chat_providers.dart 402 → modal dispatch + Sentry tier wiring</name>
  <files>mobile/lib/features/chat/chat_providers.dart, mobile/lib/app.dart, mobile/test/features/chat/chat_402_handler_test.dart</files>
  <read_first>
    - mobile/lib/features/chat/chat_providers.dart (FULL — current classifyChatStreamError + 401 branch)
    - mobile/lib/app.dart (Phase 31 H6 + WR-01 — existing Sentry user-context wiring)
    - mobile/lib/features/billing/insufficient_credits_modal.dart (Plan 11 — showInsufficientCreditsModal)
    - mobile/lib/features/usage/usage_providers.dart (existing pattern for invoking provider on sign-in)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"Mobile: chat_providers.dart" + §"app.dart")
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_chat_send_402_response_calls_showInsufficientCreditsModal
    - test_chat_send_500_response_routes_to_existing_RetryBanner_NOT_modal
    - test_chat_send_401_routes_to_existing_authExpired_branch
    - test_sentry_scope_sets_tier_on_sign_in
    - test_sentry_scope_updates_tier_when_balance_provider_invalidated_and_returns_new_tier
  </behavior>
  <action>
**File 1 — `mobile/lib/features/chat/chat_providers.dart` modification:** Locate the existing chat-send error branch (likely around the `classifyChatStreamError` call site in the POST-message handler). Add a 402 dispatch BEFORE the classifier:

```dart
// inside the chat send / dispatch error handler, e.g. after the api response:
if (response.statusCode == 402) {
  // D-21 — blocking modal, NOT RetryBanner.
  if (context.mounted) {
    await showInsufficientCreditsModal(context);
  }
  return;
}
// ...existing classifyChatStreamError + RetryBanner dispatch unchanged...
```

The exact integration point depends on the existing chat flow architecture. Re-read chat_providers.dart and find the place where the API response is interpreted. The 402 branch goes BEFORE the existing classifier so `INSUFFICIENT_BALANCE` doesn't fall into `classifyChatStreamError` and become a generic SSE error.

**Caveat:** `showInsufficientCreditsModal` requires a `BuildContext`. If chat_providers.dart is a pure Riverpod notifier without Context access, plumb the context via a callback or use `rootNavigatorKey.currentContext` (verify what app.dart sets up). Alternative: emit a `chatBlockingErrorProvider` of `enum {none, insufficientCredits, otherError}` and let the chat screen widget watch it and show the modal in its build method. The latter is cleaner; pick whichever fits the existing pattern.

**File 2 — `mobile/lib/app.dart` modification:** Existing wiring sets the Sentry user on sign-in. Extend it to also set tier:

```dart
// Existing wiring (Phase 31 WR-01):
ref.listen(loginSuccessProvider, (prev, next) {
  Sentry.configureScope((scope) {
    scope.setUser(SentryUser(id: next.userId));
    scope.setData('tier', next.tier ?? 'free');     // NEW Phase B
  });
});

// NEW: also listen to balanceNotifierProvider — when it returns, refresh tier in Sentry scope.
ref.listen(balanceNotifierProvider, (prev, next) {
  next.whenData((bal) {
    Sentry.configureScope((scope) {
      scope.setData('tier', bal.tier);
    });
  });
});
```

**Concern:** `loginSuccessProvider` may not have `tier` exposed today. If so, the cleanest path is to read tier from the `usageSummaryProvider` (Phase A) which now includes `tier`. Pivot the listener to that provider instead.

**File 3 — `mobile/test/features/chat/chat_402_handler_test.dart`:** Mock the chat dispatch path. Use `http_mock_adapter` to make the chat POST return 402; assert `showInsufficientCreditsModal` was invoked. For the 500 case, assert `chatStreamErrorProvider` was set (the existing RetryBanner path) and the modal was NOT invoked.

**Sentry tests:** Use `sentry_flutter` mock or capture invocations of `Sentry.configureScope`. Or use a thin wrapper service that the test can mock. Mirror what Phase 31 WR-01 + WR-03 tests do for verification (re-read those tests).
  </action>
  <verify>
    <automated>cd mobile &amp;&amp; flutter test test/features/chat/chat_402_handler_test.dart</automated>
  </verify>
  <done>
- All 5 chat-handler + Sentry tests pass.
- `grep -c 'showInsufficientCreditsModal' mobile/lib/features/chat/chat_providers.dart` ≥ 1.
- `grep -c "setData\('tier'" mobile/lib/app.dart` ≥ 1.
- Existing chat-error tests (Phase 31 H4 RetryBanner) still pass.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| api_server → mobile | tier returned in /v1/usage/summary; trusted (server-side authoritative) |
| Mobile UI → Sentry | tier added to user-context for crash report enrichment; NOT a security boundary |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-DSP | InfoDisclosure | usage_ticker_widget.dart | mitigate | display_balance_cents (clamped at 0) shown to user; raw balance_cents (could be negative) only used internally for is_negative computation |
| T-B-MOD | EoP | chat_providers.dart 402 branch | accept | client-side modal can be dismissed via app force-close, but next chat call will hit 402 again at api_server (server-authoritative); no client-side bypass possible |
| T-B-LK | InfoDisclosure | app.dart Sentry tier-context | accept | tier value (free/pro/ultra) is not PII; safe to surface in crash reports |
</threat_model>

<verification>
- All 11 mobile tests pass.
- 402 path goes to modal (not RetryBanner).
- Sentry scope sets tier on sign-in + tier flip.
</verification>

<success_criteria>
- `cd mobile && flutter test` all green (full suite).
- `cd mobile && flutter analyze` clean.
- Manual smoke: ultra-tier user with balance=0 sends a chat → modal appears (not banner).
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-12-SUMMARY.md` documenting the 3 mobile-side surfaces extended.
</output>
