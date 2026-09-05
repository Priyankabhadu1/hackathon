from __future__ import annotations

import os


def _load_dotenv(path: str = ".env") -> None:
    """Read .env without a dependency. A real environment variable always wins,
    so `PROBE_MODE=live python -m src.runner` overrides the file."""
    try:
        with open(path) as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


PROBE_MODE = os.environ.get("PROBE_MODE", "replay").strip().lower()
PROBE_INTERVAL = _int("PROBE_INTERVAL", 15)
METRICS_PORT = _int("METRICS_PORT", 8000)
LOG_FILE = os.environ.get("LOG_FILE", "logs/driftsentinel.log")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

AMADEUS_CLIENT_ID = os.environ.get("AMADEUS_CLIENT_ID", "")
AMADEUS_CLIENT_SECRET = os.environ.get("AMADEUS_CLIENT_SECRET", "")
AMADEUS_BASE_URL = os.environ.get("AMADEUS_BASE_URL", "https://test.api.amadeus.com")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100")

PROBE_DIR = "src/probes"
FIXTURE_DIR = "fixtures"
ALIAS_MAP_PATH = "fixtures/alias_map.json"
STATE_PATH = "fixtures/state.json"
ACTIVE_VARIANT_PATH = "fixtures/active_variant"
