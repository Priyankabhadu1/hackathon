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
> the five bullets, running on the observability stack you'd already have in production. And zero
> manual test edits during that entire incident. That's the 70–80% number, measured, not claimed."

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
That is the second half of the demo. The judge has two triggers: a fingerprint change, and a broken
invariant. The semantic case fires on the invariant, because its fingerprint is identical.

**"Isn't this just contract testing?"**
Contract testing catches shape changes. Every field here is still present and correctly typed. We
catch the case where the shape is fine and the meaning moved.

**"What stops the LLM hallucinating a drift score?"**
It can't. It returns a classification enum; the number is a lookup in code. Every value in Prometheus
is computed deterministically.

**"How does this scale to thousands of endpoints?"**
The judge only runs when a fingerprint changes, which is rare. Steady state cost is a hash comparison.

**"What about UI, security, accessibility, performance?"**
Probes are typed and pluggable — same runner, same metrics, same judge. We built the API type and the
latency slice; the others are the same shape of work, not a different architecture.

**"Why Amadeus specifically?"**
Because the semantics are travel semantics. `refundable`, `totalPrice` composition, `CONFIRMED`
before versus after ticketing — those carry money and legal meaning, and a generic QA vendor has no
way to know that. With agents consuming these APIs directly, a silent meaning change propagates
straight into bookings.
