from __future__ import annotations

import pytest

from app.duckdb_.validator import (
    SQLValidationError,
    validate_sql,
    validate_sql_or_raise,
)

# --- Allowed SELECTs ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT * FROM dados",
        "SELECT a, b FROM dados WHERE a > 10 ORDER BY b LIMIT 100",
        "SELECT COUNT(*), AVG(preco) FROM dados GROUP BY regiao",
        "WITH x AS (SELECT * FROM dados) SELECT * FROM x",
        "SELECT a FROM dados UNION ALL SELECT b FROM dados",
    ],
)
def test_validator_accepts_safe_select(sql: str) -> None:
    result = validate_sql(sql)
    assert result.ok, f"should accept: {sql} — {result.reason}"


# --- Non-SELECT DML/DDL ---


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE dados",
        "DELETE FROM dados WHERE a = 1",
        "INSERT INTO dados VALUES (1)",
        "UPDATE dados SET a = 1",
        "CREATE TABLE foo (x INT)",
        "ALTER TABLE dados ADD COLUMN x INT",
        "TRUNCATE dados",
    ],
)
def test_validator_rejects_non_select(sql: str) -> None:
    result = validate_sql(sql)
    assert not result.ok
    assert result.layer == "parse"


# --- I/O and lockdown escape attempts ---


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_parquet('s3://bucket/file')",
        "SELECT * FROM read_json_auto('data.json')",
        "COPY dados TO '/tmp/dump.csv'",
        "ATTACH 'other.db'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "PRAGMA enable_profiling",
    ],
)
def test_validator_rejects_io_and_lockdown_escapes(sql: str) -> None:
    result = validate_sql(sql)
    assert not result.ok, f"should reject: {sql}"


# --- Empty / bogus ---


@pytest.mark.parametrize("sql", ["", "   ", "not sql at all", ";"])
def test_validator_rejects_empty_or_garbage(sql: str) -> None:
    result = validate_sql(sql)
    assert not result.ok


def test_or_raise_variant() -> None:
    with pytest.raises(SQLValidationError):
        validate_sql_or_raise("DROP TABLE dados")
    validate_sql_or_raise("SELECT 1")  # no raise
