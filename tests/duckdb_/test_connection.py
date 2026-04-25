from __future__ import annotations

import duckdb
import pytest

from app.duckdb_.connection import create_hardened_connection


def test_creates_connection() -> None:
    con = create_hardened_connection()
    try:
        assert con.execute("SELECT 1").fetchone() == (1,)
    finally:
        con.close()


def test_external_access_disabled() -> None:
    con = create_hardened_connection()
    try:
        with pytest.raises(duckdb.Error):
            # read_csv uses external file access → must be blocked.
            con.execute("SELECT * FROM read_csv('/etc/passwd')").fetchall()
    finally:
        con.close()


def test_lockdown_prevents_reenabling() -> None:
    con = create_hardened_connection()
    try:
        with pytest.raises(duckdb.Error):
            con.execute("SET enable_external_access = true")
    finally:
        con.close()


def test_install_extension_fails() -> None:
    con = create_hardened_connection()
    try:
        with pytest.raises(duckdb.Error):
            con.execute("INSTALL httpfs")
    finally:
        con.close()
