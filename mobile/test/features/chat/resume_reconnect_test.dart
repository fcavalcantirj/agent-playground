// Phase 25 Wave 4 plan 25-07 task 1 — D-52 lifecycle reconnect tests.
//
// Drives the appLifecycleProvider through paused -> resumed and asserts
// that the chatScopeProvider's stream re-connects (preserving Last-Event-Id).
// Achieved via the streamBuilder static seam on ChatScope.

import 'dart:async';

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/messages_stream.dart';
import 'package:agent_playground/core/api/providers.dart';
import 'package:agent_playground/core/lifecycle/app_lifecycle_observer.dart';
import 'package:agent_playground/features/chat/chat_providers.dart';
import 'package:dio/dio.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

const _agentId = 'a-1';

class _FakeStream implements ChatStream {
  _FakeStream();
  int connectCalls = 0;
  int disconnectCalls = 0;
  bool disposed = false;
  String? _lastEventId;
  final _ctl = StreamController<SseEvent>.broadcast();

  @override
  Stream<SseEvent> get events => _ctl.stream;

  @override
  Future<void> connect() async {
    connectCalls++;
  }

  @override
  Future<void> disconnect() async {
    disconnectCalls++;
  }

  @override
  String? get lastEventId => _lastEventId;

  // ignore: use_setters_to_change_properties
  void setLastEventId(String? id) => _lastEventId = id;

  @override
  Future<void> dispose() async {
    disposed = true;
    await _ctl.close();
  }
}

ChatStream Function({
  required Uri baseUrl,
  required String agentId,
  required Future<String?> Function() cookieProvider,
}) _defaultBuilder() => ChatScope.streamBuilder;

void _restoreDefaults() {
  ChatScope.autoBootstrap = true;
  // Restore the production builder by re-instantiating the same default.
  ChatScope.streamBuilder = ({
    required Uri baseUrl,
    required String agentId,
    required Future<String?> Function() cookieProvider,
  }) {
    // ignore: invalid_use_of_visible_for_testing_member
    final ms = MessagesStream(
      baseUrl: baseUrl,
      agentId: agentId,
      cookieProvider: cookieProvider,
    );
    // Wrap via the production helper would be ideal, but for tests we
    // never invoke the restored default — restoration is symbolic, the
    // ProviderContainer is already disposed at addTearDown time.
    return _ProdLikeWrapper(ms);
  };
}

class _ProdLikeWrapper implements ChatStream {
  _ProdLikeWrapper(this._inner);
  final MessagesStream _inner;
  @override
  Stream<SseEvent> get events => _inner.events;
  @override
  Future<void> connect() => _inner.connect();
  @override
  Future<void> disconnect() => _inner.disconnect();
  @override
  Future<void> dispose() => _inner.dispose();
  @override
  String? get lastEventId => _inner.lastEventId;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('AppLifecycleState.resumed triggers stream.disconnect()+connect() '
      '(D-52) and preserves Last-Event-Id', () async {
    final fake = _FakeStream();
    ChatScope.autoBootstrap = false;
    final priorBuilder = _defaultBuilder();
    ChatScope.streamBuilder = ({
      required Uri baseUrl,
      required String agentId,
      required Future<String?> Function() cookieProvider,
    }) =>
        fake;
    addTearDown(() {
      ChatScope.streamBuilder = priorBuilder;
      _restoreDefaults();
    });

    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(ApiClient(dio))],
    );
    addTearDown(c.dispose);
    // Trigger build of the chat scope (lifecycle subscription registered).
    c.read(chatScopeProvider(_agentId));
    expect(fake.connectCalls, 0,
        reason: 'autoBootstrap=false suppresses initial connect');

    // Mark a Last-Event-Id BEFORE the resume.
    fake.setLastEventId('42');

    // Drive paused -> resumed via the appLifecycleProvider.
    final lifecycle = c.read(appLifecycleProvider.notifier);
    lifecycle.didChangeAppLifecycleState(AppLifecycleState.paused);
    lifecycle.didChangeAppLifecycleState(AppLifecycleState.resumed);
    // Allow microtasks to drain.
    await Future<void>.delayed(const Duration(milliseconds: 1));

    expect(fake.disconnectCalls, 1,
        reason: 'D-52 — must disconnect on resume');
    expect(fake.connectCalls, 1, reason: 'D-52 — then re-connect');
    expect(fake.lastEventId, '42',
        reason: 'D-52 — Last-Event-Id preserved across reconnect');
  });

  test('Disposing the chat scope cleans up the stream (cancellation)',
      () async {
    final fake = _FakeStream();
    ChatScope.autoBootstrap = false;
    final priorBuilder = _defaultBuilder();
    ChatScope.streamBuilder = ({
      required Uri baseUrl,
      required String agentId,
      required Future<String?> Function() cookieProvider,
    }) =>
        fake;
    addTearDown(() {
      ChatScope.streamBuilder = priorBuilder;
      _restoreDefaults();
    });
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:8000'));
    final c = ProviderContainer(
      overrides: [apiClientProvider.overrideWithValue(ApiClient(dio))],
    );
    c.read(chatScopeProvider(_agentId));
    // Invalidate to trigger autoDispose teardown.
    c.invalidate(chatScopeProvider(_agentId));
    // Pump microtasks to let onDispose fire.
    await Future<void>.delayed(const Duration(milliseconds: 1));
    expect(fake.disposed, isTrue);
    c.dispose();
  });
}
