"""Cleaning pipeline: nulls, duplicates, type coercion, string standardization.

All transforms use pandas 3.0 Copy-on-Write friendly patterns (`.loc[]` assignment
only — no chained assignment). String dtype is `StringDtype`, never `object`.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from app.ingestion.detector import (
    is_date_series,
    is_ptbr_number_series,
    parse_date_series,
    parse_ptbr_number_series,
)


def _deaccent_lower(s: object) -> object:
    """Strip accents (NFKD → ASCII) AND lowercase. NaN-safe."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return s
    text = str(s)
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower().strip()


@dataclass
class CleaningReport:
    nulos_preenchidos: int = 0
    duplicatas_removidas: int = 0
    tipos_convertidos: list[str] = field(default_factory=list)
    colunas_pt_br_normalizadas: list[str] = field(default_factory=list)
    textos_padronizados: list[str] = field(default_factory=list)
    categorias_normalizadas: list[dict[str, object]] = field(default_factory=list)
    linhas_vazias_removidas: int = 0
    colunas_vazias_removidas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "nulos_preenchidos": self.nulos_preenchidos,
            "duplicatas_removidas": self.duplicatas_removidas,
            "tipos_convertidos": self.tipos_convertidos,
            "colunas_pt_br_normalizadas": self.colunas_pt_br_normalizadas,
            "textos_padronizados": self.textos_padronizados,
            "categorias_normalizadas": self.categorias_normalizadas,
            "linhas_vazias_removidas": self.linhas_vazias_removidas,
            "colunas_vazias_removidas": self.colunas_vazias_removidas,
        }


@dataclass
class CleaningOptions:
    fill_nulls: bool = True
    drop_duplicates: bool = True
    convert_types: bool = True
    standardize_text: bool = True
    # Detect case/whitespace duplication in categorical columns (e.g.
    # "Moagem_01" vs "moagem_01" vs "MOAGEM_01") and lowercase them so they
    # collapse to a single category. Only kicks in when a column has
    # low cardinality AND lowercasing produces fewer distinct values.
    normalize_categories: bool = True


# Cardinality threshold for treating a column as "categorical-ish" for the
# case-normalization step. Above this we leave the column alone (likely free
# text or high-cardinality identifiers).
_CATEGORICAL_UNIQUE_CAP = 50


def clean_dataframe(
    df: pd.DataFrame, options: CleaningOptions | None = None
) -> tuple[pd.DataFrame, CleaningReport]:
    """Apply the cleaning pipeline and return (cleaned_df, report).

    Pipeline order matters:
    1. Drop 100% empty rows and columns (silent, reported).
    2. Type conversion (PT-BR numbers, dates, booleans) — BEFORE null fill so we
       don't freeze strings like "" as the fill value for numeric cols.
    3. Duplicate removal.
    4. Null fill (only on columns where it's safe).
    5. Text standardization (trim + `StringDtype`).
    """
    opts = options or CleaningOptions()
    report = CleaningReport()

    # Work on a copy so the caller's frame is untouched.
    out = df.copy()

    # 1. Drop 100% empty rows + columns.
    empty_cols = [c for c in out.columns if out[c].isna().all()]
    if empty_cols:
        report.colunas_vazias_removidas = list(empty_cols)
        out = out.drop(columns=empty_cols)
    before_rows = len(out)
    out = out.dropna(how="all")
    report.linhas_vazias_removidas = before_rows - len(out)

    # 2. Type conversion.
    if opts.convert_types:
        for col in out.columns:
            series = out[col]
            is_strish = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)
            if not is_strish:
                continue
            if is_ptbr_number_series(series):
                out[col] = parse_ptbr_number_series(series)
                report.tipos_convertidos.append(col)
                report.colunas_pt_br_normalizadas.append(col)
                continue
            if is_date_series(series):
                parsed, _ = parse_date_series(series)
                out[col] = parsed
                report.tipos_convertidos.append(col)
                continue
            # Try plain numeric (locale-neutral) conversion.
            plain_numeric = pd.to_numeric(series, errors="coerce")
            if plain_numeric.notna().sum() > 0 and plain_numeric.notna().mean() >= 0.9:
                out[col] = plain_numeric
                report.tipos_convertidos.append(col)

    # 3. Drop exact-duplicate rows.
    if opts.drop_duplicates:
        before = len(out)
        out = out.drop_duplicates(ignore_index=True)
        report.duplicatas_removidas = before - len(out)

    # 4. Null fill — per-column strategy:
    #    - string/object → "" (so SQL filters like `coluna != ''` work)
    #    - numeric    → KEEP NaN. Filling with 0 distorts MEDIAN/AVG/etc.
    #                   DuckDB aggregates already skip NaN, and `null_pct` in
    #                   the summary then reflects true missingness.
    #    - datetime   → KEEP NaT (filling dates is almost always wrong)
    if opts.fill_nulls:
        null_count = 0
        for col in out.columns:
            null_count_before = int(out[col].isna().sum())
            if null_count_before == 0:
                continue
            series = out[col]
            if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
                continue
            out[col] = series.fillna("")
            null_count += null_count_before
        report.nulos_preenchidos = null_count

    # 5. Text standardization: strip + `StringDtype`.
    if opts.standardize_text:
        for col in out.columns:
            series = out[col]
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                out[col] = series.astype("string").str.strip()
                report.textos_padronizados.append(col)

    # 6. Case + accent normalization for categorical-ish columns.
    # Resolves duplication caused by:
    #   - Inconsistent capitalization ("Moagem_01" / "moagem_01" / "MOAGEM_01")
    #   - Accent variation ("Pelotização" / "pelotizacao", "manhã" / "manha")
    # Only applies when cardinality is bounded AND lowercasing+deaccenting
    # produces fewer distinct values (evidence of duplication).
    if opts.normalize_categories:
        for col in out.columns:
            series = out[col]
            if not (
                pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series)
            ):
                continue
            unique_raw = int(series.nunique(dropna=True))
            if unique_raw < 2 or unique_raw > _CATEGORICAL_UNIQUE_CAP:
                continue
            normalized = (
                series.astype("string").map(_deaccent_lower, na_action="ignore")
            ).astype("string")
            unique_norm = int(normalized.nunique(dropna=True))
            if unique_norm < unique_raw:
                out[col] = normalized
                report.categorias_normalizadas.append(
                    {
                        "coluna": col,
                        "antes": unique_raw,
                        "depois": unique_norm,
                    }
                )

    return out, report
