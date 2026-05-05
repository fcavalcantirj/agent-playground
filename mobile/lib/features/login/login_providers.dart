// Phase 25 Wave 1 — Login screen Riverpod state providers.
//
// `loginPendingProvider` — null = idle, 'google'/'github' = button-in-flight
// (D-05). `loginErrorProvider` — non-null = inline red caption text (D-06).
// `showSignedOutBannerProvider` — true when arrived from a 401 → /login
// redirect (D-03 banner above buttons).
// `loginSuccessProvider` — set to the SessionUser on success; the router
// listens and replaces with /dashboard. Tests assert via container.listen.

import 'package:agent_playground/core/api/dtos.dart';
import 'package:flutter_riverpod/legacy.dart';

final loginPendingProvider = StateProvider<String?>((ref) => null);

final loginErrorProvider = StateProvider<String?>((ref) => null);

final showSignedOutBannerProvider = StateProvider<bool>((ref) => false);

final loginSuccessProvider = StateProvider<SessionUser?>((ref) => null);
