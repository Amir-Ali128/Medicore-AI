"""FastAPI application for the simplified MediCore backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
# Install the clinical runtime layers at startup in a fixed order. They were
# previously imported lazily by the first source-only evaluation request, so the
# AI prompt/behaviour silently changed after the first such request.
import app.domain.clinical_domain_router_runtime  # noqa: F401,E402
from app.infrastructure.ai_privacy_context import privacy_request_context
from app.domain.privacy_gateway import PrivacyViolation, PRIVACY_ERROR_CODE, PRIVACY_MESSAGE
from app.infrastructure.admin_bootstrap import ensure_bootstrap_admin
from app.infrastructure.voice_model_provisioning import prepare_offline_voice
from app.infrastructure.database.feedback_migrations import ensure_user_feedback
from app.infrastructure.database.lab_reader_telemetry import ensure_lab_reader_events
from app.infrastructure.database.session import AsyncSessionFactory, engine
from app.infrastructure.database.startup_migrations import (
    ensure_analytics_presence,
    ensure_patient_protocol_numbers,
    ensure_user_nicknames,
    purge_old_analytics,
)
from app.infrastructure.runtime_health import (
    build_readiness_snapshot,
    run_noncritical_startup_step,
)


def _log_ai_mode() -> None:
    """One startup line that states where clinical AI runs (never logs secrets)."""
    from app.core.config import get_settings
    from app.infrastructure.local_llm import LocalLLMNotConfigured, validated_base_url

    settings = get_settings()
    if not settings.ai_local_only:
        print("AI mode: EXTERNAL providers allowed (AI_LOCAL_ONLY=false).")
        return
    try:
        print(f"AI mode: local-only; clinical reports by '{settings.local_llm_model}' at {validated_base_url()}.")
    except LocalLLMNotConfigured as exc:
        print(f"AI mode: local-only; NO local model configured - AI reports are disabled. {exc}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    _log_ai_mode()
    user_backfilled = await ensure_user_nicknames(engine)
    if user_backfilled:
        print(
            "User nickname startup migration completed: "
            f"backfilled {user_backfilled} user(s)."
        )

    patient_backfilled = await ensure_patient_protocol_numbers(engine)
    if patient_backfilled:
        print(
            "Patient protocol numbers startup migration completed: "
            f"backfilled {patient_backfilled} patient(s)."
        )

    await ensure_analytics_presence(engine)
    await ensure_user_feedback(engine)
    await ensure_lab_reader_events(engine)

    async with AsyncSessionFactory() as session:
        await session.commit()

    admin_bootstrap = await run_noncritical_startup_step(
        "admin_bootstrap",
        ensure_bootstrap_admin,
    )
    if admin_bootstrap == "created":
        print("Admin bootstrap completed: administrator account created.")

    purged_analytics_rows = await run_noncritical_startup_step(
        "analytics_retention_cleanup",
        lambda: purge_old_analytics(engine),
    )
    if purged_analytics_rows:
        print(
            "Analytics retention cleanup completed: "
            f"removed {purged_analytics_rows} stale presence row(s)."
        )

    await run_noncritical_startup_step("offline_turkish_voice", prepare_offline_voice)

    yield


def _extra_cors_origins() -> list[str]:
    from app.core.config import get_settings

    return [item.strip().rstrip("/") for item in get_settings().cors_origins.split(",") if item.strip()]


app = FastAPI(title="MediCore AI API", version="1.0.0-simple", lifespan=lifespan, dependencies=[Depends(privacy_request_context)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://medicore-ai-web.onrender.com",
        *_extra_cors_origins(),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> JSONResponse:
    from app.core.config import get_settings

    settings = get_settings()
    snapshot = await build_readiness_snapshot(
        engine,
        timeout_seconds=settings.health_check_timeout_seconds,
    )
    return JSONResponse(
        status_code=200 if snapshot["ready"] else 503,
        content=snapshot,
    )


@app.exception_handler(PrivacyViolation)
async def privacy_failure(_request, _exc):
    return JSONResponse(status_code=422,content={"code":PRIVACY_ERROR_CODE,"detail":PRIVACY_MESSAGE})
