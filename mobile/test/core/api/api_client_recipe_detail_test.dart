// Phase 25 Wave 3 plan 25-05 task 1 — ApiClient.recipeDetail() coverage.
//
// Mirrors api_client_test.dart's http_mock_adapter pattern (Phase 24 dev
// dep). Real dio + real JSON encode/decode + real interceptor chain;
// only the network socket is short-circuited.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

void main() {
  late Dio dio;
  late DioAdapter adapter;
  late ApiClient api;

  setUp(() {
    dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    adapter = DioAdapter(dio: dio);
    api = ApiClient(dio);
  });

  test('recipeDetail(openclaw) returns Ok(RecipeDetail) on 200', () async {
    adapter.onGet(
      '/v1/recipes/openclaw',
      (server) => server.reply(200, <String, dynamic>{
        'recipe': <String, dynamic>{
          'name': 'openclaw',
          'description': 'OpenClaw — Anthropic-compatible Claude clone.',
          'channels': <String, dynamic>{
            'inapp': <String, dynamic>{
              'required_user_input': <dynamic>[],
              'optional_user_input': <dynamic>[],
            },
            'telegram': <String, dynamic>{
              'required_user_input': <Map<String, dynamic>>[
                {
                  'env': 'TELEGRAM_BOT_TOKEN',
                  'secret': true,
                  'hint': 'Create via @BotFather /newbot.',
                },
              ],
              'provider_compat': <String, dynamic>{
                'deferred': <dynamic>['openrouter'],
                'supported': <dynamic>['anthropic'],
              },
            },
          },
        },
      }),
    );
    final r = await api.recipeDetail(name: 'openclaw');
    switch (r) {
      case Ok(:final value):
        expect(value.name, 'openclaw');
        expect(value.channelsSupported, containsAll(['inapp', 'telegram']));
        expect(
          value.channels['telegram']!.requiredUserInput.first.env,
          'TELEGRAM_BOT_TOKEN',
        );
        expect(
          value.channelProviderCompat['telegram']!.deferred,
          contains('openrouter'),
        );
      case Err(:final error):
        fail('expected Ok, got ${error.message}');
    }
  });

  test('recipeDetail(nonexistent) returns Err on 404 without throwing',
      () async {
    adapter.onGet(
      '/v1/recipes/nonexistent',
      (server) => server.reply(404, <String, dynamic>{
        'error': <String, dynamic>{
          'type': 'invalid_request_error',
          'code': 'RECIPE_NOT_FOUND',
          'message': "recipe 'nonexistent' not found",
          'param': 'name',
        },
      }),
    );
    final r = await api.recipeDetail(name: 'nonexistent');
    switch (r) {
      case Ok():
        fail('expected Err for 404');
      case Err(:final error):
        expect(error.code, ErrorCode.recipeNotFound);
        expect(error.statusCode, 404);
    }
  });
}
