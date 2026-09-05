from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

from src import config

_file_handle = None


def _out():
    global _file_handle
    if _file_handle is None and config.LOG_FILE:
        os.makedirs(os.path.dirname(config.LOG_FILE) or ".", exist_ok=True)
        _file_handle = open(config.LOG_FILE, "a", buffering=1)
    return _file_handle


def emit(kind: str, probe: str = "-", **fields) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "kind": kind,
        "probe": probe,
    }
    record.update(fields)
    line = json.dumps(record, separators=(",", ":"), default=str)
    print(line, flush=True)
    handle = _out()
    if handle is not None:
        handle.write(line + "\n")


def excerpt(payload, limit: int = 600) -> str:
    text = json.dumps(payload, separators=(",", ":"), default=str)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def fail(message: str, **fields) -> None:
    emit("error", message=message, **fields)
    print(f"driftsentinel: {message}", file=sys.stderr, flush=True)
