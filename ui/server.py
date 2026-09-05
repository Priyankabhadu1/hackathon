"""Local console for DriftSentinel. Serves one page and one JSON endpoint.

Everything it shows is read live from the running stack: Prometheus for the numbers,
Loki for the reasoning, the runner's own state file for the fingerprints. It stores
nothing and computes no quality signal of its own - if a value is on the page, some
other component put it in Prometheus or Loki first.

The page is same-origin with this server, which is why no CORS configuration is needed
on Prometheus or Loki.

    python -m ui.server        # http://localhost:8090
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

from src import config, llm, fingerprint as fp
from src.paths import resolve

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PORT = int(os.environ.get("UI_PORT", "8090"))

VARIANTS = ("baseline", "cosmetic", "semantic", "semantic_cold",
            "validation_swallowed", "minor_units", "minor_units_consistent")


def _prom(query: str) -> List[Dict[str, Any]]:
    try:
        r = httpx.get(f"{config.PROMETHEUS_URL}/api/v1/query",
                      params={"query": query}, timeout=4.0)
        r.raise_for_status()
        return r.json().get("data", {}).get("result", [])
    except Exception:
        return []


def _loki(selector: str, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        r = httpx.get(
            f"{config.LOKI_URL}/loki/api/v1/query_range",
            params={"query": selector, "limit": limit, "direction": "backward",
                    "start": str(int((time.time() - 1800) * 1e9))},
            timeout=4.0,
        )
        r.raise_for_status()
        rows = []
        for stream in r.json().get("data", {}).get("result", []):
            for ts, line in stream.get("values", []):
                try:
                    rows.append({"ts": int(ts), "rec": json.loads(line)})
                except json.JSONDecodeError:
                    continue
        rows.sort(key=lambda x: x["ts"], reverse=True)
        return rows[:limit]
    except Exception:
        return []


def _prom_range(query: str, minutes: int = 30, step: int = 15) -> List[Dict[str, Any]]:
    now = time.time()
    try:
        r = httpx.get(f"{config.PROMETHEUS_URL}/api/v1/query_range",
                      params={"query": query, "start": now - minutes * 60, "end": now,
                              "step": step}, timeout=6.0)
        r.raise_for_status()
        return r.json().get("data", {}).get("result", [])
    except Exception:
        return []


def _scalar(result: List[Dict[str, Any]], default: float = 0.0) -> float:
    return float(result[0]["value"][1]) if result else default


def _by(result: List[Dict[str, Any]], *labels: str) -> Dict[Any, float]:
    out = {}
    for row in result:
        key = tuple(row["metric"].get(l, "") for l in labels)
        out[key if len(labels) > 1 else key[0]] = float(row["value"][1])
    return out


def _reachable(url: str, path: str) -> bool:
    try:
        return httpx.get(url + path, timeout=2.0).status_code < 500
    except Exception:
        return False


def active_variant() -> str:
    try:
        with open(os.path.join(REPO, config.ACTIVE_VARIANT_PATH)) as fh:
            return fh.read().strip() or "baseline"
    except OSError:
        return "baseline"


def runner_state() -> Dict[str, Any]:
    try:
        with open(os.path.join(REPO, config.STATE_PATH)) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _fixture(variant: str, probe: str):
    path = (os.path.join(REPO, "fixtures", "baseline", f"{probe}.json") if variant == "baseline"
            else os.path.join(REPO, "fixtures", "drifted", variant, f"{probe}.json"))
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _first_offer(doc, alias):
    for candidate in alias.get("offer_list", []):
        found = resolve(doc, candidate)
        if found:
            offers = found[0] if len(found) == 1 and isinstance(found[0], list) else found
            if offers:
                return offers[0]
    return None


def quantities(doc, alias) -> Dict[str, Any]:
    """The values the invariants actually read, resolved the way the assertions resolve
    them. Showing the raw payload would show mostly itinerary noise."""
    offer = _first_offer(doc, alias)
    if offer is None:
        return {"(no offer)": "response carries no offer list"}
    out = {}
    for logical, label in (("offer.currency", "currency"), ("offer.base", "base"),
                           ("offer.total", "total")):
        for candidate in alias.get(logical, []):
            found = resolve(offer, candidate)
            if found:
                out[label] = found[0]
                break
        else:
            out[label] = None
    for logical, label in (("offer.taxes", "taxes"), ("offer.fees", "fees")):
        for candidate in alias.get(logical, []):
            found = resolve(offer, candidate)
            if found:
                out[label] = found
                break
        else:
            out[label] = []
    return out


def payload_view(variant: str, alias: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Baseline against what the replay client is serving right now, per drifting probe."""
    views = []
    drifted_dir = os.path.join(REPO, "fixtures", "drifted", variant)
    if variant == "baseline" or not os.path.isdir(drifted_dir):
        return views
    for filename in sorted(os.listdir(drifted_dir)):
        if not filename.endswith(".json"):
            continue
        probe = filename[:-5]
        base_doc, cur_doc = _fixture("baseline", probe), _fixture(variant, probe)
        if base_doc is None or cur_doc is None:
            continue
        base_fp, cur_fp = fp.fingerprint(base_doc), fp.fingerprint(cur_doc)
        delta = fp.diff(base_fp, cur_fp)
        views.append({
            "probe": probe,
            "baseline": quantities(base_doc, alias),
            "current": quantities(cur_doc, alias),
            "fingerprint_baseline": base_fp["hash"],
            "fingerprint_current": cur_fp["hash"],
            "structure_moved": not fp.is_empty(delta),
            "delta": delta,
        })
    return views


