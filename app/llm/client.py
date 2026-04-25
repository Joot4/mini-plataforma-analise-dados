"""Thin wrapper around `AsyncOpenAI.chat.completions.parse()`.

Every call here:
- Emits a structured log entry with {provider, model, tokens_in, tokens_out,
  cost_estimated, latency_ms, session_id} — OPS-03 contract.
- Uses Pydantic response_format so the caller always receives a typed model.
- Swallows nothing — any failure bubbles up so the caller can decide on fallback.
"""
from __future__ import annotations

import time
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.costs import estimate_cost_usd

logger = get_logger("app.llm")

ResponseT = TypeVar("ResponseT", bound=BaseModel)

PROVIDER = "openai"

_client_singleton: AsyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    """Return a module-level AsyncOpenAI client bound to Settings.OPENAI_API_KEY."""
    global _client_singleton
    if _client_singleton is None:
        settings = get_settings()
        _client_singleton = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client_singleton


def reset_openai_client() -> None:
    """Test hook: drop the cached client so env changes take effect."""
    global _client_singleton
    _client_singleton = None


async def parse_structured(
    *,
    model: str,
    messages: list[dict[str, str]],
    response_model: type[ResponseT],
    session_id: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> ResponseT:
    """Call OpenAI's structured-output endpoint and return a parsed Pydantic model.

    Logs tokens/cost/latency per OPS-03. Raises any OpenAI SDK exception unchanged.
    """
    client = get_openai_client()
    start = time.monotonic()
    kwargs: dict[str, object] = {
        "model": model,
        "messages": messages,
        "response_format": response_model,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    completion = await client.chat.completions.parse(**kwargs)
    latency_ms = int((time.monotonic() - start) * 1000)

    usage = getattr(completion, "usage", None)
    tokens_in = int(getattr(usage, "prompt_tokens", 0) or 0)
    tokens_out = int(getattr(usage, "completion_tokens", 0) or 0)
    cost = estimate_cost_usd(model, tokens_in, tokens_out)

    logger.info(
        "llm.call",
        provider=PROVIDER,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_estimated=cost,
        latency_ms=latency_ms,
        session_id=session_id,
    )

    parsed = completion.choices[0].message.parsed
    if parsed is None:  # OpenAI may refuse — surface as error
        raise RuntimeError("OpenAI retornou resposta sem parsed content.")
    return parsed


__all__ = ["get_openai_client", "parse_structured", "reset_openai_client"]
