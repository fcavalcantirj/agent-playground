---
phase: B-stripe
plan: 11
type: execute
wave: 5
depends_on: [B-stripe-10]
files_modified:
  - mobile/lib/features/billing/topup_screen.dart
  - mobile/lib/features/billing/pack_picker_widget.dart
  - mobile/lib/features/billing/checkout_webview_screen.dart
  - mobile/lib/features/billing/topup_inflight_widget.dart
  - mobile/lib/features/billing/transactions_screen.dart
  - mobile/lib/features/billing/insufficient_credits_modal.dart
  - mobile/lib/core/router/app_router.dart
  - mobile/test/features/billing/topup_screen_test.dart
  - mobile/test/features/billing/checkout_webview_screen_test.dart
  - mobile/test/features/billing/insufficient_credits_modal_test.dart
  - mobile/test/features/billing/transactions_screen_test.dart
autonomous: false
gap_closure: false
requirements_addressed:
  - D-21 (mobile 402 modal + top-up flow + pack picker + Stripe Checkout webview + balance polling)
  - D-22 (manual UAT for webview interception is the primary verification — included as checkpoint)
  - APP-02 (Solvr Labs design language carries over)
  - AMD-03 (flutter_inappwebview package binding)
must_haves:
  truths:
    - "TopUpScreen renders the 5 packs from PacksNotifier and lets the user tap one to start Checkout"
    - "PackPickerWidget shows pack label + usd_amount_cents + credit_cents (rendered via formatUsd)"
    - "CheckoutWebViewScreen opens the Stripe-hosted Checkout URL in flutter_inappwebview and intercepts success/cancel via shouldOverrideUrlLoading"
    - "On success_url interception, screen pops with PaymentResult.success and the calling screen polls BalanceNotifier until balance reflects the top-up (or 30s timeout)"
    - "InsufficientCreditsModal is a BLOCKING AlertDialog (barrierDismissible: false) per D-21"
    - "TransactionsScreen renders the paginated TransactionsPage with kind+amount+date; load-more on scroll"
    - "TopUpInflightWidget reuses the deploy_step.dart Stopwatch + Timer.periodic + mm:ss + Cancel pattern"
  artifacts:
    - path: "mobile/lib/features/billing/topup_screen.dart"
      provides: "Pack picker + post-Checkout polling state"
    - path: "mobile/lib/features/billing/checkout_webview_screen.dart"
      provides: "InAppWebView with shouldOverrideUrlLoading interception"
    - path: "mobile/lib/features/billing/insufficient_credits_modal.dart"
      provides: "BLOCKING modal with Top-Up CTA"
      exports: ["showInsufficientCreditsModal"]
  key_links:
    - from: "topup_screen.dart"
      to: "checkout_webview_screen.dart"
      via: "Navigator.push → returns _PaymentResult on pop"
      pattern: "_PaymentResult"
    - from: "insufficient_credits_modal.dart"
      to: "/billing/topup"
      via: "ctx.push('/billing/topup') from the modal's Top-up CTA"
      pattern: "ctx\\.push\\(['\\\"]\\/billing\\/topup"
---

<objective>
Mobile UI screens. Replaces Plan 10's stub widgets with real implementations. Includes the Stripe Checkout webview interception (the only spike-validated mobile-novel surface in Phase B) and the BLOCKING modal users see when they hit 402.

Purpose: Wave 5's primary user-facing artifact. Without these screens, the api_server billing surface has no mobile UI to consume it.
Output: 6 new widget files + checkpoint:human-verify gate for the webview UX (only thoroughly verifiable on a real device).
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
@.planning/phases/B-stripe-paywall/B-stripe-10-SUMMARY.md
@.planning/phases/B-stripe-paywall/B-stripe-01-SUMMARY.md
@mobile/lib/features/usage/agent_usage_screen.dart
@mobile/lib/features/new_agent/deploy_step.dart
@mobile/lib/shared/confirm_dialog.dart
@mobile/lib/features/billing/billing_providers.dart
@mobile/integration_test/spike_e_inappwebview_intercept.dart

