# Demo Runbook — 5 minutes

## Pre-flight (10 min before)

- [ ] `docker compose -f infra/docker-compose.yml up -d` — four containers healthy
- [ ] `python -m src.runner` running, probes green for **at least 3 minutes** so the chart has history
- [ ] `python -m ui.server` running
- [ ] Console open at **http://localhost:8090**, on the **Overview** view, variant `baseline`
- [ ] Verdict reads **PASS**. If it reads HOLD from an earlier rehearsal, wipe the window:
      `docker compose -f infra/docker-compose.yml rm -sf prometheus && docker compose -f infra/docker-compose.yml up -d prometheus`
- [ ] Grafana in a second browser tab, for anyone who asks to see it
- [ ] Notifications off, font size up, laptop on the projector

Everything is driven from buttons in the console. No terminal on screen.

## The script — five minutes

Timings are cumulative. Every action is a click in the console toolbar.

### 0:00 · The problem (35s)

Say this before showing anything.

> "Everyone here will show you an AI that repairs a broken selector. That is a solved commercial
> category. We asked the harder half of the brief: what breaks when the software is being *written*
> by AI?
>
> The answer is that structure stays valid while meaning quietly changes. An AI assistant
> refactoring code is optimising for one thing — the tests still pass. Test suites check shape. So
> shape is what gets preserved, and meaning is the one dimension nobody is constraining. And on the
> other end, the consumer is increasingly an agent that will never raise an eyebrow at a total that
> looks light. The human safety net is being removed from both ends of the pipe at once."

### 0:35 · Steady state (35s)

**Overview** view.

> "Four probes against Amadeus MCP. Not endpoint pings — travel workflows. A return search, a
> connecting flight, a hotel search, and a deliberately malformed request that has to be *rejected*.
> All green, release gate says PASS. The judge has not been called once — steady state costs a hash
> comparison."

### 1:10 · A change arrives, and heals itself (60s)

Click **cosmetic rename**. Wait one cycle.

> "A service ships. The pricing helper was refactored and `price.grandTotal` is now
> `price.totalPayable`. Same money, new name."

Switch to **Pipeline**.

> "The fingerprint moved, so the judge ran. It read the structural diff, called it a rename, and the
> healer remapped the *intent* — 'an offer exposes a total price' — onto the new path. Look at the
> alias map: the new path is prepended, the old one kept as a fallback. The probe never went red.
> Zero human edits."

### 2:10 · The change that must not heal (80s)

Click **semantic drift**. Stay on **Pipeline**.

> "The same helper ships again. Every field name is identical to what you just watched us heal to.
> Valid schema, correct types, the response parses."

Point at the red banner above the payload table.

> "The fingerprint is unchanged. Byte for byte — the same hash on both sides. Structural change
> detection sees nothing here. Contract testing sees nothing. Schema validation passes."

Point at the payload table, where `total` is struck through and the new value is red.

> "It was caught by an invariant instead: an offer total must equal base plus taxes plus fees. That
> relation holds whatever the fare is, which is how you test an API whose prices move on every call.
> Here it stopped holding. 389 where 512.30 was owed — 123 euros of tax quietly left the total."

Scroll to the healer stage.

> "And here is the part that matters. It healed the rename. It **refuses** to heal this, and says
> why in writing. A self-healing framework that repairs a meaning change turns a caught defect into
> a green build — worse than having no healing at all. Cosmetic heals. Semantic never does."

### 3:30 · Inside the four milliseconds (45s)

**Simulator** view. Prior `cosmetic`, receives `semantic`. Click **Run one cycle**, then **Play**.

> "All of that happened in about four milliseconds across six modules, so here it is stepped out.
> Same functions, run in a sandbox. Watch which branch lights up — the structural detector reports
> no change, so the judge is woken by the *invariant* path instead. The cosmetic branch never fires.
> Every value on screen is the real input and output of that stage."

### 4:15 · The decision (30s)

**Delivery** view.

> "Change failure rate: the share of changes to this API that altered meaning rather than shape.
> That is DORA's metric, pointed at the dependency instead of at our own pipeline — and it is a
> number no consumer of a third-party API currently has."

Back to **Overview** for the HOLD.

> "The release gate is deterministic. Hard rules make the call; the model only writes the note and
> is explicitly told it cannot change the decision. Unreachable telemetry is itself a blocking
> reason, so it fails closed."

### 4:45 · Close (15s)

> "Change detection, self-healing, business intent, explainable insights, release decision — five of
> the five bullets, running on the observability stack you would already have in production. One
> assertion remapped automatically, one refused on purpose, zero human edits either way."

## If you have two minutes, not five

Cut to three beats: the problem (0:00), **cosmetic rename** healing itself, **semantic drift**
refusing to heal on an identical fingerprint. Skip the simulator and Delivery entirely. The
identical hash is the whole argument; everything else is supporting evidence.

## If you have ten minutes

Add, in this order: **validation swallowed** (a second probe, a different failure class), then
**everything in cents** (the case the sum invariant cannot catch, and the plausibility band that
can), then the **Stack** view for what each service is doing, then stop Prometheus to show the gate
failing closed.

## Handling interruptions

- **Asked a question mid-flow?** Answer it, then say "let me show you" and continue from where you
  were. The console is live; nothing is on rails.
- **Something goes red unexpectedly?** Say what you see. The system is a detector — a genuine
  detection during a demo is a feature, not a failure.
- **The model is on `heuristic-fallback`?** Get ahead of it: "no API credit today, so the judge is
  on its deterministic classifier. That is the designed fallback — the pipeline degrades in quality
  of explanation, not in correctness. Same classification, same refusal."
- **Running behind?** Drop the simulator. Never drop the semantic refusal.

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
