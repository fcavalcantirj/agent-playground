# Phase B Plan 11 — Manual UAT Log

**Status:** PENDING (auto-mode auto-approved — real device verification owed before Plan 11 is "shipped" in the user-facing sense)

**What was auto-approved:** automated coverage on the unit + widget surface (36/36 green) is sufficient to merge the code; the integration smoke (real Stripe TEST mode + real iPhone simulator) cannot run in the executor environment because (a) the simulator is not booted, (b) `make ios` requires sourcing `.env` interactively, and (c) Stripe TEST cards must be entered by hand on the webview.

**Auto-mode log line:** `⚡ Auto-approved: B-stripe-11 manual UAT (iPhone sim Stripe TEST flow)`

---

## What this plan ships

- `TopUpScreen` (lib/features/billing/topup_screen.dart) — pack picker + post-Checkout balance polling.
- `PackPickerWidget` (lib/features/billing/pack_picker_widget.dart) — 5-card column.
- `TopUpInflightWidget` (lib/features/billing/topup_inflight_widget.dart) — Stopwatch + Timer.periodic + mm:ss + Cancel.
- `CheckoutWebViewScreen` (lib/features/billing/checkout_webview_screen.dart) — InAppWebView + `shouldOverrideUrlLoading` + `classifyNavigationForResult` pure helper.
- `InsufficientCreditsModal` (lib/features/billing/insufficient_credits_modal.dart) — BLOCKING AlertDialog (`barrierDismissible: false`) with Top-up CTA.
- `TransactionsScreen` (lib/features/billing/transactions_screen.dart) — paginated ledger history with infinite scroll.
- `_stubs.dart` deleted — Plan 10's PHASE_B_STUB scaffolding is now fully replaced.
- `app_router.dart` — 3 routes wired to real screens.

## What CANNOT be verified by `flutter test`

The InAppWebView's platform channel does not initialize in `flutter test`'s host
binding. The 3 spike-validated mobile-novel surfaces below need a real device or
simulator + the deploy stack at `localhost:8000` + Stripe TEST keys + a Stripe
TEST card to confirm:

1. **Webview navigation interception** — the live `https://checkout.stripe.com/c/...`
   redirect to `https://app.solvrlabs.com/billing/return-success` actually fires the
   `shouldOverrideUrlLoading` callback (the unit test exercises only the pure
   `classifyNavigationForResult` helper).
2. **Post-Checkout balance polling** — the Stripe webhook latency (5–15s typical) is
   bridged correctly by the 30s polling budget; the SnackBar "Top-up confirmed!"
   fires when the balance bumps.
3. **402 → blocking modal flow** — sending a chat after balance hits 0 produces a 402
   `INSUFFICIENT_BALANCE` from the api_server, the chat path catches it, and
   `showInsufficientCreditsModal` opens.

## Manual UAT steps (run when an iPhone simulator is available)

1. **Confirm deploy stack is up** —
   ```
   docker compose -f deploy/docker-compose.prod.yml ps
   ```
   should show `api_server`, `temporal-worker`, `postgres`, `temporal` all healthy.

2. **Confirm Stripe TEST keys are in `deploy/.env.prod`** —
   ```
   grep -c '^AP_STRIPE_API_KEY=sk_test_' deploy/.env.prod   # expect 1
   grep -c '^AP_STRIPE_WEBHOOK_SECRET=whsec_' deploy/.env.prod   # expect 1
   ```

3. **Boot mobile against the deploy stack** —
   ```
   set -a; source .env; set +a
   cd mobile && make ios DEVICE=<sim-id> BASE_URL=http://localhost:8000
   ```

4. **Sign in** with a test Google account.

5. **Navigate to `/billing/topup`** — via deep link (`xcrun simctl openurl booted "solvrlabs://billing/topup"`) or temporary nav button if the dashboard does not yet expose it. **PENDING.**

6. **Tap the $5 pack** → expect Stripe Checkout to load in an in-app webview. **PENDING.**

7. **Use Stripe TEST card** `4242 4242 4242 4242`, expiry any future date, CVC any 3 digits, ZIP any 5 digits. **PENDING.**

8. **Submit the payment.** **PENDING.**

9. **Expect**: webview pops automatically (interception fired); spinner+timer appears (`Confirming top-up…`); within 5–30s the SnackBar shows "Top-up confirmed!" and the screen pops. **PENDING.**

10. **Navigate to `/billing/transactions`** → expect a `topup` row of `+$5.00`. **PENDING.**

11. **Send a chat message** → expect the response goes through (balance now > 0, ultra tier). **PENDING — gated by Plan 12 ticker work AND Plan 13 chat 402 wiring; not strictly Plan 11.**

12. **Send chat messages until balance < 1¢** → next message → expect 402 → expect blocking modal "Out of credits" → tap "Top up" → expect routing to `/billing/topup`. **PENDING — gated by the chat surface invoking `showInsufficientCreditsModal` on 402; that wiring is Plan 13.**

## Closure

When the deploy stack + simulator + Stripe TEST card combination is available, run
steps 5–10 (the steps that fall strictly inside Plan 11's surface) and edit the
`PENDING` markers to `PASS`/`FAIL`. Plan 11's "manual UAT closed" gate is steps 5–10;
steps 11–12 belong to downstream plans.
