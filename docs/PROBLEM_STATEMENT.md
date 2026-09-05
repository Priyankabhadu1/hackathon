# Problem Statement

## The brief (as given)

**Autonomous Quality Engineering for the AI Development Era**
Prepared by Gunjan Khandpur, Amadeus Labs Bengaluru.

> AI-driven development is making software delivery faster, but traditional QA automation struggles to keep up. Frequent UI, workflow, and feature changes make test scripts fragile, increasing maintenance effort and delaying releases.

**Challenge — build an AI-powered QA system that can:**

1. Automatically detect application changes
2. Self-heal and update broken tests
3. Generate and prioritise test cases
4. Validate UI, API, security, accessibility, and performance
5. Understand business intent and provide explainable quality insights

**Goal:** self-adaptive test automation that reduces manual maintenance by **70–80%** while improving release confidence and product quality.

**The framing sentence that matters most:**
> This framing elevates the problem from "XPaths keep breaking" to a strategic industry challenge: How do we reinvent Quality Engineering when software itself is increasingly being created and modified by AI?

## Reference architecture (from the session whiteboard)

```
Application → Change Detection → AI QA Engine → Quality Validation → Quality Insights → Release Decision
                                  ├ Test Generation      ├ UI Testing
                                  ├ Self-Healing Tests   ├ API Testing
                                  └ Risk-Based Selection ├ Security Testing
                                                         ├ Accessibility Testing
                                                         └ Performance Testing
```

## Our reading of the problem

Most teams will hear "test scripts are fragile" and build **selector self-healing**: an LLM that repairs a broken XPath. That is a solved commercial category (Healenium, Testim, mabl, Applitools). It is table stakes, it is not what the brief's closing sentence asks for, and it will be the most crowded submission at the event.

The sharper problem is one layer down. When software is written and modified by AI, three things break that traditional QA never had to handle:

1. **Change arrives faster than anyone can describe it.** The system under test changes without a human-authored spec of what changed. Detection has to be *observed*, not declared.
2. **Structure stays valid while meaning shifts.** An AI-refactored service still returns valid JSON against a valid schema — but `refundable` now means something subtly different, or `total` stops including taxes. Schema diffing passes. Contract tests pass. Consumers break silently. This is the failure mode nobody is testing for.
3. **Nobody can explain the red build.** Volume of change plus volume of tests means triage, not detection, is the bottleneck. "Explainable quality insights" in the brief is not a reporting nicety; it is the actual constraint on release velocity.

## What we are building

**DriftSentinel** — an observability-native autonomous QA layer that continuously exercises **Amadeus MCP** as the system under test, and:

- runs **synthetic traveler probes** (real travel workflows, not endpoint pings) on a loop → Prometheus
- fingerprints every response and, on change, uses an LLM to judge **semantic vs cosmetic drift** with a written rationale → Prometheus + Loki
- **self-heals** assertions when a field moves but its meaning does not, logging every heal with its justification
- generates an **explainable release verdict** (PASS / HOLD) by reading its own Prometheus and Loki data

## Scope decisions for a 4-hour build

**In scope**
- API-layer validation against Amadeus MCP (flight search, hotel search, pricing shapes)
- Change Detection, Self-Healing, Quality Insights, Release Decision boxes of the reference architecture
- Prometheus (metrics), Loki (logs + rationales), Grafana (the entire frontend)

**Explicitly out of scope — and why**
| Excluded | Reason |
|---|---|
| UI/DOM self-healing | Needs a grounding layer + a real front-end under test; not achievable in 4h |
| Security & accessibility test types | Architected as pluggable probe types; demoed as a slot, not built |
| Performance testing | Latency histograms give us a credible sliver; full load modelling is out |
| Code-graph risk-based selection | Requires repo ingestion; a static risk weight table stands in |
| Custom web frontend | Grafana *is* the frontend. Building a second UI is the classic 4-hour death trap |

## Why Amadeus specifically

Amadeus is an API-first platform: 400+ airlines, 2M+ hotel properties, thousands of API consumers, and — per its own announcements — a growing population of **AI agents** consuming those APIs. Semantic drift in a travel API is not a cosmetic bug: `refundable`, `totalPrice` composition, and `status: CONFIRMED` (before vs after ticketing) carry money and legal meaning. A platform whose consumers are increasingly machines needs to test for *meaning* changes, not just shape changes. That is a problem Amadeus has and a generic QA vendor cannot solve, because the semantics are travel semantics.

## Success criteria for the hackathon

| # | Criterion | How we prove it in the demo |
|---|---|---|
| 1 | Detects change automatically | Drift score spikes on a seeded response change, no human input |
| 2 | Self-heals | Assertion remaps to the new field path, probe stays green |
| 3 | Explainable | LLM rationale visible in Loki, annotated on the Grafana timeline |
| 4 | Business intent | Probes are travel workflows; assertions are on meaning, not field names |
| 5 | Release decision | Written PASS/HOLD verdict generated from live telemetry |
| 6 | Maintenance reduction | Count: heals applied vs manual edits required (target 0 manual edits during demo) |
