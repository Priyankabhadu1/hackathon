# DriftSentinel, explained from scratch

Written for someone who has never seen the project. No jargon that is not defined on the spot.
If you can follow this document you can answer any question a judge asks.

---

## 1. The problem, in one page

### An API can lie without breaking

Imagine you sell flights. You do not own any aircraft — you call Amadeus, a travel API, and it
tells you what a flight costs. You get back something like this:

```json
{ "price": { "currency": "EUR", "base": "389.00", "total": "512.30", "grandTotal": "512.30" } }
```

You charge the customer €512.30. Everyone is happy.

Now a developer refactors the pricing code on the Amadeus side. Afterwards the response is:

```json
{ "price": { "currency": "EUR", "base": "389.00", "total": "389.00", "grandTotal": "389.00" } }
```

Look carefully at what did *not* change:

- every field is still there
- every field still has the same name
- every field is still a string containing a number
- the JSON is still valid
- the HTTP status is still 200
- the response time is unchanged

Only one thing changed: `grandTotal` used to mean *base fare plus taxes*. Now it means *base fare*.
€123.30 of tax silently vanished from the number you charge on.

**Nothing in a normal test suite notices this.** That is the entire problem.

### Why this is worse now than it was five years ago

Two reasons, and they are both about AI.

**On the writing side.** When an AI coding assistant refactors code, it is optimising for one
thing: *the tests still pass*. Your test suite becomes the objective it is steering towards.
Test suites overwhelmingly check **shape** — is the field there, is it a string, does the schema
validate. So shape is what gets carefully preserved. **Meaning is the dimension nobody is
checking, so meaning is the dimension free to drift.** AI refactoring does not merely risk this
kind of bug; it is structurally biased towards producing exactly this kind of bug.

**On the reading side.** A human developer integrating a flight API would eventually notice that
the total looks suspiciously low. An AI agent booking flights through that API will not raise an
eyebrow. It will just book.

So the human who used to be the safety net is being removed from *both ends of the pipe at the
same time*.

### Why nobody catches it today

Run the drifted response past every tool a serious platform team already owns:

| Tool | Result | Why it is blind |
|---|---|---|
| JSON Schema / OpenAPI validation | passes | Every field present, every type correct |
| Contract testing (Pact) | passes | It checks the fields the consumer uses exist. They do |
| Spec diffing | passes | It compares written specifications, not live responses |
| Snapshot testing | unusable | Flight prices change on every call, so teams disable it |
| APM / uptime monitoring | green | 200 OK, latency flat, zero errors |
| Selector self-healing (Healenium, Testim) | *would heal it* | It repairs structure and has no concept of meaning |

Six categories. All green. One real defect worth €123.30 per booking, multiplied across every
reseller downstream, discovered whenever finance next reconciles.

That last row matters most. The whole commercial category of "self-healing tests" would look at
this, see something changed, patch the test, and turn your build green. **A healer that repairs a
meaning change converts a caught defect into a silent one — actively worse than having no healer.**

---

## 2. The idea

> Test what a response **means**, not what it looks like. Heal the changes that are cosmetic.
> Refuse to heal the ones that are not, and say why in writing.

Everything in the codebase follows from that sentence.

---

## 3. How you test meaning when the data always changes

This is the hardest part of the problem, so it gets its own section.

You cannot write `assert total == 512.30`. Flight prices change every minute. Tomorrow the correct
answer is 498.10 and your test fails for no reason. This is why snapshot testing is useless here
and why most teams give up.

The trick is called a **metamorphic relation**: a rule that stays true for *every possible*
response, even though you can never predict any individual value.

```
total  ==  base + taxes + fees
```

You do not know what the base fare will be. You do not know what the taxes will be. But whatever
they turn out to be, the total must equal their sum. That holds on a €200 fare and a €5,000 fare.

That single relation catches our bug: `389.00 ≠ 389.00 + 123.30 + 0.00`. It requires no knowledge
of what the price *should* be.

### The blind spot, and the second kind of check

Metamorphic relations have a weakness, and we demonstrate it deliberately rather than hide it.

Suppose a refactor converts every price to **cents** — the currency stays `EUR`, but base becomes
`18000`, taxes become `2160`, total becomes `20160`. Check the relation:

```
20160 == 18000 + 2160 + 0     ✅  it holds perfectly
```

The response is *internally consistent* and *a hundred times wrong*. A relative check can never
catch this, because everything moved together.

So there is a second class of check, an **absolute** one — a plausibility band declared per route:

```yaml
plausible_total:      # EUR, a return BLR-FRA economy fare
  min: 150
  max: 4000
```

`20160` falls outside it. Caught.

**Teach it as a pair:** relative invariants check that the numbers agree with each other; absolute
invariants check that they agree with reality. You need both, and knowing why is the point.

---

