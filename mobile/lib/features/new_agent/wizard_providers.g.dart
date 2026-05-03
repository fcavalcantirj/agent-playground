// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'wizard_providers.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(WizardScope)
final wizardScopeProvider = WizardScopeProvider._();

final class WizardScopeProvider
    extends $NotifierProvider<WizardScope, WizardScopeState> {
  WizardScopeProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'wizardScopeProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$wizardScopeHash();

  @$internal
  @override
  WizardScope create() => WizardScope();

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(WizardScopeState value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<WizardScopeState>(value),
    );
  }
}

String _$wizardScopeHash() => r'1e8770fe9c0ab54b782ac64e0503add7d796f41f';

abstract class _$WizardScope extends $Notifier<WizardScopeState> {
  WizardScopeState build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref = this.ref as $Ref<WizardScopeState, WizardScopeState>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<WizardScopeState, WizardScopeState>,
              WizardScopeState,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}

/// Cached `GET /v1/models` for the model picker (D-26). Mirrors the shape
/// of `recipesProvider` in dashboard_providers.dart (Phase 25 Plan 25-04).

@ProviderFor(models)
final modelsProvider = ModelsProvider._();

/// Cached `GET /v1/models` for the model picker (D-26). Mirrors the shape
/// of `recipesProvider` in dashboard_providers.dart (Phase 25 Plan 25-04).

final class ModelsProvider
    extends
        $FunctionalProvider<
          AsyncValue<List<OpenRouterModel>>,
          List<OpenRouterModel>,
          FutureOr<List<OpenRouterModel>>
        >
    with
        $FutureModifier<List<OpenRouterModel>>,
        $FutureProvider<List<OpenRouterModel>> {
  /// Cached `GET /v1/models` for the model picker (D-26). Mirrors the shape
  /// of `recipesProvider` in dashboard_providers.dart (Phase 25 Plan 25-04).
  ModelsProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'modelsProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$modelsHash();

  @$internal
  @override
  $FutureProviderElement<List<OpenRouterModel>> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<List<OpenRouterModel>> create(Ref ref) {
    return models(ref);
  }
}

String _$modelsHash() => r'4449dddc1f09d48dad50bb9768da2129c926630c';
