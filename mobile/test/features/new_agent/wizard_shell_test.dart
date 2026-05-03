// Phase 25 Wave 3 plan 25-05 task 2 — WizardShell widget tests.
//
// Covers D-23 (stepper bar), D-24 (back arrow preserves state), D-31
// (X close → ConfirmDialog when dirty, immediate pop when not).

import 'dart:async';

import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/new_agent/wizard_providers.dart';
import 'package:agent_playground/features/new_agent/wizard_shell.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

GoRouter _router({required Widget Function() shell}) {
  return GoRouter(
    initialLocation: '/wizard',
    routes: [
      GoRoute(
        path: '/dashboard',
        builder: (_, _) =>
            const Scaffold(body: Center(child: Text('DASHBOARD_ROUTE'))),
      ),
      GoRoute(path: '/wizard', builder: (_, _) => shell()),
    ],
  );
}

Widget _wrap({required Widget Function() shell}) {
  return ProviderScope(
    child: MaterialApp.router(
      theme: solvrTheme(),
      routerConfig: _router(shell: shell),
    ),
  );
}

WizardShell _shell({
  String title = 'Pick a clone',
  int currentStep = 0,
  bool canGoBack = false,
  Widget body = const SizedBox.shrink(),
}) =>
    WizardShell(
      title: title,
      currentStep: currentStep,
      canGoBack: canGoBack,
      body: body,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
      'step 1 — renders title + X icon + 3-dot stepper; NO back arrow',
      (tester) async {
    await tester.pumpWidget(_wrap(shell: _shell));
    await tester.pumpAndSettle();
    expect(find.text('Pick a clone'), findsOneWidget);
    expect(find.byIcon(Icons.close), findsOneWidget);
    expect(find.byIcon(Icons.arrow_back), findsNothing);
    // Stepper dots — three filled/hollow dots; the implementation paints
    // them as Containers so we assert via the labels (one per step).
    expect(find.text('Clone'), findsOneWidget);
    expect(find.text('Model + Key'), findsOneWidget);
    expect(find.text('Name + Deploy'), findsOneWidget);
  });

  testWidgets('canGoBack=true (steps 2/3) — back arrow IS rendered',
      (tester) async {
    await tester.pumpWidget(
      _wrap(
        shell: () => _shell(
          title: 'Pick a model + key',
          currentStep: 1,
          canGoBack: true,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byIcon(Icons.arrow_back), findsOneWidget);
    expect(find.byIcon(Icons.close), findsOneWidget);
  });

  testWidgets('!isDirty + tap X → no dialog, navigates to /dashboard',
      (tester) async {
    await tester.pumpWidget(_wrap(shell: _shell));
    await tester.pumpAndSettle();
    expect(find.text('DASHBOARD_ROUTE'), findsNothing);
    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    // No ConfirmDialog appeared — went straight to /dashboard.
    expect(find.text('Discard changes?'), findsNothing);
    expect(find.text('DASHBOARD_ROUTE'), findsOneWidget);
  });

  testWidgets(
      'isDirty + tap X → ConfirmDialog visible; Cancel keeps state + does '
      'not navigate', (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          theme: solvrTheme(),
          routerConfig: _router(shell: _shell),
        ),
      ),
    );
    await tester.pumpAndSettle();
    // Dirty the wizard scope from outside.
    container
        .read(wizardScopeProvider.notifier)
        .setAgentName('typed-something');
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    expect(find.text('Discard changes?'), findsOneWidget);

    // Cancel — dialog dismisses, scope intact, still on wizard.
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Discard changes?'), findsNothing);
    expect(find.text('DASHBOARD_ROUTE'), findsNothing);
    expect(
      container.read(wizardScopeProvider).agentName,
      'typed-something',
    );
    expect(container.read(wizardScopeProvider).isDirty, isTrue);
  });

  testWidgets(
      'isDirty + tap X + Discard → wizardScope cleared + navigates to '
      '/dashboard', (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          theme: solvrTheme(),
          routerConfig: _router(shell: _shell),
        ),
      ),
    );
    await tester.pumpAndSettle();
    container.read(wizardScopeProvider.notifier).setAgentName('foo');
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.close));
    await tester.pumpAndSettle();
    expect(find.text('Discard changes?'), findsOneWidget);

    await tester.tap(find.widgetWithText(TextButton, 'Discard'));
    await tester.pumpAndSettle();
    expect(find.text('DASHBOARD_ROUTE'), findsOneWidget);
    expect(container.read(wizardScopeProvider).agentName, '');
    expect(container.read(wizardScopeProvider).isDirty, isFalse);
  });

  testWidgets('back arrow tap pops — preserves wizard scope per D-24',
      (tester) async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final router = GoRouter(
      initialLocation: '/wizard/clone',
      routes: [
        GoRoute(
          path: '/wizard/clone',
          builder: (_, _) =>
              const Scaffold(body: Center(child: Text('CLONE_STEP_BODY'))),
        ),
        GoRoute(
          path: '/wizard/model',
          builder: (_, _) => _shell(
            title: 'Pick a model + key',
            currentStep: 1,
            canGoBack: true,
          ),
        ),
      ],
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          theme: solvrTheme(),
          routerConfig: router,
        ),
      ),
    );
    await tester.pumpAndSettle();
    container.read(wizardScopeProvider.notifier).setAgentName('preserved');
    unawaited(router.push<Object?>('/wizard/model'));
    await tester.pumpAndSettle();
    // We are on step 2 — back arrow visible.
    expect(find.byIcon(Icons.arrow_back), findsOneWidget);
    await tester.tap(find.byIcon(Icons.arrow_back));
    await tester.pumpAndSettle();
    // Back to clone step — scope still has the typed value.
    expect(find.text('CLONE_STEP_BODY'), findsOneWidget);
    expect(
      container.read(wizardScopeProvider).agentName,
      'preserved',
    );
  });
}
