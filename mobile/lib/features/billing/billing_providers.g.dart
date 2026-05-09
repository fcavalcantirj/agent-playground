// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'billing_providers.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(PacksNotifier)
final packsProvider = PacksNotifierProvider._();

final class PacksNotifierProvider
    extends $AsyncNotifierProvider<PacksNotifier, List<Pack>> {
  PacksNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'packsProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$packsNotifierHash();

  @$internal
  @override
  PacksNotifier create() => PacksNotifier();
}

String _$packsNotifierHash() => r'd21c78dab5b0e1362cb967c0da0be8ee68253502';

abstract class _$PacksNotifier extends $AsyncNotifier<List<Pack>> {
  FutureOr<List<Pack>> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref = this.ref as $Ref<AsyncValue<List<Pack>>, List<Pack>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<List<Pack>>, List<Pack>>,
              AsyncValue<List<Pack>>,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}

@ProviderFor(BalanceNotifier)
final balanceProvider = BalanceNotifierProvider._();

final class BalanceNotifierProvider
    extends $AsyncNotifierProvider<BalanceNotifier, Balance> {
  BalanceNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'balanceProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$balanceNotifierHash();

  @$internal
  @override
  BalanceNotifier create() => BalanceNotifier();
}

String _$balanceNotifierHash() => r'1dbcab758a09f4804b726d0c90835d3c48d85be0';

abstract class _$BalanceNotifier extends $AsyncNotifier<Balance> {
  FutureOr<Balance> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref = this.ref as $Ref<AsyncValue<Balance>, Balance>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<Balance>, Balance>,
              AsyncValue<Balance>,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}

@ProviderFor(TransactionsNotifier)
final transactionsProvider = TransactionsNotifierProvider._();

final class TransactionsNotifierProvider
    extends $AsyncNotifierProvider<TransactionsNotifier, TransactionsPage> {
  TransactionsNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'transactionsProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$transactionsNotifierHash();

  @$internal
  @override
  TransactionsNotifier create() => TransactionsNotifier();
}

String _$transactionsNotifierHash() =>
    r'abc1873bdc06b6e9c7483ad3282e5b0be9ac3039';

abstract class _$TransactionsNotifier extends $AsyncNotifier<TransactionsPage> {
  FutureOr<TransactionsPage> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref =
        this.ref as $Ref<AsyncValue<TransactionsPage>, TransactionsPage>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<TransactionsPage>, TransactionsPage>,
              AsyncValue<TransactionsPage>,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}
