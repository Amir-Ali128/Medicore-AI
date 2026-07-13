"""Minimal FastAPI application for MediCore AI (Phase 1).

Wires the API router, CORS, and a health check.
Tables are created explicitly via the dev script.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import lab_derived_parameters as _lab_derived_parameters  # noqa: F401


app = FastAPI(title="MediCore AI API", version="0.1.0")

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
