from __future__ import annotations

import json
import os
from typing import Any, Dict

from src import config


def load() -> Dict[str, Any]:
    try:
        with open(config.STATE_PATH) as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(state: Dict[str, Any]) -> None:
    tmp = config.STATE_PATH + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(state, handle, indent=2, default=str)
        handle.write("\n")
    os.replace(tmp, config.STATE_PATH)


def trim(node: Any, keep: int = 1, depth: int = 0) -> Any:
    """Shrink a response to a shape-preserving sample.

    The judge needs to see the structure and one example of each value, not forty
    offers. Keeps state.json small and the prompt cheap.
    """
    if depth > 8:
        return "..."
    if isinstance(node, list):
        return [trim(item, keep, depth + 1) for item in node[:keep]]
    if isinstance(node, dict):
        return {key: trim(value, keep, depth + 1) for key, value in node.items()}
    return node
