"""PT-BR locale detection: encoding, delimiter, number format, date format.

Every function here runs on bytes/Series samples and never reads full files —
the caller is responsible for sampling and slicing. This keeps the functions
cheap to unit-test and lets the reader orchestrate IO.
"""

from __future__ import annotations

import csv
import re
from io import StringIO

import pandas as pd
from charset_normalizer import from_bytes

# Order matters: UTF-8 first (most common for modern exports), then BR fallbacks.
ENCODING_CANDIDATES = ["utf-8", "utf-8-sig", "cp1252", "latin-1"]

# PT-BR number: "1.234,56", "1.234.567,89", "1234,56", "123" — accepts optional decimals.
PTBR_NUMBER_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")
# Strip a leading "R$ " or similar currency prefix.
CURRENCY_PREFIX_RE = re.compile(r"^R\$\s*")
# Date pattern DD/MM/YYYY or DD-MM-YYYY (2- or 4-digit year accepted).
DATE_RE = re.compile(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2}|\d{4})$")
# ISO date / datetime: YYYY-MM-DD, YYYY-MM-DD HH:MM(:SS)?, YYYY-MM-DDTHH:MM(:SS)?(Z|±HH:MM)?
ISO_DATE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+\-]\d{2}:?\d{2})?)?"
    r"$"
)


def detect_encoding(raw: bytes) -> str:
    """Return the encoding best matching raw bytes. Tries UTF-8/CP1252/Latin-1 in order.

    Falls back to `charset_normalizer` if every candidate fails. Detects BOM first
    (UTF-8-sig, UTF-16) since those bytes also decode as a different encoding.
    """
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16"
    for enc in ENCODING_CANDIDATES:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    result = from_bytes(raw).best()
    if result is None:
        return "utf-8"
    enc = (result.encoding or "utf-8").lower()
    if enc in {"windows-1252"}:
        return "cp1252"
    if enc in {"iso-8859-1"}:
        return "latin-1"
    return enc


def detect_delimiter(text_sample: str) -> str:
    """Detect CSV delimiter from a text sample.

    PT-BR safe strategy: try csv.Sniffer first; if it fails or reports `,` but the
    sample has many more `;` than `,`, prefer `;` (Excel BR default).
    """
    if not text_sample.strip():
        return ","
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(text_sample, delimiters=",;\t|")
        sniffed = dialect.delimiter
    except csv.Error:
        sniffed = None

    counts = {d: text_sample.count(d) for d in [",", ";", "\t", "|"]}
    likely = max(counts, key=lambda d: counts[d])

    if sniffed is None:
        return likely if counts[likely] > 0 else ","
    # Sniffer sometimes returns `,` when `;` dominates — override.
    if sniffed == "," and counts.get(";", 0) > counts.get(",", 0) * 2:
        return ";"
    return sniffed


def is_ptbr_number_series(series: pd.Series, threshold: float = 0.6) -> bool:
    """Return True if >= threshold of non-null values match the PT-BR number pattern.

    Only considers values that look numeric (contain a digit).
    """
    non_null = series.dropna().astype(str).str.strip()
    if len(non_null) == 0:
        return False
    cleaned = non_null.str.replace(CURRENCY_PREFIX_RE, "", regex=True).str.strip()
    matches = cleaned.apply(lambda s: bool(PTBR_NUMBER_RE.match(s)))
    # Require a comma-decimal on at least one value — otherwise it's just an int column.
    has_comma_decimal = cleaned.str.contains(",", regex=False).any()
    return bool(has_comma_decimal and matches.mean() >= threshold)


def parse_ptbr_number_series(series: pd.Series) -> pd.Series:
    """Convert a PT-BR-formatted string series to float.

    Removes currency prefix + thousand dots + converts decimal comma to period.
    Returns a float Series; unparseable values become NaN.
    """
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace(CURRENCY_PREFIX_RE, "", regex=True)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def is_date_series(series: pd.Series, threshold: float = 0.8) -> bool:
    """Return True if >= threshold of non-null values match DD/MM/YYYY or ISO date/datetime."""
    non_null = series.dropna().astype(str).str.strip()
    if len(non_null) == 0:
        return False
    matches = non_null.apply(
        lambda s: bool(DATE_RE.match(s) or ISO_DATE_RE.match(s))
    )
    return bool(matches.mean() >= threshold)


def parse_date_series(series: pd.Series) -> tuple[pd.Series, bool]:
    """Parse a date string Series. Returns (parsed_series, dayfirst_used).

    - ISO-formatted strings (YYYY-MM-DD…) are unambiguous; pandas parses them
      natively without needing `dayfirst`.
    - Slash/dash DD/MM date strings use `dayfirst=True` (PT-BR safe).
    """
    non_null = series.dropna().astype(str).str.strip()
    if len(non_null) == 0:
        return pd.to_datetime(series, errors="coerce"), False

    iso_share = non_null.head(50).apply(lambda s: bool(ISO_DATE_RE.match(s))).mean()
    if iso_share > 0.5:
        # ISO format — dayfirst is irrelevant.
        return pd.to_datetime(series, errors="coerce"), False

    first_parts = non_null.str.split(r"[/\-]").str[0]
    numeric_first = pd.to_numeric(first_parts, errors="coerce")
    parsed = pd.to_datetime(series, dayfirst=True, errors="coerce")
    unambiguous = bool((numeric_first > 12).any())
    return parsed, unambiguous


def read_csv_bytes_with_encoding(
    raw: bytes, encoding: str, delimiter: str, nrows: int | None = None
) -> pd.DataFrame:
    """Decode bytes with the given encoding and parse CSV into a DataFrame.

    Keeps everything as strings (dtype=str) — type inference runs later in normalize.
    """
    text = raw.decode(encoding, errors="replace")
    return pd.read_csv(
        StringIO(text),
        sep=delimiter,
        dtype=str,
        keep_default_na=True,
        na_values=["", "NA", "N/A", "null", "NULL", "-"],
        nrows=nrows,
    )
