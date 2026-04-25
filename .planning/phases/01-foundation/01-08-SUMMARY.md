# Plan 01-08 — Dockerfile + compose — SUMMARY

**Status:** complete
**Commits:**
- `71f12bd` — `build(docker):[GSD-112] - Add multi-stage Dockerfile and compose with healthcheck`
- `0f06ba5` — `build(docker):[GSD-113] - Drop BuildKit syntax and cache mount for broader compat`

**Files:**
- `Dockerfile` — two-stage (python:3.12-slim builder with `uv` → runtime with `.venv` copied)
- `docker-compose.yml` — single `api` service, named volumes for `data/db` and `data/uploads`, healthcheck hitting `/api/v1/health`
- `.dockerignore` — excludes `.git`, `.venv`, `.env`, tests, `.planning`, `.claude`, SQLite files

## Runtime verification (actual)

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Image size | <500MB | **386MB** | PASS |
| `docker compose up -d` to control returned | <10s | ~0s (control) — container healthy at 11s | PASS |
| Migrations auto-run on startup | yes | `alembic upgrade head` in CMD before uvicorn | PASS |
| Smoke: `GET /api/v1/health` | 200 | 200 | PASS |
| Smoke: `POST /api/v1/auth/register` | 201 | 201, returns user payload with UUID | PASS |
| Container healthcheck | healthy | `Up 11 seconds (healthy)` | PASS |

## Deviations from an ideal Dockerfile

1. **Removed BuildKit syntax + cache mount.** User's Docker CLI did not have buildx/BuildKit available at build time. `--mount=type=cache,target=/root/.cache/uv` was dropped; build works with the legacy builder. Cost: cold uv cache on every rebuild. Can be reinstated in any environment with buildx installed.
2. **Base image is `python:3.12-slim`**, not the uv distroless image — keeps the `sh` shell available for the CMD's `alembic && uvicorn` chain, and stays close to the standard Python image the team already uses locally.
3. **UV_COMPILE_BYTECODE=0** (builder) + **PYTHONDONTWRITEBYTECODE=1** (runtime) keep the image slim by not shipping `.pyc` files inside the venv.

## Notes for the user

- **Docker credential helper popup on macOS.** The keychain popup during pulls came from `docker-credential-desktop` being on PATH (even though Docker Desktop isn't installed — OrbStack inherits the CLI). Workaround used during this plan: `DOCKER_CONFIG=/tmp/docker-nocreds` with a config.json containing only `{}`. Permanent fix options:
  1. `echo '{"credsStore":""}' > ~/.docker/config.json` (keeps current context; disables credential helpers)
  2. Or remove `/usr/local/bin/docker-credential-desktop` (if you don't plan to use Docker Desktop)
- **`.env` file.** Do NOT commit a real `.env`. At runtime use either `JWT_SECRET_KEY=<hex> docker-compose up` (inject via env) or populate `.env` locally (it's gitignored). Leaving `JWT_SECRET_KEY` blank triggers an ephemeral key + `warning jwt.ephemeral_key_generated` structlog event.
