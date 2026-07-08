"""Application configuration.

Central, typed settings object loaded from environment variables (or a local
`.env` file). All other modules must depend on `get_settings()` rather than
reading environment variables directly, keeping configuration a single,
injectable source of truth.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the MediCore AI backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_name: str = "MediCore AI"
    environment: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- PostgreSQL ------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "medicore"
    postgres_password: str = "medicore"
    postgres_db: str = "medicore"

    # --- SQLAlchemy engine ----------------------------------------------
    db_echo: bool = False
    db_pool_pre_ping: bool = True
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- Reference data import ------------------------------------------
    # Default provenance tag written to imported records (source column).
    csv_import_default_source: str = "reference_full_demographic_FINAL_v11"

    # --- Claude extraction (Module I) -----------------------------------
    # Read from the environment; never hardcode secrets. The extraction
    # service raises a clear error if the model is not configured.
    anthropic_api_key: str | None = None
    claude_extraction_model: str | None = None

    # --- Claude clinical hypothesis copilot (Module J) ------------------
    # Read from the environment; never hardcode secrets. The hypothesis
    # service raises a clear error if the model is not configured.
    claude_hypothesis_model: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL (asyncpg) used by the FastAPI application."""
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy sync URL (psycopg) used by Alembic migrations."""
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached, process-wide `Settings` instance (DI entry point)."""
    return Settings()


settings: Settings = get_settings()
