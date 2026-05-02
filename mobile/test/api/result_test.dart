// Phase 24 Plan 03 — sealed Result exhaustiveness gate.

import 'package:agent_playground/core/api/result.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('Result<T>', () {
    test('Ok carries value', () {
      const Result<int> r = Result.ok(42);
      final got = switch (r) {
        Ok(:final value) => value,
        Err(:final error) => -error.message.length, // unreachable arm proves exhaustiveness
      };
      expect(got, 42);
    });

    test('Err carries ApiError', () {
      const err = ApiError(code: ErrorCode.unauthorized, message: 'no');
      const Result<int> r = Result.err(err);
      final got = switch (r) {
        Ok(:final value) => value,
        Err(:final error) => error.code,
      };
      expect(got, ErrorCode.unauthorized);
    });

    test('switch exhaustiveness compiles without default', () {
      // The fact that this file analyzes cleanly with `very_good_analysis`
      // proves Dart 3 sealed-class exhaustiveness works. No default branch
      // is ever needed across this whole test.
      const Result<String> r = Result.ok('hi');
      expect(r is Ok<String>, isTrue);
    });
  });
}
