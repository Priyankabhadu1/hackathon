from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict

import httpx

from src import config

# A client is a callable: (probe_name, tool, params) -> response dict.
# Two implementations, chosen once in src/runner.py. Nothing below the runner knows
# which one it holds.

Client = Callable[[str, str, Dict[str, Any]], Any]


def active_variant() -> str:
    try:
        with open(config.ACTIVE_VARIANT_PATH) as handle:
            return handle.read().strip() or "baseline"
    except FileNotFoundError:
        return "baseline"


def _fixture_path(variant: str, probe: str) -> str:
    if variant == "baseline":
        return os.path.join(config.FIXTURE_DIR, "baseline", f"{probe}.json")
    return os.path.join(config.FIXTURE_DIR, "drifted", variant, f"{probe}.json")


def replay_client() -> Client:
    def call(probe: str, tool: str, params: Dict[str, Any]) -> Any:
        variant = active_variant()
        path = _fixture_path(variant, probe)
        if not os.path.exists(path):
            # A variant only overrides the probes it has an opinion about; the rest
            # keep serving baseline so the dashboard does not go uniformly red.
            path = _fixture_path("baseline", probe)
        with open(path) as handle:
            return json.load(handle)

    return call


_TOOL_ROUTES = {
    "flight-offers-search": ("GET", "/v2/shopping/flight-offers"),
    "hotel-search": ("GET", "/v3/shopping/hotel-offers"),
    "flight-price": ("POST", "/v1/shopping/flight-offers/pricing"),
}


def live_client() -> Client:
    token: Dict[str, Any] = {"value": None}

    def authenticate(http: httpx.Client) -> str:
        if token["value"]:
            return token["value"]
        response = http.post(
            "/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": config.AMADEUS_CLIENT_ID,
                "client_secret": config.AMADEUS_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        token["value"] = response.json()["access_token"]
        return token["value"]

    http = httpx.Client(base_url=config.AMADEUS_BASE_URL, timeout=20.0)

    def call(probe: str, tool: str, params: Dict[str, Any]) -> Any:
        if tool not in _TOOL_ROUTES:
            raise ValueError(f"no route for tool {tool!r}; add it to _TOOL_ROUTES")
        method, path = _TOOL_ROUTES[tool]
        headers = {"Authorization": f"Bearer {authenticate(http)}"}
        if method == "GET":
            response = http.get(path, params=params, headers=headers)
        else:
            response = http.post(path, json=params, headers=headers)
        if response.status_code == 401:
            token["value"] = None
            headers = {"Authorization": f"Bearer {authenticate(http)}"}
            response = http.get(path, params=params, headers=headers)
        # A 4xx is a legitimate response for the invalid-input probe, not a transport
        # failure - hand the body downstream and let the assertions judge it.
        if response.status_code >= 500:
            response.raise_for_status()
        return response.json()

    return call
