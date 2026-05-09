// Phase B Plan 11 Task 1 — TopUpScreen widget tests.
//
// Cases (per PLAN <behavior>):
//   - test_topup_screen_renders_5_packs_when_loaded
//   - test_topup_screen_shows_loading_indicator_while_packs_load
//   - test_topup_screen_shows_error_when_packs_load_fails
//   - test_pack_picker_calls_onSelect_with_pack_id_on_tap
//   - test_topup_inflight_widget_shows_mm_ss_timer
//
// PacksNotifier is overridden via Riverpod; CheckoutWebView is NOT
// invoked in these tests (real Navigator.push of a non-existent
// MaterialApp tree would explode). The pack-tap path therefore stops
// at the api.createPackCheckoutSession boundary — we don't need to
// drive the entire orchestrator from this screen test.

import 'dart:async';

import 'package:agent_playground/core/api/result.dart';
import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:agent_playground/features/billing/billing_providers.dart';
import 'package:agent_playground/features/billing/pack_picker_widget.dart';
import 'package:agent_playground/features/billing/topup_inflight_widget.dart';
import 'package:agent_playground/features/billing/topup_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

const _fivePacks = <Pack>[
  Pack(id: 'pack_5', label: r'$5', usdAmountCents: 500, creditCents: 500),
  Pack(id: 'pack_10', label: r'$10', usdAmountCents: 1000, creditCents: 1000),
  Pack(id: 'pack_25', label: r'$25', usdAmountCents: 2500, creditCents: 2500),
  Pack(id: 'pack_50', label: r'$50', usdAmountCents: 5000, creditCents: 5000),
  Pack(
    id: 'pack_100',
    label: r'$100',
    usdAmountCents: 10000,
    creditCents: 10000,
  ),
];

Widget _wrap(ProviderContainer container, Widget child) =>
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp(home: child),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('TopUpScreen', () {
    testWidgets('renders 5 packs when loaded', (tester) async {
      final container = ProviderContainer(
        overrides: [
          packsProvider.overrideWith(_StaticPacksNotifier.new),
        ],
      );
      addTearDown(container.dispose);

      await tester.pumpWidget(_wrap(container, const TopUpScreen()));
      await tester.pumpAndSettle();

      expect(find.byType(PackPickerWidget), findsOneWidget);
      // Each pack's label appears once.
      expect(find.text(r'$5'), findsOneWidget);
      expect(find.text(r'$10'), findsOneWidget);
      expect(find.text(r'$25'), findsOneWidget);
      expect(find.text(r'$50'), findsOneWidget);
      expect(find.text(r'$100'), findsOneWidget);
    });

    testWidgets('shows loading indicator while packs load', (tester) async {
      final container = ProviderContainer(
        overrides: [
          packsProvider.overrideWith(_PendingPacksNotifier.new),
        ],
      );
      addTearDown(container.dispose);

      await tester.pumpWidget(_wrap(container, const TopUpScreen()));
      await tester.pump(); // do not settle — packs never resolve.

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.byType(PackPickerWidget), findsNothing);
    });

    testWidgets('shows error when packs load fails', (tester) async {
      final container = ProviderContainer(
        overrides: [
          packsProvider.overrideWith(_ErrorPacksNotifier.new),
        ],
      );
      addTearDown(container.dispose);

      await tester.pumpWidget(_wrap(container, const TopUpScreen()));
      await tester.pumpAndSettle();

      expect(find.textContaining('Failed to load'), findsOneWidget);
      expect(find.byType(PackPickerWidget), findsNothing);
    });
  });

  group('PackPickerWidget', () {
    testWidgets('calls onSelect with pack on tap', (tester) async {
      Pack? tapped;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: PackPickerWidget(
              packs: _fivePacks,
              onSelect: (p) => tapped = p,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Tap the $25 pack via its label.
      await tester.tap(find.text(r'$25'));
      await tester.pumpAndSettle();

      expect(tapped, isNotNull);
      expect(tapped!.id, 'pack_25');
    });
  });

  group('TopUpInflightWidget', () {
    testWidgets('shows mm:ss timer + Confirming top-up… copy + Cancel',
        (tester) async {
      var cancelled = false;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TopUpInflightWidget(onCancel: () => cancelled = true),
          ),
        ),
      );
      await tester.pump(); // initial frame.
      expect(find.text('Confirming top-up…'), findsOneWidget);
      // mm:ss starts at 00:00.
      expect(find.text('00:00'), findsOneWidget);
      // Tick once forwards; widget rebuilds via Timer.periodic.
      await tester.pump(const Duration(seconds: 1));
      // Either 00:00 or 00:01 is acceptable — wall-clock granularity
      // depends on Stopwatch's sub-second precision; assert the
      // mm:ss SHAPE rather than the exact second.
      expect(
        find.byWidgetPredicate(
          (w) =>
              w is Text && (w.data?.startsWith(RegExp(r'\d{2}:').pattern) ?? false),
        ),
        findsAtLeastNWidgets(1),
      );

      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(cancelled, isTrue);
    });
  });
}

// ---------------------------------------------------------------------------
// Test seams.
// ---------------------------------------------------------------------------

class _StaticPacksNotifier extends PacksNotifier {
  @override
  Future<List<Pack>> build() async => _fivePacks;
}

class _PendingPacksNotifier extends PacksNotifier {
  @override
  Future<List<Pack>> build() => Completer<List<Pack>>().future;
}

class _ErrorPacksNotifier extends PacksNotifier {
  @override
  Future<List<Pack>> build() async {
    throw const ApiError(
      code: ErrorCode.network,
      message: 'no connection (test)',
    );
  }
}
