"""Per-process session store.

Each session holds its own hardened DuckDB connection and the DataFrame it was
built from. Connections are NEVER shared between sessions or users (CLAUDE.md:
sharing a DuckDB connection across sessions causes non-deterministic
RuntimeErrors under concurrency).

Access policy:
- `get(session_id, user_id)` returns the session only if the user owns it
  and it hasn't expired. Wrong owner OR expired → returns None.
- Expired sessions are removed lazily on access and also by the background
  sweeper (see `sweeper.py`).
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import duckdb
import pandas as pd

from app.core.logging import get_logger
from app.duckdb_.connection import create_hardened_connection
from app.ingestion.service import SchemaManifest

logger = get_logger("app.sessions")

# Default table name registered from the DataFrame. All LLM-generated SQL will
# reference this identifier; sessions-service is the only place that resolves it.
SESSION_TABLE_NAME = "dados"


@dataclass
class SessionRecord:
    session_id: str
    user_id: str
    connection: duckdb.DuckDBPyConnection
    schema: SchemaManifest
    table_name: str = SESSION_TABLE_NAME
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    last_accessed_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    def touch(self) -> None:
        self.last_accessed_at = datetime.now(tz=timezone.utc)

    def close(self) -> None:
        try:
            self.connection.close()
        except Exception:
            logger.warning("session.close_failed", session_id=self.session_id)

    def is_expired(self, ttl_seconds: int, now: datetime | None = None) -> bool:
        now = now or datetime.now(tz=timezone.utc)
        return (now - self.last_accessed_at) > timedelta(seconds=ttl_seconds)


class SessionStore:
    """Thread-safe dict-backed session registry with TTL expiry."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl_seconds = ttl_seconds
        self._store: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def create(
        self,
        user_id: str,
        df: pd.DataFrame,
        schema: SchemaManifest,
        *,
        table_name: str = SESSION_TABLE_NAME,
    ) -> SessionRecord:
        session_id = str(uuid.uuid4())
        conn = create_hardened_connection()
        # Register the DataFrame as a queryable table inside the hardened conn.
        # `register` binds a Python object; it's not affected by lockdown since
        # it's a Python-side API, not a DuckDB SET/PRAGMA.
        conn.register(table_name, df)
        record = SessionRecord(
            session_id=session_id,
            user_id=user_id,
            connection=conn,
            schema=schema,
            table_name=table_name,
        )
        with self._lock:
            self._store[session_id] = record
        logger.info(
            "session.created",
            session_id=session_id,
            user_id=user_id,
            rows=schema.row_count,
            cols=schema.column_count,
        )
        return record

    def get(self, session_id: str, user_id: str) -> SessionRecord | None:
        """Return an owned, non-expired session. Enforces cross-user isolation."""
        with self._lock:
            record = self._store.get(session_id)
            if record is None or record.user_id != user_id:
                return None
            if record.is_expired(self._ttl_seconds):
                self._store.pop(session_id, None)
                # Close outside lock is fine for duckdb but we keep it simple.
                record.close()
                return None
            record.touch()
            return record

    def remove(self, session_id: str) -> None:
        with self._lock:
            record = self._store.pop(session_id, None)
        if record:
            record.close()

    def sweep(self, *, now: datetime | None = None) -> int:
        """Remove and close all expired sessions. Returns how many were removed."""
        now = now or datetime.now(tz=timezone.utc)
        expired: list[SessionRecord] = []
        with self._lock:
            for sid in list(self._store.keys()):
                rec = self._store[sid]
                if rec.is_expired(self._ttl_seconds, now=now):
                    expired.append(self._store.pop(sid))
        for rec in expired:
            rec.close()
        if expired:
            logger.info("session.sweeper_cleaned", count=len(expired))
        return len(expired)

    def size(self) -> int:
        with self._lock:
            return len(self._store)

    def clear(self) -> None:
        """Close every session. Used by tests and app shutdown."""
        with self._lock:
            records = list(self._store.values())
            self._store.clear()
        for rec in records:
            rec.close()


_store_singleton: SessionStore | None = None
_singleton_lock = threading.Lock()


def get_session_store() -> SessionStore:
    global _store_singleton
    if _store_singleton is None:
        with _singleton_lock:
            if _store_singleton is None:
                from app.core.config import get_settings

                _store_singleton = SessionStore(
                    ttl_seconds=get_settings().SESSION_TTL_SECONDS
                )
    return _store_singleton


def reset_session_store() -> None:
    """Test-only: close + drop the singleton."""
    global _store_singleton
    with _singleton_lock:
        if _store_singleton is not None:
            _store_singleton.clear()
        _store_singleton = None


__all__ = [
    "SESSION_TABLE_NAME",
    "SessionRecord",
    "SessionStore",
    "get_session_store",
    "reset_session_store",
]
