// Phase 25 Wave 1 — Mechanism §1.
//
// Single WidgetsBindingObserver registered at app startup. Riverpod-exposed
// so Dashboard (D-12) and Chat (D-52) can listen via ref.listen instead of
// each registering its own observer.
//
// Riverpod 3.x — uses Notifier + NotifierProvider (the `StateNotifier` API
// moved to `legacy.dart` in Riverpod 3 and is no longer the recommended
// authoring style).

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final appLifecycleProvider =
    NotifierProvider<AppLifecycleNotifier, AppLifecycleState>(
  AppLifecycleNotifier.new,
);

class AppLifecycleNotifier extends Notifier<AppLifecycleState>
    with WidgetsBindingObserver {
  @override
  AppLifecycleState build() {
    WidgetsBinding.instance.addObserver(this);
    ref.onDispose(() {
      WidgetsBinding.instance.removeObserver(this);
    });
    return AppLifecycleState.resumed;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) =>
      this.state = state;
}
