# Demo Runbook — 5 minutes

## Pre-flight (10 min before)

- [ ] `docker compose up -d` — all four containers healthy
- [ ] `python -m src.runner` running, probes green for at least 3 minutes (need history on the graph)
- [ ] Grafana open, **D1 Workflow Health** as the visible tab, time range last 30m, refresh 5s
- [ ] Second browser tab on **D2 Drift Timeline**, third on **D3 Release Verdict**
- [ ] Terminal ready with `./scripts/trigger_drift.sh cosmetic` typed but not entered
- [ ] Second terminal line ready with `./scripts/trigger_drift.sh semantic` (run it *after* the
      cosmetic heal has landed — the two chain deliberately, no reset in between)
- [ ] Laptop on the projector, notifications off, font size up

## The script

**0:00 — The setup (30s)**
> "Everyone here will show you an AI that fixes a broken XPath. That's a solved product category.
> We asked the harder question in the brief: what breaks when the software is being *written* by AI?
> The answer is that structure stays valid while meaning quietly changes — and nothing in your
> pipeline is testing for that."

**0:30 — Live health (45s)**
Show **D1**.
> "These are live probes against Amadeus MCP. Not endpoint pings — travel workflows: a round-trip
> search, a connecting-flight search, a hotel search, and a deliberate invalid input. Success rate
> and p95 latency per workflow. This is the API Testing box in this morning's architecture."

**1:15 — A change arrives, and heals itself (60s)**
Run `./scripts/trigger_drift.sh cosmetic`.
> "A service ships. An AI assistant refactored the pricing helper and `price.total` is now
> `price.grandTotal`. Same money, new name."

Switch to **D2**. Point at the small drift blip and the heals-applied counter.
> "Fingerprint moved, so the judge ran. It read the structural diff, called it a rename, and the
> healer remapped the intent 'an offer exposes a total price' onto the new path. The probe never
> went red. Zero human edits."

Click the heal line in Loki and read the justification aloud.

**2:15 — The change that must not heal (75s)**
Run `./scripts/trigger_drift.sh semantic`.
> "Now the same helper ships again. This time every field name is identical to what you just
> watched us heal to. The schema is valid. The types are right. The response parses."

Point at the fingerprint on D1 — unchanged.
> "The fingerprint is byte-identical. Structural drift detection sees nothing. Contract testing
> sees nothing. Watch what happens anyway."

Drift spikes to 0.7 and the probe goes red.
> "It was caught by an invariant, not a schema: an offer total must equal base plus taxes plus
> fees. That relation holds whatever the fare is, so it survives an API whose prices move on every
> call. Here it stopped holding — 389 where 512.30 was owed. Tax quietly left the total."

**3:30 — The refusal (30s)**
Show the heal panel: applied 1, **refused 1**.
> "And here is the part that matters. It healed the rename. It refused to heal this. A self-healing
> framework that repairs a meaning change turns a caught bug into a green build. Cosmetic heals.
> Semantic never does."

**4:00 — The verdict (35s)**
Switch to **D3**.
> "And this is Release Decision, generated from the telemetry you just watched — not a template."

Read the HOLD verdict aloud.

**4:45 — Close (15s)**
> "Change detection, self-healing, business intent, explainable insights, release decision — five of
> the five bullets, running on the observability stack you'd already have in production. One
> assertion remapped automatically, one refused on purpose, zero human edits either way."

On the 70–80% goal, claim the instrument, not the result. `ds_manual_edits_total` is a real counter
that read zero through the incident; four hours of demo data is not a measurement of a maintenance
reduction, and a judge who builds platforms will respect the distinction more than the round number.

## The scenario menu

Seven buttons on the console, each a real fixture the replay client serves on the next cycle.
The five-minute script uses the first three; the rest are there for questions.

| Button | Probe | What the pipeline does |
|---|---|---|
| baseline | all four | green, judge never wakes |
| cosmetic rename | roundtrip_search | `price.grandTotal` → `price.totalPayable`, heal **applied**, stays green |
| semantic drift | roundtrip_search | totals collapse onto base, **identical fingerprint**, heal **refused**, HOLD |
| semantic (no rename) | roundtrip_search | the same meaning change with no rename to hide behind |
| validation swallowed | invalid_input | a 400 becomes a 200 with an empty list — an AI refactor eating the validation |
| hotel total in cents | hotel_search | second product family, the sum invariant catches it |
| everything in cents | hotel_search | base, taxes and total all converted — **the sum invariant holds**, only the range catches it |

The last one is worth volunteering rather than waiting to be caught out. It is the case a relative
invariant cannot see, and it is why there are two classes of check.

## If asked: "is the drift real or scripted?"

Answer straight:
> "The *arrival* is scheduled — a real API won't drift on cue in a four-hour window, so we seeded the
> changed response. The detection path is identical in live and replay mode; nothing about the
> fingerprinting, judging or healing is stubbed. Point it at a service that's actually changing and
> it behaves the same way."

Never claim replay data is live traffic. The honesty lands better than the bluff, and judges who
build platforms will spot it instantly.

## Likely questions and short answers

**"What if the meaning changes but no field moves?"**
That is the second half of the demo, and it is the whole point. The judge has two triggers: a
fingerprint change, and a newly broken invariant. Have the hashes ready — the cosmetic and the
semantic variant fingerprint to the *same* value, `efdac97ca912f880`. One we healed, one we refused.
Nothing that reads only structure can tell those two apart.

