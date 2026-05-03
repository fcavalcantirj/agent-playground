// Phase 25 Wave 3 plan 25-05 task 3 — ModelPickerScreen widget tests.
//
// Covers D-26 (search TextField + virtualized ListView.builder; tap row pops
// with selection; empty-search caption per UI-SPEC line 199).

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/model_picker_screen.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

ApiClient _apiWithModels(List<Map<String, dynamic>> rows) {
  final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
  DioAdapter(dio: dio).onGet('/v1/models', (s) => s.reply(200, rows));
  return ApiClient(dio);
}

class _PushHost extends StatefulWidget {
  const _PushHost();
  @override
  State<_PushHost> createState() => _PushHostState();
}

class _PushHostState extends State<_PushHost> {
  OpenRouterModel? _picked;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_picked != null) Text('PICKED:${_picked!.id}'),
            ElevatedButton(
              onPressed: () async {
                final r = await Navigator.of(context).push<OpenRouterModel>(
                  MaterialPageRoute<OpenRouterModel>(
                    builder: (_) => const ModelPickerScreen(),
                  ),
                );
                setState(() => _picked = r);
              },
              child: const Text('Open picker'),
            ),
          ],
        ),
      ),
    );
  }
}

GoRouter _router() => GoRouter(
      initialLocation: '/host',
      routes: [
        GoRoute(path: '/host', builder: (_, _) => const _PushHost()),
      ],
    );

Widget _wrap(ApiClient api) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(api)],
      child: MaterialApp.router(
        theme: solvrTheme(),
        routerConfig: _router(),
      ),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders ListView.builder + search TextField', (tester) async {
    final api = _apiWithModels(const [
      {'id': 'anthropic/claude-haiku-4-5', 'name': 'Claude Haiku 4.5'},
      {'id': 'openai/gpt-4', 'name': 'GPT 4'},
    ]);
    await tester.pumpWidget(_wrap(api));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open picker'));
    await tester.pumpAndSettle();
    expect(find.byType(ListView), findsOneWidget);
    expect(find.text('Search models…'), findsOneWidget);
    expect(find.text('anthropic/claude-haiku-4-5'), findsOneWidget);
    expect(find.text('openai/gpt-4'), findsOneWidget);
  });

  testWidgets('typing query filters list', (tester) async {
    final api = _apiWithModels(const [
      {'id': 'anthropic/claude-haiku-4-5', 'name': 'Claude Haiku 4.5'},
      {'id': 'openai/gpt-4', 'name': 'GPT 4'},
      {'id': 'meta-llama/llama-3', 'name': 'Llama 3'},
    ]);
    await tester.pumpWidget(_wrap(api));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open picker'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'gpt');
    await tester.pumpAndSettle();
    expect(find.text('openai/gpt-4'), findsOneWidget);
    expect(find.text('anthropic/claude-haiku-4-5'), findsNothing);
    expect(find.text('meta-llama/llama-3'), findsNothing);
  });

  testWidgets('empty filter result renders the no-match caption',
      (tester) async {
    final api = _apiWithModels(const [
      {'id': 'anthropic/claude-haiku-4-5', 'name': 'Claude Haiku 4.5'},
    ]);
    await tester.pumpWidget(_wrap(api));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open picker'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'asdfgh');
    await tester.pumpAndSettle();
    expect(find.text('No models match "asdfgh"'), findsOneWidget);
  });

  testWidgets('tap row pops with the selection', (tester) async {
    final api = _apiWithModels(const [
      {'id': 'anthropic/claude-haiku-4-5', 'name': 'Claude Haiku 4.5'},
    ]);
    await tester.pumpWidget(_wrap(api));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open picker'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('anthropic/claude-haiku-4-5'));
    await tester.pumpAndSettle();
    // Picker popped — back on host with the selection rendered.
    expect(find.text('PICKED:anthropic/claude-haiku-4-5'), findsOneWidget);
  });
}
