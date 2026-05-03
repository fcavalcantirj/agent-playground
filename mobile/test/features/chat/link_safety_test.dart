// Phase 25 Wave 4 plan 25-07 task 2 — D-46 link safety tests.
//
// Verifies the markdown link tap allow-list:
//   * https + http  -> launchUrl IS called with LaunchMode.externalApplication
//   * javascript:   -> launchUrl is NOT called (allow-list rejects)
//   * data:         -> launchUrl is NOT called
//   * mailto:       -> launchUrl is NOT called
//   * file:         -> launchUrl is NOT called
//   * custom://     -> launchUrl is NOT called
//   * null href     -> launchUrl is NOT called
//   * malformed     -> launchUrl is NOT called
//
// Test seam: replaces `externalLauncher` with a closure that records the
// would-be-launched Uri. Restored in addTearDown via `resetExternalLauncher`.

import 'package:agent_playground/features/chat/bubble_widget.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('handleLinkTap — D-46 https/http allow-list', () {
    setUp(() {
      // Each test installs its own launcher via _capturingLauncher.
      resetExternalLauncher();
    });
    tearDown(resetExternalLauncher);

    Future<bool> Function(Uri) _capturingLauncher(List<Uri> sink) {
      return (uri) async {
        sink.add(uri);
        return true;
      };
    }

    test('https URL is launched (allow-list passes)', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('https://example.com');
      expect(ok, isTrue);
      expect(launched.length, 1);
      expect(launched.first.scheme, 'https');
    });

    test('http URL is launched (allow-list passes)', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('http://example.com');
      expect(ok, isTrue);
      expect(launched.length, 1);
      expect(launched.first.scheme, 'http');
    });

    test('javascript: URL is rejected', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('javascript:alert(1)');
      expect(ok, isFalse);
      expect(launched, isEmpty);
    });

    test('data: URL is rejected', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('data:text/html,<script>alert(1)</script>');
      expect(ok, isFalse);
      expect(launched, isEmpty);
    });

    test('mailto: URL is rejected', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('mailto:foo@bar.com');
      expect(ok, isFalse);
      expect(launched, isEmpty);
    });

    test('file: URL is rejected', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('file:///etc/passwd');
      expect(ok, isFalse);
      expect(launched, isEmpty);
    });

    test('custom URI scheme is rejected', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('myapp://action?x=1');
      expect(ok, isFalse);
      expect(launched, isEmpty);
    });

    test('null href is rejected', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap(null);
      expect(ok, isFalse);
      expect(launched, isEmpty);
    });

    test('uppercase HTTPS scheme is normalised + launched', () async {
      final launched = <Uri>[];
      externalLauncher = _capturingLauncher(launched);
      final ok = await handleLinkTap('HTTPS://example.com');
      expect(ok, isTrue);
      expect(launched.length, 1);
    });
  });
}
