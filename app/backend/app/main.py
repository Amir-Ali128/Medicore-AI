"""Minimal FastAPI application for MediCore AI (Phase 1).

Wires the API router, CORS, health check, and the small idempotent startup
migration required by deployments without shell access.
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
from app.infrastructure.database.session import engine
from app.infrastructure.database.startup_migrations import (
    ensure_patient_protocol_numbers,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    backfilled = await ensure_patient_protocol_numbers(engine)
    if backfilled:
        print(
            "Patient protocol startup migration completed: "
            f"backfilled {backfilled} patient(s)."
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
