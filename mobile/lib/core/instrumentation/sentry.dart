// Phase 31 H6 (D-11, D-12, D-13, D-14) — sentry_flutter wrap-runner.
//
// Errors-only Sentry instrumentation. Mirrors the api_server-side
// `instrumentation/sentry.py` shape. Graceful no-op when
// SENTRY_DSN_MOBILE dart-define is empty/missing — runs the appRunner
// callback directly without initialising the SDK.
//
// The beforeSend filter drops DioException with response.statusCode < 500
// to protect the Free-tier quota (mobile equivalent of the api_server
// `_before_send` HTTPException<500 drop, T-31-02 mitigation).
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

Future<void> initSentry({required Future<void> Function() runner}) async {
  const dsn = String.fromEnvironment('SENTRY_DSN_MOBILE');
  const env = String.fromEnvironment('SENTRY_ENVIRONMENT', defaultValue: 'dev');
  const release = String.fromEnvironment('SENTRY_RELEASE');

  if (dsn.isEmpty) {
    debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)');
    await runner();
    return;
  }

  await SentryFlutter.init(
    (options) {
      options
        ..dsn = dsn
        ..environment = env
        ..tracesSampleRate = 0.0 // SPEC AC15 — errors only
        ..beforeSend = (event, hint) {
          // D-12 mobile equivalent: drop DioException with status < 500
          // (e.g. 401, 404, 429) to protect the Free-tier quota.
          final t = event.throwable;
          if (t is DioException) {
            final status = t.response?.statusCode;
            if (status != null && status < 500) {
              return null;
            }
          }
          return event;
        };
      if (release.isNotEmpty) options.release = release;
    },
    appRunner: runner,
  );
}
