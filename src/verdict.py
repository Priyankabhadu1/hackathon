from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import httpx

from src import config, llm, logs, metrics

# Release Decision. The narrative comes from the model; the decision does not.
# Hard rules win, always - a HOLD cannot be talked out of by a language model.

WINDOW = "15m"

# Below this many runs in the window, the success-rate signal is noise, not evidence.
MIN_RUNS_FOR_RATE = 5

_QUERIES = {
    "success_rate": f'sum by (workflow) (rate(ds_probe_runs_total{{result="pass"}}[{WINDOW}])) '
                    f"/ clamp_min(sum by (workflow) (rate(ds_probe_runs_total[{WINDOW}])), 0.0001)",
    "drift": "max by (probe, classification) (ds_drift_score > 0)",
    "failing_probes": "ds_probe_success == 0",
    "runs": f"sum by (workflow) (increase(ds_probe_runs_total[{WINDOW}]))",
    "heals": f"sum by (outcome) (increase(ds_self_heal_total[{WINDOW}]))",
    "manual_edits": f"increase(ds_manual_edits_total[{WINDOW}])",
}


_UNREACHABLE: List[str] = []


def _prom(query: str) -> List[Dict[str, Any]]:
    try:
        response = httpx.get(
            f"{config.PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=5.0
        )
        response.raise_for_status()
        return response.json().get("data", {}).get("result", [])
    except Exception as exc:
        logs.fail(f"prometheus query failed: {exc}")
        _UNREACHABLE.append("prometheus")
        return []


def _loki(kind: str, limit: int = 10) -> List[str]:
    try:
        response = httpx.get(
            f"{config.LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": f'{{job="driftsentinel"}} | json | kind="{kind}"',
                "limit": limit,
                "start": str(int((time.time() - 900) * 1e9)),
                "direction": "backward",
            },
            timeout=5.0,
        )
        response.raise_for_status()
        lines = []
        for stream in response.json().get("data", {}).get("result", []):
            for _, line in stream.get("values", []):
                lines.append(line)
        return lines[:limit]
    except Exception as exc:
        logs.fail(f"loki query failed: {exc}")
        _UNREACHABLE.append("loki")
        return []


def gather() -> Dict[str, Any]:
    _UNREACHABLE.clear()
    evidence: Dict[str, Any] = {name: _prom(query) for name, query in _QUERIES.items()}
    evidence["recent_judgments"] = _loki("drift_judgment")
    evidence["recent_heals"] = _loki("heal", 5)
    return evidence


def decide(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic guardrails. Reasons are facts, not opinions."""
    reasons = []

    # Fail closed. An unreachable telemetry backend is not evidence of health - without
    # it we cannot see a drift event, and a gate that says PASS when it is blind is worse
    # than no gate.
    for backend in sorted(set(_UNREACHABLE)):
        reasons.append(f"{backend} unreachable - cannot evaluate release safety")

    for series in evidence.get("drift", []):
        labels = series.get("metric", {})
        value = float(series.get("value", [0, "0"])[1])
        if value >= 0.7:
            reasons.append(
                f"{labels.get('classification')} drift on probe "
                f"{labels.get('probe')} (score {value})"
            )

    for series in evidence.get("failing_probes", []):
        labels = series.get("metric", {})
        reasons.append(f"workflow {labels.get('workflow')} failing on probe {labels.get('probe')}")

    # rate() needs two samples before it means anything, and a low-risk probe only runs
    # every fourth cycle. Without this floor a fresh Prometheus produces a HOLD for a
    # workflow that has simply not run enough times yet - a gate that cries wolf on every
    # restart is a gate people learn to ignore.
    runs = {s.get("metric", {}).get("workflow"): float(s.get("value", [0, "0"])[1])
            for s in evidence.get("runs", [])}
    for series in evidence.get("success_rate", []):
        workflow = series.get("metric", {}).get("workflow")
        if runs.get(workflow, 0) < MIN_RUNS_FOR_RATE:
            continue
        value = float(series.get("value", [0, "1"])[1])
        if value < 0.95:
            reasons.append(
                f"{workflow} success rate {round(value * 100, 1)}% over {WINDOW}"
            )

    return {"decision": "HOLD" if reasons else "PASS", "blocking_reasons": reasons}


_SYSTEM = """You write the release note for an automated quality gate.

The decision has already been made by deterministic rules - you must not change it, argue
with it, or hedge it. Write 3-5 sentences of plain English for an engineer deciding whether
to ship: what the telemetry shows, what it means commercially, and what to do next.

No marketing adjectives. No bullet points. Reply with JSON only:
{"reasoning": "...", "evidence": ["short factual line", "..."]}"""


def narrate(decision: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
    if not llm.available():
        return {
            "reasoning": (
                f"{decision['decision']} based on {len(decision['blocking_reasons'])} blocking "
                f"signal(s) over the last {WINDOW}: "
                + ("; ".join(decision["blocking_reasons"]) or "no blocking signals")
                + ". Narrative generation is disabled because no model key is configured."
            ),
            "evidence": decision["blocking_reasons"][:5],
        }

    payload = json.dumps(
        {
            "decision": decision["decision"],
            "blocking_reasons": decision["blocking_reasons"],
            "recent_drift_judgments": evidence.get("recent_judgments", [])[:5],
            "recent_heals": evidence.get("recent_heals", [])[:3],
            "window": WINDOW,
        },
        indent=2,
    )
    try:
        text = llm.complete(_SYSTEM, payload, max_tokens=600)
        start, end = text.find("{"), text.rfind("}")
        parsed = json.loads(text[start : end + 1])
        return {
            "reasoning": parsed.get("reasoning", ""),
            "evidence": parsed.get("evidence", decision["blocking_reasons"])[:6],
        }
    except Exception as exc:
        logs.fail(f"verdict narration failed: {exc}")
        return {"reasoning": f"{decision['decision']}: " + "; ".join(decision["blocking_reasons"]),
                "evidence": decision["blocking_reasons"][:5]}


def generate() -> Dict[str, Any]:
    evidence = gather()
    decision = decide(evidence)
    narrative = narrate(decision, evidence)

    metrics.release_verdict.set(1 if decision["decision"] == "PASS" else 0)
    metrics.verdict_generated_timestamp.set(time.time())

    logs.emit("verdict", decision=decision["decision"], reasoning=narrative["reasoning"],
              evidence=narrative["evidence"], window=WINDOW,
              blocking_reasons=decision["blocking_reasons"])
    return {**decision, **narrative}


if __name__ == "__main__":
    print(json.dumps(generate(), indent=2))
