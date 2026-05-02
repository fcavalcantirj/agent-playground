// SPIKE (Phase 24 D-46) — Flutter ↔ Phase 23 backend 9-step round-trip.
//
// Proves end-to-end against a REAL local api_server + REAL Docker + REAL
// OpenRouter that the foundation supports the Phase 25 chat UI:
//   - typed dio client + cookie injection (D-35)
//   - Idempotency-Key + replay (D-36 + Phase 23 D-09)
//   - SSE delivery + Last-Event-Id resume (D-33 + RESEARCH Pitfall #2)
//   - GET /messages parity with SSE-delivered content (Phase 23 D-08)
//   - clean stop (D-48)
//
// PASS criterion: all 9 steps green; spike artifact at
// spikes/flutter-api-roundtrip.md captured with verdict: PASS (Plan 10).
//
// FAIL → Phase 24 exit gate fails (D-53); Phase 25 plan-checker blocks.
//
// Local-only per D-53 (requires macOS + booted simulator/emulator + Docker
// + OpenRouter network). Not run in CI (.github/workflows/mobile.yml
// skips integration_test).
//
// Steps (D-46):
//   Step 1: POST /v1/runs (BYOK + recipe=nullclaw + model=anthropic/claude-haiku-4-5)
//   Step 2: POST /v1/agents/:id/start (channel='inapp')
//   Step 3: SSE connect on GET /v1/agents/:id/messages/stream
//   Step 4: POST /v1/agents/:id/messages with Idempotency-Key
//   Step 5: SSE delivers an assistant reply within bot timeout
//   Step 6: GET /v1/agents/:id/messages?limit=10 — parity with SSE
//   Step 7: POST /messages with SAME Idempotency-Key → SAME message_id
//   Step 8: disconnect mid-stream + reconnect with Last-Event-Id → no dupes
//   Step 9: POST /v1/agents/:id/stop

import 'package:agent_playground/core/api/api_client.dart';
import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/log_interceptor.dart';
import 'package:agent_playground/core/api/messages_stream.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:uuid/uuid.dart';

import 'spike_helpers.dart';

