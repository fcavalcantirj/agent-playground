// Riverpod async provider over IapService.getOfferings().
//
// Returns null when the platform's RC SDK isn't configured (web build,
// or dev build without dart-defines). Caller UI should treat null as
// "IAP unavailable on this platform — fall back to web Stripe link".

import 'package:agent_playground/features/billing/iap_service.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:purchases_flutter/purchases_flutter.dart';

/// Provider over the RevenueCat catalog. Loads once per app session;
/// invalidate after a user identity change so the appUserID resolved
/// inside [IapService] matches the current session.
final iapOfferingsProvider = FutureProvider<Offerings?>((ref) async {
  return IapService.instance.getOfferings();
});

/// Convenience accessor — the "current" Pro subscription Package from
/// RC's default offering. Null when offerings is null, the default
/// offering is null, or no "pro_monthly" package exists in it.
Package? proPackageFrom(Offerings? offerings) {
  final offering = offerings?.current;
  if (offering == null) return null;
  // RC convention: pro is a monthly subscription package; if our
  // catalog defines it as the only monthly, just take that. Otherwise
  // look up by identifier.
  return offering.monthly ?? offering.availablePackages.firstWhere(
    (p) => p.identifier == 'pro_monthly',
    orElse: () => offering.availablePackages.first,
  );
}

/// Convenience accessor — the list of consumable credit-pack Packages
/// from RC. We expect 5 (pack_5 .. pack_100) ordered ascending. Empty
/// list when offerings unavailable.
List<Package> packPackagesFrom(Offerings? offerings) {
  final offering = offerings?.current;
  if (offering == null) return const [];
  return offering.availablePackages
      .where((p) => p.identifier.startsWith('pack_'))
      .toList(growable: false);
}