<interfaces>
From mobile/lib/features/billing/billing_providers.dart (Plan 10):
- packsNotifierProvider → AsyncValue<List<Pack>>
- balanceNotifierProvider → AsyncValue<Balance>
- transactionsNotifierProvider → AsyncValue<TransactionsPage>; loadMore() method

From flutter_inappwebview (Wave 0 spike-e proven):
- InAppWebView widget; shouldOverrideUrlLoading callback
- NavigationActionPolicy.{ALLOW, CANCEL}

From mobile/lib/features/new_agent/deploy_step.dart:387-444:
- Stopwatch + Timer.periodic + mm:ss formatter pattern (lift verbatim)

From mobile/lib/shared/confirm_dialog.dart:
- showDialog<...>(barrierDismissible: false, ...) pattern
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: PackPickerWidget + TopUpScreen + TopUpInflightWidget + InsufficientCreditsModal + tests</name>
  <files>mobile/lib/features/billing/topup_screen.dart, mobile/lib/features/billing/pack_picker_widget.dart, mobile/lib/features/billing/topup_inflight_widget.dart, mobile/lib/features/billing/insufficient_credits_modal.dart, mobile/test/features/billing/topup_screen_test.dart, mobile/test/features/billing/insufficient_credits_modal_test.dart</files>
  <read_first>
    - mobile/lib/features/usage/agent_usage_screen.dart (FULL — Scaffold + AppBar + async.when + RefreshIndicator pattern)
    - mobile/lib/features/new_agent/deploy_step.dart:80-83, 387-444 (FULL — Stopwatch + Timer + mm:ss + Cancel template)
    - mobile/lib/shared/confirm_dialog.dart (FULL — showDialog + AlertDialog template)
    - mobile/lib/features/billing/billing_providers.dart (Plan 10 — Notifiers)
    - mobile/lib/features/billing/billing_models.dart (Plan 10 — Pack DTO)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"Mobile" sections — full templates including showInsufficientCreditsModal)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_topup_screen_renders_5_packs_when_loaded
    - test_topup_screen_shows_loading_indicator_while_packs_load
    - test_topup_screen_shows_error_when_packs_load_fails
    - test_pack_picker_calls_onSelect_with_pack_id_on_tap
    - test_insufficient_credits_modal_is_barrier_dismissible_false
    - test_insufficient_credits_modal_top_up_cta_pushes_to_billing_topup_route
    - test_insufficient_credits_modal_later_cta_dismisses
    - test_topup_inflight_widget_shows_mm_ss_timer
  </behavior>
  <action>
**File 1 — `mobile/lib/features/billing/insufficient_credits_modal.dart`:**

```dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

Future<void> showInsufficientCreditsModal(BuildContext context) async {
  await showDialog<void>(
    context: context,
    barrierDismissible: false,            // BLOCKING per D-21
    builder: (ctx) => AlertDialog(
      title: const Text('Out of credits'),
      content: const Text('Top up your balance to keep chatting.'),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text('Later'),
        ),
        FilledButton(
          onPressed: () {
            Navigator.of(ctx).pop();
            ctx.push('/billing/topup');
          },
          child: const Text('Top up'),
        ),
      ],
    ),
  );
}
```

**File 2 — `mobile/lib/features/billing/pack_picker_widget.dart`:**

```dart
import 'package:flutter/material.dart';
import 'billing_models.dart';

class PackPickerWidget extends StatelessWidget {
  const PackPickerWidget({
    super.key,
    required this.packs,
    required this.onSelect,
  });

  final List<Pack> packs;
  final ValueChanged<Pack> onSelect;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: packs
          .map((p) => Card(
                margin: const EdgeInsets.symmetric(vertical: 4),
                child: InkWell(
                  onTap: () => onSelect(p),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(p.label, style: Theme.of(context).textTheme.titleMedium),
                        Text('${p.creditCents} credits',
                            style: Theme.of(context).textTheme.bodyMedium),
                      ],
                    ),
                  ),
                ),
              ))
          .toList(growable: false),
    );
  }
}
```

