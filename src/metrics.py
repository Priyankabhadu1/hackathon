from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from src import config

# Contract lives in docs/METRICS.md. Adding one here without adding it there is a bug.

probe_runs_total = Counter(
    "ds_probe_runs_total", "Probe executions by outcome", ["probe", "workflow", "result"]
)
probe_latency_seconds = Histogram(
    "ds_probe_latency_seconds",
    "End-to-end call latency",
    ["probe", "workflow"],
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
probe_success = Gauge("ds_probe_success", "1/0 last run outcome", ["probe", "workflow"])
probe_last_run_timestamp = Gauge(
    "ds_probe_last_run_timestamp", "Unix seconds of last run", ["probe"]
)

drift_score = Gauge("ds_drift_score", "0.0-1.0 derived from classification", ["probe", "classification"])
drift_events_total = Counter("ds_drift_events_total", "Judged drift events", ["probe", "classification"])
fingerprint_changes_total = Counter(
    "ds_fingerprint_changes_total", "Fingerprint changes, including those judged none", ["probe"]
)

self_heal_total = Counter("ds_self_heal_total", "Heals applied or refused", ["probe", "outcome"])
assertion_failures_total = Counter(
    "ds_assertion_failures_total", "Intent-level assertion failures", ["probe", "assertion"]
)
manual_edits_total = Counter("ds_manual_edits_total", "Manually authored fixes")

release_verdict = Gauge("ds_release_verdict", "1 = PASS, 0 = HOLD")
verdict_generated_timestamp = Gauge("ds_verdict_generated_timestamp", "Unix seconds of last verdict")

# The maintenance-reduction claim is only credible if the series exists and sits at zero.
manual_edits_total.inc(0)

CLASSIFICATIONS = ("none", "cosmetic", "semantic", "breaking")

DRIFT_SCORE = {"none": 0.0, "cosmetic": 0.3, "semantic": 0.7, "breaking": 1.0}


def score_for(classification: str) -> float:
    return DRIFT_SCORE[classification]


def set_drift(probe: str, classification: str) -> float:
    """Publish the score for this classification and zero the others.

    Without the reset, a probe that healed yesterday keeps a stale 0.7 series alive
    and max() over the label set never comes back down.
    """
    value = score_for(classification)
    for name in CLASSIFICATIONS:
        drift_score.labels(probe=probe, classification=name).set(
            value if name == classification else 0.0
        )
    return value


def serve() -> None:
    start_http_server(config.METRICS_PORT)
