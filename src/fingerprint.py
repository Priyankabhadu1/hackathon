from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

# Structure only. Values never enter the fingerprint: flight search is non-deterministic
# by nature, and a fingerprint that moves when a price moves is noise, not signal.
# Value-level correctness is the assertion engine's job.

_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DURATION = re.compile(r"^P(?=[T\d])")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")
_CODE = re.compile(r"^[A-Z0-9]{1,6}$")


def _string_kind(value: str) -> str:
    if _ISO_DATETIME.match(value):
        return "iso_datetime"
    if _ISO_DATE.match(value):
        return "iso_date"
    if _DURATION.match(value):
        return "duration"
    if _NUMERIC.match(value):
        return "numeric_string"
    if _CURRENCY.match(value):
        return "currency_code"
    if _CODE.match(value):
        return "code"
    return "string"


def kind_of(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return _string_kind(value)
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _walk(node: Any, path: str, acc: Dict[str, set]) -> None:
    kind = kind_of(node)
    if path:
        acc.setdefault(path, set()).add(kind)
    if isinstance(node, dict):
        for key in node:
            _walk(node[key], f"{path}.{key}" if path else key, acc)
    elif isinstance(node, list):
        # Array indices are collapsed so that a 3-offer response and a 40-offer
        # response fingerprint identically.
        for item in node:
            _walk(item, f"{path}[]", acc)


def fingerprint(response: Any) -> Dict[str, Any]:
    acc: Dict[str, set] = {}
    _walk(response, "", acc)
    paths = {path: sorted(kinds) for path, kinds in sorted(acc.items())}
    canonical = "\n".join(f"{path}:{','.join(kinds)}" for path, kinds in paths.items())
    return {
        "paths": paths,
        "hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
    }


def diff(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, List]:
    old_paths = old.get("paths", {})
    new_paths = new.get("paths", {})
    added = sorted(set(new_paths) - set(old_paths))
    removed = sorted(set(old_paths) - set(new_paths))
    retyped = [
        {"path": path, "was": old_paths[path], "now": new_paths[path]}
        for path in sorted(set(old_paths) & set(new_paths))
        if old_paths[path] != new_paths[path]
    ]
    return {"added": added, "removed": removed, "retyped": retyped}


def is_empty(delta: Dict[str, List]) -> bool:
    return not (delta["added"] or delta["removed"] or delta["retyped"])