**File 3 — `mobile/lib/features/billing/topup_inflight_widget.dart`:** Lift `deploy_step.dart:387-444` shape verbatim, adapt to billing copy ("Confirming top-up…"). Include `_formatElapsed` helper:

```dart
import 'dart:async';
import 'package:flutter/material.dart';

class TopUpInflightWidget extends StatefulWidget {
  const TopUpInflightWidget({super.key, required this.onCancel});
  final VoidCallback onCancel;

  @override
  State<TopUpInflightWidget> createState() => _TopUpInflightWidgetState();
}

class _TopUpInflightWidgetState extends State<TopUpInflightWidget> {
  Stopwatch? _elapsed;
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _elapsed = Stopwatch()..start();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _tick?.cancel();
    _elapsed?.stop();
    super.dispose();
  }

  String _formatElapsed() {
    final secs = _elapsed?.elapsed.inSeconds ?? 0;
    final mm = (secs ~/ 60).toString().padLeft(2, '0');
    final ss = (secs % 60).toString().padLeft(2, '0');
    return '$mm:$ss';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(border: Border.all(color: Colors.grey)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              SizedBox(width: 24, height: 24,
                  child: CircularProgressIndicator(strokeWidth: 2)),
              SizedBox(width: 8),
              Expanded(child: Text('Confirming top-up…')),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(_formatElapsed(), style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
              TextButton(onPressed: widget.onCancel, child: const Text('Cancel')),
            ],
          ),
        ],
      ),
    );
  }
}
```

**File 4 — `mobile/lib/features/billing/topup_screen.dart`:** Wires the picker + Checkout launch + post-Checkout polling.

```dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';

import '../../core/api/api_client.dart';
import 'billing_models.dart';
import 'billing_providers.dart';
import 'pack_picker_widget.dart';
import 'topup_inflight_widget.dart';
import 'checkout_webview_screen.dart';

class TopUpScreen extends ConsumerStatefulWidget {
  const TopUpScreen({super.key});
  @override
  ConsumerState<TopUpScreen> createState() => _TopUpScreenState();
}

enum _TopUpState { picking, awaitingCheckout, awaitingWebhook }

class _TopUpScreenState extends ConsumerState<TopUpScreen> {
  _TopUpState _state = _TopUpState.picking;
  int? _baselineBalanceCents;

  Future<void> _onPackSelected(Pack pack) async {
    setState(() => _state = _TopUpState.awaitingCheckout);
    final api = ref.read(apiClientProvider);
    final r = await api.createPackCheckoutSession(packId: pack.id);
    if (!mounted) return;
    if (r case Err(:final error)) {
      setState(() => _state = _TopUpState.picking);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to start checkout: ${error.message}')),
      );
      return;
    }
    if (r case Ok(:final value)) {
      // Capture baseline balance for polling.
      final bal = ref.read(balanceNotifierProvider).value;
      _baselineBalanceCents = bal?.balanceCents ?? 0;
      // Push the webview.
      final result = await Navigator.of(context).push<PaymentResult>(
        MaterialPageRoute(builder: (_) => CheckoutWebViewScreen(checkoutUrl: value)),
      );
      if (!mounted) return;
      if (result == PaymentResult.success) {
        setState(() => _state = _TopUpState.awaitingWebhook);
        await _pollUntilTopupReflected();
      } else {
        setState(() => _state = _TopUpState.picking);
      }
    }
  }

  Future<void> _pollUntilTopupReflected() async {
    final start = DateTime.now();
    while (mounted && DateTime.now().difference(start).inSeconds < 30) {
      await Future<void>.delayed(const Duration(seconds: 2));
      ref.invalidate(balanceNotifierProvider);
      try {
        final fresh = await ref.read(balanceNotifierProvider.future);
        if (fresh.balanceCents > (_baselineBalanceCents ?? 0)) {
          if (!mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Top-up confirmed!')),
          );
          context.pop();
          return;
        }
      } catch (_) {
        // ignore transient errors and retry
      }
    }
    if (!mounted) return;
    setState(() => _state = _TopUpState.picking);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Top-up is taking longer than expected. Pull to refresh later.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final packs = ref.watch(packsNotifierProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Top up')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: switch (_state) {
          _TopUpState.awaitingWebhook =>
              TopUpInflightWidget(onCancel: () => setState(() => _state = _TopUpState.picking)),
          _ => packs.when(
                data: (list) => PackPickerWidget(
                  packs: list,
                  onSelect: _state == _TopUpState.picking ? _onPackSelected : (_) {},
                ),
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(child: Text('Failed to load packs: $e')),
              ),
        },
      ),
    );
  }
}
```