## 4. What we built

Four moving parts.

### 4.1 Probes — synthetic travellers

A **probe** is one realistic travel workflow, run on a loop, forever. Not a ping — a workflow a
real person would perform.

| Probe | What it does | Why it is in the set |
|---|---|---|
| `roundtrip_search` | BLR→FRA return, 1 adult | the money path; the one we drift in the demo |
| `connecting_search` | BLR→JFK with a stopover | multi-segment shape, richer structure |
| `hotel_search` | Bengaluru, 2 nights | a second product family — proves it is not flight-specific |
| `invalid_input` | a deliberately malformed request | asserts the API still *rejects* bad input |

That last one is subtle and worth explaining. It checks that a bad request still returns a 400
error. If an AI refactor "fixes" a failing validation test by making the endpoint return
`200 {"data": []}` instead, everything looks fine — until you realise the API stopped validating
anything. That is the most AI-specific failure mode in the whole set.

Each probe has fixed parameters. Fixed inputs are essential: a probe whose inputs change cannot
have a stable signature, and everything downstream depends on that.

### 4.2 Assertions — checking intent, never field names

This is the design decision that makes safe healing possible.

A normal test says:

```python
assert response["data"][0]["price"]["total"]     # breaks the instant anything is renamed
```

Ours says: *"every offer exposes a total price"* — and looks up **where** that lives in a separate
file called the **alias map**:

```json
{ "offer.total": ["price.grandTotal", "offers[].price.total"] }
```

The assertion knows the *intent* (`offer.total`). The alias map knows the *location*
(`price.grandTotal`). They are separate on purpose.

**Why this matters:** the self-healer is allowed to edit the alias map. It is never allowed to edit
an intent. So healing can move a path but can never weaken what is being checked. That one
separation is what stops the healer from being dangerous.

### 4.3 Two detectors

Change detection runs on two independent channels, because a meaning change can leave *zero*
structural trace.

**Detector 1 — structural (the fingerprint).** Walk the response, collect every field path and its
type, ignore all values, hash the result.

```
data[].price.base        : numeric_string
data[].price.grandTotal  : numeric_string
data[].itineraries[].segments[].departure.at : iso_datetime
→ 62eadf78ebc38624
```

Values are deliberately excluded, and array indices are collapsed, so a two-offer response and a
forty-offer response with different prices hash *identically*. The hash only moves when the
**shape** moves. That makes it a clean, cheap, noise-free signal.

**Detector 2 — relational (the invariants).** The metamorphic and plausibility checks from
section 3.

**Here is the crucial fact.** In our demo, the cosmetic variant and the semantic variant have the
**same fingerprint** — `01346094f2a2df1c` on both. Byte for byte identical. The tax disappearing
does not move a single field path.

If we only had structural detection — which is what "change detection" means to everyone else —
we would miss it completely. Detector 2 is the only thing that sees it.

### 4.4 The judge, the healer, and the gate

When either detector trips, an **LLM judge** is asked exactly one question: *did this change what
the response means?* It returns one of four labels and a written sentence explaining itself.

| Label | Meaning | What happens |
|---|---|---|
| `none` | additive or irrelevant | carry on |
| `cosmetic` | same quantity, new location | **heal** — remap the alias, probe stays green |
| `semantic` | same name, different quantity | **refuse** — fail the probe, block the release |
| `breaking` | something required is gone | **refuse** — fail, block |

**The rule that must never break:** the LLM classifies and explains. It never produces a number
that reaches the dashboard. The drift score is a fixed lookup in code:

```python
DRIFT_SCORE = {"none": 0.0, "cosmetic": 0.3, "semantic": 0.7, "breaking": 1.0}
```

A dashboard whose numbers come out of a language model is a dashboard that hallucinates. This is
the first thing a platform engineer will probe, and the answer is: it cannot, structurally.

Two further guards on healing:

- a `cosmetic` verdict below **0.7 confidence** is refused — an unsure heal has the same failure
  mode as a wrong one, and a reply that omits confidence entirely parses as `0.0`
- every heal, applied or refused, is counted and logged with its justification, so a human can
  audit the whole list rather than discovering it in production

Finally the **release gate** decides PASS or HOLD. Deterministic rules make the call; the model
only writes the human-readable note afterwards and is explicitly told it cannot change the
decision. If Prometheus or Loki is unreachable, that is *itself* a blocking reason — a gate that
says PASS while blind is worse than no gate.

---

## 5. The tools, and why each one is there

