from __future__ import annotations

import glob
import os
import sys
import time
from typing import Any, Dict, List

import yaml

from src import assertions, config, fingerprint, heal, judge, logs, mcp_client, metrics, state, verdict


def load_probes() -> List[Dict[str, Any]]:
    probes = []
    for path in sorted(glob.glob(os.path.join(config.PROBE_DIR, "*.yaml"))):
        with open(path) as handle:
            probes.append(yaml.safe_load(handle))
    return probes


RISK_DIVISOR = {"high": 1, "medium": 2, "low": 4}

VERDICT_EVERY = 4


def due(probe: Dict[str, Any], tick: int) -> bool:
    """Risk-based selection, the cheap version: high-risk workflows run every tick,
    low-risk ones a quarter as often."""
    return tick % RISK_DIVISOR.get(probe.get("risk", "medium"), 2) == 0


def failure_signature(results: List[Dict[str, Any]]) -> str:
    return ",".join(sorted(r["assertion"] for r in results if not r["ok"]))


def run_probe(probe: Dict[str, Any], client: mcp_client.Client, store: Dict[str, Any]) -> None:
    name, workflow = probe["name"], probe["workflow"]
    entry = store.setdefault(name, {})

    started = time.perf_counter()
    try:
        response = client(name, probe["tool"], probe.get("params", {}))
        error = None
    except Exception as exc:
        response, error = None, f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started

    metrics.probe_latency_seconds.labels(probe=name, workflow=workflow).observe(elapsed)
    metrics.probe_last_run_timestamp.labels(probe=name).set(time.time())

    if error is not None:
        metrics.probe_runs_total.labels(probe=name, workflow=workflow, result="error").inc()
        metrics.probe_success.labels(probe=name, workflow=workflow).set(0)
        logs.emit("probe_run", probe=name, workflow=workflow, params=probe.get("params", {}),
                  status="error", latency_ms=round(elapsed * 1000, 1), response_excerpt=error)
        return

    alias_map = assertions.load_alias_map()
    results = assertions.run(probe.get("assertions", []), response, alias_map)

    current = fingerprint.fingerprint(response)
    previous = entry.get("fingerprint")
    delta = fingerprint.diff(previous, current) if previous else {"added": [], "removed": [], "retyped": []}
    shape_changed = bool(previous) and not fingerprint.is_empty(delta)

    signature = failure_signature(results)
    failures_changed = signature != entry.get("failure_signature", "") and signature != ""

    if shape_changed:
        metrics.fingerprint_changes_total.labels(probe=name).inc()
        logs.emit("structural_diff", probe=name, added=delta["added"], removed=delta["removed"],
                  retyped=delta["retyped"], fingerprint_old=previous["hash"],
                  fingerprint_new=current["hash"])

    # Two triggers, because a meaning change need not move the structure at all:
    # a total that stops including tax has an identical fingerprint.
    if shape_changed or failures_changed:
        failures = [r for r in results if not r["ok"]]
        verdict = judge.judge(name, delta, failures, entry.get("sample"), state.trim(response))
        classification = verdict["classification"]

        score = metrics.set_drift(name, classification)
        metrics.drift_events_total.labels(probe=name, classification=classification).inc()
        logs.emit("drift_judgment", probe=name, classification=classification,
                  rationale=verdict["rationale"], proposed_heal=verdict.get("proposed_heal"),
                  model=verdict.get("model"), confidence=verdict.get("confidence"),
                  drift_score=score, trigger="structure" if shape_changed else "invariant")

        outcome, justification = heal.apply(name, verdict)
        entry["last_classification"] = classification

        if outcome == "applied":
            alias_map = assertions.load_alias_map()
            results = assertions.run(probe.get("assertions", []), response, alias_map)
            signature = failure_signature(results)

    for result in results:
        if not result["ok"]:
            metrics.assertion_failures_total.labels(probe=name, assertion=result["assertion"]).inc()
            logs.emit("assertion_failure", probe=name, assertion=result["assertion"],
                      expected=result.get("intent", ""), actual=result["detail"])

    passed = all(result["ok"] for result in results)
    metrics.probe_runs_total.labels(probe=name, workflow=workflow,
                                    result="pass" if passed else "fail").inc()
    metrics.probe_success.labels(probe=name, workflow=workflow).set(1 if passed else 0)

    if not (shape_changed or failures_changed):
        # Hold the last judgment while the probe is still failing; drop to zero once
        # it recovers, so the timeline shows a spike that ends.
        metrics.set_drift(name, entry.get("last_classification", "none") if not passed else "none")
        if passed:
            entry["last_classification"] = "none"

    logs.emit("probe_run", probe=name, workflow=workflow, params=probe.get("params", {}),
              status="pass" if passed else "fail", latency_ms=round(elapsed * 1000, 1),
              fingerprint=current["hash"], variant=mcp_client.active_variant(),
              response_excerpt=logs.excerpt(response))

    entry["fingerprint"] = current
    entry["failure_signature"] = signature
    entry["sample"] = state.trim(response)


def main() -> int:
    probes = load_probes()
    if not probes:
        logs.fail(f"no probe definitions found in {config.PROBE_DIR}")
        return 1

    # The only place in the codebase that knows which mode we are in.
    client = mcp_client.live_client() if config.PROBE_MODE == "live" else mcp_client.replay_client()

    metrics.serve()
    logs.emit("startup", mode=config.PROBE_MODE, probes=[p["name"] for p in probes],
              interval=config.PROBE_INTERVAL, metrics_port=config.METRICS_PORT)

    store = state.load()
    tick = 0
    while True:
        for probe in probes:
            if due(probe, tick):
                run_probe(probe, client, store)
        state.save(store)
        if tick % VERDICT_EVERY == 0:
            verdict.generate()
        tick += 1
        time.sleep(config.PROBE_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
