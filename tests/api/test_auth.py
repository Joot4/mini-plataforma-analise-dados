from __future__ import annotations

import pytest
from httpx import AsyncClient

API = "/api/v1"


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    r = await client.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- ROADMAP SC#1: register 201 / duplicate 409 ---


@pytest.mark.asyncio
async def test_register_returns_201_and_user_payload(client: AsyncClient) -> None:
    r = await client.post(
        f"{API}/auth/register",
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "alice@example.com"
    assert body["is_active"] is True
    assert "id" in body
    assert "password" not in body
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {"email": "alice@example.com", "password": "supersecret123"}
    r1 = await client.post(f"{API}/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await client.post(f"{API}/auth/register", json=payload)
    assert r2.status_code == 409
    body = r2.json()
    assert body["error_type"] == "email_already_exists"
    assert isinstance(body["message"], str) and body["message"]


@pytest.mark.asyncio
async def test_invalid_email_returns_422(client: AsyncClient) -> None:
    r = await client.post(
        f"{API}/auth/register",
        json={"email": "not-an-email", "password": "supersecret123"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error_type"] == "validation_failed"
    assert body["details"]["fields"]


@pytest.mark.asyncio
async def test_short_password_returns_422(client: AsyncClient) -> None:
    r = await client.post(
        f"{API}/auth/register",
        json={"email": "bob@example.com", "password": "short"},
    )
    assert r.status_code == 422


# --- ROADMAP SC#2: login + protected route 401/200 ---


@pytest.mark.asyncio
async def test_login_returns_token_and_me_works(client: AsyncClient) -> None:
    await client.post(
        f"{API}/auth/register",
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    r = await client.post(
        f"{API}/auth/login",
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert r.json()["token_type"] == "bearer"
    assert isinstance(token, str) and token.count(".") == 2

    me = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await client.post(
        f"{API}/auth/register",
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    r = await client.post(
        f"{API}/auth/login",
        json={"email": "alice@example.com", "password": "wrongpassword"},
    )
    assert r.status_code == 401
    assert r.json()["error_type"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    r = await client.get(f"{API}/auth/me")
    assert r.status_code == 401
    assert r.json()["error_type"] == "invalid_token"


@pytest.mark.asyncio
async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    r = await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


# --- ROADMAP SC#3: cross-user isolation ---


@pytest.mark.asyncio
async def test_cross_user_isolation(client: AsyncClient) -> None:
    """User A's token must resolve to User A; User B's token must resolve to User B.
    Neither token can return the other user's payload."""
    await client.post(
        f"{API}/auth/register",
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    await client.post(
        f"{API}/auth/register",
        json={"email": "bob@example.com", "password": "anotherpass456"},
    )
    login_a = await client.post(
        f"{API}/auth/login",
        json={"email": "alice@example.com", "password": "supersecret123"},
    )
    login_b = await client.post(
        f"{API}/auth/login",
        json={"email": "bob@example.com", "password": "anotherpass456"},
    )
    token_a = login_a.json()["access_token"]
    token_b = login_b.json()["access_token"]
    assert token_a != token_b

    me_a = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    me_b = await client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_a.status_code == 200 and me_b.status_code == 200
    assert me_a.json()["email"] == "alice@example.com"
    assert me_b.json()["email"] == "bob@example.com"
    assert me_a.json()["id"] != me_b.json()["id"]
