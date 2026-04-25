"""Hardened DuckDB connection factory.

Every DuckDB connection created through here is:
- In-memory (no disk file — sessions are ephemeral by design)
- External access disabled (no read_csv/read_parquet/http/ATTACH to files)
- Known extensions auto-load disabled
- Configuration locked (after lockdown, settings cannot be toggled back on)

These three pragmas are applied in a fixed order and then verified — if any
pragma silently failed the factory raises `LockdownError` and the connection
is closed. NEVER use `duckdb.connect()` directly elsewhere in the app.

CLAUDE.md non-negotiable: connections are per-session and never shared.
"""

from __future__ import annotations

import duckdb


class LockdownError(RuntimeError):
    """Raised when a hardening pragma failed to apply."""


def create_hardened_connection() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with all three hardening pragmas applied."""
    con = duckdb.connect(database=":memory:")
    try:
        con.execute("SET enable_external_access = false")
        con.execute("SET autoload_known_extensions = false")
        con.execute("SET lock_configuration = true")
    except Exception as exc:
        con.close()
        raise LockdownError(f"Falha ao aplicar lockdown DuckDB: {exc}") from exc

    # Verify: if lockdown didn't stick, further SETs would still succeed.
    # Probe by trying to flip enable_external_access back on — must fail.
    try:
        con.execute("SET enable_external_access = true")
    except duckdb.Error:
        return con  # expected path — lockdown is in effect
    else:
        con.close()
        raise LockdownError("Lockdown não aplicou: enable_external_access pôde ser reativado.")
