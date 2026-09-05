from __future__ import annotations

import json
from typing import Any, Dict, List

from src import config, logs

# The only LLM in the hot path. It returns a classification and a rationale.
# It never returns a number that reaches Prometheus - see docs/DECISIONS.md D1.

CLASSIFICATIONS = ("none", "cosmetic", "semantic", "breaking")

_SYSTEM = """You judge whether a change in an API response alters its MEANING.

You are looking at a travel distribution API. Prices, availability and offer ids change on
every call - that is normal and is never drift. You are judging the contract, not the data.

Classify as exactly one of:
- none      structure moved in a way that carries no meaning (an optional field absent this
            run, a new additive field nothing depends on)
- cosmetic  the same quantity is still present under a different name or nesting. The
            meaning is intact; only the path moved.
- semantic  a field name stayed the same but the quantity it carries changed, or a value
            that carries commercial or legal meaning changed shape. Same words, different
            promise.
- breaking  something required to consume the response is gone or unusable.

A failing invariant such as "total no longer equals base plus taxes" is semantic, never
cosmetic, when every field name is unchanged.

But read the structural diff first. If an invariant broke because the field it reads was
renamed or moved - the diff shows it removed from one path and added at another - that is
cosmetic, not semantic. The quantity did not change; the assertion simply lost track of it.

Reply with one JSON object and nothing else:
{"classification": "...", "rationale": "one sentence, plain English, name the field",
 "proposed_heal": {"old_path": "...", "new_path": "..."} or null,
 "confidence": 0.0-1.0}

Only propose a heal for a cosmetic rename. For anything else proposed_heal must be null."""


def _prompt(probe: str, delta: Dict[str, List], failures: List[Dict], old_sample, new_sample) -> str:
    return json.dumps(
        {
            "probe": probe,
            "structural_diff": delta,
            "failing_invariants": [
                {"intent": f.get("intent", f["assertion"]), "detail": f["detail"]} for f in failures
            ],
            "sample_before": logs.excerpt(old_sample, 1500),
            "sample_after": logs.excerpt(new_sample, 1500),
        },
        indent=2,
        default=str,
    )


def _heuristic(delta: Dict[str, List], failures: List[Dict]) -> Dict[str, Any]:
    """Used only when no API key is configured. Keeps the pipeline demonstrable offline."""
    added, removed = delta.get("added", []), delta.get("removed", [])

    # Order matters. A rename breaks the sum invariant too - not because the total
    # changed but because the path it lived at is gone. Structure is checked first so
    # a moved field is never mistaken for a moved quantity.
    if len(added) == 1 and len(removed) == 1:
        return {
            "classification": "cosmetic",
            "rationale": f"{removed[0]} appears to have been renamed to {added[0]}",
            "proposed_heal": {"old_path": removed[0], "new_path": added[0]},
            "confidence": 0.6,
        }
    broken_invariant = next(
        (f for f in failures
         if f["assertion"] == "price_components_sum" and "!=" in f.get("detail", "")),
        None,
    )
    if broken_invariant:
        return {
            "classification": "semantic",
            "rationale": "an offer total no longer equals base plus taxes plus fees",
            "proposed_heal": None,
            "confidence": 0.9,
        }

    if removed:
        return {
            "classification": "breaking",
            "rationale": f"{len(removed)} field paths disappeared with no replacement",
            "proposed_heal": None,
            "confidence": 0.5,
        }
    return {
        "classification": "none",
        "rationale": "additive change only",
        "proposed_heal": None,
        "confidence": 0.5,
    }


def _parse(text: str) -> Dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    parsed = json.loads(text[start : end + 1])
    if parsed.get("classification") not in CLASSIFICATIONS:
        raise ValueError(f"bad classification {parsed.get('classification')!r}")
    heal = parsed.get("proposed_heal")
    if heal and not (isinstance(heal, dict) and heal.get("old_path") and heal.get("new_path")):
        parsed["proposed_heal"] = None
    if parsed["classification"] != "cosmetic":
        parsed["proposed_heal"] = None
    return parsed


def judge(probe: str, delta: Dict[str, List], failures: List[Dict], old_sample, new_sample) -> Dict[str, Any]:
    if not config.ANTHROPIC_API_KEY:
        verdict = _heuristic(delta, failures)
        verdict["model"] = "heuristic-fallback"
        return verdict

    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = _prompt(probe, delta, failures, old_sample, new_sample)
    last_error = None
    for attempt in range(3):
        try:
            message = client.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=500,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            verdict = _parse("".join(block.text for block in message.content if block.type == "text"))
            verdict["model"] = config.ANTHROPIC_MODEL
            return verdict
        except Exception as exc:
            last_error = exc
            prompt = prompt + f"\n\nYour previous reply was rejected: {exc}. Reply with one JSON object only."

    logs.fail(f"judge failed after 3 attempts: {last_error}", probe=probe)
    verdict = _heuristic(delta, failures)
    verdict["model"] = "heuristic-fallback"
    verdict["rationale"] += " (LLM unavailable)"
    return verdict
