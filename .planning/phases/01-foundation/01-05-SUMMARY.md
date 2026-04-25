# Plan 01-05 — api-schemas + deps — SUMMARY

**Status:** complete
**Commit:** `055a1d8` — `feat(api):[GSD-109] - Add auth schemas error envelope and get_current_user dep`
**Files:**
- `app/schemas/__init__.py`
- `app/schemas/auth.py` — `RegisterRequest`, `LoginRequest`, `TokenResponse`, `UserOut`, `RegisterResponse`
- `app/schemas/errors.py` — `ErrorResponse`, `ErrorDetails`, `FieldError` (D-01..D-04 envelope)
- `app/api/__init__.py`
- `app/api/deps.py` — `get_current_user`, `CurrentUser`, `DbSession` type aliases

**Contract highlights:**
- `RegisterRequest`: `EmailStr` + `password` with `min_length=8, max_length=128`
- `UserOut`: never exposes `password_hash` (model_config `from_attributes=True` for ORM conversion)
- `ErrorResponse`: `error_type` snake_case EN; `message` PT-BR; optional `details.fields[]` for validation errors
- `get_current_user`: `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)` — we raise our own envelope-shaped 401, never FastAPI's default
- Any failure path (missing header, JWT decode error, unknown user, inactive user) → HTTP 401 with `error_type: invalid_token`
