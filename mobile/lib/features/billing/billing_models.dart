// Phase B Plan 10 — Billing DTOs (Wave 5 mobile substrate).
//
// Mirrors the FastAPI response models in
// api_server/src/api_server/routes/billing.py (Plans 03 + 05).
// PackEntry intentionally OMITS stripe_price_id server-side per T-B-PRC
// (Stripe Price ids stay server-side; mobile invokes POST /billing/checkout
// with the pack id only).
//
// Hand-written fromJson per Phase 24 D-34 (codegen restricted to
// riverpod_generator only — no json_serializable / build_runner JSON
// codegen). Defensive on additive backend fields: missing keys yield
// sane defaults (0 / 'free' / null) rather than crashing — mirrors
// features/usage/usage_models.dart exactly.

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

  /// Stable pack id (e.g. `pack_5`, `pack_25`). The mobile client passes
  /// this back in POST /v1/billing/checkout — server resolves to the
  /// matching `stripe_price_id` from the single SOT in api_server.
  final String id;

  /// Human-readable label (e.g. `$25`).
  final String label;

  /// Pack price in USD cents (server-side single source of truth).
  final int usdAmountCents;

  /// Credits granted on top-up. D-07: 1:1 with usdAmountCents — markup
  /// lives only on the debit side via `cost_weights.ap_multiplier`.
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

  /// One of `free | pro | ultra` per D-01. UI branches on this for the
  /// AppBar ticker (Plan 12) — `ultra` shows `formatCredits(balanceCents)`,
  /// the other tiers fall back to the BYOK USD ticker (Phase 27).
  final String tier;

  /// Raw ledger balance in cents (can be negative when D-16 refund
  /// drives the row below zero). Mobile uses [displayBalanceCents] for
  /// rendering; this field carries the underlying ledger truth.
  final int balanceCents;

  /// Display-clamped balance: `max(balance_cents, 0)` server-side.
  /// Pitfall 6 — show `$0` to the user while [isNegative] flags the
  /// underlying overdraft for the warning badge.
  final int displayBalanceCents;

  /// True when [balanceCents] is negative — D-16 refund-driven overdraft.
  /// Mobile shows a `$0 ⚠` warning badge in the ticker until admin
  /// write-off rebalances the row.
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

  /// Server-issued ledger row uuid.
  final String id;

  /// One of `topup | debit | refund | tier_change | admin_writeoff`
  /// per the migration 014 CHECK constraint (D-26).
  final String kind;

  /// Signed cents — positive for credits / topups / writeoffs,
  /// negative for debits / refunds.
  final int amountCents;

  /// Optional cross-reference (Stripe checkout session id, usage_log id,
  /// stripe_event id, …). Null for `admin_writeoff` rows.
  final String? referenceId;

  /// Discriminator for [referenceId] (e.g. `stripe_checkout_session`,
  /// `usage_log`, `stripe_event`, `stripe_refund`). Null when
  /// [referenceId] is null.
  final String? referenceType;

  /// Server-side timestamp (asyncpg `TIMESTAMP WITH TIME ZONE`).
  final DateTime createdAt;
}

class TransactionsPage {
  const TransactionsPage({required this.transactions, this.nextBefore});

  factory TransactionsPage.fromJson(Map<String, dynamic> json) =>
      TransactionsPage(
        transactions: ((json['transactions'] as List<dynamic>?) ??
                const <dynamic>[])
            .map((e) => Transaction.fromJson(e as Map<String, dynamic>))
            .toList(growable: false),
        nextBefore: json['next_before'] != null
            ? DateTime.parse(json['next_before'] as String)
            : null,
      );

  final List<Transaction> transactions;

  /// Cursor for the next page. Null on the last page. Mobile passes this
  /// back as the `before` query param to GET /v1/billing/transactions
  /// (server uses strict `created_at < $2` — same-second inserts can't
  /// drift the page boundary, see Plan 03 patterns-established).
  final DateTime? nextBefore;
}