def snapshot() -> Dict[str, Any]:
    success = _by(_prom("ds_probe_success"), "probe", "workflow")
    latency = _by(_prom("histogram_quantile(0.95, sum by (le, probe) "
                        "(rate(ds_probe_latency_seconds_bucket[2m])))"), "probe")
    runs = _by(_prom("sum by (probe, result) (ds_probe_runs_total)"), "probe", "result")
    last_run = _by(_prom("ds_probe_last_run_timestamp"), "probe")
    drift = _by(_prom("ds_drift_score > 0"), "probe", "classification")
    fp_changes = _by(_prom("sum by (probe) (ds_fingerprint_changes_total)"), "probe")
    heals = _by(_prom("sum by (outcome) (ds_self_heal_total)"), "outcome")
    # increase() over a short window, because the raw counter never comes back down
    # and a probe that recovered would keep advertising a failure it no longer has.
    afails = _by(_prom("sum by (probe, assertion) (increase(ds_assertion_failures_total[45s])) > 0"),
                 "probe", "assertion")

    state = runner_state()
    probes = []
    for (probe, workflow), ok in sorted(success.items(), key=lambda kv: (kv[1], kv[0][0])):
        cls = next((c for (p, c) in drift if p == probe), None)
        probes.append({
            "probe": probe,
            "workflow": workflow,
            "ok": ok == 1,
            "p95_ms": round(latency.get(probe, 0.0) * 1000, 1),
            "pass": int(runs.get((probe, "pass"), 0)),
            "fail": int(runs.get((probe, "fail"), 0)),
            "error": int(runs.get((probe, "error"), 0)),
            "last_run": last_run.get(probe, 0),
            "drift_score": drift.get((probe, cls), 0.0) if cls else 0.0,
            "classification": cls or "none",
            "fingerprint": (state.get(probe, {}).get("fingerprint") or {}).get("hash", ""),
            "fingerprint_changes": int(fp_changes.get(probe, 0)),
            # Only while the probe is actually red. The counter window trails a recovery
            # by a few cycles, and "pass" beside a failing intent reads as a bug.
            "failing_assertions": ([a for (p, a) in afails if p == probe and afails[(p, a)] > 0]
                                   if ok == 0 else []),
        })

    # Why the judge is on its fallback, if it is. Read from the log rather than by
    # calling the provider - a health check on every 2s poll would burn real quota.
    errors = _loki('{job="driftsentinel", kind="error"}', 3)
    judge_error = next((r["rec"].get("message", "") for r in errors
                        if "judge failed" in r["rec"].get("message", "")), None)

    verdict_rows = _loki('{job="driftsentinel", kind="verdict"}', 1)
    judgments = _loki('{job="driftsentinel", kind="drift_judgment"}', 6)
    heal_rows = _loki('{job="driftsentinel", kind="heal"}', 6)

    alias = json.load(open(os.path.join(REPO, config.ALIAS_MAP_PATH)))
    variant = active_variant()

    return {
        "now": time.time(),
        "mode": config.PROBE_MODE,
        "variant": variant,
        "alias_map": alias,
        "payloads": payload_view(variant, alias),
        "stack": {
            "prometheus": _reachable(config.PROMETHEUS_URL, "/-/ready"),
            "loki": _reachable(config.LOKI_URL, "/ready"),
            "runner": bool(last_run) and (time.time() - max(last_run.values(), default=0)) < 60,
            "grafana": _reachable("http://localhost:3000", "/api/health"),
        },
        "probes": probes,
        "heals": {
            "applied": int(heals.get("applied", 0)),
            "refused": int(heals.get("refused", 0)),
            "refused_low_confidence": int(heals.get("refused_low_confidence", 0)),
        },
        "manual_edits": int(_scalar(_prom("ds_manual_edits_total"))),
        "verdict_gauge": _scalar(_prom("ds_release_verdict"), -1),
        "verdict": verdict_rows[0]["rec"] if verdict_rows else None,
        "judgments": [r["rec"] for r in judgments],
        "heal_log": [r["rec"] for r in heal_rows],
        "feed": [r["rec"] for r in _loki('{job="driftsentinel"}', 60)],
        "llm": {
            "provider": llm.provider(),
            "model": llm.model_name() if llm.available() else "heuristic-fallback",
            "configured": llm.available(),
            "last_error": judge_error,
        },
        "dora": dora(),
        "series": [
            {"probe": r["metric"].get("probe", "?"),
             "points": [[float(t), float(v)] for t, v in r.get("values", [])]}
            for r in _prom_range("max by (probe) (ds_drift_score)", 30, 15)
        ],
    }


