from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.fixtures.ptbr_data import ptbr_csv_utf8_comma

API = "/api/v1"


async def _login(client: AsyncClient, email: str) -> str:
    await client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "supersecret123"},
    )
    r = await client.post(
        f"{API}/auth/login",
        json={"email": email, "password": "supersecret123"},
    )
    return r.json()["access_token"]


async def _upload_and_wait(client: AsyncClient, token: str) -> dict:
    up = await client.post(
        f"{API}/upload",
        files={"file": ("users.csv", ptbr_csv_utf8_comma(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = up.json()["task_id"]
    for _ in range(100):
        s = await client.get(
            f"{API}/upload/{task_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        if s.json()["status"] == "done":
            return s.json()
        if s.json()["status"] == "error":
            raise AssertionError(s.json())
        await asyncio.sleep(0.05)
    raise AssertionError("upload did not finish in time")


@pytest.mark.asyncio
async def test_upload_creates_session_id(client: AsyncClient) -> None:
    token = await _login(client, "sess1@example.com")
    body = await _upload_and_wait(client, token)
    assert "session_id" in body["result"]
    assert isinstance(body["result"]["session_id"], str)


@pytest.mark.asyncio
async def test_get_session_returns_schema_manifest(client: AsyncClient) -> None:
    token = await _login(client, "sess2@example.com")
    body = await _upload_and_wait(client, token)
    session_id = body["result"]["session_id"]

    r = await client.get(
        f"{API}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["session_id"] == session_id
    assert out["table_name"] == "dados"
    manifest = out["schema_manifest"]
    assert manifest["row_count"] == 2
    assert manifest["column_count"] == 3
    aliases = [c["alias"] for c in manifest["columns"]]
    assert aliases == ["name", "email", "age"]


@pytest.mark.asyncio
async def test_user_b_cannot_access_user_a_session(client: AsyncClient) -> None:
    token_a = await _login(client, "sess-a@example.com")
    token_b = await _login(client, "sess-b@example.com")
    body = await _upload_and_wait(client, token_a)
    session_id = body["result"]["session_id"]

    r = await client.get(
        f"{API}/sessions/{session_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
    assert r.json()["error_type"] == "session_not_found"


@pytest.mark.asyncio
async def test_unknown_session_returns_404(client: AsyncClient) -> None:
    token = await _login(client, "sess-unk@example.com")
    r = await client.get(
        f"{API}/sessions/does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_session_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{API}/sessions/anything")
    assert r.status_code == 401
