"""Temporary Render DB seed endpoint.


Use this ONLY for deployment/bootstrap.
Protect it with SEED_ADMIN_TOKEN and remove it after the database is seeded.


Why this route is sync:
The seed scripts call asyncio.run(...). If this endpoint is async, Uvicorn already has
a running event loop and the scripts fail with:
"asyncio.run() cannot be called from a running event loop".
FastAPI runs normal def endpoints in a worker thread, so the scripts can safely use
asyncio.run there.
"""


from __future__ import annotations


import os
import runpy
import sys
from pathlib import Path
from typing import Annotated


from fastapi import APIRouter, Header, HTTPException, status


router = APIRouter(prefix="/admin", tags=["admin-seed"])




@router.post("/seed-render-db")
def seed_render_db(
    x_seed_token: Annotated[str | None, Header(alias="X-Seed-Token")] = None,
) -> dict[str, object]:
    expected_token = os.getenv("SEED_ADMIN_TOKEN")


    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SEED_ADMIN_TOKEN is not configured.",
        )


    if x_seed_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid seed token.",
        )


    backend_root = Path(__file__).resolve().parents[3]


    scripts = [
        backend_root / "scripts" / "create_dev_tables.py",
        backend_root / "scripts" / "seed_reference_ranges.py",
        backend_root / "scripts" / "seed_demo_data.py",
        backend_root / "scripts" / "set_demo_user_passwords.py",
    ]


    executed: list[str] = []
    skipped: list[str] = []
    original_cwd = Path.cwd()


    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))


    try:
        os.chdir(backend_root)


        for script in scripts:
            if not script.exists():
                skipped.append(str(script.relative_to(backend_root)))
                continue


            runpy.run_path(str(script), run_name="__main__")
            executed.append(str(script.relative_to(backend_root)))


    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Seed failed.",
                "executed": executed,
                "skipped": skipped,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc


    finally:
        os.chdir(original_cwd)


    return {
        "ok": True,
        "message": "Render database seed completed.",
        "executed": executed,
        "skipped": skipped,
    }
