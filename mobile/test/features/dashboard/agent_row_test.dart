// Phase 25 Wave 2 plan 25-04 task 1 — AgentRow widget tests.
//
// Covers D-08 / D-14 / D-15 / D-16 / D-20 + Recipe DTO description
// fromJson parse.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/dashboard/agent_row.dart';
import 'package:agent_playground/shared/status_dot.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

AgentSummary _agent({
  String id = 'a-1',
  String name = 'claude-test-1',
  String model = 'anthropic/claude-haiku-4-5',
  String status = 'running',
  String? lastActivity,
}) =>
    AgentSummary(
      id: id,
      name: name,
      recipeName: 'openclaw',
      model: model,
      status: status,
      createdAt: '2026-05-03T00:00:00Z',
      lastActivity: lastActivity,
    );

Widget _wrap(Widget child) => MaterialApp(
      theme: solvrTheme(),
      home: Scaffold(body: SizedBox(width: 400, child: child)),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AgentRow', () {
    testWidgets('running status renders green StatusDot + name + model',
        (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        _wrap(
          AgentRow(
            agent: _agent(),
            onTap: () => taps++,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(StatusDot), findsOneWidget);
      final dot = tester.widget<StatusDot>(find.byType(StatusDot));
      expect(dot.status, 'running');
      expect(find.text('claude-test-1'), findsOneWidget);
      // Model line now reads `<recipeName> · <model>` (commit landing
      // recipe.emoji glyph in the row). Match by substring instead of
      // standalone model id.
      expect(
        find.textContaining('anthropic/claude-haiku-4-5'),
        findsOneWidget,
      );
      expect(taps, 0);
    });

    testWidgets('tap fires onTap callback exactly once', (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        _wrap(
          AgentRow(
            agent: _agent(),
            onTap: () => taps++,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byType(AgentRow));
      expect(taps, 1);
    });

    testWidgets('long agent name (200 chars) ellipsizes to a single line '
        '(D-20)', (tester) async {
      final longName = List.filled(200, 'a').join();
      await tester.pumpWidget(
        _wrap(
          AgentRow(
            agent: _agent(name: longName),
            onTap: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      final nameText = tester.widget<Text>(find.text(longName));
      expect(nameText.maxLines, 1);
      expect(nameText.overflow, TextOverflow.ellipsis);
    });

    testWidgets('long model id ellipsizes to a single line (D-20)',
        (tester) async {
      const longModel = 'anthropic/claude-3-5-sonnet-some-very-long-version-id-that-blows-the-row';
      await tester.pumpWidget(
        _wrap(
          AgentRow(
            agent: _agent(model: longModel),
            onTap: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      // Model line now reads `<recipeName> · <model>`. Find by
      // substring match on the long model id.
      final modelText = tester.widget<Text>(
        find.textContaining(longModel),
      );
      expect(modelText.maxLines, 1);
      expect(modelText.overflow, TextOverflow.ellipsis);
    });

    testWidgets('null lastActivity renders empty time slot', (tester) async {
      await tester.pumpWidget(
        _wrap(
          AgentRow(
            agent: _agent(),
            onTap: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      // The trailing time Text exists but is empty.
      expect(find.text(''), findsWidgets);
    });

    testWidgets('failed status renders red StatusDot', (tester) async {
      await tester.pumpWidget(
        _wrap(
          AgentRow(
            agent: _agent(status: 'failed'),
            onTap: () {},
          ),
        ),
      );
      await tester.pumpAndSettle();
      final dot = tester.widget<StatusDot>(find.byType(StatusDot));
      expect(dot.status, 'failed');
    });
  });

  group('AgentRow.relativeTime', () {
    final now = DateTime.utc(2026, 5, 3, 12);

    test('null/empty → empty string', () {
      expect(AgentRow.relativeTime(null, now: now), '');
      expect(AgentRow.relativeTime('', now: now), '');
      expect(AgentRow.relativeTime('not-a-date', now: now), '');
    });

    test('within last minute → "now"', () {
      final ts = now.subtract(const Duration(seconds: 30)).toIso8601String();
      expect(AgentRow.relativeTime(ts, now: now), 'now');
    });

    test('minutes (1..59) → "<N>m"', () {
      final ts5 = now.subtract(const Duration(minutes: 5)).toIso8601String();
      expect(AgentRow.relativeTime(ts5, now: now), '5m');
      final ts59 = now.subtract(const Duration(minutes: 59)).toIso8601String();
      expect(AgentRow.relativeTime(ts59, now: now), '59m');
    });

    test('hours (1..23) → "<N>h"', () {
      final ts3h = now.subtract(const Duration(hours: 3)).toIso8601String();
      expect(AgentRow.relativeTime(ts3h, now: now), '3h');
    });

    test('1..2 days → "yesterday"', () {
      final ts26h = now.subtract(const Duration(hours: 26)).toIso8601String();
      expect(AgentRow.relativeTime(ts26h, now: now), 'yesterday');
    });

    test('2..6 days → "<N>d"', () {
      final ts4d = now.subtract(const Duration(days: 4)).toIso8601String();
      expect(AgentRow.relativeTime(ts4d, now: now), '4d');
    });

    test('older than a week → ISO date prefix', () {
      final ts = now.subtract(const Duration(days: 30)).toIso8601String();
      final out = AgentRow.relativeTime(ts, now: now);
      // YYYY-MM-DD shape.
      expect(RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(out), isTrue);
    });
  });

  group('Recipe DTO description', () {
    test('fromJson parses optional description when present', () {
      final r = Recipe.fromJson(<String, dynamic>{
        'name': 'openclaw',
        'channels_supported': ['inapp', 'telegram'],
        'description': 'Local coding clone of Claude Code',
      });
      expect(r.description, 'Local coding clone of Claude Code');
      expect(r.name, 'openclaw');
      expect(r.channelsSupported, ['inapp', 'telegram']);
    });

    test('fromJson sets description=null when key absent', () {
      final r = Recipe.fromJson(<String, dynamic>{
        'name': 'hermes',
        'channels_supported': <String>[],
      });
      expect(r.description, isNull);
    });
  });
}
