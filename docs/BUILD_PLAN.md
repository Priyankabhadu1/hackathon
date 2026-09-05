# Build Plan — 4 hours

Roles assume 3 people. With 2, drop the stretch items and have Infra pick up Judge after Hour 2.

| Role | Owns |
|---|---|
| **Infra** | docker-compose, Prometheus, Loki, Promtail, Grafana provisioning, dashboards |
| **Probes** | MCP client, probe runner, assertions, metrics export, fixtures |
| **Intelligence** | Fingerprinter, drift judge, self-healer, verdict generator |

## Before the clock starts (do this the night before if allowed)

- [ ] `docker compose pull` — image download is the single biggest time sink
- [ ] Amadeus MCP credentials tested with one successful tool call, saved in `.env`
- [ ] LLM API key in `.env`, one successful completion
- [ ] `pip install -r requirements.txt` in a venv
- [ ] Save 3–4 real MCP responses into `fixtures/baseline/` — these become replay mode

## Hour 1 — Wires connected (target: one fake metric visible in Grafana)

**Infra**
- [ ] `docker compose up` — Prometheus :9090, Loki :3100, Grafana :3000, Promtail
- [ ] Confirm Grafana datasources auto-provisioned (Prometheus + Loki both green in Connections)
- [ ] Confirm Prometheus is scraping `host.docker.internal:8000/metrics` (target UP)

**Probes**
- [ ] `src/mcp_client.py` — one function, one Amadeus MCP tool call, returns dict
- [ ] `src/metrics.py` — `prometheus_client` registry + `start_http_server(8000)`
- [ ] Emit one hardcoded gauge, see it graph in Grafana

**Intelligence**
- [ ] `src/llm.py` — one function: prompt in, parsed JSON out, with retry on bad JSON
- [ ] Verify one round-trip

**Gate:** a number changes in Grafana because Python changed it. Nothing else matters yet.

## Hour 2 — Probes and health (target: workflow health dashboard)

**Probes**
- [ ] `src/probes/*.yaml` — 4 probes: `roundtrip_search`, `connecting_search`, `hotel_search`, `invalid_input`
- [ ] `src/runner.py` — load probes, loop every `PROBE_INTERVAL`, time each call, catch errors
- [ ] Export `ds_probe_runs_total`, `ds_probe_latency_seconds`, `ds_probe_success`
- [ ] `src/assertions.py` — 3 intent assertions per probe (see skill: probe-authoring)
- [ ] JSON logs to stdout with `kind=probe_run`

**Infra**
- [ ] Promtail scraping the runner's stdout into Loki; confirm in Grafana Explore
- [ ] **Dashboard D1 — Workflow Health**: success rate per workflow, p95 latency, last-run status table

**Intelligence**
- [ ] `src/fingerprint.py` — field-path set + type map + stable hash; `pytest` smoke test on it
- [ ] Store last-known-good fingerprint per probe in `fixtures/state.json`

**Gate:** D1 looks like an uptime page for *travel workflows*, updating live.

## Hour 3 — Drift, judgment, healing (target: the money shot)

**Intelligence**
- [ ] `src/judge.py` — structural diff → LLM → `{classification, rationale, proposed_heal}` (see skill)
- [ ] Map classification → `ds_drift_score` via fixed lookup. **Never** let the LLM emit the number
- [ ] `src/heal.py` — cosmetic only: write alias into `fixtures/alias_map.json`, count `ds_self_heal_total`
- [ ] Semantic/breaking → refuse heal, fail probe, log rationale
- [ ] Log `kind=drift_judgment` and `kind=heal` to Loki

**Probes**
- [ ] Assertion engine resolves field paths through the alias map
- [ ] Seed `fixtures/drifted/` — two variants: one cosmetic (field renamed), one semantic (price
      composition changed, tax excluded). See `docs/DEMO_RUNBOOK.md`
- [ ] `scripts/trigger_drift.sh` — swaps the active fixture, so drift arrives on cue

**Infra**
- [ ] **Dashboard D2 — Drift Timeline**: `ds_drift_score` over time, Loki annotation showing the
      LLM rationale at each spike, self-heal counter panel

**Gate:** run `trigger_drift.sh`, watch D2 spike, click the annotation, read the model's reasoning.

## Hour 4 — Verdict, polish, rehearse

**Intelligence**
- [ ] `src/verdict.py` — query Prometheus HTTP API (last 15m) + Loki (recent rationales) → LLM → 
      structured `{decision: PASS|HOLD, reasoning, evidence[]}`
- [ ] Log `kind=verdict`; expose decision as a gauge for a Grafana stat panel

**Infra**
- [ ] **Dashboard D3 — Release Verdict**: big PASS/HOLD stat + text panel with the reasoning
- [ ] Set Grafana home dashboard, dark theme, sensible time range (last 30m, 5s refresh)

**Everyone**
- [ ] Two full rehearsals of `docs/DEMO_RUNBOOK.md`, timed
- [ ] Fix the single most likely live failure (usually network to MCP → confirm replay fallback works)
- [ ] Cut `1.0.0` in `CHANGELOG.md`

## Stretch (only if genuinely ahead — unlikely)

- Probe variant generation: LLM proposes a new probe from an existing one
- Risk-weighted scheduling: high-risk probes run 4× more often
- A security probe type (IDOR-style: request another session's offer id)

## Anti-goals — do not build these
Custom UI · auth · a plugin system · a CLI with subcommands · Kubernetes · a database ·
retry/backoff sophistication · anything with the word "framework" in it.
