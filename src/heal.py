from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src import logs, metrics
from src.assertions import load_alias_map, save_alias_map

# Cosmetic heals. Semantic never does. A healer that repairs a meaning change turns a
# caught defect into a green build - docs/DECISIONS.md D3.

# An unsure heal is the same failure mode as a wrong one: it edits the assertion that
# would have caught the defect. Below this floor we leave the probe red and let a human
# look - docs/DECISIONS.md D10.
CONFIDENCE_FLOOR = 0.7


def _confidence(verdict: Dict[str, Any]) -> float:
    """A judgment that reports no confidence is not a confident judgment."""
    try:
        return float(verdict.get("confidence"))
    except (TypeError, ValueError):
        return 0.0


def _logical_for(alias_map: Dict[str, List[str]], old_path: str) -> Optional[str]:
    """Find the intent whose path moved. Suffix match, because the judge reports an
    absolute path and the alias map stores offer-relative ones."""
    best, best_len = None, -1
    for logical, candidates in alias_map.items():
        for candidate in candidates:
            if old_path == candidate or old_path.endswith("." + candidate):
                if len(candidate) > best_len:
                    best, best_len = logical, len(candidate)
    return best


def _relative(new_path: str, old_path: str, old_relative: str) -> str:
    prefix = old_path[: len(old_path) - len(old_relative)]
    return new_path[len(prefix) :] if new_path.startswith(prefix) else new_path


def apply(probe: str, verdict: Dict[str, Any]) -> Tuple[str, str]:
    classification = verdict["classification"]
    heal = verdict.get("proposed_heal")

    if classification in ("semantic", "breaking"):
        justification = (
            f"refused: {classification} change must not be healed - {verdict['rationale']}"
        )
        metrics.self_heal_total.labels(probe=probe, outcome="refused").inc()
        logs.emit("heal", probe=probe, outcome="refused", old_path=None, new_path=None,
                  justification=justification, classification=classification)
        return "refused", justification

    if classification != "cosmetic" or not heal:
        return "none", "no heal proposed"

    confidence = _confidence(verdict)
    if confidence < CONFIDENCE_FLOOR:
        justification = (
            f"refused: cosmetic call carried confidence {confidence}, below the {CONFIDENCE_FLOOR} "
            f"floor - {verdict['rationale']}"
        )
        metrics.self_heal_total.labels(probe=probe, outcome="refused_low_confidence").inc()
        logs.emit("heal", probe=probe, outcome="refused_low_confidence", old_path=heal["old_path"],
                  new_path=heal["new_path"], justification=justification,
                  classification=classification, confidence=confidence)
        return "refused", justification

    alias_map = load_alias_map()
    logical = _logical_for(alias_map, heal["old_path"])
    if logical is None:
        justification = (
            f"refused: {heal['old_path']} is not mapped to any intent, so there is nothing to remap"
        )
        metrics.self_heal_total.labels(probe=probe, outcome="refused").inc()
        logs.emit("heal", probe=probe, outcome="refused", old_path=heal["old_path"],
                  new_path=heal["new_path"], justification=justification,
                  classification=classification)
        return "refused", justification

    old_relative = next(
        c for c in alias_map[logical]
        if heal["old_path"] == c or heal["old_path"].endswith("." + c)
    )
    new_relative = _relative(heal["new_path"], heal["old_path"], old_relative)

    if new_relative not in alias_map[logical]:
        # Prepend: the new path wins, the old one stays as a fallback so a partial
        # rollout serving both shapes keeps passing.
        alias_map[logical] = [new_relative] + alias_map[logical]
        save_alias_map(alias_map)

    justification = (
        f"applied: intent '{logical}' remapped from {old_relative} to {new_relative} - "
        f"{verdict['rationale']}"
    )
    metrics.self_heal_total.labels(probe=probe, outcome="applied").inc()
    logs.emit("heal", probe=probe, outcome="applied", old_path=old_relative,
              new_path=new_relative, justification=justification, classification=classification,
              logical=logical)
    return "applied", justification
