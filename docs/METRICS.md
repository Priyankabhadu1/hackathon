# Metrics and Log Contract

Single source of truth. **If you add or rename anything, update this file in the same change.**

## Prometheus metrics

All metrics are prefixed `ds_`. Exposed at `http://localhost:8000/metrics`.

### Probe execution

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `ds_probe_runs_total` | Counter | `probe`, `workflow`, `result` | `result` ∈ `pass`, `fail`, `error` |
| `ds_probe_latency_seconds` | Histogram | `probe`, `workflow` | buckets: .1 .25 .5 1 2.5 5 10 |
| `ds_probe_success` | Gauge | `probe`, `workflow` | 1 or 0, last run |
| `ds_probe_last_run_timestamp` | Gauge | `probe` | unix seconds, for staleness alerts |

### Drift

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `ds_drift_score` | Gauge | `probe`, `classification` | fixed lookup, see below |
| `ds_drift_events_total` | Counter | `probe`, `classification` | one per judged fingerprint change |
| `ds_fingerprint_changes_total` | Counter | `probe` | includes changes judged `none` |

**Classification → score lookup (in code, never from the LLM):**

```python
DRIFT_SCORE = {"none": 0.0, "cosmetic": 0.3, "semantic": 0.7, "breaking": 1.0}
```

### Healing and assertions

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `ds_self_heal_total` | Counter | `probe`, `outcome` | `outcome` ∈ `applied`, `refused`, `refused_low_confidence` |
| `ds_assertion_failures_total` | Counter | `probe`, `assertion` | intent-level failures |
| `ds_manual_edits_total` | Counter | — | incremented by hand only. **Stays 0 in the demo — this is the maintenance-reduction claim** |

### Verdict

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `ds_release_verdict` | Gauge | — | 1 = PASS, 0 = HOLD |
| `ds_verdict_generated_timestamp` | Gauge | — | unix seconds |

## Loki log contract

One JSON object per line on stdout. Promtail adds `job="driftsentinel"`.

**Every line must contain:** `ts` (ISO-8601), `kind`, `probe`.

| `kind` | Additional fields |
|---|---|
| `probe_run` | `workflow`, `params`, `status`, `latency_ms`, `response_excerpt` |
| `structural_diff` | `added[]`, `removed[]`, `retyped[]`, `fingerprint_old`, `fingerprint_new` |
| `drift_judgment` | `classification`, `rationale`, `proposed_heal`, `model` |
| `heal` | `old_path`, `new_path`, `outcome`, `justification` |
| `assertion_failure` | `assertion`, `expected`, `actual` |
| `verdict` | `decision`, `reasoning`, `evidence[]`, `window` |

## Useful queries

**Grafana D1 — success rate per workflow (5m)**
```promql
sum by (workflow) (rate(ds_probe_runs_total{result="pass"}[5m]))
/ sum by (workflow) (rate(ds_probe_runs_total[5m]))
```

**Grafana D1 — p95 latency**
```promql
histogram_quantile(0.95, sum by (le, workflow) (rate(ds_probe_latency_seconds_bucket[5m])))
```

**Grafana D2 — drift timeline**
```promql
max by (probe) (ds_drift_score)
```

**Grafana D2 — rationale annotations (Loki)**
```logql
{job="driftsentinel"} | json | kind="drift_judgment" | line_format "{{.classification}}: {{.rationale}}"
```

**Grafana D2 — heals applied vs refused**
```promql
sum by (outcome) (increase(ds_self_heal_total[30m]))
```

**Grafana D3 — verdict stat**
```promql
ds_release_verdict
```

## Alert rules (infra/prometheus/rules.yml)

| Alert | Expression | Meaning |
|---|---|---|
| `SemanticDriftDetected` | `ds_drift_score >= 0.7` for 1m | a meaning change landed — block release |
| `ProbeWorkflowDown` | `ds_probe_success == 0` for 2m | a travel workflow is failing |
| `ProbeStale` | `time() - ds_probe_last_run_timestamp > 180` | runner has stopped |

The release gate ignores the success-rate signal for a workflow with fewer than
`verdict.MIN_RUNS_FOR_RATE` runs in the window — `rate()` over a single sample is not evidence.
