// Phase B Plan 11 Task 1 — 402 INSUFFICIENT_BALANCE blocking modal (D-21).
//
// Shape mirrors mobile/lib/shared/confirm_dialog.dart (showDialog +
// AlertDialog). EXPLICITLY NOT a RetryBanner: D-21 routes 402 through a
// blocking modal, NOT the Phase 31 H4 transient-SSE banner.
//
// `barrierDismissible: false` — the user must explicitly tap Later or
// Top up; tapping outside the dialog does nothing (per Plan 11
// must_haves.truths line 31).
//
// Top up CTA pops the dialog then `ctx.push('/billing/topup')` so the
// route is back on the stack and the user can tap the system back gesture
// to return to where the 402 fired.

import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Show the blocking "Out of credits" modal. Returns when the modal
/// resolves (either CTA tapped). The Top-up CTA pushes
/// `/billing/topup` onto the GoRouter stack; the Later CTA simply
/// pops the dialog.
///
/// iOS variant (Guideline 3.1.1): the Top-up CTA would route to a Stripe
/// Checkout webview — disallowed for digital purchases on iOS. Until
/// StoreKit IAP ships, iOS users see an informational body explaining
/// that subscription management is web-only, with no purchase-initiating
/// button.
Future<void> showInsufficientCreditsModal(BuildContext context) async {
  final isIOS = !kIsWeb && Platform.isIOS;
  await showDialog<void>(
    context: context,
    barrierDismissible: false, // BLOCKING per D-21
    builder: (ctx) => AlertDialog(
      title: const Text('Out of balance'),
      content: Text(
        isIOS
            ? 'Top up your balance from your account on the web to keep chatting.'
            : 'Top up your balance to keep chatting.',
      ),
      actions: isIOS
          ? [
              FilledButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('OK'),
              ),
            ]
          : [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('Later'),
              ),
              FilledButton(
                onPressed: () {
                  Navigator.of(ctx).pop();
                  // Fire-and-forget — the navigation Future is owned by
                  // GoRouter; the modal closure has nothing meaningful to
                  // await on.
                  unawaited(ctx.push('/billing/topup'));
                },
                child: const Text('Top up'),
              ),
            ],
    ),
  );
}
