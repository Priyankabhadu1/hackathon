# Decision Log

Short ADRs. One per non-obvious choice. Add to this file rather than arguing twice.

## D1 — The LLM classifies, it never measures
**Date:** 2026-09-05 · **Status:** accepted

Every value that reaches Prometheus is computed by deterministic code. The model returns a
classification enum and a rationale; `drift_score` is a dictionary lookup on that enum.

*Why:* a dashboard whose numbers come out of a language model is a dashboard that hallucinates.
This is also the answer to the first hostile question a platform engineer will ask.

*Rejected alternative:* asking the model to "rate severity 0–10". Non-reproducible, unbacktestable,
and indefensible on stage.

## D2 — Assertions target business intent, not field paths
**Date:** 2026-09-05 · **Status:** accepted

Assertions are written as `every offer exposes a total price in a valid currency`, resolved to a
concrete path via `fixtures/alias_map.json`.

*Why:* it is the mechanism that makes self-healing safe. The healer may change the path; it can never
change the intent. It's also the brief's "understand business intent" bullet, made structural rather
than rhetorical.

## D3 — Cosmetic drift heals automatically; semantic drift never does
**Date:** 2026-09-05 · **Status:** accepted

`cosmetic` → apply alias, stay green, count the heal. `semantic` / `breaking` → refuse, fail the
probe, alert, log the reasoning.

*Why:* this is the thesis. A self-healing framework that repairs a meaning change converts a caught
defect into a green build — actively worse than no healing. Every competing submission will heal
indiscriminately; the refusal is the differentiator.

## D4 — Fixture replay for demo determinism
**Date:** 2026-09-05 · **Status:** accepted

`PROBE_MODE=replay` serves stored responses; `PROBE_MODE=live` calls Amadeus MCP. Identical
downstream path.

*Why:* a real API will not drift during a five-minute demo. We schedule the *arrival* of the change,
not the detection of it. Disclosed openly to judges — see `docs/DEMO_RUNBOOK.md`.

*Constraint:* mode branching exists only in `src/runner.py`. Anything below it must not know.

## D5 — Grafana is the only frontend
**Date:** 2026-09-05 · **Status:** accepted

Dashboards provisioned as JSON. No custom UI.

*Why:* four hours. Also strategically correct — running on the stack the customer already operates is
part of the pitch, not a shortcut.

## D6 — Amadeus MCP is the system under test
**Date:** 2026-09-05 · **Status:** accepted

*Why:* a clean, scriptable, semantically rich API surface that is unmistakably Amadeus, available
without standing up an app to test. Avoids the UI-grounding work that would sink the timeline.

*Trade-off:* we cover the API dimension of the brief well and the UI dimension not at all. Handled by
making probes typed and pluggable, and saying so directly.

## D7 — Four probes, not forty
**Date:** 2026-09-05 · **Status:** accepted

`roundtrip_search`, `connecting_search`, `hotel_search`, `invalid_input`.

*Why:* enough to make a dashboard look like a real health page and to show drift on one without the
others going red. More probes add demo risk and zero narrative value.

## D8 — The judge has two triggers, not one
**Date:** 2026-09-05 · **Status:** accepted

The drift judge runs when the fingerprint changes **or** when the set of failing invariants changes.

*Why:* the fingerprint is deliberately value-blind, so a total that stops including tax produces a
byte-identical fingerprint. Structure alone cannot see the change we exist to catch. The invariant
`total == base + taxes + fees` is the second trigger, and it is metamorphic — it holds whatever the
fare is, so it survives an API whose values move on every call.

*Consequence:* a probe that is failing steadily does not re-invoke the model every cycle. The
failure signature is compared to the previous one; only a change in it re-triggers.

## D9 — A deterministic fallback classifier
**Date:** 2026-09-05 · **Status:** accepted

With no model key configured, `judge.py` falls back to a rule-based classifier and labels the output
`model: heuristic-fallback`.

*Why:* the pipeline stays demonstrable offline and survives a dead network on stage. The fallback is
never presented as the model's judgment — the log line names it.

*Gotcha found in testing:* the fallback must check the structural diff **before** the invariants. A
rename breaks `price_components_sum` too, not because the total changed but because the path it read
is gone. Checking invariants first classified a harmless rename as semantic. Structure first.
