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

    # --- Render / direct database URL -----------------------------------
    # Render provides DATABASE_URL. Prefer this when present.
    database_url: str | None = None

    # --- PostgreSQL fallback --------------------------------------------
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
    csv_import_default_source: str = "reference_full_demographic_FINAL_v11"

    # --- Claude extraction (Module I) -----------------------------------
    anthropic_api_key: str | None = None
    claude_extraction_model: str | None = None

    # --- Claude clinical hypothesis copilot (Module J) ------------------
    claude_hypothesis_model: str | None = None

    @staticmethod
    def _with_driver(url: str, driver: str) -> str:
        """Convert Render/Postgres URL into SQLAlchemy driver URL."""
        if url.startswith(f"postgresql+{driver}://"):
            return url

        if url.startswith("postgresql://"):
            return url.replace("postgresql://", f"postgresql+{driver}://", 1)

        if url.startswith("postgres://"):
            return url.replace("postgres://", f"postgresql+{driver}://", 1)

        return url

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL used by the FastAPI application."""
        if self.database_url:
            return self._with_driver(self.database_url, "asyncpg")

        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)

        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """SQLAlchemy sync URL used by Alembic migrations."""
        if self.database_url:
            return self._with_driver(self.database_url, "psycopg")

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