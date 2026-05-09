// Phase B Plan 10 Task 2 — Riverpod billing providers tests.
//
// Mirrors mobile/test/features/usage/usage_providers_test.dart shape:
// real Dio + http_mock_adapter at the transport seam, ProviderContainer
// with `apiClientProvider.overrideWith` swapping in the mocked client.
// Lifecycle resume → invalidateSelf is verified at unit level by
// reading the source's ref.listen wiring; the widget-level lifecycle
// trip belongs to Plan 11.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:agent_playground/features/billing/billing_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

class _Harness {
  _Harness() {
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    adapter = DioAdapter(dio: dio);
    api = ApiClient(dio);
    container = ProviderContainer(
      overrides: [apiClientProvider.overrideWith((ref) => api)],
    );
  }
  late final Dio dio;
  late final DioAdapter adapter;
  late final ApiClient api;
  late final ProviderContainer container;

  void dispose() => container.dispose();
}

void main() {
  group('packsNotifierProvider', () {
    test('loads 5 packs via api client', () async {
      final h = _Harness();
      addTearDown(h.dispose);
      h.adapter.onGet(
        '/v1/billing/packs',
        (s) => s.reply(200, {
          'packs': [
            {
              'id': 'pack_5',
              'label': r'$5',
              'usd_amount_cents': 500,
              'credit_cents': 500,
            },
            {
              'id': 'pack_10',
              'label': r'$10',
              'usd_amount_cents': 1000,
              'credit_cents': 1000,
            },
            {
              'id': 'pack_25',
              'label': r'$25',
              'usd_amount_cents': 2500,
              'credit_cents': 2500,
            },
            {
              'id': 'pack_50',
              'label': r'$50',
              'usd_amount_cents': 5000,
              'credit_cents': 5000,
            },
            {
              'id': 'pack_100',
              'label': r'$100',
              'usd_amount_cents': 10000,
              'credit_cents': 10000,
            },
          ],
        }),
      );
      final packs = await h.container.read(packsNotifierProvider.future);
      expect(packs, hasLength(5));
      expect(packs.first.id, 'pack_5');
      expect(packs.first.usdAmountCents, 500);
      expect(packs.last.id, 'pack_100');
      expect(packs.last.creditCents, 10000);
    });

    test('throws ApiError when server returns 401', () async {
      final h = _Harness();
      addTearDown(h.dispose);
      h.adapter.onGet(
        '/v1/billing/packs',
        (s) => s.reply(401, {
          'error': {
            'type': 'unauthorized',
            'code': 'UNAUTHORIZED',
            'message': 'Authentication required',
            'request_id': 'req-401',
          },
        }),
      );
      // ignore: only_throw_errors
      await expectLater(
        h.container.read(packsNotifierProvider.future),
        throwsA(isA<ApiError>()),
      );
    });
  });

  group('balanceNotifierProvider', () {
    test('loads balance for ultra tier', () async {
      final h = _Harness();
      addTearDown(h.dispose);
      h.adapter.onGet(
        '/v1/billing/balance',
        (s) => s.reply(200, {
          'tier': 'ultra',
          'balance_cents': 4500,
          'display_balance_cents': 4500,
          'is_negative': false,
        }),
      );
      final b = await h.container.read(balanceNotifierProvider.future);
      expect(b.tier, 'ultra');
      expect(b.balanceCents, 4500);
      expect(b.isNegative, false);
    });

    test('handles negative balance (D-16 refund overdraft)', () async {
      final h = _Harness();
      addTearDown(h.dispose);
      h.adapter.onGet(
        '/v1/billing/balance',
        (s) => s.reply(200, {
          'tier': 'ultra',
          'balance_cents': -250,
          'display_balance_cents': 0,
          'is_negative': true,
        }),
      );
      final b = await h.container.read(balanceNotifierProvider.future);
      expect(b.balanceCents, -250);
      expect(b.displayBalanceCents, 0);
      expect(b.isNegative, true);
    });
  });

  group('transactionsNotifierProvider', () {
    test('loads first page of transactions', () async {
      final h = _Harness();
      addTearDown(h.dispose);
      h.adapter.onGet(
        '/v1/billing/transactions',
        (s) => s.reply(200, {
          'transactions': [
            {
              'id': '11111111-1111-1111-1111-111111111111',
              'kind': 'topup',
              'amount_cents': 2500,
              'reference_id': 'cs_test_abc',
              'reference_type': 'stripe_checkout_session',
              'created_at': '2026-05-08T10:00:00Z',
            },
          ],
          'next_before': '2026-05-08T09:00:00Z',
        }),
        queryParameters: {'limit': 50},
      );
      final page =
          await h.container.read(transactionsNotifierProvider.future);
      expect(page.transactions, hasLength(1));
      expect(page.transactions.first.kind, 'topup');
      expect(page.nextBefore, DateTime.utc(2026, 5, 8, 9, 0, 0));
    });

    test('loadMore appends next page using cursor', () async {
      final h = _Harness();
      addTearDown(h.dispose);
      // Page 1.
      h.adapter.onGet(
        '/v1/billing/transactions',
        (s) => s.reply(200, {
          'transactions': [
            {
              'id': '11111111-1111-1111-1111-111111111111',
              'kind': 'topup',
              'amount_cents': 2500,
              'created_at': '2026-05-08T10:00:00Z',
            },
          ],
          'next_before': '2026-05-08T09:00:00Z',
        }),
        queryParameters: {'limit': 50},
      );
      final firstPage =
          await h.container.read(transactionsNotifierProvider.future);
      expect(firstPage.transactions, hasLength(1));

      // Page 2 — same path but with `before` cursor.
      h.adapter.onGet(
        '/v1/billing/transactions',
        (s) => s.reply(200, {
          'transactions': [
            {
              'id': '22222222-2222-2222-2222-222222222222',
              'kind': 'debit',
              'amount_cents': -34,
              'reference_id': '33333333-3333-3333-3333-333333333333',
              'reference_type': 'usage_log',
              'created_at': '2026-05-08T08:00:00Z',
            },
          ],
        }),
        queryParameters: {
          'limit': 50,
          'before': '2026-05-08T09:00:00.000Z',
        },
      );

      await h.container
          .read(transactionsNotifierProvider.notifier)
          .loadMore();
      final merged = h.container.read(transactionsNotifierProvider).value!;
      expect(merged.transactions, hasLength(2));
      expect(merged.transactions[0].kind, 'topup');
      expect(merged.transactions[1].kind, 'debit');
      expect(merged.nextBefore, isNull); // last page
    });

    test('loadMore is no-op when nextBefore is null', () async {
      final h = _Harness();
      addTearDown(h.dispose);
      h.adapter.onGet(
        '/v1/billing/transactions',
        (s) => s.reply(200, {
          'transactions': [
            {
              'id': '11111111-1111-1111-1111-111111111111',
              'kind': 'topup',
              'amount_cents': 2500,
              'created_at': '2026-05-08T10:00:00Z',
            },
          ],
        }),
        queryParameters: {'limit': 50},
      );
      await h.container.read(transactionsNotifierProvider.future);
      // No expectation registered for a 2nd request → if loadMore tried
      // to fetch, http_mock_adapter would throw.
      await h.container
          .read(transactionsNotifierProvider.notifier)
          .loadMore();
      final state = h.container.read(transactionsNotifierProvider).value!;
      expect(state.transactions, hasLength(1));
    });
  });

  group('billing models smoke (defensive parsing surfaces here too)', () {
    test('Pack.fromJson defensively defaults missing int fields', () {
      final p = Pack.fromJson({'id': 'pack_x', 'label': r'$X'});
      expect(p.usdAmountCents, 0);
      expect(p.creditCents, 0);
    });
  });
}
