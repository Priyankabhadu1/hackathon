# Changelog

All notable changes to DriftSentinel. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Entries are one line, plain English. Update `[Unreleased]` as you work; cut a version at each demo checkpoint.

## [Unreleased]

### Added
- Probe runner looping four travel workflows, with risk-weighted frequency
- Value-blind structural fingerprinter — array length and prices do not move the hash
- Intent-level assertion engine resolving field paths through the alias map
- Metamorphic invariant `total == base + taxes + fees`, which survives a non-deterministic API
- Drift judge with two triggers: a fingerprint change or a newly broken invariant
- Self-healer that applies cosmetic remaps and refuses semantic ones
- Release verdict with deterministic guardrails; the model writes the note, rules make the call
- Amadeus client with replay and live backends, mode chosen only in `runner.py`
- Full observability stack: Prometheus with alert rules, Loki, Promtail, Grafana with D1/D2/D3
- Fixtures for baseline, cosmetic rename, and two semantic variants; `scripts/trigger_drift.sh`
- Fingerprint smoke tests
- Confidence floor on healing: a cosmetic call under 0.7 is refused rather than applied (D10)
- Local console at `ui/` — live pipeline trace and drift controls read from Prometheus and Loki (D12)
- `price_within_plausible_range`, an absolute invariant that catches what the sum invariant cannot (D13)
- Three drift scenarios: validation swallowed, hotel total in cents, everything in cents
- `src/llm.py` — the judge runs on Anthropic, any OpenAI-compatible endpoint, or a local Ollama (D14)
- Console shows the quantities the judge is reading, and says outright when the fingerprint did not move
- Console rebuilt as a five-view operations console: overview, pipeline, simulator, delivery, feed
- Delivery view reports DORA's four metrics against the dependency rather than our own pipeline (D15)
- Step-through simulator: one probe cycle, every stage's input, output, timing and log lines (D16)
- Simulator draws the architecture and walks the real path through it, branch by branch, with the
  untaken edges faded — play, or step one stage at a time
- Drift-score timeline whose y axis is the classification enum, with a validated four-series palette
- `.gitignore`; `__pycache__` and `fixtures/state.json` are no longer tracked

### Fixed
- Fallback classifier read invariants before structure, so a rename was labelled semantic (see D9)
- `scripts/trigger_drift.sh` was not executable, so the documented demo command failed on a clone
- Fallback classifier returned `none` for any broken invariant other than the price sum, leaving a
  red probe scored 0.0; it now treats a failing intent with no structural signal as semantic
- Console listed every assertion that had ever failed, because the counter never comes back down
- Console showed a failing intent beside a passing probe while the counter window trailed a recovery
- Chart stacked its direct labels on top of each other whenever probes rested at the same score
- Release gate raised a spurious HOLD for ~40s after a Prometheus restart, because `rate()` over a
  single sample reads zero; the success-rate rule now needs 5 runs in the window
- A judge reply that omitted `confidence` was treated as certain; it now parses as 0.0 and is refused

### Changed
- Docs moved into `docs/`, skill into `.claude/skills/`, matching the layout in `CLAUDE.md`
- Demo runbook Q&A covers metamorphic testing, verdict guardrails, cost, and the invariant ceiling
- Closing line claims the maintenance instrument rather than asserting the 70–80% figure
- Fixtures rebuilt against the real Amadeus v2 / v3 schemas; taxes now sit under
  `travelerPricings[].price.taxes[]` and the cosmetic rename moved to `price.grandTotal` (D11)

---

## [0.1.0] — Scaffold — 2026-09-05

### Added
- Problem statement, architecture, build plan, demo runbook, metrics contract, decision log
- `CLAUDE.md` working agreement for AI coding sessions
- Four project skills: probe authoring, semantic drift judging, observability wiring, release verdict
- Docker Compose stack: Prometheus, Loki, Promtail, Grafana with provisioned datasources
- Directory layout for `src/`, `src/probes/`, `fixtures/`

### Decisions
- LLM classifies and explains only; every Prometheus value is computed deterministically (D1)
- Assertions target business intent; field paths live in an alias map (D2)
- Cosmetic drift heals automatically, semantic drift never does (D3)
- Fixture replay mode for demo determinism, sharing the full detection path with live mode (D4)
- Grafana is the only frontend (D5)

---

## Planned checkpoints

| Version | Checkpoint | Contents |
|---|---|---|
| 0.2.0 | End of Hour 1 | Stack up, one MCP call working, one metric visible in Grafana |
| 0.3.0 | End of Hour 2 | 4 probes looping, workflow health dashboard live |
| 0.4.0 | End of Hour 3 | Fingerprint + judge + heal working, drift dashboard with annotations |
| 1.0.0 | End of Hour 4 | Release verdict generated, demo rehearsed twice |
