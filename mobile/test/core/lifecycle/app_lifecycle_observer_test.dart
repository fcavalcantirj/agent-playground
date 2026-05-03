// Phase 25 Wave 1 — Mechanism §1 tests for AppLifecycleNotifier.
//
// Verifies the cross-cutting AppLifecycleState observer Riverpod-exposes
// resume/pause events. Wave 2 Dashboard (D-12) and Wave 4 Chat (D-52)
// listen to appLifecycleProvider; this test guards the contract.

import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('appLifecycleProvider starts as resumed', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(container.read(appLifecycleProvider), AppLifecycleState.resumed);
  });

  test('didChangeAppLifecycleState updates the provider state', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    container
        .read(appLifecycleProvider.notifier)
        .didChangeAppLifecycleState(AppLifecycleState.paused);
    expect(container.read(appLifecycleProvider), AppLifecycleState.paused);
    container
        .read(appLifecycleProvider.notifier)
        .didChangeAppLifecycleState(AppLifecycleState.resumed);
    expect(container.read(appLifecycleProvider), AppLifecycleState.resumed);
  });
}
