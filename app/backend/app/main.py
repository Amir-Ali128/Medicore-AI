"""FastAPI application for the simplified MediCore backend."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.infrastructure.admin_bootstrap import ensure_bootstrap_admin
from app.infrastructure.database.feedback_migrations import ensure_user_feedback
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


@asynccontextmanager
async def lifespan(_: FastAPI):
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

    yield


app = FastAPI(title="MediCore AI API", version="1.0.0-simple", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://medicore-ai-web.onrender.com",
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
