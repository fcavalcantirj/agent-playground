// Phase 24 Plan 06 — final boot sequence.
//
// 1. Read BASE_URL via String.fromEnvironment + Uri.tryParse (AppEnv).
// 2. Crash loud (StateError) on empty/malformed (D-43).
// 3. Lock orientation to portrait — defense-in-depth alongside Plan 07's
//    Info.plist + AndroidManifest config (D-14 + RESEARCH Q5).
// 4. SystemUiOverlayStyle.dark (D-17 — light bg + dark icons).
// 5. runApp(ProviderScope(child: SolvrLabsApp())).

import 'package:agent_playground/app.dart';
import 'package:agent_playground/core/env/app_env.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Boot validation — crashes here if BASE_URL is empty/malformed (D-43).
  // Resolving once at boot lets a misconfiguration surface immediately
  // instead of as a 502 on first dio call.
  AppEnv.fromEnvironment();

  // D-14 + RESEARCH Q5: defense-in-depth portrait lock. Plan 07 also sets
  // Info.plist UISupportedInterfaceOrientations + AndroidManifest
  // screenOrientation=portrait, but some Android OEM skins ignore the
  // manifest hint, so we belt-and-braces it programmatically too.
  await SystemChrome.setPreferredOrientations(
    [DeviceOrientation.portraitUp],
  );

  SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark);
  runApp(const ProviderScope(child: SolvrLabsApp()));
}
