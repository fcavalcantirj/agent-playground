// Phase B Plan 11 Task 2 — paginated ledger history (Wave 5 mobile UI).
//
// Backed by transactionsProvider (Plan 10). Each row shows kind +
// signed amount + local-time created_at. Pull-to-refresh
// re-invalidates the provider. Infinite scroll appends the next page
// via TransactionsNotifier.loadMore() — no-op when nextBefore is
// null (i.e. on the last page).
//
// Dumb-client discipline: NO client-side aggregation. Every signed
// dollar amount comes straight from the api_server's signed cents
// field; the screen formats `_formatAmount` (sign prefix + 2dp
// USD) but never SUMs across rows.

import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:agent_playground/features/billing/billing_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class TransactionsScreen extends ConsumerWidget {
  const TransactionsScreen({super.key});

  String _formatAmount(int cents) {
    final sign = cents < 0 ? '-' : '+';
    final dollars = (cents.abs() / 100).toStringAsFixed(2);
    return '$sign\$$dollars';
  }

  Future<void> _refresh(WidgetRef ref) async {
    ref.invalidate(transactionsProvider);
    await ref.read(transactionsProvider.future);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(transactionsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Transactions')),
      body: RefreshIndicator(
        onRefresh: () => _refresh(ref),
        child: async.when(
          data: (page) => _TxList(
            page: page,
            onLoadMore: () =>
                ref.read(transactionsProvider.notifier).loadMore(),
            formatAmount: _formatAmount,
          ),
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('Failed to load: $e')),
        ),
      ),
    );
  }
}

class _TxList extends StatelessWidget {
  const _TxList({
    required this.page,
    required this.onLoadMore,
    required this.formatAmount,
  });

  final TransactionsPage page;
  final Future<void> Function() onLoadMore;
  final String Function(int) formatAmount;

  bool _onScrollNotification(ScrollNotification n) {
    if (n is ScrollEndNotification &&
        n.metrics.extentAfter == 0 &&
        page.nextBefore != null) {
      // Fire-and-forget — TransactionsNotifier.loadMore is idempotent
      // when there's no cursor, and the provider state is the visible
      // truth.
      // ignore: discarded_futures
      onLoadMore();
    }
    return false;
  }

  @override
  Widget build(BuildContext context) {
    return NotificationListener<ScrollNotification>(
      onNotification: _onScrollNotification,
      child: ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        itemCount: page.transactions.length,
        separatorBuilder: (_, _) => const Divider(height: 0),
        itemBuilder: (context, i) {
          final tx = page.transactions[i];
          return ListTile(
            title: Text(tx.kind),
            subtitle: Text(tx.createdAt.toLocal().toString()),
            trailing: Text(
              formatAmount(tx.amountCents),
              style: Theme.of(context).textTheme.titleMedium,
            ),
          );
        },
      ),
    );
  }
}
