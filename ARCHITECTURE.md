# Architecture

## System diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                        SYSTEM UNDER TEST                               │
│                          Amadeus MCP                                   │
│        flight-offers-search · hotel-search · flight-price · ...        │
└───────────────────────────────┬────────────────────────────────────────┘
                                │ tool calls (real) / fixture replay (demo)
                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│  PROBE RUNNER (src/runner.py)              — loop every PROBE_INTERVAL │
│  ├ loads probe definitions (src/probes/*.yaml)                         │
│  ├ calls Amadeus MCP tool with fixed params                            │
│  ├ times it, catches errors                                            │
│  └ hands (probe, response) to the Fingerprinter                        │
└───────┬──────────────────────────────────────────┬─────────────────────┘
        │                                          │
        ▼                                          ▼
┌───────────────────────────┐        ┌─────────────────────────────────────┐
│ FINGERPRINTER             │        │ ASSERTION ENGINE                     │
│ (src/fingerprint.py)      │        │ (src/assertions.py)                  │
│ • field-path set          │        │ • intent-level checks                │
│ • type map                │        │   "an offer has a total price"       │
│ • semantic descriptors    │        │   "currency is a 3-letter code"      │
│ • stable hash             │        │ • resolves via field-path alias map  │
└───────┬───────────────────┘        └───────────────┬─────────────────────┘
        │ hash != last_known_good                    │ assertion fails
        ▼                                            ▼
┌────────────────────────────────────────────────────────────────────────┐
│  DRIFT JUDGE (src/judge.py)  ← the only LLM in the hot path            │
│  Input : probe name, old sample, new sample, structural diff           │
│  Output: {classification, drift_score, rationale, proposed_heal}       │
│          classification ∈ {none, cosmetic, semantic, breaking}          │
│  Rules  : LLM never produces metric values; it classifies and explains │
└───────┬────────────────────────────────────────┬───────────────────────┘
        │                                        │ proposed_heal
        │                                        ▼
        │                          ┌──────────────────────────────────┐
        │                          │ SELF-HEALER (src/heal.py)        │
        │                          │ • cosmetic → apply alias, log    │
        │                          │ • semantic → refuse, raise alert │
        │                          │ • writes fixtures/alias_map.json │
        │                          └──────────────────────────────────┘
        ▼
┌──────────────────────┐   ┌──────────────────────┐
│ PROMETHEUS           │   │ LOKI                 │
│ /metrics on :8000    │   │ via promtail or push │
│ • probe_latency      │   │ • raw req/resp       │
│ • probe_success      │   │ • structural diff    │
│ • drift_score        │   │ • LLM rationale      │
│ • self_heal_total    │   │ • heal decisions     │
└──────────┬───────────┘   └──────────┬───────────┘
           └──────────────┬───────────┘
                          ▼
             ┌────────────────────────────┐
             │ GRAFANA (the only UI)      │
             │ D1 Workflow Health         │
             │ D2 Drift Timeline + notes  │
             │ D3 Release Verdict panel   │
             └────────────┬───────────────┘
                          ▼
             ┌────────────────────────────┐
             │ VERDICT (src/verdict.py)   │
             │ queries Prom + Loki APIs,  │
             │ LLM writes PASS/HOLD text  │
             └────────────────────────────┘
```

## Mapping to the session's reference architecture

| Their box | Our component | Built? |
|---|---|---|
| Change Detection | Fingerprinter + Prometheus alert rule | ✅ core |
| AI QA Engine → Test Generation | Probe variant generator (LLM, offline) | ⚠️ stretch |
| AI QA Engine → Self-Healing Tests | Self-Healer + alias map | ✅ core |
| AI QA Engine → Risk-Based Selection | Static risk weights in probe YAML → probe frequency | ✅ minimal |
| Quality Validation → API Testing | Probe Runner + Assertion Engine | ✅ core |
| Quality Validation → UI / Security / Accessibility | Pluggable probe `type:` field, not implemented | ❌ slot only |
| Quality Validation → Performance | Latency histogram per workflow | ✅ minimal |
| Quality Insights & Reports | Grafana D1–D3 + LLM rationales | ✅ core |
| Release Decision | Verdict generator | ✅ core |

## Key design decisions

### D1 — The LLM classifies, it never measures
Every number in Prometheus is computed by deterministic code. The LLM produces a *classification* and a *rationale*. `drift_score` is derived from the classification via a fixed lookup (`none=0, cosmetic=0.3, semantic=0.7, breaking=1.0`), not sampled from the model. This is what makes the system defensible — an LLM that emits metrics is an LLM that hallucinates your dashboard.

### D2 — Assertions target intent, not field paths
An assertion says *"every offer exposes a total price in a valid currency"*, not *"`data[0].price.total` exists"*. Field paths live in `fixtures/alias_map.json` and are allowed to change. This is what makes self-healing safe: the healer may remap the path, never the intent.

### D3 — Cosmetic heals automatically, semantic never does
| Classification | Action |
|---|---|
| `none` | continue |
| `cosmetic` | apply alias, increment `self_heal_total`, log rationale, stay green |
| `semantic` | **do not heal**, mark probe failed, raise drift alert, log rationale |
| `breaking` | fail probe, drift score 1.0, verdict forced to HOLD |

A healer that silently repairs a semantic change is worse than no healer at all — it converts a caught bug into a green build. This distinction is the intellectual core of the project and should be said out loud in the pitch.

### D4 — Fixture replay for demo determinism
Live APIs do not drift on cue. `PROBE_MODE=replay` reads `fixtures/*.json` instead of calling MCP, letting us trigger a scripted drift event during the demo. `PROBE_MODE=live` calls Amadeus MCP for real. Both paths run through identical downstream code — the drift detection is not faked, only the *arrival* of the change is scheduled. Say this openly to judges; the honesty reads as rigour.

### D5 — Grafana is the frontend
No custom UI. Dashboards are provisioned as JSON in `infra/grafana/provisioning/`. Every minute spent on a React app is a minute not spent on the thing being judged.

## Metric contract (Prometheus)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `ds_probe_runs_total` | Counter | `probe`, `workflow`, `result` | probe executions by outcome |
| `ds_probe_latency_seconds` | Histogram | `probe`, `workflow` | end-to-end MCP call latency |
| `ds_probe_success` | Gauge | `probe`, `workflow` | 1/0 last run outcome |
| `ds_drift_score` | Gauge | `probe`, `classification` | 0.0–1.0, derived from classification |
| `ds_drift_events_total` | Counter | `probe`, `classification` | drift events observed |
| `ds_self_heal_total` | Counter | `probe`, `outcome` | heals applied / refused |
| `ds_assertion_failures_total` | Counter | `probe`, `assertion` | intent-level assertion failures |
| `ds_manual_edits_total` | Counter | — | manually authored fixes (stays 0 in demo — this is the 70–80% claim) |

## Log contract (Loki)

All logs are single-line JSON, labels `{job="driftsentinel", probe="<name>", kind="<kind>"}`.

| `kind` | Payload |
|---|---|
| `probe_run` | request params, status, latency_ms, truncated response |
| `structural_diff` | added/removed/retyped field paths |
| `drift_judgment` | classification, rationale, model, prompt_hash |
| `heal` | old path, new path, outcome, justification |
| `verdict` | decision, reasoning, window queried |

## Failure modes we accept

- **LLM latency** in the probe loop. Mitigated: judge only runs when the fingerprint changes, which is rare.
- **Amadeus test-env flakiness.** Mitigated: replay mode + cached last-good response.
- **Judge false-negatives** (calls a semantic change cosmetic). Mitigated: heal actions are logged and counted, never silent; a human can audit every heal in Loki.
