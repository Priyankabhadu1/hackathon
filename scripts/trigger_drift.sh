#!/usr/bin/env bash
# Schedule the arrival of a change. The detection path is identical either way -
# see docs/DECISIONS.md D4. Usage: ./scripts/trigger_drift.sh [baseline|cosmetic|semantic]
set -euo pipefail
cd "$(dirname "$0")/.."

variant="${1:-}"
case "$variant" in
  baseline|cosmetic|semantic|semantic_cold) ;;
  *)
    echo "usage: $0 [baseline|cosmetic|semantic|semantic_cold]" >&2
    echo "  baseline  restore the original response and the original alias map" >&2
    echo "  cosmetic  price.total renamed to price.grandTotal - should heal" >&2
    echo "  semantic  after cosmetic: grandTotal stops including tax - must NOT heal" >&2
    echo "  semantic_cold  same meaning change from an unhealed baseline" >&2
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
