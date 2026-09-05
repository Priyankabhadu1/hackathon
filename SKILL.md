---
name: probe-authoring
description: Author, edit, or debug DriftSentinel probes and intent-level assertions against Amadeus MCP. Use this skill whenever the work touches probe YAML files, the probe runner, assertion logic, the alias map, or adding a new travel workflow to test — even if the request is phrased as "add a test", "check the hotel flow", or "the probe is failing". Also use before writing any assertion, to avoid the field-path anti-pattern.
---

# Probe Authoring

A **probe** is one travel workflow exercised against Amadeus MCP on a loop. Not an endpoint ping —
a workflow a real traveller or seller would perform.

## Probe definition format

`src/probes/<name>.yaml`:

```yaml
name: roundtrip_search
workflow: flight_search          # coarse label used on dashboards
type: api                        # api | ui | security | accessibility | performance (only api built)
risk: high                       # high | medium | low → drives probe frequency
tool: flight-offers-search       # Amadeus MCP tool name
params:
  originLocationCode: BLR
  destinationLocationCode: FRA
  departureDate: "2026-11-12"
  returnDate: "2026-11-19"
  adults: 1
assertions:
  - offers_present
  - every_offer_has_total_price
  - currency_is_iso4217
  - price_components_sum
```

Keep `params` **fixed and deterministic**. A probe whose inputs change cannot have a stable
fingerprint, and everything downstream depends on that.

Watch dates: a hardcoded `departureDate` in the past starts returning empty results. Use a date
60–90 days out, or compute `today + 60d` at load time — but then exclude the date field from the
fingerprint.

## Writing assertions — the one rule

**Assert on business meaning. Never on a field path.**

```python
# WRONG — breaks the moment an AI refactor renames anything
assert response["data"][0]["price"]["total"]

# RIGHT — survives renames, catches meaning changes
def every_offer_has_total_price(response, resolve):
    for offer in resolve("offers", response):
        total = resolve("offer.total_price", offer)
        assert total is not None, "offer exposes no total price"
        assert float(total) > 0, "total price is not positive"
```

`resolve(logical_name, obj)` looks the logical name up in `fixtures/alias_map.json` and returns the
value at the current concrete path. The alias map is what the self-healer edits. This indirection is
the whole reason healing is safe — see decision D2 in `docs/DECISIONS.md`.

## The four probes we ship

| Probe | Workflow | Why it's in the set |
|---|---|---|
| `roundtrip_search` | flight_search | the primary money path; the one we drift during the demo |
| `connecting_search` | flight_search | multi-segment response shape, richer fingerprint |
| `hotel_search` | hotel_search | a second product family, proves the runner isn't flight-specific |
| `invalid_input` | error_handling | asserts a *graceful* error; catches AI refactors that swallow validation |

`invalid_input` is worth explaining if judges ask: it asserts the API still *rejects* bad input
properly. An AI-refactored handler that starts returning 200 with an empty list instead of a 400 is
exactly the silent regression this project exists to catch.

## Assertion library to implement

| Assertion | Checks |
|---|---|
| `offers_present` | at least one offer returned |
| `every_offer_has_total_price` | total price present and > 0 on every offer |
| `currency_is_iso4217` | currency is a 3-letter uppercase code |
| `price_components_sum` | base + fees + taxes reconciles to total (**the semantic-drift canary**) |
| `segments_are_chronological` | departure of segment N+1 is after arrival of segment N |
| `rejects_invalid_input` | error status and a structured error body, not an empty success |

`price_components_sum` is the highest-value assertion in the set. It is the one that fails when a
refactor quietly removes tax from `total` while leaving every field name and type intact. Build it
first, and point at it during the demo.

## Risk-based frequency

```python
INTERVAL = {"high": 15, "medium": 60, "low": 300}   # seconds
```

That is the entirety of "risk-based test selection" for this build. Do not build a code-graph
analyser; if asked, say the weights are static today and would be derived from change impact in a
production version.

## Debugging a failing probe

1. `PROBE_MODE=replay` first — does it fail against the stored baseline? If yes, the bug is ours.
2. Check `fixtures/alias_map.json` — did a heal remap a path incorrectly?
3. Grep Loki for `kind=assertion_failure` and the probe name; `expected` and `actual` are logged.
4. Only then suspect Amadeus MCP.

Do not add retries to mask flakiness. A flaky probe on the dashboard is honest; a retry that hides a
real regression is the failure mode this whole project is arguing against.
