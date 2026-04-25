"""Column-name normalization (PT-BR → ASCII snake_case).

Keeps a reversible mapping {alias → original_name} so the LLM sees ASCII-safe
identifiers while the UI can show the user's original labels.
"""

from __future__ import annotations

import re
import unicodedata

_NON_WORD_RE = re.compile(r"[^\w]+")


def normalize_column_name(name: str) -> str:
    """Convert a raw column label to a SQL-safe ASCII snake_case identifier.

    - Strips accents via NFKD decomposition
    - Lowercases
    - Replaces any non-word run with `_`
    - Strips leading/trailing underscores
    - Falls back to `col_<stable_hash>` for empty names after normalization
    """
    nfkd = unicodedata.normalize("NFKD", str(name))
    ascii_name = nfkd.encode("ascii", "ignore").decode("ascii")
    snake = _NON_WORD_RE.sub("_", ascii_name.strip().lower()).strip("_")
    if snake and not snake[0].isalpha() and snake[0] != "_":
        snake = f"col_{snake}"
    return snake or f"col_{abs(hash(name)) & 0xFFFF}"


def normalize_column_names(names: list[str]) -> tuple[list[str], dict[str, str]]:
    """Normalize a list of column names.

    Returns (new_names, {alias: original_name}). If two originals collide to the same
    alias, appends `_2`, `_3`, etc. to disambiguate.
    """
    aliases: list[str] = []
    mapping: dict[str, str] = {}
    seen_counts: dict[str, int] = {}

    for original in names:
        base = normalize_column_name(original)
        count = seen_counts.get(base, 0)
        alias = base if count == 0 else f"{base}_{count + 1}"
        while alias in mapping:
            count += 1
            alias = f"{base}_{count + 1}"
        seen_counts[base] = count + 1
        aliases.append(alias)
        mapping[alias] = str(original)

    return aliases, mapping
