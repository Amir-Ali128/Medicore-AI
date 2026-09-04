"""Application configuration.

Central, typed settings object loaded from environment variables (or a local
`.env` file). All other modules must depend on `get_settings()` rather than
reading environment variables directly, keeping configuration a single,
injectable source of truth.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field, computed_field
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

    # --- Experimental X-ray / ultrasound image review -------------------
    # Maximum-quality Claude vision profile. Runtime deployments can override this
    # with CLAUDE_VISION_MODEL without changing code.
    claude_vision_model: str = "claude-opus-5"

    # --- OpenAI independent radiology second reader ----------------------
    # Runtime-only secret; the original image is read independently. Prefer the
    # current frontier model when the project has access. Provider isolation in the
    # radiology router keeps Claude/Gemini available if OpenAI access is unavailable.
    openai_api_key: str | None = None
    openai_vision_model: str = "gpt-6-astra"
    openai_radiology_second_reader_enabled: bool = True

    # --- Gemini independent radiology third reader -----------------------
    # Maximum-quality multimodal profile. Gemini 3.1 Pro is currently preview;
    # deployments that require GA-only models can override this with
    # GEMINI_VISION_MODEL=gemini-3.8-flash without changing code.
    gemini_api_key: str | None = None
    gemini_vision_model: str = "gemini-3.1-pro-preview"
    gemini_radiology_third_reader_enabled: bool = True

    # --- Production hardening -------------------------------------------
    # External AI calls are optional dependencies. Bound both the number of
    # concurrent requests and the amount of time any request may occupy a worker.
    ai_call_timeout_seconds: float = Field(default=45.0, ge=1.0, le=180.0)
    ai_queue_timeout_seconds: float = Field(default=2.0, ge=0.05, le=30.0)
    ai_max_concurrency: int = Field(default=4, ge=1, le=32)
    ai_circuit_breaker_failures: int = Field(default=3, ge=1, le=20)
    ai_circuit_breaker_recovery_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=600.0,
    )

    # Readiness is intentionally much faster than model calls: health probes must
    # never accumulate while a database or dependency is unhealthy.
    health_check_timeout_seconds: float = Field(default=2.0, ge=0.1, le=10.0)

    # Binary upload limits remain configurable but bounded so an accidental env
    # value cannot turn one worker into an unbounded in-memory file buffer.
    lab_extraction_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1 * 1024 * 1024,
        le=25 * 1024 * 1024,
    )
    radiology_image_max_bytes: int = Field(
        default=15 * 1024 * 1024,
        ge=1 * 1024 * 1024,
        le=25 * 1024 * 1024,
    )

    # The configured ONNX engine is CPU-safe by default on small Render workers.
    # Model manifests still own the clinical batch limit; these settings only bound
    # process resources and concurrent execution.
    onnx_max_concurrency: int = Field(default=2, ge=1, le=16)
    onnx_concurrency_wait_seconds: float = Field(default=2.0, ge=0.05, le=30.0)
    onnx_intra_op_threads: int = Field(default=1, ge=1, le=16)
    onnx_inter_op_threads: int = Field(default=1, ge=1, le=16)

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
