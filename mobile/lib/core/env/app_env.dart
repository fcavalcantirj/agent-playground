// Phase 24 Plan 06 — env-config (D-43, D-44).
//
// BASE_URL is baked at compile time via --dart-define BASE_URL=...
// The dev sets the URL externally per target. README documents:
//   iOS Simulator:    http://localhost:8000
//   Android Emulator: http://10.0.2.2:8000
//   Real device LAN:  http://192.168.X.Y:8000
//   ngrok tunnel:     https://<id>.ngrok-free.app
//
// Per D-44 + feedback_env_config_outside_the_app.md: per-target switching
// happens at `flutter run` invocation, not at runtime. No runtime overlays,
// no menus, no in-app pickers — config is set externally.

class AppEnv {
  const AppEnv({required this.baseUrl});
  final Uri baseUrl;

  /// Read at boot. Crashes loud (StateError) on empty / malformed value.
  /// Default `http://localhost:8000` is the iOS Simulator path; Android
  /// emulator + LAN device paths require an explicit --dart-define.
  static AppEnv fromEnvironment() => fromValue(
        const String.fromEnvironment(
          'BASE_URL',
          defaultValue: 'http://localhost:8000',
        ),
      );

  /// Test seam: validate any string. Same StateError messages as the
  /// fromEnvironment path so tests cover the boot crashes.
  static AppEnv fromValue(String raw) {
    if (raw.isEmpty) {
      throw StateError(
        'BASE_URL is empty. Pass --dart-define=BASE_URL=http://... at flutter run.',
      );
    }
    final uri = Uri.tryParse(raw);
    if (uri == null ||
        !uri.hasScheme ||
        (!uri.isScheme('http') && !uri.isScheme('https'))) {
      throw StateError(
        'BASE_URL is malformed: "$raw". Must be http(s)://host[:port].',
      );
    }
    if (uri.host.isEmpty) {
      throw StateError(
        'BASE_URL is malformed: "$raw". Host component is empty.',
      );
    }
    return AppEnv(baseUrl: uri);
  }
}
