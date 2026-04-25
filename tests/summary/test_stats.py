from __future__ import annotations

import pandas as pd
import pytest

from app.duckdb_.connection import create_hardened_connection
from app.ingestion.service import ColumnSchema, SchemaManifest
from app.summary.stats import compute_stats


def _manifest(df: pd.DataFrame, types: dict[str, str] | None = None) -> SchemaManifest:
    types = types or {c: str(df[c].dtype) for c in df.columns}
    cols = [
        ColumnSchema(alias=c, original_name=c, dtype=types[c], sample_values=[]) for c in df.columns
    ]
    return SchemaManifest(
        columns=cols,
        row_count=len(df),
        column_count=len(df.columns),
        original_columns={c: c for c in df.columns},
    )


@pytest.fixture
def conn():
    con = create_hardened_connection()
    yield con
    con.close()


def test_numeric_column_stats(conn) -> None:
    df = pd.DataFrame({"preco": [10.0, 20.0, 30.0, 40.0, 50.0]})
    conn.register("dados", df)
    stats = compute_stats(conn, "dados", _manifest(df))
    assert stats.rows == 5
    assert stats.cols == 1
    c = stats.columns[0]
    assert c.kind == "numeric"
    assert c.min == 10.0 and c.max == 50.0
    assert c.mean == 30.0 and c.median == 30.0
    assert c.null_pct == 0.0
    assert c.unique == 5


def test_categorical_top5(conn) -> None:
    df = pd.DataFrame({"regiao": ["Sul"] * 4 + ["Norte"] * 3 + ["Nordeste"] * 2 + ["Sudeste"]})
    conn.register("dados", df)
    stats = compute_stats(conn, "dados", _manifest(df, {"regiao": "string"}))
    c = stats.columns[0]
    assert c.kind == "categorical"
    assert c.top5[0] == {"value": "Sul", "freq": 4}
    assert len(c.top5) == 4  # only 4 distinct values exist


def test_null_pct_reported(conn) -> None:
    df = pd.DataFrame({"x": [1.0, None, 3.0, None, 5.0]})
    conn.register("dados", df)
    stats = compute_stats(conn, "dados", _manifest(df))
    assert stats.columns[0].null_pct == 40.0


def test_datetime_min_max(conn) -> None:
    df = pd.DataFrame({"dt": pd.to_datetime(["2024-01-15", "2024-07-10", "2023-12-01"])})
    conn.register("dados", df)
    stats = compute_stats(conn, "dados", _manifest(df, {"dt": "datetime64[ns]"}))
    c = stats.columns[0]
    assert c.kind == "datetime"
    assert "2023-12-01" in str(c.min)
    assert "2024-07-10" in str(c.max)
