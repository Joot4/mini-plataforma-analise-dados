"""Performance SLA tests (Phase 6).

Marked `slow` — excluded by default. Run explicitly:
    uv run pytest -m slow

PERF-01: 80k-line PT-BR CSV → upload → clean → stats in ≤30s.
PERF-02: NL query on loaded session → full response in ≤10s.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time

import pytest
from httpx import AsyncClient

from app.schemas.nlq import ClassifyResponse, NarrationOut, SQLResponse
from tests.fixtures.ptbr_data import realistic_ptbr_csv

API = "/api/v1"
_PW = os.environ.get("PYTEST_USER_PW") or secrets.token_urlsafe(16)


async def _login(client: AsyncClient, email: str) -> str:
    await client.post(f"{API}/auth/register", json={"email": email, "password": _PW})
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": _PW})
    return r.json()["access_token"]


async def _wait_done(client: AsyncClient, task_id: str, token: str, deadline: float) -> dict:
    while time.monotonic() < deadline:
        r = await client.get(
            f"{API}/upload/{task_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        if body["status"] == "done":
            return body
        if body["status"] == "error":
            raise AssertionError(f"task errored: {body}")
        await asyncio.sleep(0.1)
    raise AssertionError("task exceeded deadline")


# --- PERF-01: 80k-line ingestion + cleaning + stats ≤30s ---


@pytest.mark.slow
@pytest.mark.asyncio
async def test_80k_ptbr_csv_under_30s(client: AsyncClient) -> None:
    """End-to-end: POST /upload → poll until done must finish within 30s for
    80,000 rows of PT-BR CSV (CP1252, `;`, BR numbers, DD/MM/YYYY dates).

    Runs WITHOUT an OpenAI key so narration is skipped — measuring only
    the deterministic ingestion+stats path.
    """
    token = await _login(client, "perf80k@example.com")
    csv_bytes = realistic_ptbr_csv(rows=80_000)
    assert len(csv_bytes) > 1_000_000, "fixture too small — suspicious"

    start = time.monotonic()
    r = await client.post(
        f"{API}/upload",
        files={"file": ("vendas_80k.csv", csv_bytes, "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    body = await _wait_done(client, task_id, token, deadline=start + 30)
    elapsed = time.monotonic() - start

    assert elapsed <= 30.0, f"PERF-01 SLA breach: {elapsed:.1f}s for 80k rows"
    # Sanity: the PT-BR conversions actually ran.
    result = body["result"]
    assert result["load"]["delimiter"] == ";"
    assert result["load"]["encoding"] in {"cp1252", "latin-1"}
    # Stats were computed
    assert result["summary"]["rows"] > 0
    assert result["summary"]["cols"] >= 5


# --- PERF-02: NL query pipeline under 10s ---


@pytest.mark.slow
@pytest.mark.asyncio
async def test_nlq_pipeline_under_10s(client: AsyncClient, monkeypatch) -> None:
    """With mocked LLM calls (zero latency), the full NLQ pipeline overhead —
    including DuckDB execution and chart generation — must stay under 10s.

    Real-world latency is dominated by OpenAI round-trips; this test asserts
    the app's own overhead doesn't add measurable time on top.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + secrets.token_hex(16))

    async def fast_classify(question, schema, session_id=None, history=None):
        return ClassifyResponse(on_topic=True, reason="ok")

    async def fast_generate(question, schema, *, retry_reason=None, previous_sql=None, session_id=None, history=None):
        return SQLResponse(
            sql="SELECT regiao, SUM(quantidade) AS total FROM dados GROUP BY regiao",
            reasoning="soma por regiao",
        )

    async def fast_narrate(question, sql, table, session_id=None, history=None):
        return "Resposta rápida."

    monkeypatch.setattr("app.nlq.service.classify_question", fast_classify)
    monkeypatch.setattr("app.nlq.service.generate_sql", fast_generate)
    monkeypatch.setattr("app.nlq.service.narrate_result", fast_narrate)

    token = await _login(client, "perf-nlq@example.com")
    # Medium dataset — 5k rows is enough to exercise DuckDB without blowing the test budget.
    r = await client.post(
        f"{API}/upload",
        files={"file": ("v.csv", realistic_ptbr_csv(rows=5_000), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = r.json()["task_id"]
    body = await _wait_done(client, task_id, token, deadline=time.monotonic() + 60)
    session_id = body["result"]["session_id"]

    start = time.monotonic()
    r = await client.post(
        f"{API}/sessions/{session_id}/query",
        json={"question": "qual o total de quantidade por região?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    elapsed = time.monotonic() - start

    assert r.status_code == 200
    assert elapsed <= 10.0, f"PERF-02 SLA breach: {elapsed:.2f}s for NLQ"
