from __future__ import annotations

import asyncio
import os
import secrets

import pytest
from httpx import AsyncClient

from app.schemas.nlq import ClassifyResponse, SQLResponse
from tests.fixtures.ptbr_data import ptbr_csv_cp1252_semicolon

API = "/api/v1"
_PW = os.environ.get("PYTEST_USER_PW") or secrets.token_urlsafe(16)
_FAKE_KEY = "sk-" + secrets.token_hex(16)


async def _login(client: AsyncClient, email: str) -> str:
    await client.post(f"{API}/auth/register", json={"email": email, "password": _PW})
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": _PW})
    return r.json()["access_token"]


async def _upload_and_session(client: AsyncClient, token: str) -> str:
    r = await client.post(
        f"{API}/upload",
        files={"file": ("vendas.csv", ptbr_csv_cp1252_semicolon(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = r.json()["task_id"]
    for _ in range(200):
        s = await client.get(
            f"{API}/upload/{task_id}/status", headers={"Authorization": f"Bearer {token}"}
        )
        if s.json()["status"] == "done":
            return s.json()["result"]["session_id"]
        if s.json()["status"] == "error":
            raise AssertionError(s.json())
        await asyncio.sleep(0.05)
    raise AssertionError("upload did not finish")


@pytest.mark.asyncio
async def test_query_requires_auth(client: AsyncClient) -> None:
    r = await client.post(f"{API}/sessions/x/query", json={"question": "oi"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_query_without_api_key_returns_503(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    token = await _login(client, "nlq-nokey@example.com")
    session_id = await _upload_and_session(client, token)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "qual o total?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503
    assert r.json()["error_type"] == "llm_unavailable"


@pytest.mark.asyncio
async def test_happy_path_returns_table_and_chart(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    async def fake_classify(question, schema, session_id=None, history=None):
        return ClassifyResponse(on_topic=True, reason="sobre vendas")

    async def fake_generate(
        question, schema, *, retry_reason=None, previous_sql=None, session_id=None, history=None
    ):
        return SQLResponse(
            sql="SELECT regiao, SUM(preco_r) AS total FROM dados GROUP BY regiao",
            reasoning="soma por regiao",
        )

    async def fake_narrate(question, sql, table, session_id=None, history=None):
        return "O Sudeste concentra o maior volume de vendas."

    monkeypatch.setattr("app.nlq.service.classify_question", fake_classify)
    monkeypatch.setattr("app.nlq.service.generate_sql", fake_generate)
    monkeypatch.setattr("app.nlq.service.narrate_result", fake_narrate)

    token = await _login(client, "nlq-ok@example.com")
    session_id = await _upload_and_session(client, token)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "Qual o total por regiao?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "O Sudeste concentra o maior volume de vendas."
    assert body["generated_sql"].upper().startswith("SELECT")
    assert body["table"]["columns"] == ["regiao", "total"]
    assert len(body["table"]["rows"]) >= 1
    assert body["chart_spec"] is not None
    assert body["chart_spec"]["mark"] == "bar"


@pytest.mark.asyncio
async def test_off_topic_question_returns_400(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    async def fake_classify(question, schema, session_id=None, history=None):
        return ClassifyResponse(on_topic=False, reason="pergunta geral")

    monkeypatch.setattr("app.nlq.service.classify_question", fake_classify)

    token = await _login(client, "nlq-offtopic@example.com")
    session_id = await _upload_and_session(client, token)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "qual a capital do brasil?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert r.json()["error_type"] == "out_of_scope"


@pytest.mark.asyncio
async def test_cross_user_session_returns_404(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    token_a = await _login(client, "nlq-a@example.com")
    token_b = await _login(client, "nlq-b@example.com")
    session_id = await _upload_and_session(client, token_a)

    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "qualquer coisa"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
    assert r.json()["error_type"] == "session_not_found"


@pytest.mark.asyncio
async def test_question_too_short_returns_422(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    token = await _login(client, "nlq-empty@example.com")
    session_id = await _upload_and_session(client, token)
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
