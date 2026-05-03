// Phase 25 Wave 1 D-17 — AsciiAgentBanner widget unit tests.

import 'dart:async';

import 'package:agent_playground/shared/ascii_agent_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('renders ONE name from the stream at a time', (tester) async {
    final ctl = StreamController<List<String>>();
    addTearDown(ctl.close);

    await tester.pumpWidget(
      wrap(AsciiAgentBanner(namesStream: ctl.stream, intervalMs: 100000)),
    );
    // Initial: fallback
    expect(find.text('solvr_labs'), findsOneWidget);

    ctl.add(['openclaw', 'hermes']);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('openclaw'), findsOneWidget);
    expect(find.text('hermes'), findsNothing);
  });

  testWidgets('cross-fades between names via AnimatedSwitcher',
      (tester) async {
    final ctl = StreamController<List<String>>();
    addTearDown(ctl.close);

    await tester.pumpWidget(
      wrap(
        AsciiAgentBanner(
          namesStream: ctl.stream,
          intervalMs: 200,
        ),
      ),
    );
    ctl.add(['openclaw', 'hermes']);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(AnimatedSwitcher), findsOneWidget);

    // Advance past intervalMs to trigger the timer.
    await tester.pump(const Duration(milliseconds: 250));
    // Mid-crossfade — both names may exist in the tree briefly. Pump
    // through the 300ms switch duration.
    await tester.pump(const Duration(milliseconds: 350));
    expect(find.text('hermes'), findsOneWidget);
  });

  testWidgets('empty stream falls back to solvr_labs', (tester) async {
    final ctl = StreamController<List<String>>();
    addTearDown(ctl.close);

    await tester.pumpWidget(
      wrap(AsciiAgentBanner(namesStream: ctl.stream, intervalMs: 100000)),
    );
    ctl.add(<String>[]);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 10));
    expect(find.text('solvr_labs'), findsOneWidget);
  });

  testWidgets('uses JetBrains Mono w600 28px style', (tester) async {
    final ctl = StreamController<List<String>>();
    addTearDown(ctl.close);

    await tester.pumpWidget(
      wrap(AsciiAgentBanner(namesStream: ctl.stream, intervalMs: 100000)),
    );
    final text = tester.widget<Text>(find.text('solvr_labs'));
    expect(text.style?.fontSize, 28);
    expect(text.style?.fontWeight, FontWeight.w600);
    // google_fonts encodes the family in the runtime style.
    expect(text.style?.fontFamily, contains('JetBrainsMono'));
  });

  testWidgets('does NOT hardcode any clawclones recipe name', (tester) async {
    // Smoke check that the file cannot satisfy this test by smuggling a
    // recipe name in a dynamic literal — the runtime fallback list is
    // ['solvr_labs'] only.
    final ctl = StreamController<List<String>>();
    addTearDown(ctl.close);
    await tester.pumpWidget(
      wrap(AsciiAgentBanner(namesStream: ctl.stream, intervalMs: 100000)),
    );
    expect(find.text('openclaw'), findsNothing);
    expect(find.text('hermes'), findsNothing);
    expect(find.text('nullclaw'), findsNothing);
    expect(find.text('picoclaw'), findsNothing);
    expect(find.text('nanobot'), findsNothing);
  });
}
