# --- Builder stage: resolve + install deps into a .venv ------------------------
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# Install uv (static binary — no apt deps required).
COPY --from=ghcr.io/astral-sh/uv:0.4.22 /uv /usr/local/bin/uv

WORKDIR /app

# Cache-friendly layer: lockfile + project metadata only.
COPY pyproject.toml uv.lock .python-version ./

# Install runtime deps into /opt/venv (no dev deps, no project code yet).
RUN uv sync --frozen --no-dev --no-install-project

# --- Runtime stage: slim image with .venv + app code ---------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

# Create unprivileged user.
RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy the resolved venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy source + alembic config. Only what runtime needs.
COPY app ./app
COPY alembic.ini ./alembic.ini

# Data volume (SQLite + uploads). Owned by app user.
RUN mkdir -p /app/data/db /app/data/uploads && chown -R app:app /app

USER app

EXPOSE 8000

# Run alembic upgrade then uvicorn. SQLite file lives on the mounted volume.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