| Tool | What it is | Why we use it |
|---|---|---|
| **Amadeus MCP** | The travel API under test | Real travel semantics — `refundable`, price composition and `CONFIRMED` carry money and legal meaning. A generic QA vendor cannot know that |
| **Python** | The runner and all logic | Standard library plus four packages. No framework |
| **Prometheus** | Time-series database for numbers | Stores every metric. Purpose-built for "what was this value 10 minutes ago" |
| **Loki** | Log database, by the Grafana team | Stores the *reasoning* — every rationale and justification, searchable next to the raw payloads. Prometheus holds numbers; Loki holds sentences |
| **Promtail** | Log shipper | Tails our log file and pushes lines into Loki, adding labels |
| **Grafana** | Dashboards | Reads both Prometheus and Loki. Three dashboards: workflow health, drift timeline, release verdict |
| **Docker Compose** | Runs those four containers | One command to stand the stack up |
| **The console** (`ui/`) | Our own small web page | Grafana shows *values over time*. It cannot show that the judge fired on an invariant rather than on structure, refused the heal, and left the alias map alone. That narrative had nowhere to live |
| **An LLM** | The judge and the note-writer | The only component that reads a diff and says what it *means* |

**Why the observability stack matters strategically:** we did not build a bespoke UI with its own
database. We emit metrics and logs onto the stack a platform team already runs in production.
That is part of the pitch, not a shortcut.

---

## 6. What actually happens, in order

One probe cycle, end to end. This is what the Simulator view animates.

```
1  Probe call        src/mcp_client.py   fetch the response (live MCP, or a stored fixture)
2  Fingerprint       src/fingerprint.py  hash the shape, diff against last time
3  Assertions        src/assertions.py   run the intent checks through the alias map
4  Trigger           src/runner.py       did the shape move OR did an invariant break?
5  Judge             src/judge.py        if triggered: classify + explain (the only LLM call)
6  Heal              src/heal.py         cosmetic → remap. semantic/breaking → refuse
7  Re-assert         src/runner.py       if healed, re-run the checks through the new path
8  Metrics           src/metrics.py      export the numbers, all computed in code
9  Gate              src/verdict.py      every 4th cycle: PASS or HOLD from hard rules
```

The whole thing takes about **four milliseconds**. Step 5 is the only expensive one and it only
runs when steps 2 or 3 trip — which in steady state is almost never.

### The cost story, which answers "does this scale?"

| Layer | Runs | Cost |
|---|---|---|
| Fingerprint compare | every cycle | free |
| Invariants | every cycle | free |
| **LLM judge** | **only when something changed** | **cents, and rarely** |
| Release gate | every 4th cycle | free |

The model is the *narrowest* layer in the system. Steady state is a hash comparison.

---

## 7. The demo, scenario by scenario

Seven buttons in the console. Each swaps which stored response the probe receives on its next
cycle.

| Button | What changes | Result |
|---|---|---|
| **baseline** | nothing | all green, judge never wakes |
| **cosmetic rename** | `price.grandTotal` → `price.totalPayable`, same value | fingerprint moves → judged **cosmetic** → **heal applied** → probe stays green, zero human edits |
| **semantic drift** | `totalPayable` drops the tax | **fingerprint identical** → only the invariant fires → judged **semantic** → **heal refused** → HOLD |
| **semantic, no rename** | same meaning change, from a clean baseline | proves it does not depend on the rename |
| **validation swallowed** | `invalid_input` returns `200 {"data":[]}` instead of 400 | second probe, a completely different failure class |
| **hotel total in cents** | hotel total → `20160`, base and taxes unchanged | second product family, the sum invariant catches it |
| **everything in cents** | base, taxes *and* total all → cents | **the sum invariant holds** — only the plausibility band catches it |

The first three are the five-minute script. The rest exist for questions.

**Volunteer the last one rather than waiting to be caught out.** Showing the case your own design
cannot catch — and then showing the second check that does — is far stronger than pretending the
system is complete.

### The single most important sentence in the demo

> "Same field name. Same type. Same fingerprint — byte for byte. One of these we healed
> automatically. The other we refused to heal and blocked the release. Nothing that looks only at
> structure can tell those two apart."

---

## 8. The numbers on the board

Every metric is prefixed `ds_` and is computed by code, never by the model.

| Metric | What it tells you |
|---|---|
| `ds_probe_success` | is this workflow working right now, 1 or 0 |
| `ds_probe_latency_seconds` | how slow the API is |
| `ds_drift_score` | 0.0 / 0.3 / 0.7 / 1.0, looked up from the classification |
| `ds_drift_events_total` | how many changes we judged, by classification |
| `ds_fingerprint_changes_total` | how often the shape moved at all |
| `ds_self_heal_total` | heals applied vs refused vs refused-for-low-confidence |
| `ds_assertion_failures_total` | which intent broke |
| `ds_manual_edits_total` | human fixes required — the maintenance claim |

### Delivery metrics, pointed the other way

The console's Delivery view reports **DORA's four metrics** — the industry-standard measures of
software delivery — but aimed at the API you *depend on* rather than at your own pipeline.

