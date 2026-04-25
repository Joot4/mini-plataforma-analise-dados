"""SC#3 of Phase 6: no raw Python/OpenAI/DuckDB error strings leak into HTTP
response bodies. Every error path must return a structured envelope with a
Portuguese `message` and a stable `error_type`.
"""
from __future__ import annotations

import asyncio
import os
import secrets

import pytest
from httpx import AsyncClient

from app.schemas.nlq import ClassifyResponse, SQLResponse
from tests.fixtures.ptbr_data import ptbr_csv_utf8_comma

API = "/api/v1"
_PW = os.environ.get("PYTEST_USER_PW") or secrets.token_urlsafe(16)
_FAKE_KEY = "sk-" + secrets.token_hex(16)


async def _login(client: AsyncClient, email: str) -> str:
    await client.post(f"{API}/auth/register", json={"email": email, "password": _PW})
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": _PW})
    return r.json()["access_token"]


async def _session(client: AsyncClient, token: str) -> str:
    r = await client.post(
        f"{API}/upload",
        files={"file": ("u.csv", ptbr_csv_utf8_comma(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = r.json()["task_id"]
    for _ in range(200):
        s = await client.get(
            f"{API}/upload/{task_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        if s.json()["status"] == "done":
            return s.json()["result"]["session_id"]
        if s.json()["status"] == "error":
            raise AssertionError(s.json())
        await asyncio.sleep(0.05)
    raise AssertionError("upload did not finish")


def _assert_envelope(body: dict) -> None:
    assert "error_type" in body, f"missing error_type: {body}"
    assert isinstance(body["error_type"], str)
    assert "message" in body
    assert isinstance(body["message"], str) and body["message"]
    # No leaks:
    forbidden = [
        "Traceback",
        "File \"",
        "AssertionError",
        "TypeError",
        "ValueError",
        "duckdb.Error",
        "openai.",
        "AuthenticationError",
    ]
    full = str(body)
    for needle in forbidden:
        assert needle not in full, f"leaked internal detail `{needle}` in: {full}"


@pytest.mark.asyncio
async def test_auth_401_envelope(client: AsyncClient) -> None:
    r = await client.get(f"{API}/auth/me")
    assert r.status_code == 401
    _assert_envelope(r.json())
    assert r.json()["error_type"] == "invalid_token"


@pytest.mark.asyncio
async def test_register_409_envelope(client: AsyncClient) -> None:
    await client.post(f"{API}/auth/register", json={"email": "dup@example.com", "password": _PW})
    r = await client.post(f"{API}/auth/register", json={"email": "dup@example.com", "password": _PW})
    assert r.status_code == 409
    _assert_envelope(r.json())


@pytest.mark.asyncio
async def test_validation_error_envelope(client: AsyncClient) -> None:
    r = await client.post(f"{API}/auth/register", json={"email": "not-an-email", "password": "short"})
    assert r.status_code == 422
    body = r.json()
    _assert_envelope(body)
    assert body["error_type"] == "validation_failed"
    assert body["details"]["fields"]


@pytest.mark.asyncio
async def test_bad_upload_format_envelope(client: AsyncClient) -> None:
    token = await _login(client, "badfmt@example.com")
    r = await client.post(
        f"{API}/upload",
        files={"file": ("x.xml", b"<xml/>", "application/xml")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 415
    _assert_envelope(r.json())
    assert r.json()["error_type"] == "unsupported_format"


@pytest.mark.asyncio
async def test_execution_failure_returns_envelope(
    client: AsyncClient, monkeypatch
) -> None:
    """LLM returns valid-looking SELECT that references a non-existent column.
    DuckDB will raise — the endpoint must map it to an `execution_failed`
    envelope, NOT leak the raw DuckDB error text.
    """
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    async def fake_classify(question, schema, session_id=None, history=None):
        return ClassifyResponse(on_topic=True, reason="ok")

    async def fake_generate(question, schema, *, retry_reason=None, previous_sql=None, session_id=None, history=None):
        return SQLResponse(sql="SELECT coluna_inexistente FROM dados", reasoning="-")

    monkeypatch.setattr("app.nlq.service.classify_question", fake_classify)
    monkeypatch.setattr("app.nlq.service.generate_sql", fake_generate)

    token = await _login(client, "execfail@example.com")
    session_id = await _session(client, token)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "mostra coluna x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    _assert_envelope(r.json())
    assert r.json()["error_type"] == "execution_failed"


@pytest.mark.asyncio
async def test_invalid_question_envelope(client: AsyncClient, monkeypatch) -> None:
    """Both SQL attempts are rejected by the validator → invalid_question envelope."""
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    async def fake_classify(question, schema, session_id=None, history=None):
        return ClassifyResponse(on_topic=True, reason="ok")

    async def always_invalid(question, schema, *, retry_reason=None, previous_sql=None, session_id=None, history=None):
        return SQLResponse(sql="DROP TABLE dados", reasoning="-")

    monkeypatch.setattr("app.nlq.service.classify_question", fake_classify)
    monkeypatch.setattr("app.nlq.service.generate_sql", always_invalid)

    token = await _login(client, "invq@example.com")
    session_id = await _session(client, token)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "apagar tudo"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    _assert_envelope(r.json())
    assert r.json()["error_type"] == "invalid_question"


@pytest.mark.asyncio
async def test_unhandled_exception_returns_generic_envelope(
    client: AsyncClient, monkeypatch
) -> None:
    """Inject a crash in the classifier and confirm the generic handler wraps
    it into an `internal_error` envelope — no traceback in response body.
    """
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)
    monkeypatch.setenv("DEBUG", "false")

    async def crash(question, schema, session_id=None, history=None):
        raise RuntimeError("PII_SECRET_IN_MESSAGE: Traceback (most recent call last)")

    monkeypatch.setattr("app.nlq.service.classify_question", crash)

    token = await _login(client, "crash@example.com")
    session_id = await _session(client, token)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "seja lá o que for"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 500
    body = r.json()
    _assert_envelope(body)
    assert body["error_type"] == "internal_error"
    # The secret from the exception message must not appear in the response.
    assert "PII_SECRET_IN_MESSAGE" not in str(body)


@pytest.mark.asyncio
async def test_cross_user_session_envelope(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    token_a = await _login(client, "ea@example.com")
    token_b = await _login(client, "eb@example.com")
    session_id = await _session(client, token_a)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "oi"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
    _assert_envelope(r.json())
    assert r.json()["error_type"] == "session_not_found"
