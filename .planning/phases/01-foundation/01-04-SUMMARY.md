# Plan 01-04 — auth_service — SUMMARY

**Status:** complete
**Commit:** `f3ade3c` — `feat(services):[GSD-108] - Add auth_service with register and authenticate`
**Files:**
- `app/services/__init__.py`
- `app/services/auth_service.py`

**Exports:**
- `EmailAlreadyExistsError` — raised when register hits UNIQUE violation on email
- `register_user(session, email, plain_password) -> User` — normalizes email (lower+strip), bcrypts password, catches `IntegrityError`, rolls back on collision
- `authenticate_user(session, email, plain_password) -> User | None` — returns None on unknown email, inactive user, or bad password
- `get_user_by_id(session, user_id) -> User | None` — used by `get_current_user` dep

**Notes:**
- Plan was not drafted as a formal PLAN.md because the planner subagent hit a rate limit after writing only 01-04. Implementation was executed directly from the VERIFICATION gap block, which named file paths and missing artifacts precisely.
- All assertions validated by the 10-test integration suite in `tests/api/test_auth.py` (see plan 01-07 summary).
