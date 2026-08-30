"""Admin-only Claude token and estimated-cost analytics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.api.routes.auth import require_roles
from app.domain.enums import UserRole
from app.infrastructure.database.session import AsyncSessionFactory

router = APIRouter(prefix="/analytics/ai-costs", tags=["analytics"])


@router.get("")
async def ai_costs(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    minutes: int = Query(default=1440, ge=1, le=43200),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

    async with AsyncSessionFactory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        id,
                        analysis_run_id,
                        created_at,
                        metadata_json->>'model' AS model,
                        COALESCE((metadata_json->>'ai_called')::boolean, false) AS ai_called,
                        metadata_json->>'generated_by' AS generated_by,
                        NULLIF(metadata_json->'claude_usage'->>'input_tokens', '')::integer AS input_tokens,
                        NULLIF(metadata_json->'claude_usage'->>'output_tokens', '')::integer AS output_tokens,
                        NULLIF(metadata_json->'claude_usage'->>'total_tokens', '')::integer AS total_tokens,
                        NULLIF(metadata_json->'claude_usage'->>'estimated_cost_usd', '')::numeric AS estimated_cost_usd
                    FROM clinical_hypotheses
                    WHERE source = 'claude_compact_risk_summary'
                      AND created_at >= :cutoff
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"cutoff": cutoff, "limit": limit},
            )
        ).mappings().all()

    events: list[dict[str, Any]] = []
    input_tokens = 0
    output_tokens = 0
    cost_usd = 0.0
    tracked_calls = 0
    untracked_ai_calls = 0
    fallback_count = 0

    for row in rows:
        item = dict(row)
        raw_cost = item.get("estimated_cost_usd")
        item["estimated_cost_usd"] = float(raw_cost) if raw_cost is not None else None
        if item.get("input_tokens") is not None and item.get("output_tokens") is not None:
            tracked_calls += 1
            input_tokens += int(item["input_tokens"] or 0)
            output_tokens += int(item["output_tokens"] or 0)
            cost_usd += float(item["estimated_cost_usd"] or 0.0)
        elif item.get("ai_called"):
            untracked_ai_calls += 1
        else:
            fallback_count += 1
        events.append(item)

    return {
        "generated_at": datetime.now(UTC),
        "window_minutes": minutes,
        "compact_evaluations": len(events),
        "tracked_calls": tracked_calls,
        "untracked_ai_calls": untracked_ai_calls,
        "fallback_count": fallback_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": round(cost_usd, 8),
        "pricing": {
            "model": "claude-sonnet-5",
            "input_per_million_usd": 2.0,
            "output_per_million_usd": 10.0,
            "source": "Anthropic Sonnet 5 public API pricing",
        },
        "events": events,
    }
