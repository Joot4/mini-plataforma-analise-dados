from __future__ import annotations

import asyncio
import time

import pytest
from httpx import AsyncClient

from tests.fixtures.ptbr_data import (
    huge_row_count_csv,
    ptbr_csv_cp1252_semicolon,
    ptbr_csv_utf8_comma,
)

API = "/api/v1"


async def _register_and_login(client: AsyncClient, email: str = "upload@example.com") -> str:
    await client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "supersecret123"},
    )
    r = await client.post(
        f"{API}/auth/login",
        json={"email": email, "password": "supersecret123"},
    )
    return r.json()["access_token"]


async def _wait_for_status(
    client: AsyncClient, task_id: str, token: str, target: str, timeout: float = 10.0
) -> dict:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        r = await client.get(
            f"{API}/upload/{task_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        if body.get("status") == target:
            return body
        if body.get("status") == "error":
            return body
        await asyncio.sleep(0.05)
    raise AssertionError(f"Timeout waiting for status={target}; last={body}")


# --- Auth guard ---


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient) -> None:
    r = await client.post(f"{API}/upload", files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_status_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{API}/upload/some-id/status")
    assert r.status_code == 401


# --- SC#1: POST /upload returns 202 with task_id ---


@pytest.mark.asyncio
async def test_upload_returns_202_with_task_id(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    r = await client.post(
        f"{API}/upload",
        files={"file": ("users.csv", ptbr_csv_utf8_comma(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert isinstance(body["task_id"], str) and len(body["task_id"]) >= 10


# --- SC#2: oversize rejected with 413 + PT-BR message ---


@pytest.mark.asyncio
async def test_oversize_file_returns_413(client: AsyncClient, monkeypatch) -> None:
    # Shrink cap for this test rather than generating 50MB of data.
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    try:
        token = await _register_and_login(client)
        big = b"a,b\n" + b"1,2\n" * 5000  # ~20KB
        r = await client.post(
            f"{API}/upload",
            files={"file": ("big.csv", big, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 413, r.text
        assert r.json()["error_type"] == "file_too_large"
        assert "limite" in r.json()["message"].lower()
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_too_many_rows_returns_error(client: AsyncClient, monkeypatch) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("MAX_UPLOAD_ROWS", "100")
    try:
        token = await _register_and_login(client)
        content = huge_row_count_csv(rows=500)
        r = await client.post(
            f"{API}/upload",
            files={"file": ("rows.csv", content, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 202
        task_id = r.json()["task_id"]
        body = await _wait_for_status(client, task_id, token, "error")
        assert body["status"] == "error"
        assert body["error"]["error_type"] == "too_many_rows"
    finally:
        get_settings.cache_clear()


# --- SC#3: PT-BR CSV (CP1252 + ; + 1.234,56) processed correctly ---


@pytest.mark.asyncio
async def test_ptbr_csv_full_roundtrip(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    r = await client.post(
        f"{API}/upload",
        files={"file": ("vendas.csv", ptbr_csv_cp1252_semicolon(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]
    body = await _wait_for_status(client, task_id, token, "done")
    assert body["status"] == "done", body
    result = body["result"]

    # Delimiter + encoding detected correctly
    assert result["load"]["delimiter"] == ";"
    assert result["load"]["encoding"] in {"cp1252", "latin-1"}

    # Accented columns present as ASCII aliases with original mapping preserved
    aliases = [c["alias"] for c in result["schema"]["columns"]]
    assert "regiao" in aliases
    assert any("preco" in a for a in aliases)

    # Cleaning report shows non-zero counts (SC#5)
    report = result["cleaning_report"]
    assert report["duplicatas_removidas"] >= 1
    assert report["linhas_vazias_removidas"] >= 1
    assert report["nulos_preenchidos"] >= 1
    assert len(report["colunas_pt_br_normalizadas"]) >= 1

    # Preço dtype is numeric (PT-BR number conversion worked)
    preco_col = next(c for c in result["schema"]["columns"] if "preco" in c["alias"])
    assert "float" in preco_col["dtype"].lower()


# --- SC#4: DD/MM/YYYY dates with day > 12 parse correctly ---


@pytest.mark.asyncio
async def test_ddmmyyyy_with_day_over_12(client: AsyncClient) -> None:
    # Sanity: 15/07/2024 must end up as July 15 in the parsed series.
    token = await _register_and_login(client)
    csv = b"id,data\n1,15/07/2024\n2,21/11/2023\n3,03/02/2024\n"
    r = await client.post(
        f"{API}/upload",
        files={"file": ("datas.csv", csv, "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = r.json()["task_id"]
    body = await _wait_for_status(client, task_id, token, "done")
    cols = {c["alias"]: c for c in body["result"]["schema"]["columns"]}
    assert "datetime" in cols["data"]["dtype"].lower()
    # Sample includes the July-15 value
    assert any("2024-07-15" in (v or "") for v in cols["data"]["sample_values"])


# --- SC#5: status returns done with cleaning report ---


@pytest.mark.asyncio
async def test_status_shows_done_with_report(client: AsyncClient) -> None:
    token = await _register_and_login(client)
    r = await client.post(
        f"{API}/upload",
        files={"file": ("users.csv", ptbr_csv_utf8_comma(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = r.json()["task_id"]
    body = await _wait_for_status(client, task_id, token, "done")
    assert body["status"] == "done"
    assert "cleaning_report" in body["result"]
    assert "schema" in body["result"]


# --- Cross-user isolation on the task registry ---


@pytest.mark.asyncio
async def test_user_b_cannot_see_user_a_task(client: AsyncClient) -> None:
    token_a = await _register_and_login(client, email="a@example.com")
    token_b = await _register_and_login(client, email="b@example.com")

    r = await client.post(
        f"{API}/upload",
        files={"file": ("u.csv", ptbr_csv_utf8_comma(), "text/csv")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    task_id = r.json()["task_id"]
    resp_b = await client.get(
        f"{API}/upload/{task_id}/status",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 404
    assert resp_b.json()["error_type"] == "task_not_found"
