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

### Fixed
- Fallback classifier read invariants before structure, so a rename was labelled semantic (see D9)

### Changed
- Docs moved into `docs/`, skill into `.claude/skills/`, matching the layout in `CLAUDE.md`

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
