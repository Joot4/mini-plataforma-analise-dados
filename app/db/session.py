from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.models import Base  # re-exported for alembic env.py convenience

settings = get_settings()

# `future=True` is default in 2.x but we set it for clarity.
# `echo=settings.DEBUG` surfaces SQL in dev; silent in prod.
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    # SQLite-specific: allow same thread checks to relax (aiosqlite handles concurrency).
    connect_args={"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {},
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency.

    Yields an async SQLAlchemy session, commits on success, rolls back on exception,
    always closes in finally. Plan 06 (app/api/deps.py) re-exports this.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


__all__ = ["Base", "engine", "AsyncSessionLocal", "get_db_session"]
