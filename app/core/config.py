from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Loads from environment variables; falls back to .env file.
    Environment variables take precedence over .env (standard pydantic-settings behavior).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Database ---
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/db/app.sqlite"

    # --- JWT / Auth ---
    # None => ephemeral key generated in security.py with WARNING log (see PITFALLS.md#12).
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1, le=1440)

    # --- Uploads (Phase 2 consumes) ---
    UPLOADS_DIR: str = "/data/uploads"
    MAX_UPLOAD_BYTES: int = 52_428_800  # 50 MB
    MAX_UPLOAD_ROWS: int = 500_000
    SESSION_TTL_SECONDS: int = 3600

    # --- OpenAI (Phase 4 consumes) ---
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- App ---
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor. Tests call get_settings.cache_clear() to refresh."""
    return Settings()  # type: ignore[call-arg]