| DORA metric | Here it means |
|---|---|
| Deployment frequency | how often the API's shape changed |
| **Change failure rate** | **what share of those changes altered meaning rather than shape** |
| Time to restore | how long a workflow stayed broken before recovering |
| Lead time *(no clean analogue)* | replaced by: share of change absorbed with no human edit |

Change failure rate translates exactly, and it is a number no consumer of a third-party API
currently has. Be honest that lead time does not map — we never see the provider's commit.

---

## 9. Honest limits

Say these before you are asked. Nothing costs credibility faster than being caught defending
something indefensible.

1. **Coverage is only as good as the invariants somebody wrote.** `total == base + taxes + fees`
   is hand-written. If `refundable` quietly changed meaning today, nothing here would catch it.
   The invariant is the unit of work. The next step is having a model *propose* invariants from a
   corpus of responses for a human to review and merge — which stays inside the "LLM never
   measures" rule, because a proposed invariant is code someone reads, not a number appearing on a
   dashboard.
2. **The arrival of the drift is scheduled, the detection is not.** A real API will not drift on
   cue inside a five-minute demo, so the changed response is seeded. The detection path is
   identical in replay and live mode; nothing about fingerprinting, judging or healing is stubbed.
   Never present replay data as live traffic.
3. **API layer only.** Probes carry a `type:` field for ui, security, accessibility and
   performance. Only `api` is implemented, plus a latency histogram. Same runner, same judge —
   it is a slot, not a feature.
4. **Maintenance reduction is instrumented, not proven.** `ds_manual_edits_total` reads zero
   across the incident against one automatic heal. That is the instrument working. Four hours of
   demo data does not establish a 70–80% reduction, and claiming it does will get you caught.
5. **Test generation is the weakest bullet.** Risk weights in the probe YAML drive how often each
   probe runs. That is prioritisation, barely, and no generation.

---

## 10. Questions you will get, and the short answers

**"Isn't this just contract testing?"**
Contract testing catches shape changes. Every field here is present and correctly typed. We catch
the case where the shape is fine and the meaning moved.

**"How can you test an API whose response is different on every call?"**
Metamorphic relations — properties that hold for every input even though no single output is
predictable. `total == base + taxes + fees` is true at any fare. That is the standard answer to
non-determinism in testing research, and it is why snapshot testing is unusable here and this is
not.

**"What stops the LLM hallucinating a drift score?"**
It cannot. It returns one of four labels; the number is a dictionary lookup in code. Every value
in Prometheus is computed deterministically.

**"Can the model argue its way out of a HOLD?"**
No. Hard rules produce the decision first; the model receives it as input and is told to write the
note, not change it. It also fails closed — unreachable telemetry is itself a blocking reason.

**"What if the judge is wrong and heals something it shouldn't?"**
Two guards. A cosmetic call below 0.7 confidence is refused and the probe stays red. And every
heal is counted and logged with its justification, so the full list is auditable.

**"What happens when the LLM is down?"**
It degrades to a deterministic rule-based classifier and keeps running. We have tested this: the
cosmetic heal still applied, the probe stayed green, the gate still said PASS. A dead model
lowers the quality of the written rationale; it does not break the pipeline.

**"How does this scale to thousands of endpoints?"**
The judge only runs when a fingerprint moves or an invariant breaks, which is rare. Steady state
is a hash comparison.

**"Does it do anything beyond one endpoint?"**
Four probes, two product families, a negative path, and five drift scenarios across three
distinct failure classes.

**"Why Amadeus specifically?"**
Because the semantics are travel semantics. `refundable`, total price composition, `CONFIRMED`
before versus after ticketing — those carry money and legal meaning, and a generic QA vendor has
no way to know that. With agents consuming these APIs directly, a silent meaning change
propagates straight into bookings.

---

## 11. Where everything lives

```
src/mcp_client.py   talks to Amadeus, or replays a stored response
src/runner.py       the loop; the only file that knows which mode we are in
src/fingerprint.py  structural hash and diff
src/assertions.py   the intent checks
src/paths.py        resolves "price.taxes[].amount" against a document
src/judge.py        the LLM call and the deterministic fallback
src/heal.py         applies or refuses a remap
src/verdict.py      the release gate
src/metrics.py      every Prometheus metric, defined once
src/llm.py          Anthropic, any OpenAI-compatible endpoint, or a local Ollama
src/probes/*.yaml   the four probe definitions
fixtures/           stored responses, the alias map, the drift variants
infra/              Docker Compose, Prometheus, Loki, Promtail, Grafana
ui/                 the console: server.py, index.html, simulate.py
docs/               this file, plus the problem statement, architecture and decision log
```

`docs/DECISIONS.md` records sixteen decisions with their trade-offs. If someone asks "why did you
do it that way", the answer is almost certainly in there.