const _baseUrl = String.fromEnvironment('BASE_URL');
const _sessionId = String.fromEnvironment('SESSION_ID');
const _byokKey = String.fromEnvironment('OPENROUTER_KEY');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    '9-step round-trip — D-46 (Phase 24 exit gate)',
    (tester) async {
      // ----- Pre-flight: env vars are required (D-50). -----
      expect(
        _baseUrl,
        isNotEmpty,
        reason: 'BASE_URL not set. See `make spike` usage.',
      );
      expect(
        _sessionId,
        isNotEmpty,
        reason: 'SESSION_ID not set. Paste ap_session cookie from browser.',
      );
      expect(
        _byokKey,
        isNotEmpty,
        reason: 'OPENROUTER_KEY not set. Pass via --dart-define.',
      );

      // Build dio with cookie pre-injected via interceptor (no secure_storage
      // path on spike — D-49). Same connect/receive timeouts as production
      // (Plan 06 / D-37).
      final dio = Dio(
        BaseOptions(
          // _baseUrl is a const-evaluated String.fromEnvironment that the
          // analyzer sees as '' at static-analysis time, matching
          // BaseOptions.baseUrl's default. At runtime the expect() above
          // guarantees it's non-empty.
          // ignore: avoid_redundant_argument_values
          baseUrl: _baseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 30),
        ),
      );
      dio.interceptors.addAll([
        InterceptorsWrapper(
          onRequest: (options, handler) {
            options.headers['Cookie'] = 'ap_session=$_sessionId';
            handler.next(options);
          },
        ),
        const RedactingLogInterceptor(),
      ]);
      final api = ApiClient(dio);

      // -------------------------------------------------------------
      // Step 1: POST /v1/runs
      // -------------------------------------------------------------
      final ts = DateTime.now().millisecondsSinceEpoch;
      final agentName = 'spike-roundtrip-$ts-${shortRandHex()}';
      final runResult = await api.runs(
        body: RunRequest(
          recipeName: 'nullclaw',
          model: 'anthropic/claude-haiku-4-5',
          agentName: agentName,
        ),
        byokOpenRouterKey: _byokKey,
      );
      final runResp = expectOk(runResult, step: 1);
      final agentId = runResp.agentInstanceId;
      expect(agentId, isNotEmpty);

      // -------------------------------------------------------------
      // Step 2: POST /v1/agents/:id/start (channel='inapp')
      // -------------------------------------------------------------
      final startRes = await api.start(
        agentId: agentId,
        byokOpenRouterKey: _byokKey,
      );
      expectOk(startRes, step: 2);

      // -------------------------------------------------------------
      // Step 3: connect SSE on /v1/agents/:id/messages/stream
      // -------------------------------------------------------------
      final stream = MessagesStream(
        baseUrl: Uri.parse(_baseUrl),
        agentId: agentId,
        cookieProvider: () async => _sessionId,
      );
      final received = <SseEvent>[];
      final sseSub = stream.events.listen(
        received.add,
        onError: (Object e, _) => fail('SSE error in step 3+: $e'),
      );
      await stream.connect();
      // Give SSE 2 seconds to settle the connection before posting.
      await Future<void>.delayed(const Duration(seconds: 2));

      // -------------------------------------------------------------
      // Step 4: POST /v1/agents/:id/messages with Idempotency-Key
      // -------------------------------------------------------------
      final idemKey = const Uuid().v4();
      final ackRes = await api.postMessage(
        agentId: agentId,
        content: 'spike roundtrip',
        idempotencyKey: idemKey,
      );
      final ack = expectOk(ackRes, step: 4);
      final messageId = ack.messageId;
      expect(messageId, isNotEmpty);

      // -------------------------------------------------------------
      // Step 5: SSE delivers an assistant reply within bot timeout
      // -------------------------------------------------------------
      final firstReply = await waitForOutbound(received);
      final firstReplyText = extractAssistantContent(firstReply.data);
      expect(
        firstReplyText,
        isNotEmpty,
        reason: 'Step 5: assistant reply was empty',
      );
      expect(
        stream.lastEventId,
        isNotNull,
        reason:
            'Step 5: MessagesStream must capture event.id from inapp_outbound',
      );

      // -------------------------------------------------------------
      // Step 6: GET /messages?limit=10 parity (Phase 23 D-08)
      // -------------------------------------------------------------
      final histRes = await api.messagesHistory(agentId: agentId, limit: 10);
      final hist = expectOk(histRes, step: 6);
      // History order is ASC oldest→newest (Phase 23 D-04). The last
      // assistant row must byte-equal the SSE-delivered content.
      final assistants =
          hist.messages.where((m) => m.role == 'assistant').toList();
      expect(
        assistants,
        isNotEmpty,
        reason: 'Step 6: history has no assistant rows',
      );
      expect(
        assistants.last.content,
        firstReplyText,
        reason:
            'Step 6: history assistant content does not match SSE delivery',
      );

      // -------------------------------------------------------------
      // Step 7: idempotency replay — same key returns same message_id
      // -------------------------------------------------------------
      final replayRes = await api.postMessage(
        agentId: agentId,
        content: 'spike roundtrip',
        idempotencyKey: idemKey,
      );
      final replayAck = expectOk(replayRes, step: 7);
      expect(replayAck.messageId, messageId,
          reason:
              'Step 7: idempotency replay returned a DIFFERENT message_id');

      // -------------------------------------------------------------
      // Step 8: disconnect mid-stream + reconnect with Last-Event-Id
      // -------------------------------------------------------------
      final lastSeenId = stream.lastEventId;
      expect(
        lastSeenId,
        isNotNull,
        reason: 'Step 8 pre-condition: stream.lastEventId is null',
      );
      final receivedCountBeforeResume = received.length;
      await stream.disconnect();
      // Cursor MUST survive disconnect.
      expect(
        stream.lastEventId,
        lastSeenId,
        reason:
            'Step 8: disconnect cleared lastEventId — Plan 05 regression',
      );
      await stream.connect();
      await Future<void>.delayed(const Duration(seconds: 2));

      // Send a NEW message so the resumed stream gets a new event past
      // the cursor.
      final idemKey2 = const Uuid().v4();
      final ack2Res = await api.postMessage(
        agentId: agentId,
        content: 'after-resume',
        idempotencyKey: idemKey2,
      );
      expectOk(ack2Res, step: 8);

      // Wait for the next inapp_outbound past the resume cursor.
      await waitForOutbound(received, afterIndex: receivedCountBeforeResume);

      // Verify NO duplicate of the first reply landed after the resume.
      final duplicates = received
          .skip(receivedCountBeforeResume)
          .where((e) => e.id == lastSeenId)
          .toList();
      expect(duplicates, isEmpty,
          reason:
              'Step 8: Last-Event-Id resume produced a duplicate of cursor');

      // -------------------------------------------------------------
      // Step 9: POST /v1/agents/:id/stop (D-48 cleanup)
      // -------------------------------------------------------------
      final stopRes = await api.stop(agentId: agentId);
      expectOk(stopRes, step: 9);

      // ----- Cleanup -----
      await sseSub.cancel();
      await stream.dispose();
      dio.close(force: true);
    },
    // D-55 half-day max — 15 min hard ceiling per run
    timeout: const Timeout(Duration(minutes: 15)),
  );
}
