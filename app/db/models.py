from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """UTC timezone-aware now. CLAUDE.md: never use deprecated datetime.utcnow()."""
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models. Used by alembic autogenerate."""


class User(Base):
    __tablename__ = "users"

    # UUID4 PK — never sequential integers (PITFALLS.md#11 — enumeration attack prevention).
    # Stored as String(36) on SQLite (no native UUID type; aiosqlite cannot bind UUID instances,
    # so the column type AND default both produce str). Future Postgres migration becomes
    # PG_UUID(as_uuid=True) — trivial.
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
