// Phase B Plan 10 Task 2 — Riverpod billing providers tests.
//
// Mirrors mobile/test/features/chat/dedup_test.dart shape:
// real Dio + http_mock_adapter at the transport seam, ProviderContainer
// with `apiClientProvider.overrideWithValue` swapping in the mocked client.
// Auto-dispose providers need a `_hold` listener so they stay mounted
// across the awaited gap of `read(provider.future)` — without it
// autoDispose fires its onDispose callback (cancelling the inflight
// CancelToken) before the http_mock_adapter response lands.
//
// Lifecycle resume → invalidateSelf is verified at unit level by reading
// the source's ref.listen wiring; the widget-level lifecycle trip
// belongs to Plan 11.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
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
      overrides: [apiClientProvider.overrideWithValue(api)],
    );
  }
  late final Dio dio;
  late final DioAdapter adapter;
  late final ApiClient api;
  late final ProviderContainer container;

  void dispose() => container.dispose();
}

/// Pin an autoDispose provider mounted across the awaited gap of
/// `read(provider.future)`. Without this the build()-cycle CancelToken
/// is cancelled by the dispose callback before the mocked response
/// lands and we see a spurious `ErrorCode.network/'cancelled'` error.
/// Mirrors the `_hold` pattern in mobile/test/features/chat/dedup_test.dart.
void _holdPacks(ProviderContainer c) {
  final sub = c.listen<AsyncValue<List<Pack>>>(
    packsProvider,
    (_, _) {},
    fireImmediately: true,
  );
  addTearDown(sub.close);
}

void _holdBalance(ProviderContainer c) {
  final sub = c.listen<AsyncValue<Balance>>(
    balanceProvider,
    (_, _) {},
    fireImmediately: true,
  );
  addTearDown(sub.close);
}

void _holdTransactions(ProviderContainer c) {
  final sub = c.listen<AsyncValue<TransactionsPage>>(
    transactionsProvider,
    (_, _) {},
    fireImmediately: true,
  );
  addTearDown(sub.close);
}

void main() {
  group('packsProvider', () {
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
      _holdPacks(h.container);
      final packs = await h.container.read(packsProvider.future);
      expect(packs, hasLength(5));
      expect(packs.first.id, 'pack_5');
      expect(packs.first.usdAmountCents, 500);
      expect(packs.last.id, 'pack_100');
      expect(packs.last.creditCents, 10000);
    });

    test('surfaces ApiError on AsyncValue when server returns 401', () async {
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
      // Observe via listen — the build's thrown ApiError lands on
      // AsyncValue.error before `.future` resolves. Riverpod 3.x's
      // `read.future` semantics race autoDispose for unrescued throws,
      // so we read the error off the value directly.
      ApiError? captured;
      final sub = h.container.listen<AsyncValue<List<Pack>>>(
        packsProvider,
        (prev, next) {
          if (next.hasError && next.error is ApiError) {
            captured = next.error! as ApiError;
          }
        },
        fireImmediately: true,
      );
      addTearDown(sub.close);

      // Pump until the build's error lands (typically <100ms; cap at 2s).
      final deadline = DateTime.now().add(const Duration(seconds: 2));
      while (captured == null && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }

      expect(captured, isNotNull,
          reason: 'expected build to throw ApiError onto AsyncValue.error');
      expect(captured!.code, ErrorCode.unauthorized);
      expect(captured!.statusCode, 401);
    });
  });

  group('balanceProvider', () {
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
      _holdBalance(h.container);
      final b = await h.container.read(balanceProvider.future);
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
      _holdBalance(h.container);
      final b = await h.container.read(balanceProvider.future);
      expect(b.balanceCents, -250);
      expect(b.displayBalanceCents, 0);
      expect(b.isNegative, true);
    });
  });

  group('transactionsProvider', () {
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
      _holdTransactions(h.container);
      final page = await h.container.read(transactionsProvider.future);
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
      _holdTransactions(h.container);
      final firstPage =
          await h.container.read(transactionsProvider.future);
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
          .read(transactionsProvider.notifier)
          .loadMore();
      final merged = h.container.read(transactionsProvider).value!;
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
      _holdTransactions(h.container);
      await h.container.read(transactionsProvider.future);
      // No expectation registered for a 2nd request → if loadMore tried
      // to fetch, http_mock_adapter would throw.
      await h.container
          .read(transactionsProvider.notifier)
          .loadMore();
      final state = h.container.read(transactionsProvider).value!;
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
