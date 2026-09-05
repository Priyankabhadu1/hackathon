"""One completion call, whichever model you have a key for.

The judge and the verdict writer do not care who serves the tokens, so provider choice
lives here and nowhere else. Two shapes cover everything we might plausibly be given on
the day: Anthropic's messages API, and the OpenAI chat-completions shape that OpenAI,
Groq, Together, OpenRouter and a local Ollama all speak.

    ANTHROPIC_API_KEY=sk-ant-...                         # Anthropic
    OPENAI_API_KEY=sk-...                                # OpenAI
    OPENAI_API_KEY=gsk_...  OPENAI_BASE_URL=https://api.groq.com/openai/v1
    OPENAI_BASE_URL=http://localhost:11434/v1  OPENAI_MODEL=llama3.1   # Ollama, no key

With none of them set, callers fall back to their deterministic classifier - see D9.
"""
from __future__ import annotations

import httpx

from src import config


class Permanent(RuntimeError):
    """A bad key, an exhausted balance, a model that does not exist. Retrying a
    permanent error just makes the demo stall three times instead of once."""


_PERMANENT = ("insufficient_quota", "credit_balance_exhausted", "invalid_api_key",
              "account_deactivated", "model_not_found", "invalid_request_error")


def _raise_for(status: int, body: str, where: str) -> None:
    detail = body[:300].replace("\n", " ")
    error = Permanent if (status in (401, 403, 404) or any(m in body for m in _PERMANENT)) else RuntimeError
    raise error(f"{status} from {where}: {detail}")


def provider() -> str:
    """Explicit choice wins; otherwise whichever credential is present."""
    chosen = config.LLM_PROVIDER
    if chosen in ("anthropic", "openai"):
        return chosen
    if config.ANTHROPIC_API_KEY:
        return "anthropic"
    # A local server needs no key, so a base url on its own is enough to opt in.
    if config.OPENAI_API_KEY or config.OPENAI_BASE_URL != config.OPENAI_BASE_URL_DEFAULT:
        return "openai"
    return "none"


def available() -> bool:
    return provider() != "none"


def model_name() -> str:
    return config.ANTHROPIC_MODEL if provider() == "anthropic" else config.OPENAI_MODEL


def _anthropic(system: str, prompt: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text")


def _openai(system: str, prompt: str, max_tokens: int) -> str:
    headers = {"Content-Type": "application/json"}
    if config.OPENAI_API_KEY:
        headers["Authorization"] = f"Bearer {config.OPENAI_API_KEY}"
    response = httpx.post(
        f"{config.OPENAI_BASE_URL.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": config.OPENAI_MODEL,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": prompt}],
        },
        timeout=60.0,
    )
    if response.status_code >= 400:
        # The body carries the actual reason - an exhausted balance and a genuine rate
        # limit are both 429 and need completely different responses from a human.
        _raise_for(response.status_code, response.text, config.OPENAI_BASE_URL)
    return response.json()["choices"][0]["message"]["content"] or ""


def complete(system: str, prompt: str, max_tokens: int = 600) -> str:
    which = provider()
    if which == "anthropic":
        return _anthropic(system, prompt, max_tokens)
    if which == "openai":
        return _openai(system, prompt, max_tokens)
    raise RuntimeError("no model configured")
