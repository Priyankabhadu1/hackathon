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
    # Collect first, apply after: within the file the last occurrence of a key wins,
    # which is what every other dotenv reader does. Applying line by line let an empty
    # placeholder earlier in the file silently shadow a real value appended later.
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    for key, value in values.items():
        os.environ.setdefault(key, value)


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

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "auto").strip().lower()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# Any OpenAI-compatible server: OpenAI, Groq, Together, OpenRouter, a local Ollama.
OPENAI_BASE_URL_DEFAULT = "https://api.openai.com/v1"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", OPENAI_BASE_URL_DEFAULT)
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

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