**File 5 — `mobile/test/features/billing/topup_screen_test.dart`:** Widget tests using `ProviderContainer` + `tester.pumpWidget`. Mock the `packsNotifierProvider` with `overrideWith(...)`. Cover the 4 topup-screen behaviors.

**File 6 — `mobile/test/features/billing/insufficient_credits_modal_test.dart`:** Widget tests that `tester.pumpWidget` a host with a Button → tap → `showInsufficientCreditsModal(...)`. Assert: barrier tap does NOT dismiss; "Later" button dismisses; "Top up" button calls `ctx.push('/billing/topup')` (mock GoRouter).
  </action>
  <verify>
    <automated>cd mobile &amp;&amp; flutter test test/features/billing/topup_screen_test.dart test/features/billing/insufficient_credits_modal_test.dart</automated>
  </verify>
  <done>
- All 8 widget tests pass.
- `grep -c 'barrierDismissible: false' mobile/lib/features/billing/insufficient_credits_modal.dart` ≥ 1.
- `grep -c "ctx.push('/billing/topup')" mobile/lib/features/billing/insufficient_credits_modal.dart` ≥ 1.
- `grep -c 'Stopwatch\|Timer.periodic' mobile/lib/features/billing/topup_inflight_widget.dart` ≥ 2.
- Stub TopUpScreen in app_router.dart (Plan 10 stub) replaced with real import — search for `// PHASE_B_STUB` comments and confirm they're removed for TopUpScreen + TransactionsScreen + CheckoutWebViewScreen.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: CheckoutWebViewScreen + TransactionsScreen + tests</name>
  <files>mobile/lib/features/billing/checkout_webview_screen.dart, mobile/lib/features/billing/transactions_screen.dart, mobile/test/features/billing/checkout_webview_screen_test.dart, mobile/test/features/billing/transactions_screen_test.dart, mobile/lib/core/router/app_router.dart</files>
  <read_first>
    - mobile/integration_test/spike_e_inappwebview_intercept.dart (Wave 0 — exact shouldOverrideUrlLoading callback signature)
    - .planning/phases/B-stripe-paywall/B-stripe-RESEARCH.md (§Example D — full template)
    - .planning/phases/B-stripe-paywall/B-stripe-PATTERNS.md (§"Mobile: features/billing/checkout_webview_screen.dart" + §"Mobile: features/billing/transactions_screen.dart")
    - mobile/lib/features/billing/billing_providers.dart (Plan 10 — TransactionsNotifier + loadMore)
    - mobile/lib/features/usage/agent_usage_screen.dart (RefreshIndicator + ListView pattern)
  </read_first>
  <behavior>
    Tests written FIRST:
    - test_checkout_webview_loads_url_on_init
    - test_checkout_webview_intercepts_success_url_pops_with_success_result
    - test_checkout_webview_intercepts_cancel_url_pops_with_cancelled_result
    - test_checkout_webview_allows_navigation_to_other_urls
    - test_transactions_screen_renders_list_from_provider
    - test_transactions_screen_load_more_appends_to_list
    - test_transactions_screen_renders_negative_amount_for_debit_kind
  </behavior>
  <action>
**File 1 — `mobile/lib/features/billing/checkout_webview_screen.dart`:**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

enum PaymentResult { success, cancelled }

class CheckoutWebViewScreen extends StatefulWidget {
  const CheckoutWebViewScreen({super.key, required this.checkoutUrl});
  final String checkoutUrl;

  @override
  State<CheckoutWebViewScreen> createState() => _CheckoutWebViewScreenState();
}

