from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Set deterministic JWT secret BEFORE app modules import settings.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-deterministic-32bytes-hex")
os.environ.setdefault("DEBUG", "false")

from app.api.deps import get_db_session  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.security import _reset_secret  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.sessions.store import reset_session_store  # noqa: E402
from app.tasks.registry import reset_task_registry  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[object]:
    """In-memory SQLite engine, fresh per test for isolation."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncIterator[AsyncClient]:
    """httpx AsyncClient bound to the FastAPI app, with the DB dep overridden
    to share a single in-memory engine across all requests in this test."""
    SessionLocal = async_sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)

    async def _override_get_db_session() -> AsyncIterator:
        async with SessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    get_settings.cache_clear()
    _reset_secret()
    reset_task_registry()
    reset_session_store()
    app = create_app()
    app.dependency_overrides[get_db_session] = _override_get_db_session

    # raise_app_exceptions=False lets our generic Exception handler
    # actually convert unhandled errors into 500 envelopes in tests — by default
    # ASGITransport re-raises for debuggability, which masks the handler.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
