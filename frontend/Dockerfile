# Separate Dockerfile for the Streamlit front-end so the API image stays slim.
# Two-stage same pattern as the backend.

FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY --from=ghcr.io/astral-sh/uv:0.4.22 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./

# Only pull the `ui` group (streamlit + its deps); `--only-group` skips both
# `[project.dependencies]` (heavy backend libs we don't need here) and other groups.
RUN uv sync --frozen --only-group ui --no-install-project


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY frontend ./frontend

RUN chown -R app:app /app
USER app

EXPOSE 8501

CMD ["streamlit", "run", "frontend/app.py"]
