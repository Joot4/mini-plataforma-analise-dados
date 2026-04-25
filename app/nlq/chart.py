"""Deterministic chart-type picker + Vega-Lite spec emitter.

Heuristic (NLQ-09):
- 1 datetime + 1 numeric → line
- 1 categorical + 1 numeric → bar
- 2 numeric → point (scatter)
- else → None (return only the table)

Emits a Vega-Lite v5/v6-compatible dict via Altair's `to_dict()` so the frontend
can render it directly with any Vega-Lite runtime (vega-embed, etc.).
"""
from __future__ import annotations

import math
from typing import Any

import altair as alt
import pandas as pd


def _classify_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    numeric, datetime_cols, categorical = [], [], []
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            datetime_cols.append(col)
        elif pd.api.types.is_numeric_dtype(series):
            numeric.append(col)
        else:
            # Try coerce to datetime — DuckDB sometimes returns dates as strings.
            try:
                coerced = pd.to_datetime(series, errors="raise")
                if coerced.notna().all():
                    datetime_cols.append(col)
                    continue
            except (ValueError, TypeError):
                pass
            categorical.append(col)
    return {"numeric": numeric, "datetime": datetime_cols, "categorical": categorical}


def _sanitize_for_json(df: pd.DataFrame) -> pd.DataFrame:
    """Convert NaN/NaT to None and ensure datetimes become ISO strings.

    Altair `to_dict()` bakes the data into the spec; the resulting JSON must be
    serializable by `json.dumps` without custom encoders. Numpy ints/floats are
    fine natively; NaN and datetime are not.
    """
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            out[col] = s.dt.strftime("%Y-%m-%dT%H:%M:%S").where(s.notna(), None)
        elif pd.api.types.is_float_dtype(s):
            out[col] = s.where(s.notna(), None).astype(object).map(
                lambda v: None if (isinstance(v, float) and math.isnan(v)) else v
            )
    return out


def build_chart_spec(df: pd.DataFrame) -> dict[str, Any] | None:
    """Return a Vega-Lite dict spec, or None if no chart fits."""
    if df is None or df.empty or len(df.columns) < 2:
        return None

    kinds = _classify_columns(df)
    sdf = _sanitize_for_json(df)

    if kinds["datetime"] and kinds["numeric"]:
        x, y = kinds["datetime"][0], kinds["numeric"][0]
        chart = alt.Chart(sdf).mark_line().encode(
            x=alt.X(f"{x}:T", title=x), y=alt.Y(f"{y}:Q", title=y)
        )
    elif kinds["categorical"] and kinds["numeric"]:
        x, y = kinds["categorical"][0], kinds["numeric"][0]
        chart = alt.Chart(sdf).mark_bar().encode(
            x=alt.X(f"{x}:N", title=x, sort="-y"), y=alt.Y(f"{y}:Q", title=y)
        )
    elif len(kinds["numeric"]) >= 2:
        x, y = kinds["numeric"][0], kinds["numeric"][1]
        chart = alt.Chart(sdf).mark_point().encode(
            x=alt.X(f"{x}:Q", title=x), y=alt.Y(f"{y}:Q", title=y)
        )
    else:
        return None

    # Altair validates the schema when calling to_dict() with validate=True (default).
    spec = chart.to_dict()
    return _normalize_spec(spec)


def _normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Flatten altair output to a conventional Vega-Lite shape.

    - `data.values`: inline rows instead of `data.name` + `datasets[<name>]`
    - `mark`: a plain string ("bar"/"line"/"point") instead of `{"type": "bar"}`
    The result is still a valid Vega-Lite v5/v6 spec — just easier for clients.
    """
    # Inline data.
    data_ref = spec.get("data", {})
    name = data_ref.get("name") if isinstance(data_ref, dict) else None
    datasets = spec.get("datasets", {})
    if name and name in datasets:
        spec["data"] = {"values": datasets[name]}
        datasets.pop(name)
        if not datasets:
            spec.pop("datasets", None)

    # Flatten mark.
    mark = spec.get("mark")
    if isinstance(mark, dict) and "type" in mark:
        spec["mark"] = mark["type"]

    return spec
