// Phase 25 Wave 3 plan 25-05 task 1 — RecipeDetail DTOs.
//
// Permissive parser per 25-RESEARCH Open Question #3 — defensive against
// missing optional fields. Tests cover:
//
//   - ChannelUserInput.fromJson full round-trip + defensive defaults.
//   - RecipeChannelMeta.fromJson with required/optional lists; .allInputs
//     concatenates; both-missing → empty.
//   - ChannelProviderCompat.fromJson with supported/deferred lists; missing
//     fields → empty lists.
//   - RecipeDetail.fromJson against the wire shape (recipes endpoint
//     wraps the recipe in a `{"recipe": {...}}` envelope per
//     api_server.routes.recipes.RecipeDetailResponse). RecipeDetail
//     accepts either the wrapped or unwrapped form for test convenience.
//   - RecipeDetail synthesizes channelProviderCompat by walking
//     channels.<id>.provider_compat (recipes_loader.py:128-143 mirror).
//   - RecipeDetail extends Recipe — accessible name/channelsSupported.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ChannelUserInput.fromJson', () {
    test('parses full payload {env, secret, hint, hint_url, kind}', () {
      final input = ChannelUserInput.fromJson(<String, dynamic>{
        'env': 'TELEGRAM_BOT_TOKEN',
        'secret': true,
        'hint': 'Create via @BotFather /newbot.',
        'hint_url': 'https://t.me/BotFather',
        'kind': 'token',
      });
      expect(input.env, 'TELEGRAM_BOT_TOKEN');
      expect(input.secret, isTrue);
      expect(input.hint, 'Create via @BotFather /newbot.');
      expect(input.hintUrl, 'https://t.me/BotFather');
      expect(input.kind, 'token');
    });

    test('omitted optional fields default to null', () {
      final input = ChannelUserInput.fromJson(<String, dynamic>{
        'env': 'X_FOO',
        'secret': false,
      });
      expect(input.env, 'X_FOO');
      expect(input.secret, isFalse);
      expect(input.hint, isNull);
      expect(input.hintUrl, isNull);
      expect(input.kind, isNull);
    });

    test('omitted secret defaults to false (defensive)', () {
      final input = ChannelUserInput.fromJson(<String, dynamic>{
        'env': 'X_NO_SECRET_FLAG',
      });
      expect(input.secret, isFalse);
    });
  });

  group('RecipeChannelMeta.fromJson', () {
    test('parses required + optional inputs; allInputs concatenates', () {
      final meta = RecipeChannelMeta.fromJson(<String, dynamic>{
        'required_user_input': <Map<String, dynamic>>[
          {'env': 'A', 'secret': true},
          {'env': 'B', 'secret': false},
        ],
        'optional_user_input': <Map<String, dynamic>>[
          {'env': 'C', 'secret': false},
        ],
      });
      expect(meta.requiredUserInput.length, 2);
      expect(meta.optionalUserInput.length, 1);
      expect(meta.allInputs.map((i) => i.env).toList(), ['A', 'B', 'C']);
    });

    test('both lists missing → empty .allInputs', () {
      final meta = RecipeChannelMeta.fromJson(<String, dynamic>{});
      expect(meta.requiredUserInput, isEmpty);
      expect(meta.optionalUserInput, isEmpty);
      expect(meta.allInputs, isEmpty);
    });
  });

  group('ChannelProviderCompat.fromJson', () {
    test('parses {supported, deferred}', () {
      final compat = ChannelProviderCompat.fromJson(<String, dynamic>{
        'supported': <dynamic>['anthropic'],
        'deferred': <dynamic>['openrouter'],
      });
      expect(compat.supported, ['anthropic']);
      expect(compat.deferred, ['openrouter']);
    });

    test('missing fields → empty lists', () {
      final compat = ChannelProviderCompat.fromJson(<String, dynamic>{});
      expect(compat.supported, isEmpty);
      expect(compat.deferred, isEmpty);
    });
  });

  group('RecipeDetail.fromJson', () {
    test('parses an inapp+telegram recipe (wrapped {"recipe": ...} form)', () {
      // Wire shape per api_server.routes.recipes.get_recipe →
      // RecipeDetailResponse(recipe={...}).model_dump().
      final detail = RecipeDetail.fromJson(<String, dynamic>{
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
                {
                  'env': 'TELEGRAM_ALLOWED_USER',
                  'secret': false,
                  'kind': 'telegram_numeric_id',
                  'hint_url': 'https://t.me/userinfobot',
                  'hint': 'Numeric Telegram user ID (no @). Runner '
                      'auto-prefixes "tg:".',
                },
              ],
              'optional_user_input': <dynamic>[],
              'provider_compat': <String, dynamic>{
                'supported': <dynamic>['anthropic'],
                'deferred': <dynamic>['openrouter'],
              },
            },
          },
        },
      });
      expect(detail.name, 'openclaw');
      expect(detail.description, isNotEmpty);
      expect(detail.channelsSupported, containsAll(['inapp', 'telegram']));
      expect(detail.channels.containsKey('telegram'), isTrue);
      expect(detail.channels['telegram']!.requiredUserInput.length, 2);
      expect(
        detail.channels['telegram']!.requiredUserInput.first.env,
        'TELEGRAM_BOT_TOKEN',
      );
      // channelProviderCompat synthesized from channels.<id>.provider_compat
      // per recipes_loader.py:128-143 mirror.
      expect(detail.channelProviderCompat['telegram']!.deferred,
          contains('openrouter'));
      expect(detail.channelProviderCompat['telegram']!.supported,
          contains('anthropic'));
    });

    test('parses an unwrapped recipe dict (test convenience)', () {
      final detail = RecipeDetail.fromJson(<String, dynamic>{
        'name': 'nullclaw',
        'channels': <String, dynamic>{
          'inapp': <String, dynamic>{},
        },
      });
      expect(detail.name, 'nullclaw');
      expect(detail.channelsSupported, contains('inapp'));
      expect(detail.channels.containsKey('inapp'), isTrue);
      // No provider_compat on this channel → key absent in compat map.
      expect(detail.channelProviderCompat.containsKey('inapp'), isFalse);
    });

    test('missing channels block → empty channels + empty compat', () {
      final detail = RecipeDetail.fromJson(<String, dynamic>{
        'recipe': <String, dynamic>{'name': 'minimal'},
      });
      expect(detail.name, 'minimal');
      expect(detail.channels, isEmpty);
      expect(detail.channelProviderCompat, isEmpty);
      expect(detail.channelsSupported, isEmpty);
    });

    test('extends Recipe (subtype + accessors)', () {
      final detail = RecipeDetail.fromJson(<String, dynamic>{
        'recipe': <String, dynamic>{
          'name': 'r',
          'description': 'd',
          'channels': <String, dynamic>{'inapp': <String, dynamic>{}},
        },
      });
      expect(detail, isA<Recipe>());
      // Subtype assertion is the contract under test (RecipeDetail extends
      // Recipe — drop-in replacement). The lint warns the type-check is
      // unnecessary because the static type already implies it; keeping
      // the runtime check makes the contract explicit at the test layer.
      // ignore: unnecessary_type_check
      expect(detail is Recipe, isTrue);
      // Accessible as Recipe.
      final asRecipe = detail as Recipe;
      expect(asRecipe.name, 'r');
      expect(asRecipe.description, 'd');
      expect(asRecipe.channelsSupported, contains('inapp'));
    });
  });
}