def _restore_times(minutes: int = 60) -> Dict[str, Any]:
    """How long a probe stayed red before it came back. DORA's time-to-restore, read
    off ds_probe_success rather than off an incident tracker nobody fills in."""
    spans, open_since = [], {}
    for series in _prom_range("ds_probe_success", minutes, 15):
        probe = series.get("metric", {}).get("probe", "?")
        for ts, value in series.get("values", []):
            ok = float(value) == 1
            if not ok and probe not in open_since:
                open_since[probe] = float(ts)
            elif ok and probe in open_since:
                spans.append({"probe": probe, "seconds": round(float(ts) - open_since.pop(probe))})
    still_red = [{"probe": p, "seconds": round(time.time() - t)} for p, t in open_since.items()]
    closed = [s["seconds"] for s in spans]
    return {
        "restored": spans[-5:],
        "open": still_red,
        "mean_seconds": round(sum(closed) / len(closed)) if closed else None,
        "count": len(closed),
    }


def dora(minutes: int = 60) -> Dict[str, Any]:
    """The four delivery metrics, restated for an API contract instead of a deploy
    pipeline. The system under test is the thing shipping; we are the ones watching."""
    events = _by(_prom("sum by (classification) (ds_drift_events_total)"), "classification")
    total_events = sum(events.values())
    breaking = events.get("semantic", 0) + events.get("breaking", 0)
    heals = _by(_prom("sum by (outcome) (ds_self_heal_total)"), "outcome")
    applied = heals.get("applied", 0)
    total_heals = sum(heals.values())
    changes = _scalar(_prom(f"sum(increase(ds_fingerprint_changes_total[{minutes}m]))"))
    restore = _restore_times(minutes)

    return {
        "window_minutes": minutes,
        "change_frequency": {
            "value": round(changes, 1),
            "unit": f"shape changes / {minutes}m",
            "detail": f"{int(total_events)} judged drift events",
        },
        "change_failure_rate": {
            "value": round(100 * breaking / total_events, 1) if total_events else None,
            "unit": "% of changes that altered meaning",
            "detail": f"{int(breaking)} semantic or breaking of {int(total_events)}",
            "mix": {k: int(v) for k, v in sorted(events.items())},
        },
        "time_to_restore": {
            "value": restore["mean_seconds"],
            "unit": "seconds, mean",
            "detail": (f"{restore['count']} recoveries"
                       + (f", {len(restore['open'])} still failing" if restore["open"] else "")),
            "open": restore["open"],
            "restored": restore["restored"],
        },
        "autonomous_remediation": {
            "value": round(100 * applied / total_heals, 1) if total_heals else None,
            "unit": "% of drift absorbed without a human",
            "detail": f"{int(applied)} applied, {int(total_heals - applied)} refused on purpose",
        },
        "manual_edits": int(_scalar(_prom("ds_manual_edits_total"))),
    }