**"How can you test an API whose response is different on every call?"**
`total == base + taxes + fees` is a metamorphic relation: a property that holds for every input even
though no single output is predictable. That is the standard answer to non-determinism in testing
research, and it is why snapshot testing is unusable here and this is not. Prices move freely; the
relation between them does not.

**"Why is AI-written software worse than a human refactor?"**
A coding agent refactoring against a test suite is optimising for "the tests still pass." The suite
becomes its objective function. Suites check shape, so shape is what gets preserved and meaning is
the unconstrained dimension. And on the consumer side, an agent booking through the API has no
eyebrow to raise at a total that looks light. The human who was the semantic safety net is being
removed from both ends of the pipe at once.

**"How much does the model cost you per day?"**
Four layers, and the model is the narrowest. A hash compare and the invariants run every tick and are
free. The LLM runs only when one of them trips, which in steady state is close to never. The
deterministic gate that makes the actual decision is free again. You are paying cents per drift
event, not per probe run.

**"Can the model argue its way out of a HOLD?"**
No. `decide()` runs first on hard rules and produces the decision; the model receives that decision
as input and is told to write the note, not to change it. It also fails closed — if Prometheus or
Loki is unreachable, that is itself a blocking reason, because a gate that says PASS while blind is
worse than no gate.

**"What if the judge is wrong and heals something it shouldn't?"**
Two guards. A cosmetic call below 0.7 confidence is refused and the probe stays red (D10) — a reply
that omits confidence entirely parses as 0.0, so it is refused too. And every heal is counted and
logged with its justification in Loki, so a human can audit the full list rather than discovering it
in production.

**"Isn't this just contract testing?"**
Contract testing catches shape changes. Every field here is still present and correctly typed. We
catch the case where the shape is fine and the meaning moved.

**"What stops the LLM hallucinating a drift score?"**
It can't. It returns a classification enum; the number is a lookup in code. Every value in Prometheus
is computed deterministically.

**"How does this scale to thousands of endpoints?"**
The judge only runs when a fingerprint changes or an invariant breaks, which is rare. Steady state
cost is a hash comparison.

**"Does it do anything beyond that one endpoint?"**
Four probes, two product families and a negative path. Hit *validation swallowed* — `invalid_input`
goes red because the API answered a malformed request with `200 {"data": []}` instead of a 400.
Nothing about the shape is wrong; a bad request simply stopped being refused. That is the same
class of defect as the price one and it is the most AI-specific failure in the set: a refactor
that made the tests pass by removing the thing that was failing them.

**"What can't it catch?"**
Convert base, taxes and total to cents in the same commit and `price_components_sum` still holds —
18000 + 2160 really does equal 20160. The response is internally perfect and a hundred times wrong.
That is why `price_within_plausible_range` exists: a per-route band that anchors to the outside
world. Show it with *everything in cents*. Relative invariants check coherence, absolute ones check
reality, and you need both.

**"So the coverage is only as good as the invariants somebody wrote."**
Correct, and that is the honest ceiling of this approach. `total == base + taxes + fees` is
hand-written; if `refundable` quietly changed meaning today, nothing here would catch it. The
invariant is the unit of work, and the next step is having a model *propose* invariants from a
response corpus for a human to merge — which stays inside D1, because a proposed invariant is code
someone reviews, not a number arriving in Prometheus.

**"What about UI, security, accessibility, performance?"**
Probes are typed and pluggable — same runner, same metrics, same judge. We built the API type and the
latency slice; the others are the same shape of work, not a different architecture.

**"What is Prometheus / Loki / Grafana actually doing here?"**
Open the **Stack** view rather than answering from memory — every figure on it is a live read.
Prometheus: the scrape target reporting UP, the interval, the count of `ds_` series, and the three
alert rules with their current state. Loki: the count of log lines by kind over the last 30 minutes,
which is the proof that the reasoning is stored and not just printed. Grafana: the three dashboards,
provisioned as JSON from the repo rather than clicked together. The line to use is *Prometheus holds
the numbers, Loki holds the sentences.*

**"Do you use Kubernetes?"**
No, and say so plainly — it is an explicit anti-goal in the build plan, next to "no database". Then
turn it round: the runner is already cluster-shaped. A stateless loop with `/metrics` on :8000 is a
Deployment plus a ServiceMonitor; all config is environment variables, so a ConfigMap and a Secret;
logs are single-line JSON on stdout, which is what a cluster collector expects, so Promtail becomes
a DaemonSet with no code change; probes are declarative YAML. Volunteer the blocker before they find
it: the runner keeps local file state in `fixtures/state.json` and `fixtures/alias_map.json`, so
today it is one replica. A PersistentVolumeClaim deploys it as-is; horizontal scaling needs that
state moved out first. The Stack view has all of this on screen.

**"Prove the telemetry is live and not staged."**
Stop the Prometheus container. Within one gate cycle the verdict flips to HOLD with
`prometheus unreachable - cannot evaluate release safety`, because the gate fails closed. Thirty
seconds, and it demonstrates the whole chain at once.

**"Why Amadeus specifically?"**
Because the semantics are travel semantics. `refundable`, `totalPrice` composition, `CONFIRMED`
before versus after ticketing — those carry money and legal meaning, and a generic QA vendor has no
way to know that. With agents consuming these APIs directly, a silent meaning change propagates
straight into bookings.
