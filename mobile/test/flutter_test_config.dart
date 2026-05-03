// Phase 25 Wave 1 D-62 — golden_toolkit-style test boot.
//
// flutter_test auto-loads this file before any test in this directory
// tree. Without `loadAppFonts()` (Pitfall #6 in 25-RESEARCH.md), golden
// snapshots render with the Ahem fallback font and visual diff reviews
// are useless.
//
// **Parallel-execution gap (resolved at merge):** Plan 25-02 owns
// `pubspec.yaml` and adds `golden_toolkit: ^0.15.0` as a dev_dependency.
// Until 25-02 lands, this file uses a hand-rolled `loadAppFonts()` that
// scans the AssetManifest for `Inter*` and `JetBrainsMono*` font assets
// and registers them with `FontLoader`. Once 25-02 is merged, the
// `golden_toolkit` package becomes available and the cleaner
// `GoldenToolkit.runWithConfiguration(loadAppFonts: ...)` form per
// 25-PATTERNS.md lines 1232-1250 becomes available — Wave 5 may swap.
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  TestWidgetsFlutterBinding.ensureInitialized();
  await loadAppFonts();
  await testMain();
}

/// Hand-rolled font loader — loads any font asset bundled with the app
/// (Inter, JetBrains Mono, plus any system fonts that ship with
/// google_fonts cache files when present).
///
/// Mirrors the public surface of `golden_toolkit.loadAppFonts()` so the
/// test config can swap in the package later without rewriting tests.
Future<void> loadAppFonts() async {
  // Tests run without a real asset bundle in many cases (no
  // `AssetManifest.json` shipped to the host VM). Treat a missing
  // manifest as "no bundled fonts to load" — Flutter falls back to
  // Ahem only for golden snapshots; widget unit tests still measure
  // text geometry correctly without bundled fonts.
  // rootBundle.loadString throws FlutterError (a subclass of Error) when
  // an asset is missing. The widget-test environment routinely lacks
  // AssetManifest.json, so we catch + bail rather than crash the entire
  // test suite.
  String manifestRaw;
  try {
    manifestRaw = await rootBundle.loadString('AssetManifest.json');
  // The framework throws FlutterError (Error subclass) for missing assets;
  // we intentionally catch it here so test runs without bundled fonts
  // continue rather than abort.
  // ignore: avoid_catching_errors
  } on FlutterError {
    return;
  }
  final manifest = json.decode(manifestRaw) as Map<String, dynamic>;
  final fontAssets = manifest.keys
      .where(
        (k) => k.toLowerCase().endsWith('.ttf') ||
            k.toLowerCase().endsWith('.otf'),
      )
      .toList();
  for (final asset in fontAssets) {
    final family = _familyFromAsset(asset);
    final loader = FontLoader(family)..addFont(rootBundle.load(asset));
    await loader.load();
  }
}

String _familyFromAsset(String assetPath) {
  // assets/fonts/Inter-Regular.ttf → Inter
  final basename = assetPath.split('/').last;
  final stem = basename.replaceAll(RegExp(r'\.(ttf|otf)$'), '');
  final dashIdx = stem.indexOf('-');
  return dashIdx > 0 ? stem.substring(0, dashIdx) : stem;
}
