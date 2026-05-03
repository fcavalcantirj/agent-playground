// Phase 24 Plan 01 / Phase 25 Wave 1 — smoke test. Proves the scaffold
// compiles and the root widget renders without throwing.
//
// Phase 25 Wave 1 update: HealthzScreen was deleted; the default initial
// route is /login. LoginScreen does not auto-fire any HTTP (taps drive
// AuthService), so a rejecting Dio adapter is preserved as belt-and-braces
// — any unexpected dio call leaves no pending timer.

import 'package:agent_playground/app.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('SolvrLabsApp renders without throwing', (tester) async {
    // Inject a Dio whose adapter rejects every outbound request so the
    // /healthz call does not leave a 10s timer pending.
    final fakeDio = Dio(BaseOptions(baseUrl: 'http://test.invalid'))
      ..httpClientAdapter = _RejectingAdapter();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          dioProvider.overrideWith((ref) => fakeDio),
        ],
        child: const SolvrLabsApp(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(MaterialApp), findsOneWidget);
    expect(find.byType(Scaffold), findsOneWidget);
    fakeDio.close(force: true);
  });
}

class _RejectingAdapter implements HttpClientAdapter {
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<dynamic>? cancelFuture,
  ) async {
    throw DioException(
      requestOptions: options,
      type: DioExceptionType.connectionError,
      message: 'rejected in smoke test',
    );
  }

  @override
  void close({bool force = false}) {}
}
