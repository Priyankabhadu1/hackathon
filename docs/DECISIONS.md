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

## D10 — A heal the judge is unsure about is refused
**Date:** 2026-09-05 · **Status:** accepted

A `cosmetic` classification below `heal.CONFIDENCE_FLOOR` (0.7) is not applied. It is counted as
`ds_self_heal_total{outcome="refused_low_confidence"}` and the probe stays red.

*Why:* an uncertain heal has the same failure mode as a wrong one — it edits the assertion that
would otherwise have caught the defect. D3 says a healer must never convert a caught defect into a
green build; a heal applied on a guess can do exactly that. Leaving the probe red costs a human two
minutes; healing wrongly costs a silent regression.

*Consequence:* a judgment that reports no confidence at all parses as 0.0 and is therefore refused.
Fail-safe, consistent with the verdict generator's fail-closed rule.

*Also changed:* the fallback classifier rated a clean rename 0.6. Exactly one path removed and
exactly one added is a structurally unambiguous inference, not a coin flip — that number was too
low, and is now 0.75.

## D11 — Fixtures mirror the real Amadeus response shape, taxes included
**Date:** 2026-09-05 · **Status:** accepted

Flight fixtures follow Flight Offers Search v2 exactly: the offer-level `price` block carries
`base`, `total`, `grandTotal` and `fees[]`, while taxes live one subtree away under
`travelerPricings[].price.taxes[]`. Hotels follow Hotel Search v3 (`data[].offers[].price`).
The alias map lists the flight path first and the hotel path as a fallback, so one map serves both.

*Why:* the earlier fixtures put taxes inside `price`, which Amadeus does not. That flattening
quietly destroyed the best part of the argument. In the real schema the price block and the tax
breakdown are in different subtrees, so a refactor consolidating price math genuinely cannot see
the taxes from where it is standing — the seeded semantic drift stops being a contrivance and
becomes the mistake the schema invites.

*Constraint:* `price_components_sum` compares an offer-level base against per-traveler taxes, which
is only correct for a single traveler. Every probe books one adult. A multi-traveler probe would
need the relation restated per `travelerPricings` entry.

## D12 — A local console, alongside Grafana rather than instead of it
**Date:** 2026-09-05 · **Status:** accepted · **narrows D5**

`ui/server.py` serves one page and one JSON endpoint on :8090, reading live from Prometheus and
Loki. It renders pipeline state — which stage ran, what it decided, how the alias map has moved —
and exposes the drift trigger as buttons. It deliberately draws no time series; Grafana D1–D3 keep
that job and the console links to them.

*Why:* D5 said Grafana is the only frontend, to stop a four-hour build sinking into a React app.
The reason holds for charts and does not hold for the pipeline trace: Grafana can show that
`ds_drift_score` is 0.7, but not that the judge fired on an invariant rather than on structure,
refused the heal, and left the alias map untouched. That narrative is the project's whole argument
and it had nowhere to live.

*Constraint:* the console computes nothing. Every value on the page was put into Prometheus or Loki
by some other component first. It stores no state and holds no quality signal of its own.

## D13 — Two classes of invariant, because one of them has a blind spot
**Date:** 2026-09-05 · **Status:** accepted

`price_components_sum` is *relative*: total equals base plus taxes plus fees, whatever the fare.
`price_within_plausible_range` is *absolute*: the total sits inside a per-route band declared in the
probe YAML.

*Why:* a relative invariant cannot see a units error. Convert base, taxes and total to cents
together and base + taxes still equals total — the response is internally perfect and a hundred
times wrong. The `minor_units_consistent` fixture is that case, kept deliberately so the gap is
demonstrated rather than hidden. Only a bound tied to the outside world catches it.

*Trade-off:* the band is hand-set per probe and will need widening for volatile routes. A band that
is too loose is useless and a band that is too tight is noise; there is no way to derive it from the
response alone, which is precisely why it is a second class of check and not a variant of the first.

## D14 — The judge takes whichever model key is available
**Date:** 2026-09-05 · **Status:** accepted

`src/llm.py` is the only module that knows a provider exists. It speaks Anthropic's messages API
and the OpenAI chat-completions shape, the latter covering OpenAI, Groq, Together, OpenRouter and a
local Ollama — which needs no key at all.

*Why:* the demo should not be blocked on which credential happens to be to hand, and running the
judge on a local model is a better answer than running it on an if-statement. `heuristic-fallback`
stays as the last resort when nothing is configured (D9).

## D15 — DORA's four metrics, pointed at the dependency instead of the pipeline
**Date:** 2026-09-05 · **Status:** accepted

The console reports change frequency, change failure rate, time to restore and autonomous
remediation, computed from `ds_fingerprint_changes_total`, `ds_drift_events_total`,
`ds_probe_success` and `ds_self_heal_total`.

*Why:* DORA measures how well *you* ship. Nobody measures how well the API you depend on ships,
and when the thing changing it is an AI agent that is the number that matters. Change failure rate
translates exactly — the share of detected changes that altered meaning rather than shape — and it
is a number no consumer of a third-party API currently has.

*Honest mapping:* three of the four are direct. Lead time has no clean analogue, because we do not
observe the provider's commit; the tile in its place reports autonomous remediation, the share of
change absorbed without a human edit. Time to restore is read off `ds_probe_success` transitions,
so it measures how long a workflow stayed broken, not how long a fix took to write.

## D16 — A step-through simulator, run in a sandbox
**Date:** 2026-09-05 · **Status:** accepted

`ui/simulate.py` replays one probe cycle stage by stage and reports each stage's inputs, outputs,
timing and emitted log lines. It runs as a subprocess against a copy of the alias map in a temp
directory: no Prometheus counter anyone scrapes moves, `fixtures/alias_map.json` is untouched, and
nothing reaches the real log.

*Why:* the whole argument happens in about four milliseconds across six modules, and a dashboard
can only show the wreckage afterwards. Explaining the internals from a slide is weaker than
stepping through them on real data.

The console renders the trace twice: once as the architecture diagram with the path this cycle
actually took lit up and the untaken branches faded, steppable a stage at a time, and once as the
full ordered list underneath.

*Constraint:* it calls the same functions in the same order rather than calling `run_probe`, so a
change to the runner's sequencing has to be mirrored here, and so does the node walk in the
diagram. That is the price of having it produce no side effects; the alternative was letting a demo
aid write to the metrics the demo is showing.
