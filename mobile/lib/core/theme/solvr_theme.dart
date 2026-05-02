// Phase 24 Plan 02 — Solvr Labs theme
//
// Source of truth (light mode only — D-22 carry-forward, dark mode deferred):
//   /Users/fcavalcanti/dev/solvr/frontend/app/globals.css :root block (lines 6-39)
//
// Authoritative hex values per CONTEXT.md line 139:
//   --background = #FAFAF7
//   --foreground = #1F1F1F
//   --radius     = 0rem  ->  BorderRadius.zero everywhere

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Solvr Labs light-mode color tokens.
///
/// Background and foreground are LOCKED (CONTEXT line 139). The remaining
/// values are sRGB approximations of the OKLCH tokens in
/// solvr/frontend/app/globals.css:7-31. They may be revised if a Solvr
/// Labs token export becomes available.
abstract final class SolvrColors {
  SolvrColors._();

  // LOCKED (CONTEXT line 139)
  static const Color background = Color(0xFFFAFAF7); // --background
  static const Color foreground = Color(0xFF1F1F1F); // --foreground

  // OKLCH-derived (best-effort sRGB conversion; may revise)
  static const Color card = Color(0xFFFFFFFF); // --card
  static const Color muted =
      Color(0xFFEFEFEC); // --muted / --secondary / --accent
  static const Color mutedForeground = Color(0xFF6B6B6B); // --muted-foreground
  static const Color border = Color(0xFFDEDEDA); // --border / --input
  static const Color destructive = Color(0xFFD9333A); // --destructive
}

/// Solvr Labs typography.
///
/// `Inter` for sans-serif body (APP-02). `JetBrainsMono` for status / code
/// text (the `>_ SOLVR_LABS` mark family).
abstract final class SolvrTextStyles {
  SolvrTextStyles._();

  static TextTheme bodyTextTheme(TextTheme base) =>
      GoogleFonts.interTextTheme(base).apply(
        bodyColor: SolvrColors.foreground,
        displayColor: SolvrColors.foreground,
      );

  static TextStyle mono({double? fontSize, FontWeight? fontWeight}) =>
      GoogleFonts.jetBrainsMono(
        fontSize: fontSize,
        fontWeight: fontWeight,
        color: SolvrColors.foreground,
      );
}

/// Builds the Solvr Labs `ThemeData` (light mode).
///
/// `BorderRadius.zero` is non-negotiable per `--radius: 0rem` in globals.css
/// + CONTEXT line 222 ("flat surfaces").
ThemeData solvrTheme() {
  final base = ThemeData.light();
  const flatShape = RoundedRectangleBorder(
    // BorderRadius.zero IS the default for RoundedRectangleBorder, but we
    // keep it explicit so APP-02's "zero corners everywhere" invariant is
    // self-documenting at every flat-shape callsite.
    // ignore: avoid_redundant_argument_values
    borderRadius: BorderRadius.zero,
  );

  return base.copyWith(
    scaffoldBackgroundColor: SolvrColors.background,
    colorScheme: const ColorScheme.light(
      surface: SolvrColors.background,
      onSurface: SolvrColors.foreground,
      primary: SolvrColors.foreground,
      onPrimary: SolvrColors.background,
      secondary: SolvrColors.muted,
      onSecondary: SolvrColors.foreground,
      error: SolvrColors.destructive,
      onError: SolvrColors.background,
      outline: SolvrColors.border,
    ),
    textTheme: SolvrTextStyles.bodyTextTheme(base.textTheme),
    cardTheme: const CardThemeData(
      color: SolvrColors.card,
      elevation: 0,
      shape: flatShape,
      margin: EdgeInsets.zero,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: SolvrColors.foreground,
        foregroundColor: SolvrColors.background,
        elevation: 0,
        shape: flatShape,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: SolvrColors.foreground,
        side: const BorderSide(color: SolvrColors.border),
        shape: flatShape,
      ),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      border: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: SolvrColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: SolvrColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.zero,
        borderSide: BorderSide(color: SolvrColors.foreground),
      ),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: SolvrColors.background,
      foregroundColor: SolvrColors.foreground,
      elevation: 0,
      shape: flatShape,
    ),
    dividerTheme: const DividerThemeData(
      color: SolvrColors.border,
      thickness: 1,
      space: 1,
    ),
  );
}
