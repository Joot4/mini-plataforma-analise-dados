from __future__ import annotations

import pandas as pd

from app.nlq.chart import build_chart_spec


def test_datetime_plus_numeric_gives_line() -> None:
    df = pd.DataFrame({
        "data": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
        "vendas": [100, 150, 200],
    })
    spec = build_chart_spec(df)
    assert spec is not None
    assert spec["mark"] == "line"
    # Altair emits encodings at top level for single-layer charts.
    enc = spec["encoding"]
    assert enc["x"]["field"] == "data"
    assert enc["y"]["field"] == "vendas"


def test_categorical_plus_numeric_gives_bar() -> None:
    df = pd.DataFrame({
        "regiao": ["Sul", "Norte", "Sudeste"],
        "total": [100, 200, 500],
    })
    spec = build_chart_spec(df)
    assert spec is not None
    assert spec["mark"] == "bar"


def test_two_numerics_gives_point() -> None:
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [10.0, 20.0, 30.0]})
    spec = build_chart_spec(df)
    assert spec is not None
    assert spec["mark"] == "point"


def test_single_column_returns_none() -> None:
    df = pd.DataFrame({"only": [1, 2, 3]})
    assert build_chart_spec(df) is None


def test_empty_df_returns_none() -> None:
    assert build_chart_spec(pd.DataFrame()) is None


def test_chart_spec_has_data_values() -> None:
    df = pd.DataFrame({
        "regiao": ["Sul", "Norte"],
        "total": [100.0, 200.0],
    })
    spec = build_chart_spec(df)
    assert spec is not None
    # Data embedded for client-side render.
    assert "data" in spec
    assert "values" in spec["data"]
    assert len(spec["data"]["values"]) == 2


def test_chart_spec_nan_serialized_safely() -> None:
    import math

    df = pd.DataFrame({
        "regiao": ["Sul", "Norte"],
        "total": [100.0, float("nan")],
    })
    spec = build_chart_spec(df)
    assert spec is not None
    for v in spec["data"]["values"]:
        if "total" in v and v["total"] is not None:
            assert not (isinstance(v["total"], float) and math.isnan(v["total"]))
