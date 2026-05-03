// Phase 25 Wave 1 D-07/D-28/D-31 — ConfirmDialog widget unit tests.

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/shared/confirm_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<ConfirmDialogResult> _openAndAct(
  WidgetTester tester, {
  required String confirmLabel,
  required Future<void> Function() act,
  String? thirdButtonLabel,
}) async {
  late ConfirmDialogResult capturedResult;
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (ctx) => ElevatedButton(
            onPressed: () async {
              capturedResult = await ConfirmDialog.show(
                ctx,
                title: 'Sign out of Solvr Labs?',
                confirmLabel: confirmLabel,
                thirdButtonLabel: thirdButtonLabel,
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await act();
  return capturedResult;
}

void main() {
  testWidgets('Cancel returns ConfirmDialogResult.cancel', (tester) async {
    final r = await _openAndAct(
      tester,
      confirmLabel: 'Sign out',
      act: () async {
        await tester.tap(find.text('Cancel'));
        await tester.pumpAndSettle();
      },
    );
    expect(r, ConfirmDialogResult.cancel);
  });

  testWidgets('Confirm returns ConfirmDialogResult.confirm', (tester) async {
    final r = await _openAndAct(
      tester,
      confirmLabel: 'Sign out',
      act: () async {
        await tester.tap(find.text('Sign out'));
        await tester.pumpAndSettle();
      },
    );
    expect(r, ConfirmDialogResult.confirm);
  });

  testWidgets('thirdButtonLabel returns ConfirmDialogResult.third',
      (tester) async {
    final r = await _openAndAct(
      tester,
      confirmLabel: 'Re-deploy',
      thirdButtonLabel: 'Rename',
      act: () async {
        expect(find.text('Cancel'), findsOneWidget);
        expect(find.text('Re-deploy'), findsOneWidget);
        expect(find.text('Rename'), findsOneWidget);
        await tester.tap(find.text('Rename'));
        await tester.pumpAndSettle();
      },
    );
    expect(r, ConfirmDialogResult.third);
  });

  testWidgets('barrierDismissible: false — tap outside does NOT cancel',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => ElevatedButton(
              onPressed: () => ConfirmDialog.show(
                ctx,
                title: 'Sign out of Solvr Labs?',
                confirmLabel: 'Sign out',
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);

    // Tap at (10, 10) which is outside the dialog.
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
  });

  testWidgets('confirm button uses destructive red foreground when destructive',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => ElevatedButton(
              onPressed: () => ConfirmDialog.show(
                ctx,
                title: 'Discard changes?',
                confirmLabel: 'Discard',
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    final discardButton = tester.widget<TextButton>(
      find.ancestor(
        of: find.text('Discard'),
        matching: find.byType(TextButton),
      ),
    );
    final fg = discardButton.style?.foregroundColor?.resolve({});
    expect(fg, SolvrColors.destructive);
  });

  testWidgets('non-destructive uses foreground color', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (ctx) => ElevatedButton(
              onPressed: () => ConfirmDialog.show(
                ctx,
                title: 'Save?',
                confirmLabel: 'Save',
                destructive: false,
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    final saveButton = tester.widget<TextButton>(
      find.ancestor(
        of: find.text('Save'),
        matching: find.byType(TextButton),
      ),
    );
    final fg = saveButton.style?.foregroundColor?.resolve({});
    expect(fg, SolvrColors.foreground);
  });
}
