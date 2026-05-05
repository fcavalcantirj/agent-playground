// Phase 27 Change 3b Wave 1 — auto-precision USD formatter (D-24).
//
// Decision rules (locked in 27-CHANGE-3B-PLAN.md):
//   - value == 0       → "$0"          (no decimals)
//   - 0 < value < 0.01 → 4 decimals    (sub-cent visible: "$0.0034")
//   - value >= 0.01    → 2 decimals    (cent/dollar:    "$0.04", "$1.23")
//   - thousands grouping via intl: "$1,234.56"
//   - boundary: "0.009999" still < 0.01 → 4-decimal mode → "$0.0100"
//     (precision flips ONLY when the value crosses 0.01 exactly)
//
// Input is the API's decimal string (D-14 — server returns USD as String).

import 'package:agent_playground/core/format/usd_formatter.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('formatUsd', () {
    test('zero renders as "\$0"', () {
      expect(formatUsd('0'), r'$0');
    });

    test('sub-cent value uses 4 decimals', () {
      expect(formatUsd('0.0034'), r'$0.0034');
    });

    test('cent-range value uses 2 decimals', () {
      expect(formatUsd('0.04'), r'$0.04');
    });

    test('dollar value uses 2 decimals', () {
      expect(formatUsd('1.23'), r'$1.23');
    });

    test('thousands grouping uses commas', () {
      expect(formatUsd('1234.56'), r'$1,234.56');
    });

    test('boundary: "0.009999" stays in sub-cent (4-decimal) mode', () {
      // 0.009999 < 0.01 → 4 decimals. Rounds up to "0.0100".
      // Locked decision: precision flips ONLY when value >= 0.01.
      expect(formatUsd('0.009999'), r'$0.0100');
    });

    test('boundary: "0.01" flips to cent (2-decimal) mode', () {
      expect(formatUsd('0.01'), r'$0.01');
    });

    test('large value with grouping', () {
      expect(formatUsd('123456.78'), r'$123,456.78');
    });
  });
}