class _CheckoutWebViewScreenState extends State<CheckoutWebViewScreen> {
  // Webview-internal sentinel URL pattern (RESEARCH Open Q #2 — no AppLinks/UniversalLinks needed).
  static const String _expectedHost = 'app.solvrlabs.com';
  static const String _successPath = '/billing/return-success';
  static const String _cancelPath = '/billing/return-cancel';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Checkout')),
      body: InAppWebView(
        initialUrlRequest: URLRequest(url: WebUri(widget.checkoutUrl)),
        shouldOverrideUrlLoading: (controller, action) async {
          final uri = action.request.url;
          if (uri == null) return NavigationActionPolicy.ALLOW;
          if (uri.host == _expectedHost && uri.path == _successPath) {
            if (mounted) Navigator.of(context).pop(PaymentResult.success);
            return NavigationActionPolicy.CANCEL;
          }
          if (uri.host == _expectedHost && uri.path == _cancelPath) {
            if (mounted) Navigator.of(context).pop(PaymentResult.cancelled);
            return NavigationActionPolicy.CANCEL;
          }
          return NavigationActionPolicy.ALLOW;
        },
      ),
    );
  }
}
```

**File 2 — `mobile/lib/features/billing/transactions_screen.dart`:**

```dart
import 'package:flutter/material.dart';
import 'package:hooks_riverpod/hooks_riverpod.dart';

import 'billing_models.dart';
import 'billing_providers.dart';

class TransactionsScreen extends ConsumerWidget {
  const TransactionsScreen({super.key});

  String _formatAmount(int cents) {
    final sign = cents < 0 ? '-' : '+';
    final dollars = (cents.abs() / 100).toStringAsFixed(2);
    return '$sign\$$dollars';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(transactionsNotifierProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Transactions')),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(transactionsNotifierProvider.future),
        child: async.when(
          data: (page) => NotificationListener<ScrollNotification>(
            onNotification: (n) {
              if (n is ScrollEndNotification &&
                  n.metrics.extentAfter == 0 &&
                  page.nextBefore != null) {
                ref.read(transactionsNotifierProvider.notifier).loadMore();
              }
              return false;
            },
            child: ListView.separated(
              physics: const AlwaysScrollableScrollPhysics(),
              itemCount: page.transactions.length,
              separatorBuilder: (_, __) => const Divider(height: 0),
              itemBuilder: (context, i) {
                final tx = page.transactions[i];
                return ListTile(
                  title: Text(tx.kind),
                  subtitle: Text(tx.createdAt.toLocal().toString()),
                  trailing: Text(_formatAmount(tx.amountCents),
                      style: Theme.of(context).textTheme.titleMedium),
                );
              },
            ),
          ),
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('Failed to load: $e')),
        ),
      ),
    );
  }
}
```

**File 3 — `mobile/lib/core/router/app_router.dart`:** Remove the `// PHASE_B_STUB` stubs added in Plan 10. Replace with proper imports + the routes already defined now point to real screens.

**File 4 — `mobile/test/features/billing/checkout_webview_screen_test.dart`:** Use the patterns from `mobile/integration_test/spike_e_inappwebview_intercept.dart`. The webview can't be fully tested in `flutter test` (needs a device); the unit test asserts:
- The widget builds with the URL.
- The shouldOverrideUrlLoading callback returns CANCEL for success_url + cancels with PaymentResult.success on Navigator.pop.

For the unit-testable part, factor out the URL-classification logic into a pure function `_classifyNavigation(uri) -> NavigationAction` and unit-test that. The integration test for the actual webview lives in Plan 12 (the human-verify checkpoint).

**File 5 — `mobile/test/features/billing/transactions_screen_test.dart`:** Mock TransactionsNotifier with overrideWith. Cover the 3 transaction-screen behaviors.
  </action>
  <verify>
    <automated>cd mobile &amp;&amp; flutter test test/features/billing/checkout_webview_screen_test.dart test/features/billing/transactions_screen_test.dart</automated>
  </verify>
  <done>
