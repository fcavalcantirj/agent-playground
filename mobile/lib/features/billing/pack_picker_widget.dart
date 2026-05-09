// Phase B Plan 11 Task 1 — pack picker (Wave 5 mobile UI).
//
// Renders the 5 packs returned by GET /v1/billing/packs as a column
// of tappable cards. Mobile NEVER hardcodes the catalog — the caller
// (TopUpScreen) reads packsProvider and forwards the resolved list.
//
// Each card shows pack.label (e.g. `$25`) on the leading edge and
// `<credit_cents> credits` on the trailing edge. Tapping the card
// fires onSelect(pack) — the parent screen owns the navigation /
// orchestrator wiring.

import 'package:agent_playground/features/billing/billing_models.dart';
import 'package:flutter/material.dart';

class PackPickerWidget extends StatelessWidget {
  const PackPickerWidget({
    required this.packs,
    required this.onSelect,
    super.key,
  });

  final List<Pack> packs;
  final ValueChanged<Pack> onSelect;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: packs
          .map(
            (p) => Card(
              margin: const EdgeInsets.symmetric(vertical: 4),
              child: InkWell(
                onTap: () => onSelect(p),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        p.label,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text(
                        '${p.creditCents} credits',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          )
          .toList(growable: false),
    );
  }
}
