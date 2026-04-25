"""Verify OPS-03: every LLM call produces a structured log entry with all
required fields (provider, model, tokens_in, tokens_out, cost_estimated,
latency_ms, session_id).
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
import structlog

from app.llm.client import parse_structured, reset_openai_client
from app.schemas.summary import NarrationResponse


class _FakeCompletions:
    """Stands in for `client.chat.completions` — async `parse()` returning canned data."""

    def __init__(self, *, parsed_obj, tokens_in: int, tokens_out: int) -> None:
        self._parsed = parsed_obj
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self.last_kwargs: dict = {}

    async def parse(self, **kwargs):
        self.last_kwargs = kwargs
        choice = SimpleNamespace(message=SimpleNamespace(parsed=self._parsed))
        usage = SimpleNamespace(prompt_tokens=self._tokens_in, completion_tokens=self._tokens_out)
        return SimpleNamespace(choices=[choice], usage=usage)


class _FakeClient:
    def __init__(self, completions) -> None:
        self.chat = SimpleNamespace(completions=completions)


@pytest.fixture
def fake_client(monkeypatch):
    reset_openai_client()
    completions = _FakeCompletions(
        parsed_obj=NarrationResponse(narration="texto de teste em pt-br"),
        tokens_in=125,
        tokens_out=47,
    )
    client = _FakeClient(completions)
    monkeypatch.setattr("app.llm.client.get_openai_client", lambda: client)
    yield client
    reset_openai_client()


@pytest.mark.asyncio
async def test_parse_structured_returns_parsed_model(fake_client) -> None:
    out = await parse_structured(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "oi"}],
        response_model=NarrationResponse,
        session_id="sess-1",
    )
    assert isinstance(out, NarrationResponse)
    assert out.narration == "texto de teste em pt-br"


@pytest.mark.asyncio
async def test_llm_call_emits_ops03_log(fake_client, caplog) -> None:
    # Use stdlib caplog but route structlog through it.
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    with caplog.at_level(logging.INFO, logger="app.llm"):
        await parse_structured(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "oi"}],
            response_model=NarrationResponse,
            session_id="sess-abc",
        )

    matching = [
        json.loads(r.message)
        for r in caplog.records
        if r.name == "app.llm" and "llm.call" in r.message
    ]
    assert matching, f"expected llm.call log; got records={[r.message for r in caplog.records]}"
    entry = matching[0]
    # OPS-03 contract: every one of these keys MUST be present.
    for key in (
        "provider",
        "model",
        "tokens_in",
        "tokens_out",
        "cost_estimated",
        "latency_ms",
        "session_id",
    ):
        assert key in entry, f"missing OPS-03 key: {key}"
    assert entry["provider"] == "openai"
    assert entry["model"] == "gpt-4o-mini"
    assert entry["tokens_in"] == 125
    assert entry["tokens_out"] == 47
    assert entry["cost_estimated"] > 0
    assert entry["session_id"] == "sess-abc"


@pytest.mark.asyncio
async def test_parse_structured_passes_response_format(fake_client) -> None:
    await parse_structured(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "oi"}],
        response_model=NarrationResponse,
    )
    kwargs = fake_client.chat.completions.last_kwargs
    assert kwargs["response_format"] is NarrationResponse
    assert kwargs["model"] == "gpt-4o-mini"
