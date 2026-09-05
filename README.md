# DriftSentinel

**Autonomous Quality Engineering for the AI Development Era** — Amadeus Labs Bengaluru hackathon, 4 hours.

Continuously probes **Amadeus MCP** with real travel workflows, detects when a response's *meaning*
changes while its schema stays valid, self-heals cosmetic changes, **refuses** to heal semantic ones,
and generates an explainable release verdict.

## The one-line version

> Everyone else will show you an AI that fixes a broken XPath. We show you the platform noticing —
> and explaining — that an API still returns valid JSON but no longer means what it did.

## Why this and not selector self-healing

Selector self-healing is a solved commercial category. The brief's real question is what breaks when
software is *written* by AI, and the answer is silent semantic drift: an AI-refactored service still
returns valid JSON, every field present and correctly typed, but `price.total` no longer includes tax.
Schema diffing passes. Contract tests pass. Consumers — increasingly AI agents — book on it.

## Quick start

```bash
cp .env.example .env          # PROBE_MODE=replay works with no credentials at all
pip install -r requirements.txt
cd infra && docker compose up -d && cd ..
python -m src.runner
```

Runs offline out of the box: `replay` mode serves fixtures, and with no `ANTHROPIC_API_KEY` the
judge falls back to a rule-based classifier labelled `heuristic-fallback` in the logs. Add the key
for real judgments, add Amadeus credentials and `PROBE_MODE=live` for real traffic.

| Service | URL |
|---|---|
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9090 |
| Runner metrics | http://localhost:8000/metrics |

Demo sequence — the two chain deliberately, no reset in between:

```bash
./scripts/trigger_drift.sh cosmetic   # price.total -> price.grandTotal · heals, stays green
./scripts/trigger_drift.sh semantic   # grandTotal drops tax · identical fingerprint · REFUSED
./scripts/trigger_drift.sh baseline   # reset alias map and fingerprint state
```

## How it works

```
Amadeus MCP ─▶ Probe Runner ─▶ Fingerprinter ─┬─ unchanged ─▶ metrics only (no LLM, ~free)
                                              └─ changed ───▶ Drift Judge (LLM)
                                                                ├ cosmetic → self-heal, stay green
                                                                └ semantic → REFUSE, fail, alert
                                              ▼
                                  Prometheus + Loki ─▶ Grafana ─▶ Release Verdict
```

The design rule everything else follows: **the LLM classifies and explains; it never produces a
number that lands in Prometheus.** Drift score is a lookup on a classification enum.

## Documentation

| Doc | Read it when |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Start of every AI coding session — working agreement and hard constraints |
| [docs/PROBLEM_STATEMENT.md](docs/PROBLEM_STATEMENT.md) | Understanding the brief and what we chose to scope out |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component design, data flow, mapping to the session's reference architecture |
| [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) | During the build — hour-by-hour tasks, roles, gates |
| [docs/DEMO_RUNBOOK.md](docs/DEMO_RUNBOOK.md) | Before presenting — 5-minute script, likely questions |
| [docs/METRICS.md](docs/METRICS.md) | Adding any metric or log line — the contract |
| [docs/DECISIONS.md](docs/DECISIONS.md) | When tempted to revisit a settled trade-off |
| [CHANGELOG.md](CHANGELOG.md) | Every change, one line |

Skills in `.claude/skills/`: `probe-authoring`. The other three named in `CLAUDE.md`
(`semantic-drift-judge`, `observability-wiring`, `release-verdict`) are not written yet.

## Coverage against the brief

| Requirement | Status |
|---|---|
| Automatically detect application changes | ✅ fingerprint diff + drift judge |
| Self-heal and update broken tests | ✅ cosmetic only, by design |
| Generate and prioritise test cases | ⚠️ static risk weights drive frequency; generation is a stretch goal |
| Validate UI / API / security / accessibility / performance | ⚠️ API + latency built; others are pluggable probe types |
| Understand business intent, explainable insights | ✅ intent-level assertions + LLM rationales in Loki |
| Reduce manual maintenance 70–80% | ✅ measured as `ds_manual_edits_total` (0 during the demo incident) |
