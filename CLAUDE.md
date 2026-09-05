# CLAUDE.md

Working agreement for AI coding sessions on this repo. Read this first, every session.

## What this project is

**DriftSentinel** — an observability-native autonomous QA layer for the Amadeus Labs Bengaluru hackathon
("Autonomous Quality Engineering for the AI Development Era"). It continuously probes **Amadeus MCP** with
travel workflows, detects **semantic** drift in responses, self-heals cosmetic changes, refuses to heal
semantic ones, and emits an explainable release verdict.

Full context: `docs/PROBLEM_STATEMENT.md`. Design: `docs/ARCHITECTURE.md`. Build order: `docs/BUILD_PLAN.md`.

## Hard constraint: this is a 4-hour build

Every decision is subordinate to shipping a working demo in four hours. When in doubt, ship the
narrower thing. Specifically:

- **No custom frontend.** Grafana is the UI. If you find yourself writing HTML, stop.
- **No abstraction for a second backend.** There is one system under test: Amadeus MCP.
- **No test framework for the test framework.** A `pytest` smoke test on the fingerprinter is the ceiling.
- **No config system.** Environment variables and two YAML files.
- **No database.** JSON files in `fixtures/` are the state store.
- **No auth, no multi-tenancy, no RBAC.**

If a task is not on the critical path in `docs/BUILD_PLAN.md`, do not start it. Say so and ask.

## The one rule that must never be broken

**The LLM classifies and explains. It never produces a number that lands in Prometheus.**

`drift_score` is a fixed lookup from the classification enum. Latency is measured with a clock.
Success is a boolean from an exception handler. If you are tempted to have the model "rate the
severity from 0 to 10", that is the wrong design — return an enum and map it in code.

Related: **never auto-heal a `semantic` or `breaking` classification.** Cosmetic only. A healer that
repairs a meaning change turns a caught defect into a green build. This distinction is the project's
entire thesis; protect it.

## Repository layout

```
docs/          PROBLEM_STATEMENT · ARCHITECTURE · BUILD_PLAN · DEMO_RUNBOOK · METRICS · DECISIONS
.claude/skills/  probe-authoring · semantic-drift-judge · observability-wiring · release-verdict
infra/         docker-compose + Prometheus/Loki/Promtail/Grafana provisioning
src/           runner · fingerprint · judge · heal · assertions · verdict · metrics
src/probes/    probe definitions (YAML)
fixtures/      last-known-good responses, alias_map.json, seeded drift fixtures
```

## Conventions

- **Python 3.11**, standard library plus: `prometheus_client`, `pyyaml`, `httpx`, `anthropic`.
- **Single-line JSON logs** to stdout. Promtail scrapes them. Never `print()` free text.
- **Every log line carries** `probe`, `kind`, `ts`. See the log contract in `docs/ARCHITECTURE.md`.
- **Metric names are prefixed `ds_`.** The full list is in `docs/METRICS.md` — do not invent new ones
  without adding them there in the same commit.
- **Functions over classes** unless state genuinely persists across calls.
- **No comments explaining what the code does.** Comments explain *why* a non-obvious choice was made.

## Modes

`PROBE_MODE=live` → real Amadeus MCP tool calls.
`PROBE_MODE=replay` → reads `fixtures/`, used for the demo and for offline development.

Both share the entire downstream path. Never branch on mode below `src/runner.py`.

## When you change something

1. Update `CHANGELOG.md` under `[Unreleased]` — one line, plain English.
2. If it's a design choice with a trade-off, add an entry to `docs/DECISIONS.md`.
3. If it adds or renames a metric or log kind, update `docs/METRICS.md` **in the same change**.

## What to do when stuck

- Amadeus MCP failing? Switch to `PROBE_MODE=replay` and keep building. Do not spend more than
  15 minutes debugging credentials — flag it and move on.
- Grafana not showing data? Check Prometheus targets at `localhost:9090/targets` first, then the
  datasource UID in `infra/grafana/provisioning/datasources/`. Do not rebuild the dashboard.
- LLM judge returning garbage? Tighten the JSON schema in the prompt and add one worked example.
  See `.claude/skills/semantic-drift-judge/SKILL.md`.

## Demo integrity

The seeded drift fixture is a *scheduled arrival of a change*, not a faked detection. The detection
path is identical in live and replay mode. State this plainly if asked — do not present replay data
as live traffic.

## Tone for any generated docs or slides

Plain, direct, no marketing adjectives. The idea is strong enough that overselling it makes it
sound weaker. Never write "revolutionary", "seamless", or "cutting-edge".
