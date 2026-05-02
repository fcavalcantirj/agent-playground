// Phase 24 Plan 06 — Riverpod providers tree.
//
// RESEARCH Pitfall #1 (line 872): D-34 forbids `build_runner` for JSON
// codegen — it does NOT forbid `riverpod_generator`, which is an
// INDEPENDENT runner. Using @riverpod here is the 2026 community-default
// authoring style and does not regress D-34.

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/auth_interceptor.dart';
import 'package:agent_playground/core/api/log_interceptor.dart';
import 'package:agent_playground/core/auth/auth_event_bus.dart';
import 'package:agent_playground/core/env/app_env.dart';
import 'package:agent_playground/core/storage/secure_storage.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'providers.g.dart';

@Riverpod(keepAlive: true)
AppEnv appEnv(Ref ref) => AppEnv.fromEnvironment();

@Riverpod(keepAlive: true)
SecureStorage secureStorage(Ref ref) => SecureStorage();

@Riverpod(keepAlive: true)
AuthEventBus authEventBus(Ref ref) {
  final bus = AuthEventBus();
  ref.onDispose(bus.dispose);
  return bus;
}

@Riverpod(keepAlive: true)
Dio dio(Ref ref) {
  final env = ref.watch(appEnvProvider);
  final storage = ref.watch(secureStorageProvider);
  final bus = ref.watch(authEventBusProvider);

  final dio = Dio(
    BaseOptions(
      baseUrl: env.baseUrl.toString(),
      connectTimeout: const Duration(seconds: 10), // D-37
      receiveTimeout: const Duration(seconds: 30), // D-37
    ),
  );
  dio.interceptors.add(AuthInterceptor(storage, bus));
  if (kDebugMode) {
    dio.interceptors.add(const RedactingLogInterceptor());
  }
  ref.onDispose(dio.close);
  return dio;
}

@Riverpod(keepAlive: true)
ApiClient apiClient(Ref ref) => ApiClient(ref.watch(dioProvider));
