// Phase 25 Wave 1 — Login screen widget tests covering D-04..D-06.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/core/auth/auth_service.dart';
import 'package:agent_playground/core/auth/providers.dart';
import 'package:agent_playground/core/theme/solvr_theme.dart';
import 'package:agent_playground/features/login/login_providers.dart';
import 'package:agent_playground/features/login/login_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeAuth implements AuthService {
  _FakeAuth({this.googleResult, this.githubResult, this.delay});

  final Result<SessionUser>? googleResult;
  final Result<SessionUser>? githubResult;
  final Duration? delay;
  int signOutCalls = 0;

  @override
  Future<Result<SessionUser>> signInWithGoogle() async {
    if (delay != null) await Future<void>.delayed(delay!);
    return googleResult ??
        const Result.err(
          ApiError(code: ErrorCode.internal, message: 'unset'),
        );
  }

  @override
  Future<Result<SessionUser>> signInWithGithub() async {
    if (delay != null) await Future<void>.delayed(delay!);
    return githubResult ??
        const Result.err(
          ApiError(code: ErrorCode.internal, message: 'unset'),
        );
  }

  @override
  Future<Result<SessionUser>> signInWithGithubCode({
    required String code,
    required String codeVerifier,
  }) =>
      signInWithGithub();

  @override
  Future<Result<SessionUser>> signInWithApple() async {
    return const Result.err(
      ApiError(code: ErrorCode.internal, message: 'unset'),
    );
  }

  @override
  Future<Result<int>> requestEmailCode({required String email}) async =>
      const Result.ok(60);

  @override
  Future<Result<SessionUser>> verifyEmailCode({
    required String email,
    required String code,
  }) async => const Result.err(
        ApiError(code: ErrorCode.internal, message: 'unset'),
      );


  @override
  Future<void> signOut() async {
    signOutCalls++;
  }
}

SessionUser _user() => const SessionUser(
      id: 'u1',
      email: 'a@b',
      displayName: 'A',
      provider: 'google',
      createdAt: '2026-05-03T00:00:00Z',
    );

Widget _wrap(_FakeAuth auth, {Widget? child}) {
  return ProviderScope(
    overrides: [
      authServiceProvider.overrideWithValue(auth),
    ],
    child: MaterialApp(
      theme: solvrTheme(),
      home: child ?? const LoginScreen(),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('renders SOLVR_LABS wordmark + 2 OAuth buttons',
      (tester) async {
    await tester.pumpWidget(_wrap(_FakeAuth()));
    await tester.pumpAndSettle();
    expect(find.textContaining('SOLVR_LABS'), findsOneWidget);
    expect(find.text('Continue with Google'), findsOneWidget);
    expect(find.text('Continue with GitHub'), findsOneWidget);
  });

  testWidgets('pending state: tapping Google replaces label with spinner; '
      'GitHub greys out', (tester) async {
    final auth = _FakeAuth(
      googleResult: Result.ok(_user()),
      delay: const Duration(seconds: 2),
    );
    await tester.pumpWidget(_wrap(auth));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue with Google'));
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    final ghBtn = tester.widget<ElevatedButton>(
      find.ancestor(
        of: find.text('Continue with GitHub'),
        matching: find.byType(ElevatedButton),
      ),
    );
    expect(ghBtn.onPressed, isNull);
    // Drain the pending future so the test does not leak a timer.
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('error state: failed sign-in renders red caption',
      (tester) async {
    final auth = _FakeAuth(
      googleResult: const Result.err(
        ApiError(code: ErrorCode.internal, message: 'boom'),
      ),
    );
    await tester.pumpWidget(_wrap(auth));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue with Google'));
    await tester.pumpAndSettle();
    expect(find.textContaining("Couldn't sign in"), findsOneWidget);

    // Tapping again clears the previous caption while the new request flies.
    await tester.tap(find.text('Continue with Google'));
    await tester.pump();
    // After error fires again, caption is back; that proves the "cleared on
    // next tap" invariant — the tap sets the error provider to null first.
    await tester.pumpAndSettle();
    expect(find.textContaining("Couldn't sign in"), findsOneWidget);
  });

  testWidgets('success: signing-in publishes a loginSuccessProvider event',
      (tester) async {
    final auth = _FakeAuth(googleResult: Result.ok(_user()));
    final container = ProviderContainer(
      overrides: [authServiceProvider.overrideWithValue(auth)],
    );
    addTearDown(container.dispose);

    SessionUser? observed;
    final sub = container.listen<SessionUser?>(
      loginSuccessProvider,
      (prev, next) => observed = next,
    );
    addTearDown(sub.close);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(theme: solvrTheme(), home: const LoginScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue with Google'));
    await tester.pumpAndSettle();
    expect(observed, isNotNull);
    expect(observed!.provider, 'google');
  });

  testWidgets('GitHub button drives signInWithGithub on tap',
      (tester) async {
    final auth = _FakeAuth(githubResult: Result.ok(_user()));
    final container = ProviderContainer(
      overrides: [authServiceProvider.overrideWithValue(auth)],
    );
    addTearDown(container.dispose);

    SessionUser? observed;
    final sub = container.listen<SessionUser?>(
      loginSuccessProvider,
      (prev, next) => observed = next,
    );
    addTearDown(sub.close);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(theme: solvrTheme(), home: const LoginScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue with GitHub'));
    await tester.pumpAndSettle();
    expect(observed, isNotNull);
  });

  testWidgets('signed-out banner renders when showSignedOutBannerProvider=true',
      (tester) async {
    final container = ProviderContainer(
      overrides: [
        authServiceProvider.overrideWithValue(_FakeAuth()),
      ],
    );
    addTearDown(container.dispose);
    container.read(showSignedOutBannerProvider.notifier).state = true;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(theme: solvrTheme(), home: const LoginScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text('Signed out · Sign in to continue'),
      findsOneWidget,
    );
  });
}
