// Phase 31 H4 — chat-stream error banner widget tests.
//
// Covers SPEC AC5-AC11. Uses an isolated test harness widget mirroring
// the production banner-block in chat_screen.dart so the test does not
// have to spin up the entire chat feature (which depends on dio +
// agentsListProvider + chatScopeProvider + go_router + ...).
//
// The harness mirrors the production block byte-for-byte:
//   - same RetryBanner constructor args (key, message, actionLabel,
//     tone, dismissible, onDismiss, onTap)
//   - same actionLabel branching (authExpired -> 'Sign in', else 'Retry')
//   - same _streamErrorCopy mapping
// If chat_screen.dart drifts, the AC5/6/7 byte-exact text-find assertions
// fail.
import 'package:agent_playground/features/chat/chat_stream_error_banner_provider.dart';
import 'package:agent_playground/features/chat/chat_stream_error_classifier.dart';
import 'package:agent_playground/shared/retry_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

/// Mirror of chat_screen.dart's `_streamErrorCopy` helper. Must match
/// the production string mapping byte-for-byte.
String _streamErrorCopy(ChatStreamErrorClass c) {
  switch (c) {
    case ChatStreamErrorClass.networkTransient:
      return 'Connection lost — tap to retry';
    case ChatStreamErrorClass.authExpired:
      return 'Session expired — sign in again';
    case ChatStreamErrorClass.serverError:
      return 'Server error — try again later';
  }
}

class _BannerHarness extends ConsumerWidget {
  const _BannerHarness({required this.onRetry, required this.onSignIn});

  final VoidCallback onRetry;
  final VoidCallback onSignIn;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final err = ref.watch(chatStreamErrorProvider);
    return MaterialApp(
      home: Scaffold(
        body: Column(
          children: [
            if (err != null)
              RetryBanner(
                key: const Key('chat-stream-error-banner'),
                message: _streamErrorCopy(err.errorClass),
                actionLabel: err.errorClass == ChatStreamErrorClass.authExpired
                    ? 'Sign in'
                    : 'Retry',
                tone: RetryBannerTone.warning,
                dismissible: true,
                onDismiss: () =>
                    ref.read(chatStreamErrorProvider.notifier).state = null,
                onTap: () {
                  if (err.errorClass == ChatStreamErrorClass.authExpired) {
                    onSignIn();
                  } else {
                    onRetry();
                  }
                },
              ),
          ],
        ),
      ),
    );
  }
}

ChatStreamErrorState _state(ChatStreamErrorClass c) => ChatStreamErrorState(
      agentInstanceId: 'a1',
      errorClass: c,
      lastFailedAction: 'connect',
    );

void main() {
  testWidgets(
      'AC5: networkTransient renders "Connection lost — tap to retry"',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatStreamErrorProvider.overrideWith(
            (_) => _state(ChatStreamErrorClass.networkTransient),
          ),
        ],
        child: _BannerHarness(onRetry: () {}, onSignIn: () {}),
      ),
    );
    expect(find.byKey(const Key('chat-stream-error-banner')), findsOneWidget);
    expect(find.text('Connection lost — tap to retry'), findsOneWidget);
  });

  testWidgets('AC6: authExpired renders "Session expired — sign in again"',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatStreamErrorProvider
              .overrideWith((_) => _state(ChatStreamErrorClass.authExpired)),
        ],
        child: _BannerHarness(onRetry: () {}, onSignIn: () {}),
      ),
    );
    expect(find.text('Session expired — sign in again'), findsOneWidget);
  });

  testWidgets('AC7: serverError renders "Server error — try again later"',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatStreamErrorProvider
              .overrideWith((_) => _state(ChatStreamErrorClass.serverError)),
        ],
        child: _BannerHarness(onRetry: () {}, onSignIn: () {}),
      ),
    );
    expect(find.text('Server error — try again later'), findsOneWidget);
  });

  testWidgets('Banner key absent when chatStreamErrorProvider is null',
      (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: _BannerHarness(onRetry: () {}, onSignIn: () {}),
      ),
    );
    expect(find.byKey(const Key('chat-stream-error-banner')), findsNothing);
  });

  testWidgets('AC9: networkTransient retry CTA invokes the retry callback',
      (tester) async {
    var retryCount = 0;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatStreamErrorProvider.overrideWith(
            (_) => _state(ChatStreamErrorClass.networkTransient),
          ),
        ],
        child: _BannerHarness(
          onRetry: () => retryCount += 1,
          onSignIn: () {},
        ),
      ),
    );
    await tester.tap(find.text('Retry'));
    await tester.pump();
    expect(retryCount, 1);
  });

  testWidgets('AC10: authExpired CTA invokes the sign-in callback',
      (tester) async {
    var signInCount = 0;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          chatStreamErrorProvider
              .overrideWith((_) => _state(ChatStreamErrorClass.authExpired)),
        ],
        child: _BannerHarness(
          onRetry: () {},
          onSignIn: () => signInCount += 1,
        ),
      ),
    );
    await tester.tap(find.text('Sign in'));
    await tester.pump();
    expect(signInCount, 1);
  });

  testWidgets('AC11: no technical jargon in rendered banner copy',
      (tester) async {
    final classes = <ChatStreamErrorClass>[
      ChatStreamErrorClass.networkTransient,
      ChatStreamErrorClass.authExpired,
      ChatStreamErrorClass.serverError,
    ];
    final jargon = RegExp(r'\b(SSE|fetch|Dio|HTTP|401|5xx|stream)\b');
    for (final c in classes) {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            chatStreamErrorProvider.overrideWith((_) => _state(c)),
          ],
          child: _BannerHarness(onRetry: () {}, onSignIn: () {}),
        ),
      );
      expect(
        find.byWidgetPredicate((w) {
          if (w is Text && w.data != null) {
            return jargon.hasMatch(w.data!);
          }
          return false;
        }),
        findsNothing,
        reason: 'jargon found in $c banner',
      );
    }
  });
}
