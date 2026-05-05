// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'usage_providers.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(UsageSummaryNotifier)
final usageSummaryProvider = UsageSummaryNotifierProvider._();

final class UsageSummaryNotifierProvider
    extends $AsyncNotifierProvider<UsageSummaryNotifier, UsageSummary> {
  UsageSummaryNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'usageSummaryProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$usageSummaryNotifierHash();

  @$internal
  @override
  UsageSummaryNotifier create() => UsageSummaryNotifier();
}

String _$usageSummaryNotifierHash() =>
    r'9cd5444c8242a5987ff15d53e9405d23555d56f1';

abstract class _$UsageSummaryNotifier extends $AsyncNotifier<UsageSummary> {
  FutureOr<UsageSummary> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref = this.ref as $Ref<AsyncValue<UsageSummary>, UsageSummary>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<UsageSummary>, UsageSummary>,
              AsyncValue<UsageSummary>,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}

@ProviderFor(AgentUsageNotifier)
final agentUsageProvider = AgentUsageNotifierFamily._();

final class AgentUsageNotifierProvider
    extends $AsyncNotifierProvider<AgentUsageNotifier, AgentUsageData> {
  AgentUsageNotifierProvider._({
    required AgentUsageNotifierFamily super.from,
    required String super.argument,
  }) : super(
         retry: null,
         name: r'agentUsageProvider',
         isAutoDispose: true,
         dependencies: null,
         $allTransitiveDependencies: null,
       );

  @override
  String debugGetCreateSourceHash() => _$agentUsageNotifierHash();

  @override
  String toString() {
    return r'agentUsageProvider'
        ''
        '($argument)';
  }

  @$internal
  @override
  AgentUsageNotifier create() => AgentUsageNotifier();

  @override
  bool operator ==(Object other) {
    return other is AgentUsageNotifierProvider && other.argument == argument;
  }

  @override
  int get hashCode {
    return argument.hashCode;
  }
}

String _$agentUsageNotifierHash() =>
    r'2c1cb8efffdd77d66554bd03401374bc395044ca';

final class AgentUsageNotifierFamily extends $Family
    with
        $ClassFamilyOverride<
          AgentUsageNotifier,
          AsyncValue<AgentUsageData>,
          AgentUsageData,
          FutureOr<AgentUsageData>,
          String
        > {
  AgentUsageNotifierFamily._()
    : super(
        retry: null,
        name: r'agentUsageProvider',
        dependencies: null,
        $allTransitiveDependencies: null,
        isAutoDispose: true,
      );

  AgentUsageNotifierProvider call(String agentId) =>
      AgentUsageNotifierProvider._(argument: agentId, from: this);

  @override
  String toString() => r'agentUsageProvider';
}

abstract class _$AgentUsageNotifier extends $AsyncNotifier<AgentUsageData> {
  late final _$args = ref.$arg as String;
  String get agentId => _$args;

  FutureOr<AgentUsageData> build(String agentId);
  @$mustCallSuper
  @override
  void runBuild() {
    final ref = this.ref as $Ref<AsyncValue<AgentUsageData>, AgentUsageData>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<AgentUsageData>, AgentUsageData>,
              AsyncValue<AgentUsageData>,
              Object?,
              Object?
            >;
    element.handleCreate(ref, () => build(_$args));
  }
}
