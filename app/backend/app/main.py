"""Minimal FastAPI application for MediCore AI (Phase 1).

Wires the API router, CORS, health check, and small idempotent startup
migrations required by deployments without shell access.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import lab_derived_parameters as _lab_derived_parameters  # noqa: F401
from app.api.routes import lab_common_parameters as _lab_common_parameters  # noqa: F401
from app.api.routes import lab_parser_safety as _lab_parser_safety  # noqa: F401
from app.api.routes import lab_globulin_fix as _lab_globulin_fix  # noqa: F401
from app.api.routes import lab_case01_safety as _lab_case01_safety  # noqa: F401
from app.api.routes import lab_case01_sql_hotfix as _lab_case01_sql_hotfix  # noqa: F401
from app.domain import claude_compact_runtime_fix as _claude_compact_runtime_fix  # noqa: F401
from app.domain import abnormal_lab_explanation_runtime as _abnormal_lab_explanation_runtime  # noqa: F401
from app.domain import pathological_findings_runtime as _pathological_findings_runtime  # noqa: F401
from app.domain import lab_clinical_interpretation_runtime as _lab_clinical_interpretation_runtime  # noqa: F401
from app.domain import lab_followup_runtime as _lab_followup_runtime  # noqa: F401
from app.domain import compact_abnormal_only_runtime as _compact_abnormal_only_runtime  # noqa: F401
from app.domain import multisource_summary_runtime as _multisource_summary_runtime  # noqa: F401
from app.domain import ultrasound_result_only_runtime as _ultrasound_result_only_runtime  # noqa: F401
from app.domain import claude_sonnet5_compat_runtime as _claude_sonnet5_compat_runtime  # noqa: F401
from app.domain import claude_usage_runtime as _claude_usage_runtime  # noqa: F401
from app.domain import compact_hypothesis_dedup_runtime as _compact_hypothesis_dedup_runtime  # noqa: F401
from app.domain import claude_possibility_review_runtime as _claude_possibility_review_runtime  # noqa: F401
from app.domain import compact_summary_complete_runtime as _compact_summary_complete_runtime  # noqa: F401
from app.infrastructure.admin_bootstrap import ensure_bootstrap_admin
from app.infrastructure.database.feedback_migrations import ensure_user_feedback
from app.infrastructure.database.session import AsyncSessionFactory, engine
from app.infrastructure.database.startup_migrations import (
    ensure_analytics_presence,
    ensure_patient_protocol_numbers,
    ensure_user_nicknames,
    purge_old_analytics,
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
        await _lab_case01_safety._ensure_case01_parameters(session)
        await session.commit()

    admin_bootstrap = await ensure_bootstrap_admin()
    if admin_bootstrap == "created":
        print("Admin bootstrap completed: administrator account created.")

    purged_analytics_rows = await purge_old_analytics(engine)
    if purged_analytics_rows:
        print(
            "Analytics retention cleanup completed: "
            f"removed {purged_analytics_rows} stale presence row(s)."
        )

    yield


app = FastAPI(title="MediCore AI API", version="0.1.0", lifespan=lifespan)

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
