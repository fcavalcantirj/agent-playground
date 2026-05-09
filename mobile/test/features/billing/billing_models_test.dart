// Phase B Plan 10 Task 1 — Billing DTO unit tests.
//
// Hand-written fromJson per Phase 24 D-34 (no json_serializable codegen).
// Defensive defaults on missing optional/int fields. Mirrors the tests in
// test/features/usage/usage_providers_test.dart (UsageSummary.fromJson
// defensive parsing group).
//
// Server JSON contract — see api_server/src/api_server/routes/billing.py
// (Plans 03 + 05). PackEntry intentionally omits stripe_price_id (T-B-PRC).

import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Pack.fromJson', () {
    test('parses complete object', () {
      final p = Pack.fromJson({
        'id': 'pack_25',
        'label': r'$25',
        'usd_amount_cents': 2500,
        'credit_cents': 2500,
      });
      expect(p.id, 'pack_25');
      expect(p.label, r'$25');
      expect(p.usdAmountCents, 2500);
      expect(p.creditCents, 2500);
    });

    test('handles missing int fields with defaults', () {
      // Defensive on additive backend fields (D-34 contract).
      final p = Pack.fromJson({'id': 'pack_5', 'label': r'$5'});
      expect(p.usdAmountCents, 0);
      expect(p.creditCents, 0);
    });
  });

  group('Balance.fromJson', () {
    test('parses positive balance', () {
      final b = Balance.fromJson({
        'tier': 'ultra',
        'balance_cents': 4500,
        'display_balance_cents': 4500,
        'is_negative': false,
      });
      expect(b.tier, 'ultra');
      expect(b.balanceCents, 4500);
      expect(b.displayBalanceCents, 4500);
      expect(b.isNegative, false);
    });

    test('parses negative balance (D-16 refund-driven negative)', () {
      // Pitfall 6 / D-16 — display clamps to 0 while raw stays negative,
      // is_negative flags the underlying ledger truth.
      final b = Balance.fromJson({
        'tier': 'ultra',
        'balance_cents': -250,
        'display_balance_cents': 0,
        'is_negative': true,
      });
      expect(b.balanceCents, -250);
      expect(b.displayBalanceCents, 0);
      expect(b.isNegative, true);
    });

    test('handles missing fields with defensive defaults', () {
      final b = Balance.fromJson({});
      expect(b.tier, 'free');
      expect(b.balanceCents, 0);
      expect(b.displayBalanceCents, 0);
      expect(b.isNegative, false);
    });
  });

  group('Transaction.fromJson', () {
    test('parses topup row with complete object', () {
      final t = Transaction.fromJson({
        'id': '11111111-1111-1111-1111-111111111111',
        'kind': 'topup',
        'amount_cents': 2500,
        'reference_id': 'cs_test_abc',
        'reference_type': 'stripe_checkout_session',
        'created_at': '2026-05-08T10:00:00Z',
      });
      expect(t.id, '11111111-1111-1111-1111-111111111111');
      expect(t.kind, 'topup');
      expect(t.amountCents, 2500);
      expect(t.referenceId, 'cs_test_abc');
      expect(t.referenceType, 'stripe_checkout_session');
      expect(t.createdAt, DateTime.utc(2026, 5, 8, 10, 0, 0));
    });

    test('handles null reference fields (e.g. admin_writeoff)', () {
      final t = Transaction.fromJson({
        'id': '22222222-2222-2222-2222-222222222222',
        'kind': 'admin_writeoff',
        'amount_cents': 100,
        'created_at': '2026-05-08T10:00:00Z',
      });
      expect(t.referenceId, isNull);
      expect(t.referenceType, isNull);
    });

    test('debit row carries negative amount', () {
      final t = Transaction.fromJson({
        'id': '33333333-3333-3333-3333-333333333333',
        'kind': 'debit',
        'amount_cents': -34,
        'reference_id': '44444444-4444-4444-4444-444444444444',
        'reference_type': 'usage_log',
        'created_at': '2026-05-08T10:00:00Z',
      });
      expect(t.kind, 'debit');
      expect(t.amountCents, -34);
    });
  });

  group('TransactionsPage.fromJson', () {
    test('parses page with next_before cursor', () {
      final page = TransactionsPage.fromJson({
        'transactions': [
          {
            'id': '11111111-1111-1111-1111-111111111111',
            'kind': 'topup',
            'amount_cents': 2500,
            'reference_id': 'cs_test_abc',
            'reference_type': 'stripe_checkout_session',
            'created_at': '2026-05-08T10:00:00Z',
          },
          {
            'id': '22222222-2222-2222-2222-222222222222',
            'kind': 'debit',
            'amount_cents': -34,
            'reference_id': '44444444-4444-4444-4444-444444444444',
            'reference_type': 'usage_log',
            'created_at': '2026-05-08T09:00:00Z',
          },
        ],
        'next_before': '2026-05-08T09:00:00Z',
      });
      expect(page.transactions, hasLength(2));
      expect(page.nextBefore, DateTime.utc(2026, 5, 8, 9, 0, 0));
    });

    test('parses last page (no next_before)', () {
      final page = TransactionsPage.fromJson({
        'transactions': [
          {
            'id': '11111111-1111-1111-1111-111111111111',
            'kind': 'topup',
            'amount_cents': 2500,
            'created_at': '2026-05-08T10:00:00Z',
          },
        ],
      });
      expect(page.transactions, hasLength(1));
      expect(page.nextBefore, isNull);
    });

    test('handles missing transactions array (defensive default)', () {
      final page = TransactionsPage.fromJson({});
      expect(page.transactions, isEmpty);
      expect(page.nextBefore, isNull);
    });
  });
}
