// Phase 24 Plan 01 — smoke test. Proves the scaffold compiles and the root
// widget renders.
//
// Plan 24-06 update: HealthzScreen.initState fires a real /healthz call on
// boot. The smoke test overrides `dioProvider` with a Dio whose adapter
// rejects every outbound request immediately, so the widget tree settles
// without leaving a 10s timer pending. The real /healthz call is exercised
// on real infra by the Plan 24-09 spike (D-46).

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

