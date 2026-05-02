// Phase 24 Wave 1 — minimum viable entry. Plan 06 replaces this with the
// full BASE_URL boot validation + SystemUiOverlayStyle.dark + AppEnv read.
// Right now we just need something that compiles and boots through
// ProviderScope.

import 'package:agent_playground/app.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

void main() {
  runApp(const ProviderScope(child: SolvrLabsApp()));
}