def _json_get(url: str, params: Dict[str, Any] = None) -> Any:
    try:
        r = httpx.get(url, params=params or {}, timeout=4.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def stack() -> Dict[str, Any]:
    """What each backing service is doing right now.

    Every claim on the Stack view is a live read, not a caption: if Prometheus is
    scraping, the target says so; if the alert rules loaded, they are listed with
    their state; if Loki holds the reasoning, the counts per log kind prove it.
    """
    targets = _json_get(f"{config.PROMETHEUS_URL}/api/v1/targets") or {}
    active = (targets.get("data") or {}).get("activeTargets", [])
    rules_doc = _json_get(f"{config.PROMETHEUS_URL}/api/v1/rules") or {}
    rules = [
        {"name": r.get("name"), "state": r.get("state"), "health": r.get("health"),
         "expr": r.get("query", "")}
        for g in (rules_doc.get("data") or {}).get("groups", [])
        for r in g.get("rules", [])
    ]
    names = _json_get(f"{config.PROMETHEUS_URL}/api/v1/label/__name__/values") or {}
    ds_series = [n for n in (names.get("data") or []) if n.startswith("ds_")]

    kinds_doc = _json_get(
        f"{config.LOKI_URL}/loki/api/v1/query",
        {"query": 'sum by (kind) (count_over_time({job="driftsentinel"}[30m]))'}) or {}
    kinds = {r["metric"].get("kind", "?"): int(float(r["value"][1]))
             for r in (kinds_doc.get("data") or {}).get("result", [])}

    boards = _json_get("http://localhost:3000/api/search", {"type": "dash-db"}) or []

    return {
        "prometheus": {
            "up": bool(active),
            "scrape_interval": "5s",
            "targets": [{"job": t["labels"].get("job"), "url": t.get("scrapeUrl"),
                         "health": t.get("health"), "error": t.get("lastError", "")}
                        for t in active],
            "rules": rules,
            "metric_names": sorted(ds_series),
        },
        "loki": {"up": bool(kinds), "kinds": kinds, "window": "30m"},
        "grafana": {
            "up": bool(boards),
            "dashboards": [{"title": b.get("title"),
                            "url": "http://localhost:3000" + b.get("url", "")}
                           for b in boards if isinstance(b, dict)],
        },
    }


class Console(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # the console is not a web access log
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, code: int = 200) -> None:
        self._send(code, json.dumps(payload, default=str).encode(), "application/json")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                self._send(200, fh.read(), "text/html; charset=utf-8")
        elif path == "/api/state":
            self._json(snapshot())
        elif path == "/api/stack":
            self._json(stack())
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/simulate":
            self._simulate()
            return
        if path != "/api/variant":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            variant = json.loads(self.rfile.read(length) or b"{}").get("variant")
        except json.JSONDecodeError:
            variant = None
        if variant not in VARIANTS:
            self._json({"error": f"variant must be one of {', '.join(VARIANTS)}"}, 400)
            return
        result = subprocess.run(
            [os.path.join(REPO, "scripts/trigger_drift.sh"), variant],
            cwd=REPO, capture_output=True, text=True,
        )
        self._json({"variant": variant, "ok": result.returncode == 0,
                    "message": (result.stdout or result.stderr).strip()},
                   200 if result.returncode == 0 else 500)

    def _simulate(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        variant = body.get("variant", "semantic")
        prior = body.get("prior", "baseline")
        probe = body.get("probe", "roundtrip_search")
        if variant not in VARIANTS or prior not in VARIANTS:
            self._json({"error": "unknown variant"}, 400)
            return
        result = subprocess.run(
            [sys.executable, "-m", "ui.simulate", "--variant", variant,
             "--from", prior, "--probe", probe],
            cwd=REPO, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            self._json({"error": (result.stderr or "simulation failed").strip()[-600:]}, 500)
            return
        try:
            self._json(json.loads(result.stdout))
        except json.JSONDecodeError:
            self._json({"error": "simulation produced no trace"}, 500)


def main() -> int:
    server = Console(("127.0.0.1", PORT), Handler)
    print(f"driftsentinel console on http://localhost:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
