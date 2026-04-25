from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.ingestion.service import SchemaManifest
from app.sessions.store import SESSION_TABLE_NAME, SessionStore


def _manifest(df: pd.DataFrame) -> SchemaManifest:
    return SchemaManifest(
        columns=[],
        row_count=int(len(df)),
        column_count=int(len(df.columns)),
        original_columns={c: c for c in df.columns},
    )


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30]})


def test_create_and_get(df: pd.DataFrame) -> None:
    store = SessionStore(ttl_seconds=3600)
    rec = store.create(user_id="u1", df=df, schema=_manifest(df))
    assert store.get(rec.session_id, "u1") is rec
    rec.close()


def test_get_with_wrong_user_returns_none(df: pd.DataFrame) -> None:
    store = SessionStore(ttl_seconds=3600)
    rec = store.create(user_id="u1", df=df, schema=_manifest(df))
    assert store.get(rec.session_id, "other-user") is None
    rec.close()


def test_query_runs_on_registered_table(df: pd.DataFrame) -> None:
    store = SessionStore(ttl_seconds=3600)
    rec = store.create(user_id="u1", df=df, schema=_manifest(df))
    try:
        rows = rec.connection.execute(f"SELECT SUM(a) FROM {SESSION_TABLE_NAME}").fetchone()
        assert rows == (6,)
    finally:
        rec.close()


def test_ttl_expiry_lazy_on_get(df: pd.DataFrame) -> None:
    store = SessionStore(ttl_seconds=1)
    rec = store.create(user_id="u1", df=df, schema=_manifest(df))
    # Force expiry by backdating last_accessed_at.
    rec.last_accessed_at = datetime.now(tz=timezone.utc) - timedelta(seconds=5)
    assert store.get(rec.session_id, "u1") is None
    assert store.size() == 0


def test_sweep_removes_expired(df: pd.DataFrame) -> None:
    store = SessionStore(ttl_seconds=1)
    r1 = store.create(user_id="u1", df=df, schema=_manifest(df))
    r2 = store.create(user_id="u1", df=df, schema=_manifest(df))
    # Only r1 is expired.
    r1.last_accessed_at = datetime.now(tz=timezone.utc) - timedelta(seconds=10)
    removed = store.sweep()
    assert removed == 1
    assert store.size() == 1
    assert store.get(r2.session_id, "u1") is r2
    r2.close()


def test_two_users_concurrent(df: pd.DataFrame) -> None:
    """SQL-03: each session has its own connection; two users querying in
    parallel must not trigger DuckDB thread-safety RuntimeErrors."""
    store = SessionStore(ttl_seconds=3600)
    ra = store.create(user_id="userA", df=df, schema=_manifest(df))
    rb = store.create(user_id="userB", df=df, schema=_manifest(df))
    errors: list[BaseException] = []

    def hammer(rec, expected_sum):
        for _ in range(50):
            got = rec.connection.execute(
                f"SELECT SUM(a) FROM {SESSION_TABLE_NAME}"
            ).fetchone()
            if got != (expected_sum,):
                errors.append(AssertionError(f"expected {expected_sum}, got {got}"))

    ta = threading.Thread(target=hammer, args=(ra, 6))
    tb = threading.Thread(target=hammer, args=(rb, 6))
    ta.start()
    tb.start()
    ta.join(timeout=10)
    tb.join(timeout=10)
    assert not errors, errors
    ra.close()
    rb.close()
