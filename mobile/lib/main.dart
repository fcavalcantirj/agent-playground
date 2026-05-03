// Phase 25 Wave 1 — boot sequence with cold-start /v1/users/me probe.
//
// 1. Read BASE_URL via String.fromEnvironment + Uri.tryParse (AppEnv).
// 2. Crash loud (StateError) on empty/malformed (Phase 24 D-43).
// 3. Build a ProviderContainer eagerly so we can issue the boot probe
//    before runApp(). Same container is then handed to the widget tree
//    via UncontrolledProviderScope so providers are not recreated.
// 4. resolveInitialRoute(api) — D-01/D-02:
//      Ok               → /dashboard
//      Err(401)         → /login
//      Err(other)/throw → /retry-bootstrap
// 5. Lock orientation (Phase 24 D-14) + dark icons (D-17).
// 6. runApp(SolvrLabsApp(initialRoute: ...)) — native splash hides on
//    first frame.

import 'package:agent_playground/app.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/boot/resolve_initial_route.dart';
import 'package:agent_playground/core/env/app_env.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Boot validation — crashes here if BASE_URL is empty/malformed (D-43).
  AppEnv.fromEnvironment();

  // D-01..D-02 cold-start probe. We build the container eagerly so the
  // dio chain (with AuthInterceptor + cached session_id) is the same one
  // the widget tree will see — the boot probe must not re-fire on first
  // frame.
  final container = ProviderContainer();
  final initialRoute = await resolveInitialRoute(
    container.read(apiClientProvider),
  );

  // D-14 + RESEARCH Q5: defense-in-depth portrait lock (manifest hint
  // alone is ignored by some Android OEM skins).
  await SystemChrome.setPreferredOrientations(
    [DeviceOrientation.portraitUp],
  );

  SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark);

  runApp(
    UncontrolledProviderScope(
      container: container,
      child: SolvrLabsApp(initialRoute: initialRoute),
    ),
  );
}
