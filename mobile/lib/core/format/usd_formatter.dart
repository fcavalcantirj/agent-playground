// Phase 27 Change 3b — auto-precision USD formatter (D-24).
//
// Server returns USD as a decimal String (D-14 — NUMERIC(14,8) in Postgres).
// Precision step:
//   value == 0       → "$0"
//   0 < value < 0.01 → 4 decimals (sub-cent visible)
//   value >= 0.01    → 2 decimals (cent / dollar)
// Threshold flips at exactly 0.01 — "0.009999" stays in sub-cent (4-decimal) mode.

import 'package:intl/intl.dart';

final NumberFormat _subCent = NumberFormat.currency(
  locale: 'en_US',
  symbol: r'$',
  decimalDigits: 4,
);

final NumberFormat _cent = NumberFormat.currency(
  locale: 'en_US',
  symbol: r'$',
  decimalDigits: 2,
);

String formatUsd(String decimal) {
  final value = double.parse(decimal);
  if (value == 0) return r'$0';
  if (value < 0.01) return _subCent.format(value);
  return _cent.format(value);
}
