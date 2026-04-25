"""Per-column statistics computed via the session's hardened DuckDB connection.

Numeric columns produce `{min, max, mean, median, null_pct, unique}`.
Date/datetime columns produce `{min, max, null_pct, unique}`.
Categorical/string columns produce `{top5, null_pct, unique}`.

All stats come from SQL (not pandas) so Phase 5 can reuse the same engine.
Identifiers are double-quoted to survive alias edge cases; values are parameter-
bound where possible, otherwise the column name is quoted in-place (column names
are already ASCII snake_case aliases post-normalization — safe for quoting).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb

from app.ingestion.service import SchemaManifest


@dataclass
class ColumnStats:
    alias: str
    label: str  # original column name
    dtype: str
    kind: str  # "numeric" | "datetime" | "categorical"
    null_pct: float
    unique: int
    # Numeric / datetime:
    min: float | str | None = None
    max: float | str | None = None
    mean: float | None = None
    median: float | None = None
    # Categorical:
    top5: list[dict[str, Any]] = field(default_factory=list)  # [{value, freq}]

    def to_dict(self) -> dict[str, Any]:
        base: dict[str, Any] = {
            "alias": self.alias,
            "label": self.label,
            "dtype": self.dtype,
            "kind": self.kind,
            "null_pct": self.null_pct,
            "unique": self.unique,
        }
        if self.kind == "numeric":
            base.update(
                {"min": self.min, "max": self.max, "mean": self.mean, "median": self.median}
            )
        elif self.kind == "datetime":
            base.update({"min": self.min, "max": self.max})
        else:
            base["top5"] = self.top5
        return base


@dataclass
class SummaryStats:
    rows: int
    cols: int
    columns: list[ColumnStats]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "columns": [c.to_dict() for c in self.columns],
        }


def _classify(dtype: str) -> str:
    low = dtype.lower()
    if "datetime" in low or "date" in low or "timestamp" in low:
        return "datetime"
    if any(t in low for t in ("int", "float", "double", "decimal", "numeric")):
        return "numeric"
    return "categorical"


def compute_stats(
    conn: duckdb.DuckDBPyConnection, table: str, schema: SchemaManifest
) -> SummaryStats:
    """Run a SQL statistics pass over every column of the session table."""
    rows = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    col_stats: list[ColumnStats] = []

    for col in schema.columns:
        alias = col.alias
        quoted = f'"{alias}"'
        kind = _classify(col.dtype)

        nulls_row = conn.execute(
            f'SELECT COUNT(*) - COUNT({quoted}), COUNT(DISTINCT {quoted}) FROM "{table}"'
        ).fetchone()
        null_count = int(nulls_row[0])
        unique_count = int(nulls_row[1])
        null_pct = round((null_count / rows) * 100, 2) if rows else 0.0

        cs = ColumnStats(
            alias=alias,
            label=col.original_name,
            dtype=col.dtype,
            kind=kind,
            null_pct=null_pct,
            unique=unique_count,
        )

        if kind == "numeric" and rows > 0:
            stats_row = conn.execute(
                f"SELECT MIN({quoted}), MAX({quoted}), AVG({quoted}), "
                f'MEDIAN({quoted}) FROM "{table}"'
            ).fetchone()
            cs.min = None if stats_row[0] is None else float(stats_row[0])
            cs.max = None if stats_row[1] is None else float(stats_row[1])
            cs.mean = None if stats_row[2] is None else round(float(stats_row[2]), 4)
            cs.median = None if stats_row[3] is None else float(stats_row[3])
        elif kind == "datetime" and rows > 0:
            dt_row = conn.execute(f'SELECT MIN({quoted}), MAX({quoted}) FROM "{table}"').fetchone()
            cs.min = None if dt_row[0] is None else str(dt_row[0])
            cs.max = None if dt_row[1] is None else str(dt_row[1])
        else:
            top_rows = conn.execute(
                f"SELECT {quoted} AS v, COUNT(*) AS freq "
                f'FROM "{table}" WHERE {quoted} IS NOT NULL '
                "GROUP BY v ORDER BY freq DESC LIMIT 5"
            ).fetchall()
            cs.top5 = [{"value": "" if v is None else str(v), "freq": int(f)} for v, f in top_rows]

        col_stats.append(cs)

    return SummaryStats(rows=rows, cols=len(col_stats), columns=col_stats)
