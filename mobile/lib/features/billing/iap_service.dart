// IAP service — thin wrapper over the RevenueCat SDK (purchases_flutter).
//
// Constructor takes the userId so RC's appUserID matches our user UUID;
// that's how our /v1/billing/revenuecat/webhook resolves an event to a
// row in the users table. Without the matching userId the webhook can't
// credit the right account.
//
// The wrapper is GRACEFUL when the platform key is empty (e.g. dev /
// web-only builds). `init` becomes a no-op, `getOfferings` returns null,
// and `purchase` throws a typed `IapNotConfigured` error so the caller
// can show a "Sign in to billing on the web for now" message instead
// of crashing.

import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;
import 'package:flutter/services.dart' show PlatformException;
import 'package:purchases_flutter/purchases_flutter.dart';

/// Compile-time dart-defines populated by mobile/scripts/release.sh from
/// prod /opt/solvr-labs/agent-playground/deploy/.env.prod. Empty in dev
/// unless overridden manually.
const String _rcApiKeyIOS =
    String.fromEnvironment('REVENUECAT_API_KEY_IOS');
const String _rcApiKeyAndroid =
    String.fromEnvironment('REVENUECAT_API_KEY_ANDROID');


/// Raised by [IapService.purchase] / [IapService.getOfferings] when the
/// RC SDK isn't configured for the current platform. Caller should fall
/// back to a web-link or a "billing unavailable" message.
class IapNotConfigured implements Exception {
  IapNotConfigured(this.reason);
  final String reason;
  @override
  String toString() => 'IapNotConfigured: $reason';
}


/// Outcome of [IapService.purchase].
enum IapPurchaseStatus {
  /// User completed payment; the store confirmed and RC will fire a
  /// webhook to our server. Caller should poll /v1/billing/balance for
  /// the credit to land (typically 5-15s).
  purchased,
  /// User cancelled the purchase sheet — no payment was made.
  cancelled,
  /// Network / SDK error during purchase. Caller should show an error.
  error,
}


class IapService {
  IapService._();
  static final IapService instance = IapService._();

  bool _initialized = false;

  /// Returns the platform's SDK key (or empty string when not configured).
  /// Web always returns "" — RC has no web SDK and we keep Stripe for web.
  String get _platformApiKey {
    if (kIsWeb) return '';
    if (Platform.isIOS) return _rcApiKeyIOS;
    if (Platform.isAndroid) return _rcApiKeyAndroid;
    return '';
  }

  /// True when the RC SDK is configured for the current platform. False
  /// on web, or when the dart-define for this platform is empty.
  bool get enabled => _platformApiKey.isNotEmpty;

  /// Initialize the RC SDK. Idempotent — repeated calls during a session
  /// are no-ops. MUST be called after the user has signed in so the
  /// appUserID is tied to our user UUID for webhook attribution.
  ///
  /// Returns silently when [enabled] is false; the rest of the surface
  /// will throw `IapNotConfigured` so the UI can degrade gracefully.
  Future<void> init({required String userId}) async {
    if (_initialized) return;
    if (!enabled) return;
    if (kDebugMode) {
      await Purchases.setLogLevel(LogLevel.warn);
    }
    await Purchases.configure(
      PurchasesConfiguration(_platformApiKey)..appUserID = userId,
    );
    _initialized = true;
  }

  /// Tell RC that the active user changed (e.g. after a fresh sign-in
  /// without an app relaunch). Anchors subsequent purchases to the
  /// correct AP user_id.
  Future<void> identify(String userId) async {
    if (!enabled) return;
    if (!_initialized) {
      await init(userId: userId);
      return;
    }
    await Purchases.logIn(userId);
  }

  /// Anonymous-out — call on sign-out so a subsequent signed-out anon
  /// purchase isn't auto-attributed to the previous user.
  Future<void> logout() async {
    if (!enabled || !_initialized) return;
    await Purchases.logOut();
  }

  /// Fetch the current offerings from RC's catalog. Returns null when
  /// the SDK isn't enabled (web / dev without keys). Throws on SDK errors
  /// — those should be surfaced as a "couldn't load IAP catalog" UI state.
  Future<Offerings?> getOfferings() async {
    if (!enabled) return null;
    if (!_initialized) {
      throw IapNotConfigured(
        'IapService.init() must be called before getOfferings()',
      );
    }
    return Purchases.getOfferings();
  }

  /// Launch the native store sheet for [package]. The user is presented
  /// with Apple/Google's native confirmation UI and the result lands
  /// here as an [IapPurchaseStatus].
  ///
  /// On [IapPurchaseStatus.purchased], the RC SDK has already settled
  /// with the store. RC's server fires a webhook to our backend within
  /// ~5-15s; the caller should poll /v1/billing/balance until the
  /// credit lands (mirror existing topup_screen.dart polling).
  Future<IapPurchaseStatus> purchase(Package package) async {
    if (!enabled) {
      throw IapNotConfigured('IAP not configured for this platform');
    }
    try {
      await Purchases.purchase(PurchaseParams.package(package));
      return IapPurchaseStatus.purchased;
    } on PlatformException catch (e) {
      final errorCode = PurchasesErrorHelper.getErrorCode(e);
      if (errorCode == PurchasesErrorCode.purchaseCancelledError) {
        return IapPurchaseStatus.cancelled;
      }
      return IapPurchaseStatus.error;
    } on Exception {
      return IapPurchaseStatus.error;
    }
  }

  /// Apple App Store Guideline requirement — restore previously-purchased
  /// products on demand. Refreshes RC's CustomerInfo, which our backend
  /// reconciles via the next webhook (RC re-emits INITIAL_PURCHASE on
  /// restore for non-consumables / subs; consumable packs are already
  /// credited so this is mostly a sub-tier sanity check).
  Future<void> restorePurchases() async {
    if (!enabled) {
      throw IapNotConfigured('IAP not configured for this platform');
    }
    await Purchases.restorePurchases();
  }
}
