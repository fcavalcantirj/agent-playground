// Phase B Plan 10 — Billing Riverpod hub (Wave 5 mobile substrate).
//
// Three async-notifier providers backing the Phase B mobile surfaces:
//
//   - packsNotifierProvider        → GET /v1/billing/packs (D-06 single SOT)
//   - balanceNotifierProvider      → GET /v1/billing/balance (D-21 / Pitfall 6)
//   - transactionsNotifierProvider → GET /v1/billing/transactions (paginated)
//
// All three follow the Phase 27 usage_providers.dart shape:
//   - CancelToken concurrency guard (Pitfall #8): a build()-cycle cancel
//     supersedes any inflight request when the user resumes mid-fetch.
//   - ref.listen<AppLifecycleState>(appLifecycleProvider) → invalidateSelf
//     on resume (D-32 trigger #2). Lifted from UsageSummaryNotifier.
//   - Result<T> switch arms throw ApiError on Err so AsyncValue carries
//     it widget-side (Phase 24 D-32).
//
// transactionsNotifierProvider also exposes loadMore() — the cursor
// (TransactionsPage.nextBefore) is consumed; no-op when null. The
// merged page replaces state.value.

import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'billing_providers.g.dart';

@riverpod
class PacksNotifier extends _$PacksNotifier {
  CancelToken? _cancel;

  @override
  Future<List<Pack>> build() async {
    _cancel?.cancel('superseded by ref.invalidate');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) {
        cancel.cancel('PacksNotifier disposed');
      }
    });

    final api = ref.watch(apiClientProvider);
    final r = await api.billingPacks(cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      // ignore: only_throw_errors
      Err(:final error) => throw error,
    };
  }
}

@riverpod
class BalanceNotifier extends _$BalanceNotifier {
  CancelToken? _cancel;

  @override
  Future<Balance> build() async {
    _cancel?.cancel('superseded by ref.invalidate');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) {
        cancel.cancel('BalanceNotifier disposed');
      }
    });

    // D-32 trigger #2 — refetch on app resume. Webhook-driven balance
    // updates land in 5-15s; resume-refresh closes the gap if the user
    // background-then-foregrounds during that window.
    // ignore: cascade_invocations
    ref.listen<AppLifecycleState>(appLifecycleProvider, (prev, next) {
      if (prev != next && next == AppLifecycleState.resumed) {
        ref.invalidateSelf();
      }
    });

    final api = ref.watch(apiClientProvider);
    final r = await api.billingBalance(cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      // ignore: only_throw_errors
      Err(:final error) => throw error,
    };
  }
}

@riverpod
class TransactionsNotifier extends _$TransactionsNotifier {
  CancelToken? _cancel;

  @override
  Future<TransactionsPage> build() async {
    _cancel?.cancel('superseded by ref.invalidate');
    final cancel = _cancel = CancelToken();
    ref.onDispose(() {
      if (!cancel.isCancelled) {
        cancel.cancel('TransactionsNotifier disposed');
      }
    });

    final api = ref.watch(apiClientProvider);
    final r = await api.billingTransactions(limit: 50, cancelToken: cancel);
    return switch (r) {
      Ok(:final value) => value,
      // ignore: only_throw_errors
      Err(:final error) => throw error,
    };
  }

  /// Append the next page using [TransactionsPage.nextBefore] as cursor.
  /// No-op when the current page is null or has no `nextBefore`.
  ///
  /// On error the call is silently swallowed (state remains the prior
  /// page); the caller is expected to surface a toast / SnackBar via
  /// the screen-side `result` it pulls from `api.billingTransactions`
  /// directly if it wants explicit error UX. Plan 11 owns that wiring.
  Future<void> loadMore() async {
    final current = state.value;
    if (current == null || current.nextBefore == null) {
      return;
    }
    final api = ref.read(apiClientProvider);
    final r = await api.billingTransactions(
      limit: 50,
      before: current.nextBefore,
    );
    if (r case Ok(:final value)) {
      state = AsyncValue<TransactionsPage>.data(
        TransactionsPage(
          transactions: <Transaction>[
            ...current.transactions,
            ...value.transactions,
          ],
          nextBefore: value.nextBefore,
        ),
      );
    }
  }
}
