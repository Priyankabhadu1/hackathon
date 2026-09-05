"""Step the pipeline through one probe cycle and report what every stage did.

The demo problem this solves: the interesting work happens in about four milliseconds
across six modules, and a dashboard can only show you the wreckage afterwards. This
replays the same functions in the same order with the timings, the inputs and the log
lines each one produced, so the internals can be walked through rather than described.

It runs as a subprocess against a copy of the alias map in a temp directory, so nothing
it does touches the running system: no Prometheus counters that anyone scrapes, no edit
to fixtures/alias_map.json, no lines in the real log.

    python -m ui.simulate --variant semantic --probe roundtrip_search
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time


def _stage(name, module, func, note=""):
    return {"name": name, "module": module, "func": func, "note": note,
            "ran": True, "ms": 0.0, "input": {}, "output": {}, "logs": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="semantic")
    ap.add_argument("--probe", default="roundtrip_search")
    ap.add_argument("--from", dest="prior", default="baseline",
                    help="the variant the probe saw on its previous cycle")
    args = ap.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo)
    sandbox = tempfile.mkdtemp(prefix="ds-sim-")
    alias_path = os.path.join(sandbox, "alias_map.json")
    shutil.copy(os.path.join(repo, "fixtures/alias_map.baseline.json"), alias_path)

    os.environ["LOG_FILE"] = os.path.join(sandbox, "sim.log")
    os.environ["PROBE_MODE"] = "replay"
    sys.path.insert(0, repo)

    from src import assertions, config, fingerprint, heal, judge, llm, state
    config.ALIAS_MAP_PATH = alias_path

    probes = {}
    import glob
    import yaml
    for path in sorted(glob.glob(os.path.join(config.PROBE_DIR, "*.yaml"))):
        with open(path) as fh:
            p = yaml.safe_load(fh)
            probes[p["name"]] = p
    probe = probes[args.probe]
    names = probe.get("assertions", [])

    def serve(variant):
        # Read the fixture directly. The live active_variant file is never touched,
        # so simulating never disturbs whatever the running probe loop is serving.
        path = (os.path.join(repo, "fixtures/baseline", f"{args.probe}.json")
                if variant == "baseline"
                else os.path.join(repo, "fixtures/drifted", variant, f"{args.probe}.json"))
        if not os.path.exists(path):
            path = os.path.join(repo, "fixtures/baseline", f"{args.probe}.json")
        with open(path) as fh:
            return json.load(fh), os.path.relpath(path, repo)

    def timed(fn):
        buf = io.StringIO()
        started = time.perf_counter()
        with contextlib.redirect_stdout(buf):
            value = fn()
        ms = round((time.perf_counter() - started) * 1000, 3)
        lines = [l for l in buf.getvalue().splitlines() if l.strip().startswith("{")]
        return value, ms, lines

    stages = []

    # ---- 0. establish the last-known-good the probe is comparing against -----------
    prior_doc, prior_path = serve(args.prior)
    prior_fp = fingerprint.fingerprint(prior_doc)

    # ---- 1. probe call --------------------------------------------------------------
    (doc, doc_path), ms, _ = timed(lambda: serve(args.variant))
    s = _stage("Probe call", "src/mcp_client.py", "replay_client()",
               "In live mode this is an Amadeus MCP tool call with the same fixed params.")
    s["ms"] = ms
    s["input"] = {"tool": probe["tool"], "params": probe.get("params", {})}
    s["output"] = {"served": doc_path, "bytes": len(json.dumps(doc)),
                   "offers": len(doc.get("data", []))}
    stages.append(s)

    # ---- 2. fingerprint -------------------------------------------------------------
    (cur_fp, delta), ms, _ = timed(
        lambda: (fingerprint.fingerprint(doc), None))
    delta = fingerprint.diff(prior_fp, cur_fp)
    shape_changed = not fingerprint.is_empty(delta)
    s = _stage("Fingerprint", "src/fingerprint.py", "fingerprint() then diff()",
               "Field paths and type kinds only. Values never enter the hash, so a price "
               "move or a different offer count cannot shift it.")
    s["ms"] = ms
    s["input"] = {"previous": f"{prior_path} -> {prior_fp['hash']}",
                  "paths_tracked": len(cur_fp["paths"])}
    s["output"] = {"hash": cur_fp["hash"], "changed": shape_changed,
                   "added": delta["added"], "removed": delta["removed"],
                   "retyped": delta["retyped"]}
    stages.append(s)

    # ---- 3. assertions --------------------------------------------------------------
    alias = assertions.load_alias_map()
    results, ms, _ = timed(lambda: assertions.run(names, doc, alias, probe))
    failures = [r for r in results if not r["ok"]]
    s = _stage("Intent assertions", "src/assertions.py", "run()",
               "Each check names an intent and resolves it through the alias map. No "
               "assertion mentions a field path directly - that is what makes healing safe.")
    s["ms"] = ms
    s["input"] = {"assertions": names, "offer.total resolves via": alias.get("offer.total")}
    s["output"] = {"results": [{"assertion": r["assertion"], "intent": r["intent"],
                                "ok": r["ok"], "detail": r["detail"]} for r in results],
                   "failing": [r["assertion"] for r in failures]}
    stages.append(s)

    # ---- 4. trigger decision --------------------------------------------------------
    signature = ",".join(sorted(r["assertion"] for r in failures))
    triggered = shape_changed or bool(signature)
    s = _stage("Trigger", "src/runner.py", "run_probe()",
               "Two independent triggers. A meaning change need not move the structure at "
               "all, so an invariant breaking is its own reason to wake the judge.")
    s["input"] = {"shape_changed": shape_changed, "failing_signature": signature or "(none)"}
    s["output"] = {"judge_runs": triggered,
                   "because": "structure" if shape_changed else ("invariant" if signature else "nothing changed")}
    s["ran"] = True
    stages.append(s)

    # ---- 5. judge -------------------------------------------------------------------
    verdict = None
    if triggered:
        verdict, ms, logs = timed(lambda: judge.judge(
            args.probe, delta, failures, state.trim(prior_doc), state.trim(doc)))
        s = _stage("Drift judge", "src/judge.py", "judge()",
                   "The only model call in the hot path, and it never returns a number that "
                   "reaches Prometheus - drift_score is a lookup on the classification.")
        s["ms"] = ms
        s["input"] = {"provider": llm.provider(), "structural_diff": delta,
                      "failing_invariants": [{"intent": f["intent"], "detail": f["detail"]}
                                             for f in failures]}
        s["output"] = {"classification": verdict["classification"],
                       "rationale": verdict["rationale"],
                       "confidence": verdict.get("confidence"),
                       "proposed_heal": verdict.get("proposed_heal"),
                       "model": verdict.get("model"),
                       "drift_score": {"none": 0.0, "cosmetic": 0.3,
                                       "semantic": 0.7, "breaking": 1.0}[verdict["classification"]]}
        s["logs"] = logs
        stages.append(s)
    else:
        s = _stage("Drift judge", "src/judge.py", "judge()",
                   "Skipped. Steady state costs one hash comparison and the invariants - no "
                   "model call, no tokens.")
        s["ran"] = False
        stages.append(s)

    # ---- 6. healer ------------------------------------------------------------------
    before_alias = dict(assertions.load_alias_map())
    if verdict:
        (outcome, why), ms, logs = timed(lambda: heal.apply(args.probe, verdict))
        after_alias = assertions.load_alias_map()
        s = _stage("Self-healer", "src/heal.py", "apply()",
                   "Cosmetic remaps are applied and counted. Semantic and breaking are "
                   "refused on principle, and a cosmetic call under the confidence floor "
                   "is refused too.")
        s["ms"] = ms
        s["input"] = {"classification": verdict["classification"],
                      "confidence": verdict.get("confidence"),
                      "floor": heal.CONFIDENCE_FLOOR,
                      "offer.total before": before_alias.get("offer.total")}
        s["output"] = {"outcome": outcome, "justification": why,
                       "offer.total after": after_alias.get("offer.total"),
                       "alias_changed": before_alias != after_alias}
        s["logs"] = logs
        stages.append(s)
    else:
        s = _stage("Self-healer", "src/heal.py", "apply()", "Skipped - no judgment to act on.")
        s["ran"] = False
        stages.append(s)

    # ---- 7. re-assert after a heal --------------------------------------------------
    final = results
    if verdict and stages[-1]["output"].get("outcome") == "applied":
        alias2 = assertions.load_alias_map()
        final, ms, _ = timed(lambda: assertions.run(names, doc, alias2, probe))
        s = _stage("Re-assert", "src/runner.py", "assertions.run()",
                   "The heal only counts if the intent holds afterwards. This is the same "
                   "response, re-checked through the remapped path.")
        s["ms"] = ms
        s["input"] = {"offer.total resolves via": alias2.get("offer.total")}
        s["output"] = {"results": [{"assertion": r["assertion"], "ok": r["ok"],
                                    "detail": r["detail"]} for r in final],
                       "failing": [r["assertion"] for r in final if not r["ok"]]}
        stages.append(s)

    # ---- 8. what would be exported --------------------------------------------------
    passed = all(r["ok"] for r in final)
    cls = verdict["classification"] if verdict else "none"
    score = {"none": 0.0, "cosmetic": 0.3, "semantic": 0.7, "breaking": 1.0}[cls]
    heal_stage = next((x for x in stages if x["module"] == "src/heal.py" and x["ran"]), None)
    exported = {
        "ds_probe_success": 1 if passed else 0,
        "ds_probe_runs_total{result}": "pass" if passed else "fail",
        "ds_drift_score": score if not passed or cls != "none" else 0.0,
        "ds_fingerprint_changes_total": 1 if shape_changed else 0,
        "ds_self_heal_total{outcome}": (heal_stage["output"]["outcome"] if heal_stage else "-"),
        "ds_assertion_failures_total": [r["assertion"] for r in final if not r["ok"]],
        "ds_manual_edits_total": 0,
    }
    s = _stage("Metrics export", "src/metrics.py", "set_drift() and counters",
               "Every one of these is computed by code. The model contributed a "
               "classification and a sentence, nothing numeric.")
    s["output"] = exported
    stages.append(s)

    total = round(sum(x["ms"] for x in stages), 3)
    shutil.rmtree(sandbox, ignore_errors=True)

    print(json.dumps({
        "probe": args.probe, "variant": args.variant, "prior": args.prior,
        "provider": llm.provider(), "total_ms": total,
        "probe_result": "pass" if passed else "fail",
        "classification": cls, "drift_score": score,
        "stages": stages,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
