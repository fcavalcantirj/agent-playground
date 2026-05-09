// Phase B Plan 11 Task 2 — TransactionsScreen widget tests.
//
// Cases (per PLAN <behavior>):
//   - test_transactions_screen_renders_list_from_provider
//   - test_transactions_screen_load_more_appends_to_list
//   - test_transactions_screen_renders_negative_amount_for_debit_kind
//
// TransactionsNotifier is overridden via Riverpod with a counted-call
// fake to assert loadMore is invoked when scrolling lands at the
// bottom of the list with a non-null `nextBefore`.

import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:agent_playground/features/billing/billing_providers.dart';
import 'package:agent_playground/features/billing/transactions_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Transaction _tx({
  String id = '11111111-1111-1111-1111-111111111111',
  String kind = 'topup',
  int amountCents = 2500,
  DateTime? createdAt,
}) =>
    Transaction(
      id: id,
      kind: kind,
      amountCents: amountCents,
      createdAt: createdAt ?? DateTime.utc(2026, 5, 8, 10),
    );

class _StaticTxNotifier extends TransactionsNotifier {
  _StaticTxNotifier(this._page);
  final TransactionsPage _page;
  int loadMoreCalls = 0;

  @override
  Future<TransactionsPage> build() async => _page;

  @override
  Future<void> loadMore() async {
    loadMoreCalls += 1;
    final current = state.value;
    if (current == null || current.nextBefore == null) return;
    state = AsyncValue<TransactionsPage>.data(
      TransactionsPage(
        transactions: <Transaction>[
          ...current.transactions,
          _tx(
            id: '22222222-2222-2222-2222-222222222222',
            kind: 'debit',
            amountCents: -34,
            createdAt: DateTime.utc(2026, 5, 8, 8),
          ),
        ],
      ),
    );
  }
}

Widget _wrap(_StaticTxNotifier n) => ProviderScope(
      overrides: [
        transactionsProvider.overrideWith(() => n),
      ],
      child: const MaterialApp(home: TransactionsScreen()),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('TransactionsScreen', () {
    testWidgets('renders list from provider', (tester) async {
      final n = _StaticTxNotifier(
        TransactionsPage(transactions: [_tx()]),
      );
      await tester.pumpWidget(_wrap(n));
      await tester.pumpAndSettle();
      expect(find.text('topup'), findsOneWidget);
      // +$25.00 — positive sign + 2 decimals.
      expect(find.textContaining(r'+$25.00'), findsOneWidget);
    });

    testWidgets('renders negative amount for debit kind', (tester) async {
      final n = _StaticTxNotifier(
        TransactionsPage(
          transactions: [
            _tx(kind: 'debit', amountCents: -34),
          ],
        ),
      );
      await tester.pumpWidget(_wrap(n));
      await tester.pumpAndSettle();
      expect(find.text('debit'), findsOneWidget);
      // -$0.34 — negative sign + 2 decimals.
      expect(find.textContaining(r'-$0.34'), findsOneWidget);
    });

    testWidgets('load_more appends next page when scrolled to bottom',
        (tester) async {
      // Start with a single tx and a non-null nextBefore so loadMore
      // is allowed to run.
      final n = _StaticTxNotifier(
        TransactionsPage(
          transactions: [_tx()],
          nextBefore: DateTime.utc(2026, 5, 8, 9),
        ),
      );
      await tester.pumpWidget(_wrap(n));
      await tester.pumpAndSettle();

      // Scroll the inner ListView to its bottom — ScrollEndNotification
      // with extentAfter==0 fires loadMore().
      await tester.drag(find.byType(ListView), const Offset(0, -1500));
      await tester.pumpAndSettle();

      expect(n.loadMoreCalls, greaterThanOrEqualTo(1));
      // Both rows now present.
      expect(find.text('topup'), findsOneWidget);
      expect(find.text('debit'), findsOneWidget);
    });
  });
}
