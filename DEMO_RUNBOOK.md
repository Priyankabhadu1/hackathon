# Demo Runbook — 5 minutes

## Pre-flight (10 min before)

- [ ] `docker compose up -d` — all four containers healthy
- [ ] `python -m src.runner` running, probes green for at least 3 minutes (need history on the graph)
- [ ] Grafana open, **D1 Workflow Health** as the visible tab, time range last 30m, refresh 5s
- [ ] Second browser tab on **D2 Drift Timeline**, third on **D3 Release Verdict**
- [ ] Terminal ready with `./scripts/trigger_drift.sh semantic` typed but not entered
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

**1:15 — The change arrives (45s)**
Run `./scripts/trigger_drift.sh semantic`.
> "Now a service ships. An AI assistant refactored the pricing helper. The schema is still valid,
> every field is still there, the response still parses. Watch."

Switch to **D2**.

**2:00 — Detection and judgment (75s)**
Point at the `ds_drift_score` spike.
> "Fingerprint changed, so the judge ran. It didn't diff JSON — it was asked one question: does this
> change what the response *means*?"

Click the annotation, read the rationale aloud — something like *"semantic: `price.total` no longer
includes tax; the same field name now carries a different quantity."*

> "That's the model's reasoning, stored in Loki next to the raw before-and-after. Auditable."

**3:15 — The refusal (45s)**
Show the self-heal panel and the Loki `kind=heal` line.
> "Here's the part I want you to notice. Earlier, a field got *renamed* — cosmetic. The system healed
> it: remapped the path, kept the probe green, zero human edits. This one it refused to heal.
> A self-healing framework that repairs a meaning change turns a caught bug into a green build.
> Cosmetic heals. Semantic never does."

**4:00 — The verdict (45s)**
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
