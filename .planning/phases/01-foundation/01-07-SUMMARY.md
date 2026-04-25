# Plan 01-07 — integration tests — SUMMARY

**Status:** complete
**Commit:** `4583863` — `test(auth):[GSD-111] - Add integration tests and fix aiosqlite UUID binding`
**Files:**
- `tests/__init__.py`
- `tests/api/__init__.py`
- `tests/conftest.py`
- `tests/api/test_auth.py`
- `app/db/models.py` — **bug fix** applied (see below)

**Test outcome:** `10 passed in 2.48s`

## Bug fix (deviation — pre-existing from Plan 01-03)

Plan 01-03 declared the User PK as:
```python
id: Mapped[uuid.UUID] = mapped_column(String(36), primary_key=True, default=uuid.uuid4)
```

Alembic migration verified correctly, but actual INSERTs via aiosqlite failed with
`sqlite3.ProgrammingError: Error binding parameter 1: type 'UUID' is not supported`. SQLAlchemy
does not auto-coerce `uuid.UUID` → str for SQLite when the column is `String(36)`; aiosqlite's
driver has no UUID adapter.

**Fix** (aligned with PITFALLS.md#11 — "Stored as String(36) on SQLite"):
```python
id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
```

Future Postgres migration becomes `PG_UUID(as_uuid=True)` — trivial column swap.

## Test coverage vs ROADMAP Phase 1 SC

| SC | Coverage |
|----|----------|
| SC#1 register 201 / duplicate 409 | `test_register_returns_201_and_user_payload`, `test_duplicate_email_returns_409`, plus 422 coverage for invalid email / short password |
| SC#2 login + protected 401/200 | `test_login_returns_token_and_me_works`, `test_login_wrong_password_returns_401`, `test_me_without_token_returns_401`, `test_me_with_garbage_token_returns_401` |
| SC#3 cross-user isolation | `test_cross_user_isolation` — registers A+B, logs both in, asserts `/auth/me` resolves each token to its own User, ids differ |

## Fixtures

- `db_engine` — in-memory SQLite (`sqlite+aiosqlite:///:memory:`) per test; tables created from `Base.metadata.create_all`; disposed after
- `client` — `httpx.AsyncClient` via `ASGITransport(app=create_app())`; DB dep overridden to use the shared in-memory engine; deterministic `JWT_SECRET_KEY` via env set before imports
