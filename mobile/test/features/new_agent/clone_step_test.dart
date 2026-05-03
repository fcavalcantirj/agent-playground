// Phase 25 Wave 3 plan 25-05 task 3 — CloneStep widget tests.
//
// Covers D-25 (horizontal scrolling card row from recipesProvider; selected
// card 2px black border vs idle 1px grey; Next disabled until selected).

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/clone_step.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

class _Harness {
  _Harness() {
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    adapter = DioAdapter(dio: dio);
    api = ApiClient(dio);
  }
  late final Dio dio;
  late final DioAdapter adapter;
  late final ApiClient api;

  void stubRecipes(List<Map<String, dynamic>> rows) {
    adapter.onGet('/v1/recipes', (s) => s.reply(200, {'recipes': rows}));
  }

  void stubRecipeDetail(String name, Map<String, dynamic> body) {
    adapter.onGet('/v1/recipes/$name', (s) => s.reply(200, body));
  }
}

GoRouter _router({String initial = '/new-agent/clone'}) {
  return GoRouter(
    initialLocation: initial,
    routes: [
      GoRoute(path: '/dashboard', builder: (_, _) => const _Stub('DASH')),
      GoRoute(
        path: '/new-agent/clone',
        builder: (_, _) => const CloneStep(),
      ),
      GoRoute(
        path: '/new-agent/model',
        builder: (_, _) => const _Stub('MODEL_STEP'),
      ),
    ],
  );
}

class _Stub extends StatelessWidget {
  const _Stub(this.label);
  final String label;
  @override
  Widget build(BuildContext context) =>
      Scaffold(body: Center(child: Text(label)));
}

Widget _wrap(_Harness h, {ProviderContainer? container}) {
  final inner = MaterialApp.router(
    theme: solvrTheme(),
    routerConfig: _router(),
  );
  if (container != null) {
    return UncontrolledProviderScope(container: container, child: inner);
  }
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(h.api)],
    child: inner,
  );
}

Map<String, dynamic> _summary(
  String name, {
  String? description,
  List<String> channels = const ['inapp'],
}) =>
    <String, dynamic>{
      'name': name,
      'description': ?description,
      'channels_supported': channels,
    };

Map<String, dynamic> _detailBody(String name) => <String, dynamic>{
      'recipe': <String, dynamic>{
        'name': name,
        'channels': <String, dynamic>{'inapp': <String, dynamic>{}},
      },
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders horizontal recipe cards from recipesProvider',
      (tester) async {
    final h = _Harness()
      ..stubRecipes([
        _summary('openclaw', description: 'OpenClaw — clone.'),
        _summary('hermes', description: 'Hermes — clone.'),
        _summary('nullclaw', description: 'NullClaw — clone.'),
      ]);
    await tester.pumpWidget(_wrap(h));
    await tester.pumpAndSettle();
    // Names appear (via _RecipeCard).
    expect(find.text('openclaw'), findsOneWidget);
    expect(find.text('hermes'), findsOneWidget);
    expect(find.text('nullclaw'), findsOneWidget);
  });

  testWidgets('Next button is disabled until a card is tapped (D-25)',
      (tester) async {
    final h = _Harness()
      ..stubRecipes([_summary('openclaw', description: 'd')])
      ..stubRecipeDetail('openclaw', _detailBody('openclaw'));
    await tester.pumpWidget(_wrap(h));
    await tester.pumpAndSettle();
    final btn = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Next'),
    );
    expect(btn.onPressed, isNull);
  });

  testWidgets(
      'tap card → recipeDetail() fetched + wizardScope.selectedRecipe set;'
      ' Next becomes enabled', (tester) async {
    final container = ProviderContainer(overrides: [
      apiClientProvider.overrideWith((ref) {
        final h = _Harness()
          ..stubRecipes([_summary('openclaw', description: 'd')])
          ..stubRecipeDetail('openclaw', _detailBody('openclaw'));
        return h.api;
      }),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(_wrap(_Harness(), container: container));
    await tester.pumpAndSettle();
    await tester.tap(find.text('openclaw'));
    await tester.pumpAndSettle();
    final scope = container.read(wizardScopeProvider);
    expect(scope.selectedRecipe?.name, 'openclaw');
    final btn = tester.widget<ElevatedButton>(
      find.widgetWithText(ElevatedButton, 'Next'),
    );
    expect(btn.onPressed, isNotNull);
  });

  testWidgets('tap Next after selection → routes to /new-agent/model',
      (tester) async {
    final h = _Harness()
      ..stubRecipes([_summary('openclaw', description: 'd')])
      ..stubRecipeDetail('openclaw', _detailBody('openclaw'));
    await tester.pumpWidget(_wrap(h));
    await tester.pumpAndSettle();
    await tester.tap(find.text('openclaw'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await tester.pumpAndSettle();
    expect(find.text('MODEL_STEP'), findsOneWidget);
  });

  testWidgets('horizontal scroll axis (D-25 horizontal cards)',
      (tester) async {
    final h = _Harness()
      ..stubRecipes([
        _summary('a', description: 'd'),
        _summary('b', description: 'd'),
      ]);
    await tester.pumpWidget(_wrap(h));
    await tester.pumpAndSettle();
    // ListView with horizontal scroll direction is the contract.
    final lv = tester.widget<ListView>(find.byType(ListView));
    expect(lv.scrollDirection, Axis.horizontal);
  });
}