- All 7 widget tests pass.
- `grep -c 'shouldOverrideUrlLoading' mobile/lib/features/billing/checkout_webview_screen.dart` ≥ 1.
- `grep -c '/billing/return-success\|/billing/return-cancel' mobile/lib/features/billing/checkout_webview_screen.dart` ≥ 2.
- All 3 stub widgets in app_router.dart are removed (replaced with real imports).
- `cd mobile && flutter analyze` clean.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Manual UAT — Stripe Checkout webview against real Stripe TEST mode</name>
  <what-built>
- TopUpScreen + PackPickerWidget that fetches packs from /v1/billing/packs.
- CheckoutWebViewScreen using flutter_inappwebview with shouldOverrideUrlLoading interception.
- TransactionsScreen with paginated load-more.
- InsufficientCreditsModal blocking dialog.
- TopUpInflightWidget mm:ss timer.
  </what-built>
  <how-to-verify>
On a real iOS or Android device (or simulator with credentials configured):
1. Confirm deploy stack is up: `docker compose -f deploy/docker-compose.prod.yml ps` shows api_server + temporal-worker + postgres + temporal alive.
2. Confirm Stripe TEST keys are in `deploy/.env.prod` (AP_STRIPE_API_KEY=sk_test_..., AP_STRIPE_WEBHOOK_SECRET=whsec_...).
3. Run mobile against the deploy stack: `set -a; source .env; set +a; cd mobile && make ios DEVICE=<id> BASE_URL=http://localhost:8000`.
4. Sign in with a test Google account.
5. Navigate to `/billing/topup` (via deep link or temporary shortcut button — executor adds a temp button if no nav exists yet).
6. Tap the $5 pack → expect Stripe Checkout to load in an in-app webview.
7. Use Stripe TEST card: `4242 4242 4242 4242`, expiry any future date, CVC any 3 digits, ZIP any 5 digits.
8. Submit the payment.
9. Expect: webview pops automatically (interception fired); spinner+timer appears (`Confirming top-up…`); within 5-30s the SnackBar shows "Top-up confirmed!" and the screen pops.
10. Navigate to `/billing/transactions` → expect a `topup` row of +$5.00.
11. Send a chat message → expect the response goes through (balance now > 0, ultra tier).
12. Send chat messages until balance < 1¢ → next message → expect 402 → expect blocking modal "Out of credits" → tap "Top up" → expect routing to `/billing/topup`.

Document each step's PASS/FAIL in `B-stripe-11-UAT-LOG.md` (executor creates this file inline as evidence).
  </how-to-verify>
  <resume-signal>Type "approved — webview UX works end-to-end on iOS|Android" or describe specific failure.</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Mobile InAppWebView → Stripe Checkout | external HTTPS; no AP secrets cross this boundary |
| InAppWebView ← redirect URL | shouldOverrideUrlLoading inspects each navigation; only the host+path match triggers pop |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-B-DEEP | Spoofing | checkout_webview_screen.dart shouldOverrideUrlLoading | mitigate | only `host == 'app.solvrlabs.com'` AND specific paths trigger a pop; arbitrary URLs route through ALLOW |
| T-B-WV | Tampering | InAppWebView session state | accept | webview is created fresh per Checkout; no persistent cookies that the next user could inherit |
| T-B-MOD | EoP | insufficient_credits_modal.dart | accept | modal is dismissable via "Later" but the underlying chat is still 402-blocked at api_server; client-side bypass has no effect |
| T-B-NEG | InfoDisclosure | transactions_screen.dart | accept | negative amounts shown as `-$X.XX`; user can see refund debits clearly. Per Pitfall 6, the AppBar ticker handles negative balance with the `is_negative` flag separately. |
</threat_model>

<verification>
- 15 mobile widget tests pass.
- Manual UAT (Task 3) approved by user with PASS log.
- All 3 stubs from Plan 10 replaced with real screens.
</verification>

<success_criteria>
- `cd mobile && flutter test test/features/billing/` all green.
- `cd mobile && flutter analyze` clean.
- Manual UAT log committed.
</success_criteria>

<output>
After completion, create `.planning/phases/B-stripe-paywall/B-stripe-11-SUMMARY.md` documenting screens + the manual UAT outcome.
</output>
