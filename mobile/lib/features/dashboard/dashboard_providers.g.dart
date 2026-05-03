// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'dashboard_providers.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning

@ProviderFor(AgentsList)
final agentsListProvider = AgentsListProvider._();

final class AgentsListProvider
    extends $AsyncNotifierProvider<AgentsList, List<AgentSummary>> {
  AgentsListProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'agentsListProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$agentsListHash();

  @$internal
  @override
  AgentsList create() => AgentsList();
}

String _$agentsListHash() => r'09dc3dcfd585163fcfdccbb188decb5bb440501f';

abstract class _$AgentsList extends $AsyncNotifier<List<AgentSummary>> {
  FutureOr<List<AgentSummary>> build();
  @$mustCallSuper
  @override
  void runBuild() {
    final ref =
        this.ref as $Ref<AsyncValue<List<AgentSummary>>, List<AgentSummary>>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<List<AgentSummary>>, List<AgentSummary>>,
              AsyncValue<List<AgentSummary>>,
              Object?,
              Object?
            >;
    element.handleCreate(ref, build);
  }
}

/// Cached `GET /v1/recipes`. Drives AsciiAgentBanner names per D-17.

@ProviderFor(recipes)
final recipesProvider = RecipesProvider._();

/// Cached `GET /v1/recipes`. Drives AsciiAgentBanner names per D-17.

final class RecipesProvider
    extends
        $FunctionalProvider<
          AsyncValue<List<Recipe>>,
          List<Recipe>,
          FutureOr<List<Recipe>>
        >
    with $FutureModifier<List<Recipe>>, $FutureProvider<List<Recipe>> {
  /// Cached `GET /v1/recipes`. Drives AsciiAgentBanner names per D-17.
  RecipesProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'recipesProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$recipesHash();

  @$internal
  @override
  $FutureProviderElement<List<Recipe>> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<List<Recipe>> create(Ref ref) {
    return recipes(ref);
  }
}

String _$recipesHash() => r'271d2f52ed6dacae8ce9513bbde18ed5577eb5d1';

/// `Stream<List<String>>` projection of recipe names — AsciiAgentBanner
/// consumes a Stream so the widget stays pure (UI-SPEC line 314).
///
/// Single-emit by design — recipesProvider invalidation re-runs this
/// builder.

@ProviderFor(recipeNamesStream)
final recipeNamesStreamProvider = RecipeNamesStreamProvider._();

/// `Stream<List<String>>` projection of recipe names — AsciiAgentBanner
/// consumes a Stream so the widget stays pure (UI-SPEC line 314).
///
/// Single-emit by design — recipesProvider invalidation re-runs this
/// builder.

final class RecipeNamesStreamProvider
    extends
        $FunctionalProvider<
          AsyncValue<List<String>>,
          List<String>,
          Stream<List<String>>
        >
    with $FutureModifier<List<String>>, $StreamProvider<List<String>> {
  /// `Stream<List<String>>` projection of recipe names — AsciiAgentBanner
  /// consumes a Stream so the widget stays pure (UI-SPEC line 314).
  ///
  /// Single-emit by design — recipesProvider invalidation re-runs this
  /// builder.
  RecipeNamesStreamProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'recipeNamesStreamProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$recipeNamesStreamHash();

  @$internal
  @override
  $StreamProviderElement<List<String>> $createElement(
    $ProviderPointer pointer,
  ) => $StreamProviderElement(pointer);

  @override
  Stream<List<String>> create(Ref ref) {
    return recipeNamesStream(ref);
  }
}

String _$recipeNamesStreamHash() => r'38914347f6d7c3d70e5662ae2b6d0307c7f1d8f7';
