"""Two-layer SQL validator.

Layer 1: parse with `sqlglot.parse_one(sql, read="duckdb")` and require the
         root AST node to be `exp.Select`. Anything else (DROP/DELETE/ATTACH/
         COPY/INSERT/UPDATE/PRAGMA/CREATE/…) is rejected before touching DuckDB.

Layer 2: walk every Anonymous/Function/Table node in the Select tree; if the
         identifier matches the blocklist, reject. Catches `SELECT * FROM
         read_csv('/etc/passwd')` and `SELECT pragma_*()` — both of which are
         syntactically a Select but semantically escape routes to the host FS.

CLAUDE.md non-negotiable: this is the first of the two layers that protect the
LLM-generated SQL; the second layer is the lockdown on the connection itself.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

# Blocklist of function/table identifiers that must never appear inside a Select.
# Case-insensitive; comparison is done on lowercased names.
_BLOCKLIST_NAMES: frozenset[str] = frozenset(
    {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "read_blob",
        "read_text",
        "copy",
        "attach",
        "detach",
        "install",
        "load",
        "set",
        "call",
        "sniff_csv",
    }
)

# Prefixes that are always forbidden (matches pragma_*, duckdb_*, glob-related).
_BLOCKLIST_PREFIXES: tuple[str, ...] = ("pragma_", "duckdb_", "glob")

# sqlglot class-name prefixes that signal IO/lockdown escape. sqlglot turns
# `read_csv(...)` into an `exp.ReadCSV` node, not `exp.Anonymous` — so a
# class-name-based check is needed in addition to identifier checks.
_BLOCKLIST_CLASS_PREFIXES: tuple[str, ...] = ("Read", "Copy")

# Statement/expression types that are allowed as the query root. Everything else
# (DROP/DELETE/INSERT/UPDATE/CREATE/ALTER/TRUNCATE/ATTACH/COPY/PRAGMA/...) is
# rejected upfront at the "parse" layer.
_ALLOWED_ROOTS: tuple[type, ...] = (
    exp.Select,
    exp.Union,
    exp.Intersect,
    exp.Except,
    exp.Subquery,
)


class SQLValidationError(Exception):
    """Raised when SQL fails either validation layer."""

    def __init__(self, reason: str, layer: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.layer = layer


@dataclass
class ValidationResult:
    ok: bool
    reason: str | None = None
    layer: str | None = None  # "parse" | "ast" | None


def _is_blocklisted_name(name: str) -> bool:
    lower = name.lower()
    if lower in _BLOCKLIST_NAMES:
        return True
    return any(lower.startswith(prefix) for prefix in _BLOCKLIST_PREFIXES)


def validate_sql(sql: str) -> ValidationResult:
    """Validate that `sql` is a safe read-only SELECT against the session table.

    Returns a ValidationResult. Callers should raise SQLValidationError when
    `ok=False`, or call `validate_sql_or_raise()` for the strict variant.
    """
    if not sql or not sql.strip():
        return ValidationResult(False, "SQL vazia.", layer="parse")

    try:
        parsed = sqlglot.parse_one(sql, read="duckdb")
    except sqlglot.errors.ParseError as exc:
        return ValidationResult(False, f"SQL inválida: {exc}", layer="parse")

    if parsed is None:
        return ValidationResult(False, "SQL não produziu AST.", layer="parse")

    # Layer 1: must be a read-only query root (Select, Union, Intersect, Except).
    if not isinstance(parsed, _ALLOWED_ROOTS):
        kind = type(parsed).__name__
        return ValidationResult(
            False,
            f"Apenas queries SELECT são permitidas (recebido: {kind}).",
            layer="parse",
        )

    # Layer 2: walk for blocklisted identifiers and IO-class AST nodes.
    for node in parsed.walk():
        cls_name = type(node).__name__
        # Class-name check first: catches ReadCSV / ReadParquet / Copy / AlterTable /
        # Drop / Insert / Update / Delete / Command nodes inside a Select subtree.
        if cls_name.startswith(_BLOCKLIST_CLASS_PREFIXES):
            return ValidationResult(
                False,
                f"Operação proibida detectada: {cls_name}.",
                layer="ast",
            )
        if isinstance(node, exp.Anonymous):
            name = node.name or ""
            if _is_blocklisted_name(name):
                return ValidationResult(
                    False,
                    f"Função proibida detectada: {name}.",
                    layer="ast",
                )
        elif isinstance(node, exp.Table):
            tbl_name = node.name or ""
            if _is_blocklisted_name(tbl_name):
                return ValidationResult(
                    False,
                    f"Tabela/função proibida detectada: {tbl_name}.",
                    layer="ast",
                )
        elif isinstance(node, exp.Command):
            # exp.Command covers raw unknown statements (e.g. PRAGMA, SET, INSTALL).
            return ValidationResult(
                False,
                f"Comando não permitido: {node.name}.",
                layer="ast",
            )

    return ValidationResult(True)


def validate_sql_or_raise(sql: str) -> None:
    """Strict variant: raises SQLValidationError on failure."""
    result = validate_sql(sql)
    if not result.ok:
        raise SQLValidationError(result.reason or "SQL inválida.", layer=result.layer or "unknown")
