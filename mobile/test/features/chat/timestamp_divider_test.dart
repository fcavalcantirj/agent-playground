// Phase 25 Wave 4 plan 25-07 task 4 — D-47 timestamp divider tests.
//
// Pure unit tests on `TimestampDivider.maybeBuildFromIso` (also exercised
// indirectly via the typed `maybeBuild`):
//   * Gap < 5min                      -> null
//   * Gap > 5min, same day            -> 'HH:mm' caption
//   * Gap > 5min, different day       -> 'MMM dd HH:mm' caption
//   * No prev (first bubble)          -> null
//   * Unparseable createdAt           -> null
//   * Caption color is mutedForeground (rendered widget)
//
// Plus a ChatScreen-integration test that asserts ListView.builder injects
// exactly one TimestampDivider between two rows whose gap > 5 min and
// none for the consecutive-pair < 5 min.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/chat/chat_providers.dart';
import 'package:agent_playground/features/chat/chat_screen.dart';
import 'package:agent_playground/features/chat/timestamp_divider.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http_mock_adapter/http_mock_adapter.dart';

const _agentId = 'a-1';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('TimestampDivider.maybeBuildFromIso (D-47 gap rule)', () {
    test('gap < 5min returns null', () {
      final w = TimestampDivider.maybeBuildFromIso(
        prevIso: '2026-05-03T14:00:00Z',
        nextIso: '2026-05-03T14:04:00Z',
      );
      expect(w, isNull);
    });

    test('gap == 5min returns null (boundary)', () {
      // 5min == threshold; spec says ">5min". Equal -> NO divider.
      final w = TimestampDivider.maybeBuildFromIso(
        prevIso: '2026-05-03T14:00:00Z',
        nextIso: '2026-05-03T14:05:00Z',
      );
      expect(w, isNull);
    });

    test('gap > 5min same-day returns HH:mm caption', () {
      final w = TimestampDivider.maybeBuildFromIso(
        prevIso: '2026-05-03T14:00:00Z',
        nextIso: '2026-05-03T14:32:00Z',
        now: DateTime.utc(2026, 5, 3, 12),
      );
      expect(w, isNotNull);
      final divider = w! as TimestampDivider;
      // Local-rendered next.toLocal(); regardless of TZ the format must
      // be 5 chars matching HH:mm (digit:digit pattern).
      expect(
        RegExp(r'^\d{2}:\d{2}$').hasMatch(divider.label),
        isTrue,
        reason: 'same-day caption format is HH:mm; got "${divider.label}"',
      );
    });

    test('gap > 5min different-day returns MMM dd HH:mm caption', () {
      final w = TimestampDivider.maybeBuildFromIso(
        prevIso: '2026-04-28T10:00:00Z',
        nextIso: '2026-05-03T14:32:00Z',
        now: DateTime.utc(2026, 5, 1),
      );
      expect(w, isNotNull);
      final divider = w! as TimestampDivider;
      // 'MMM dd HH:mm' = e.g. 'May 03 14:32' — 12 chars.
      expect(
        RegExp(r'^[A-Za-z]{3} \d{2} \d{2}:\d{2}$').hasMatch(divider.label),
        isTrue,
        reason:
            'different-day caption format is "MMM dd HH:mm"; got "${divider.label}"',
      );
    });

    test('null prev returns null (no divider above first bubble)', () {
      final w = TimestampDivider.maybeBuildFromIso(
        prevIso: null,
        nextIso: '2026-05-03T14:32:00Z',
      );
      expect(w, isNull);
    });

    test('unparseable next returns null (graceful)', () {
      final w = TimestampDivider.maybeBuildFromIso(
        prevIso: '2026-05-03T14:00:00Z',
        nextIso: 'not-a-date',
      );
      expect(w, isNull);
    });

    test('unparseable prev returns null (graceful)', () {
      final w = TimestampDivider.maybeBuildFromIso(
        prevIso: 'not-a-date',
        nextIso: '2026-05-03T14:32:00Z',
      );
      expect(w, isNull);
    });

    test('typed maybeBuild forwards to maybeBuildFromIso', () {
      const prev = ChatMessage(
        inappMessageId: 'a',
        role: 'user',
        content: 'x',
        createdAt: '2026-05-03T14:00:00Z',
      );
      const next = ChatMessage(
        inappMessageId: 'b',
        role: 'assistant',
        content: 'y',
        createdAt: '2026-05-03T14:32:00Z',
      );
      final w =
          TimestampDivider.maybeBuild(prev: prev, next: next, now: DateTime.utc(2026, 5, 3, 12));
      expect(w, isNotNull);
    });
  });

  group('TimestampDivider widget render', () {
    testWidgets('caption renders centered grey muted-foreground 12sp',
        (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: solvrTheme(),
          home: const Scaffold(
            body: TimestampDivider(label: '14:32'),
          ),
        ),
      );
      expect(find.text('14:32'), findsOneWidget);
      // Center widget present in tree.
      expect(find.byType(Center), findsAtLeastNWidgets(1));
      final text = tester.widget<Text>(find.text('14:32'));
      expect(text.style?.fontSize, 12);
      expect(text.style?.color, SolvrColors.mutedForeground);
    });
  });

  group('ChatScreen integration — divider injected between rows', () {
    testWidgets('exactly one TimestampDivider between rows whose gap > 5min',
        (tester) async {
      ChatScope.autoBootstrap = true;
      final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
      final adapter = DioAdapter(dio: dio);
      // Three messages — gaps 2min (no divider), 10min (divider).
      adapter.onGet(
        '/v1/agents/$_agentId/messages',
        (s) => s.reply(200, <String, dynamic>{
          'messages': [
            {
              'inapp_message_id': 'a',
              'role': 'user',
              'content': 'first',
              'created_at': '2026-05-03T14:00:00Z',
            },
            {
              'inapp_message_id': 'b',
              'role': 'assistant',
              'content': 'second',
              'created_at': '2026-05-03T14:02:00Z',
            },
            {
              'inapp_message_id': 'c',
              'role': 'assistant',
              'content': 'third',
              'created_at': '2026-05-03T14:12:00Z',
            },
          ],
        }),
        queryParameters: {'limit': 200},
      );
      adapter.onGet(
        '/v1/agents',
        (s) => s.reply(200, [
          {
            'id': _agentId,
            'name': 'foo',
            'recipe_name': 'openclaw',
            'model': 'anthropic/claude-haiku-4-5',
            'status': 'running',
            'created_at': '2026-05-03T00:00:00Z',
          },
        ]),
      );
      final api = ApiClient(dio);
      final router = GoRouter(
        initialLocation: '/chat/$_agentId',
        routes: [
          GoRoute(
            path: '/chat/:id',
            builder: (_, state) =>
                ChatScreen(agentInstanceId: state.pathParameters['id']!),
          ),
          GoRoute(
            path: '/dashboard',
            builder: (_, _) => const Scaffold(),
          ),
        ],
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            apiClientProvider.overrideWithValue(api),
            authServiceProvider.overrideWithValue(_FakeAuth()),
          ],
          child: MaterialApp.router(
            theme: solvrTheme(),
            routerConfig: router,
          ),
        ),
      );
      await tester.pumpAndSettle();
      // Three rows -> at most 2 dividers between them. Only the
      // second-to-third gap (>5min) should produce one.
      expect(find.byType(TimestampDivider), findsOneWidget);
    });
  });
}

class _FakeAuth implements AuthService {
  @override
  Future<Result<SessionUser>> signInWithGoogle() async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<Result<SessionUser>> signInWithGithub() async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<Result<SessionUser>> signInWithGithubCode({
    required String code,
    required String codeVerifier,
  }) async =>
      const Result.err(ApiError(code: ErrorCode.internal, message: 'unset'));
  @override
  Future<void> signOut() async {}
}
