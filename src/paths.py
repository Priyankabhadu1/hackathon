from __future__ import annotations

from typing import Any, List

# Path grammar: dotted keys, "[]" to fan out over an array. "price.taxes[].amount"
# returns every tax amount in the offer.


def resolve(node: Any, path: str) -> List[Any]:
    if path in ("", "."):
        return [node]
    current = [node]
    for segment in path.split("."):
        fan_out = segment.endswith("[]")
        key = segment[:-2] if fan_out else segment
        nxt: List[Any] = []
        for item in current:
            if not isinstance(item, dict) or key not in item:
                continue
            value = item[key]
            if fan_out:
                if isinstance(value, list):
                    nxt.extend(value)
            else:
                nxt.append(value)
        current = nxt
        if not current:
            return []
    return current


def first(node: Any, path: str, default: Any = None) -> Any:
    found = resolve(node, path)
    return found[0] if found else default


def exists(node: Any, path: str) -> bool:
    return bool(resolve(node, path))
