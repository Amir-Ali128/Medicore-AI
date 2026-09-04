"""Liveness/readiness helpers for production deployments.

Liveness is intentionally process-only. Readiness verifies the critical database
path while reporting optional AI/model circuits as degraded instead of taking the
whole API offline. This matches MediCore's physician-review/fallback architecture:
core records must remain available even when an optional model is temporarily down.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.infrastructure.runtime_resilience import registered_dependency_snapshots

logger = logging.getLogger(__name__)
T = TypeVar("T")

_COMPONENTS: dict[str, dict[str, Any]] = {}
_COMPONENTS_LOCK = threading.Lock()


def record_runtime_component(
    name: str,
    *,
    status: str,
    critical: bool = False,
    detail: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "status": str(status),
        "critical": bool(critical),
    }
    if detail:
        payload["detail"] = str(detail)[:240]
    with _COMPONENTS_LOCK:
        _COMPONENTS[str(name)] = payload


def runtime_component_snapshots() -> dict[str, dict[str, Any]]:
    with _COMPONENTS_LOCK:
        return {name: dict(value) for name, value in _COMPONENTS.items()}


async def run_noncritical_startup_step(
    name: str,
    operation: Callable[[], Awaitable[T]],
) -> T | None:
    """Run optional startup work without making the whole process unbootable."""
    try:
        result = await operation()
    except Exception as exc:
        logger.exception("Non-critical startup step failed: %s", name)
        record_runtime_component(
            name,
            status="degraded",
            critical=False,
            detail=exc.__class__.__name__,
        )
        return None

    record_runtime_component(name, status="ok", critical=False)
    return result


async def probe_database(
    engine: AsyncEngine,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    async def _probe() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_probe(), timeout=float(timeout_seconds))
    except TimeoutError:
        return {"status": "timeout", "critical": True}
    except Exception as exc:
        return {
            "status": "unavailable",
            "critical": True,
            "error_type": exc.__class__.__name__,
        }
    return {"status": "ok", "critical": True}


def compose_readiness_snapshot(
    *,
    database: dict[str, Any],
    dependency_guards: dict[str, dict[str, Any]],
    runtime_components: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    database_ready = database.get("status") == "ok"
    critical_component_failed = any(
        component.get("critical") is True and component.get("status") != "ok"
        for component in runtime_components.values()
    )
    ready = database_ready and not critical_component_failed

    open_dependencies = [
        name
        for name, snapshot in dependency_guards.items()
        if (snapshot.get("circuit") or {}).get("state") in {"open", "half_open"}
    ]
    degraded_components = [
        name
        for name, component in runtime_components.items()
        if component.get("status") not in {"ok", "disabled"}
        and component.get("critical") is not True
    ]

    if not ready:
        status = "not_ready"
    elif open_dependencies or degraded_components:
        status = "degraded"
    else:
        status = "ready"

    return {
        "status": status,
        "ready": ready,
        "components": {
            "database": database,
            "dependency_guards": dependency_guards,
            "runtime": runtime_components,
        },
        "degraded_optional_dependencies": sorted(
            set(open_dependencies + degraded_components)
        ),
    }


async def build_readiness_snapshot(
    engine: AsyncEngine,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    database = await probe_database(engine, timeout_seconds=timeout_seconds)
    return compose_readiness_snapshot(
        database=database,
        dependency_guards=registered_dependency_snapshots(),
        runtime_components=runtime_component_snapshots(),
    )


def reset_runtime_health_for_tests() -> None:
    with _COMPONENTS_LOCK:
        _COMPONENTS.clear()
