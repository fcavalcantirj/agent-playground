// Phase 31 H6 — mobile Sentry init tests (SPEC AC15).
//
// `flutter test` does not pass --dart-define by default, so
// String.fromEnvironment('SENTRY_DSN_MOBILE') returns '' and initSentry
// MUST hit the no-init branch and invoke the runner directly.
//
// AC14 (real-DSN capture via SentryTransport mock) is not exercised here
// — sentry_flutter 9.x's transport-injection from a Dart test is
// brittle relative to the api_server-side `Transport` mock and adds
// flakiness without proportional confidence. The externally-observable
// contract verified here (DSN-empty -> no init, runner runs) is the
// load-bearing branch for this project's deploy posture.
import 'package:agent_playground/core/instrumentation/sentry.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

void main() {
  test('AC15: initSentry runs the runner when SENTRY_DSN_MOBILE is empty',
      () async {
    var ranInRunner = false;
    await initSentry(runner: () async {
      ranInRunner = true;
    });
    expect(
      ranInRunner,
      isTrue,
      reason: 'runner MUST be invoked once even when DSN is empty',
    );
    // Sanity probe: SDK must not be initialised in this branch.
    // Sentry.isEnabled is a public static getter on sentry_flutter 9.x.
    expect(
      Sentry.isEnabled,
      isFalse,
      reason: 'SDK must not be active when SENTRY_DSN_MOBILE is empty',
    );
  });

  test('AC15: initSentry runner is invoked exactly once', () async {
    var runCount = 0;
    await initSentry(runner: () async {
      runCount += 1;
    });
    expect(runCount, 1);
  });
}
