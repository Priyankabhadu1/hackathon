from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Tuple

from src import config
from src.paths import resolve

# Assertions state an intent. They never name a field path directly - paths live in
# fixtures/alias_map.json and are allowed to move. That separation is what makes
# healing safe: the healer may remap a path, never an intent.

Result = Tuple[bool, str]
Probe = Dict[str, Any]

_CURRENCY = re.compile(r"^[A-Z]{3}$")


def load_alias_map() -> Dict[str, List[str]]:
    with open(config.ALIAS_MAP_PATH) as handle:
        return json.load(handle)


def save_alias_map(alias_map: Dict[str, List[str]]) -> None:
    tmp = config.ALIAS_MAP_PATH + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(alias_map, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, config.ALIAS_MAP_PATH)


def lookup(alias_map: Dict[str, List[str]], logical: str, node: Any) -> List[Any]:
    """First candidate path that actually resolves wins."""
    for candidate in alias_map.get(logical, []):
        found = resolve(node, candidate)
        if found:
            return found
    return []


def _offers(response: Any, alias_map: Dict[str, List[str]]) -> List[Any]:
    found = lookup(alias_map, "offer_list", response)
    if len(found) == 1 and isinstance(found[0], list):
        return found[0]
    return found


def _number(value: Any):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def offers_present(response, alias_map, probe) -> Result:
    offers = _offers(response, alias_map)
    return (bool(offers), f"{len(offers)} offers")


def every_offer_has_total_price(response, alias_map, probe) -> Result:
    offers = _offers(response, alias_map)
    if not offers:
        return False, "no offers to check"
    for index, offer in enumerate(offers):
        values = lookup(alias_map, "offer.total", offer)
        if not values or _number(values[0]) is None:
            return False, f"offer {index} exposes no numeric total price"
    return True, f"{len(offers)} offers priced"


def currency_is_iso4217(response, alias_map, probe) -> Result:
    offers = _offers(response, alias_map)
    for index, offer in enumerate(offers):
        values = lookup(alias_map, "offer.currency", offer)
        if not values:
            return False, f"offer {index} has no currency"
        if not _CURRENCY.match(str(values[0])):
            return False, f"offer {index} currency {values[0]!r} is not a 3-letter code"
    return True, "all currencies well formed"


def price_components_sum(response, alias_map, probe) -> Result:
    """Total must equal base plus taxes plus fees.

    A metamorphic check: it holds whatever the actual fare is, so it survives a
    non-deterministic API. This is the one that catches a total whose composition
    changed while every field name and type stayed put.
    """
    offers = _offers(response, alias_map)
    if not offers:
        return False, "no offers to check"
    for index, offer in enumerate(offers):
        total = _number(next(iter(lookup(alias_map, "offer.total", offer)), None))
        base = _number(next(iter(lookup(alias_map, "offer.base", offer)), None))
        if total is None or base is None:
            return False, f"offer {index} missing total or base"
        taxes = sum(filter(None, (_number(v) for v in lookup(alias_map, "offer.taxes", offer))))
        fees = sum(filter(None, (_number(v) for v in lookup(alias_map, "offer.fees", offer))))
        expected = round(base + taxes + fees, 2)
        if abs(expected - total) > 0.01:
            return (
                False,
                f"offer {index}: total {total} != base {base} + taxes {round(taxes,2)} "
                f"+ fees {round(fees,2)} = {expected}",
            )
    return True, f"{len(offers)} offers internally consistent"


def itinerary_segments_present(response, alias_map, probe) -> Result:
    offers = _offers(response, alias_map)
    for index, offer in enumerate(offers):
        if not lookup(alias_map, "offer.segments", offer):
            return False, f"offer {index} has no segments"
    return True, "every offer carries an itinerary"


def rejects_invalid_input(response, alias_map, probe) -> Result:
    """The negative probe. A bad request must be refused, not answered."""
    if lookup(alias_map, "error_list", response):
        return True, "rejected as expected"
    offers = _offers(response, alias_map)
    if offers:
        return False, f"invalid input returned {len(offers)} offers instead of an error"
    return False, "invalid input neither errored nor returned offers"


def price_within_plausible_range(response, alias_map, probe) -> Result:
    """An absolute anchor, where price_components_sum is a relative one.

    Internal consistency cannot see a units error: convert base, taxes and total to
    cents together and base + taxes still equals total. Only a bound tied to the real
    world catches that, so the range comes from the probe definition, per route.
    """
    bounds = (probe or {}).get("plausible_total")
    if not bounds:
        return True, "no range configured for this probe"
    low, high = float(bounds["min"]), float(bounds["max"])
    offers = _offers(response, alias_map)
    if not offers:
        return False, "no offers to check"
    for index, offer in enumerate(offers):
        total = _number(next(iter(lookup(alias_map, "offer.total", offer)), None))
        if total is None:
            return False, f"offer {index} exposes no numeric total price"
        if not low <= total <= high:
            return False, (f"offer {index}: total {total} is outside the plausible "
                           f"{low:g}-{high:g} range for this route")
    return True, f"{len(offers)} offers within {low:g}-{high:g}"


REGISTRY: Dict[str, Callable[[Any, Dict[str, List[str]], Probe], Result]] = {
    "offers_present": offers_present,
    "every_offer_has_total_price": every_offer_has_total_price,
    "currency_is_iso4217": currency_is_iso4217,
    "price_components_sum": price_components_sum,
    "itinerary_segments_present": itinerary_segments_present,
    "rejects_invalid_input": rejects_invalid_input,
    "price_within_plausible_range": price_within_plausible_range,
}

INTENT = {
    "offers_present": "the search returns at least one bookable offer",
    "every_offer_has_total_price": "every offer exposes a numeric total price",
    "currency_is_iso4217": "every price is denominated in a valid ISO-4217 currency",
    "price_components_sum": "an offer total equals its base fare plus taxes plus fees",
    "itinerary_segments_present": "every offer carries the itinerary it prices",
    "rejects_invalid_input": "a malformed request is refused rather than answered",
    "price_within_plausible_range": "a total price is a believable amount for this route",
}


def run(names: List[str], response: Any, alias_map: Dict[str, List[str]],
        probe: Probe = None) -> List[Dict[str, Any]]:
    results = []
    for name in names:
        check = REGISTRY.get(name)
        if check is None:
            results.append({"assertion": name, "ok": False, "detail": "unknown assertion"})
            continue
        try:
            ok, detail = check(response, alias_map, probe)
        except Exception as exc:  # a broken assertion is a failed assertion, not a crashed runner
            ok, detail = False, f"assertion raised {type(exc).__name__}: {exc}"
        results.append(
            {"assertion": name, "ok": ok, "detail": detail, "intent": INTENT.get(name, name)}
        )
    return results
