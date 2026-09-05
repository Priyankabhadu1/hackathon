#!/usr/bin/env bash
# Schedule the arrival of a change. The detection path is identical either way -
# see docs/DECISIONS.md D4. Usage: ./scripts/trigger_drift.sh [baseline|cosmetic|semantic]
set -euo pipefail
cd "$(dirname "$0")/.."

variant="${1:-}"
case "$variant" in
  baseline|cosmetic|semantic|semantic_cold|validation_swallowed|minor_units|minor_units_consistent) ;;
  *)
    echo "usage: $0 [baseline|cosmetic|semantic|semantic_cold|validation_swallowed|minor_units|minor_units_consistent]" >&2
    echo "  baseline  restore the original response and the original alias map" >&2
    echo "  cosmetic  price.grandTotal renamed to price.totalPayable - should heal" >&2
    echo "  semantic  after cosmetic: totalPayable stops including tax - must NOT heal" >&2
    echo "  semantic_cold  same meaning change from an unhealed baseline" >&2
    echo "  validation_swallowed  invalid_input answered 200 with an empty list instead of 400" >&2
    echo "  minor_units    hotel total switches to cents - the sum invariant catches it" >&2
    echo "  minor_units_consistent  base, taxes and total all in cents - only the range catches it" >&2
    exit 1 ;;
esac

echo "$variant" > fixtures/active_variant
if [ "$variant" = "baseline" ]; then
  cp fixtures/alias_map.baseline.json fixtures/alias_map.json
  rm -f fixtures/state.json
  echo "reset to baseline: alias map restored, fingerprint state cleared"
else
  echo "variant '$variant' active - next probe cycle will pick it up"
fi
