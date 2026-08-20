"""Privacy-aware live visitor analytics for MediCore.

Tracks anonymous/authenticated browser presence and exposes an admin-only live
view. Raw IP storage and third-party IP geolocation are explicit environment
opt-ins because both are personal-data processing concerns.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Annotated

import httpx
from fastapi import APIRouter, Depends, Query, Request
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.routes.auth import ALGORITHM, SECRET_KEY, require_roles
from app.domain.enums import UserRole
from app.infrastructure.database.session import AsyncSessionFactory

router = APIRouter(prefix="/analytics", tags=["analytics"])

_TRUE_VALUES = {"1", "true", "yes", "on"}
_STORE_RAW_IP = os.getenv("ANALYTICS_STORE_RAW_IP", "false").strip().lower() in _TRUE_VALUES
_GEOLOOKUP_ENABLED = (
    os.getenv("ANALYTICS_GEOLOOKUP_ENABLED", "false").strip().lower() in _TRUE_VALUES
)
_GEOLOOKUP_BASE_URL = os.getenv("ANALYTICS_GEOLOOKUP_BASE_URL", "https://ipwho.is").rstrip("/")
_IP_HASH_SALT = os.getenv("ANALYTICS_IP_HASH_SALT", SECRET_KEY)


class HeartbeatRequest(BaseModel):
    visitor_id: str = Field(min_length=8, max_length=64)
    path: str = Field(default="/", max_length=512)
    timezone: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default=None, max_length=128)
    device_brand: str | None = Field(default=None, max_length=128)
    device_model: str | None = Field(default=None, max_length=192)
    device_type: str | None = Field(default=None, max_length=32)
    os_name: str | None = Field(default=None, max_length=128)
    os_version: str | None = Field(default=None, max_length=128)
    browser_name: str | None = Field(default=None, max_length=128)
    browser_version: str | None = Field(default=None, max_length=128)
    architecture: str | None = Field(default=None, max_length=64)


def _extract_client_ip(request: Request) -> str | None:
    """Return the best-effort public client IP behind common reverse proxies.

    Render and similar platforms populate X-Forwarded-For. This value is used
    only for analytics, never for authorization or security decisions.
    """

    for header_name in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"):
        value = request.headers.get(header_name)
        if not value:
            continue
        candidate = value.split(",", 1)[0].strip()
        if candidate:
            return candidate

    return request.client.host if request.client else None


def _hash_ip(ip_address: str | None) -> str | None:
    if not ip_address:
        return None
    return hmac.new(
        _IP_HASH_SALT.encode("utf-8"),
        ip_address.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _optional_user_id(request: Request) -> uuid.UUID | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        return uuid.UUID(str(subject)) if subject else None
    except (JWTError, ValueError, TypeError):
        return None


def _is_public_ip(ip_address: str | None) -> bool:
    if not ip_address:
        return False
    try:
        return ipaddress.ip_address(ip_address).is_global
    except ValueError:
        return False


async def _cached_geo(ip_hash: str | None) -> dict[str, Any] | None:
    if not ip_hash:
        return None

    async with AsyncSessionFactory() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT country_code, country, region, city, latitude, longitude
                    FROM analytics_presence
                    WHERE ip_hash = :ip_hash
                      AND (country IS NOT NULL OR city IS NOT NULL)
                    ORDER BY last_seen_at DESC
                    LIMIT 1
                    """
                ),
                {"ip_hash": ip_hash},
            )
        ).mappings().first()

    return dict(row) if row else None


async def _lookup_geo(ip_address: str | None, ip_hash: str | None) -> dict[str, Any]:
    cached = await _cached_geo(ip_hash)
    if cached:
        return cached

    if not _GEOLOOKUP_ENABLED or not _is_public_ip(ip_address):
        return {}

    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{_GEOLOOKUP_BASE_URL}/{ip_address}")
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        return {}

    if payload.get("success") is False:
        return {}

    return {
        "country_code": payload.get("country_code"),
        "country": payload.get("country"),
        "region": payload.get("region"),
        "city": payload.get("city"),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
    }


@router.post("/heartbeat")
async def heartbeat(payload: HeartbeatRequest, request: Request) -> dict[str, bool]:
    """Upsert one browser-presence heartbeat.

    The endpoint is intentionally public so the login page can be counted as an
    anonymous visit. A valid MediCore bearer token associates the session with a
    user without trusting a user id supplied by the browser.
    """

    ip_address = _extract_client_ip(request)
    ip_hash = _hash_ip(ip_address)
    user_id = _optional_user_id(request)
    geo = await _lookup_geo(ip_address, ip_hash)

    raw_ip = ip_address if _STORE_RAW_IP else None
    user_agent = request.headers.get("user-agent", "")[:512] or None

    values = {
        "id": uuid.uuid4(),
        "visitor_id": payload.visitor_id,
        "user_id": user_id,
        "last_path": payload.path[:512],
        "ip_address": raw_ip,
        "ip_hash": ip_hash,
        "country_code": geo.get("country_code"),
        "country": geo.get("country"),
        "region": geo.get("region"),
        "city": geo.get("city"),
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "user_agent": user_agent,
        "timezone": payload.timezone,
        "language": payload.language,
        "platform": payload.platform,
        "device_brand": payload.device_brand,
        "device_model": payload.device_model,
        "device_type": payload.device_type,
        "os_name": payload.os_name,
        "os_version": payload.os_version,
        "browser_name": payload.browser_name,
        "browser_version": payload.browser_version,
        "architecture": payload.architecture,
    }

    async with AsyncSessionFactory() as session:
        await session.execute(
            text(
                """
                INSERT INTO analytics_presence (
                    id, visitor_id, user_id, first_seen_at, last_seen_at,
                    last_path, ip_address, ip_hash,
                    country_code, country, region, city, latitude, longitude,
                    user_agent, timezone, language, platform,
                    device_brand, device_model, device_type,
                    os_name, os_version, browser_name, browser_version, architecture,
                    request_count
                ) VALUES (
                    :id, :visitor_id, :user_id, NOW(), NOW(),
                    :last_path, :ip_address, :ip_hash,
                    :country_code, :country, :region, :city, :latitude, :longitude,
                    :user_agent, :timezone, :language, :platform,
                    :device_brand, :device_model, :device_type,
                    :os_name, :os_version, :browser_name, :browser_version, :architecture,
                    1
                )
                ON CONFLICT (visitor_id) DO UPDATE SET
                    user_id = COALESCE(EXCLUDED.user_id, analytics_presence.user_id),
                    last_seen_at = NOW(),
                    last_path = EXCLUDED.last_path,
                    ip_address = EXCLUDED.ip_address,
                    ip_hash = EXCLUDED.ip_hash,
                    country_code = COALESCE(EXCLUDED.country_code, analytics_presence.country_code),
                    country = COALESCE(EXCLUDED.country, analytics_presence.country),
                    region = COALESCE(EXCLUDED.region, analytics_presence.region),
                    city = COALESCE(EXCLUDED.city, analytics_presence.city),
                    latitude = COALESCE(EXCLUDED.latitude, analytics_presence.latitude),
                    longitude = COALESCE(EXCLUDED.longitude, analytics_presence.longitude),
                    user_agent = EXCLUDED.user_agent,
                    timezone = EXCLUDED.timezone,
                    language = EXCLUDED.language,
                    platform = EXCLUDED.platform,
                    device_brand = COALESCE(EXCLUDED.device_brand, analytics_presence.device_brand),
                    device_model = COALESCE(EXCLUDED.device_model, analytics_presence.device_model),
                    device_type = COALESCE(EXCLUDED.device_type, analytics_presence.device_type),
                    os_name = COALESCE(EXCLUDED.os_name, analytics_presence.os_name),
                    os_version = COALESCE(EXCLUDED.os_version, analytics_presence.os_version),
                    browser_name = COALESCE(EXCLUDED.browser_name, analytics_presence.browser_name),
                    browser_version = COALESCE(EXCLUDED.browser_version, analytics_presence.browser_version),
                    architecture = COALESCE(EXCLUDED.architecture, analytics_presence.architecture),
                    request_count = analytics_presence.request_count + 1
                """
            ),
            values,
        )
        await session.commit()

    return {"ok": True}


@router.get("/live")
async def live_visitors(
    _: Annotated[object, Depends(require_roles(UserRole.ADMIN))],
    minutes: int = Query(default=5, ge=1, le=1440),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Return live/recent presence rows to administrators only."""

    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

    async with AsyncSessionFactory() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        p.visitor_id,
                        p.user_id,
                        u.nickname,
                        u.role::text AS role,
                        p.first_seen_at,
                        p.last_seen_at,
                        p.last_path,
                        p.ip_address,
                        p.country_code,
                        p.country,
                        p.region,
                        p.city,
                        p.latitude,
                        p.longitude,
                        p.user_agent,
                        p.timezone,
                        p.language,
                        p.platform,
                        p.device_brand,
                        p.device_model,
                        p.device_type,
                        p.os_name,
                        p.os_version,
                        p.browser_name,
                        p.browser_version,
                        p.architecture,
                        p.request_count
                    FROM analytics_presence p
                    LEFT JOIN users u ON u.id = p.user_id
                    WHERE p.last_seen_at >= :cutoff
                    ORDER BY p.last_seen_at DESC
                    LIMIT :limit
                    """
                ),
                {"cutoff": cutoff, "limit": limit},
            )
        ).mappings().all()

    sessions: list[dict[str, Any]] = []
    role_counts: dict[str, int] = {}
    authenticated = 0

    for row in rows:
        item = dict(row)
        role = item.get("role") or "anonymous"
        role_counts[role] = role_counts.get(role, 0) + 1
        if item.get("user_id"):
            authenticated += 1
        sessions.append(item)

    return {
        "generated_at": datetime.now(UTC),
        "window_minutes": minutes,
        "total": len(sessions),
        "authenticated": authenticated,
        "anonymous": len(sessions) - authenticated,
        "role_counts": role_counts,
        "raw_ip_enabled": _STORE_RAW_IP,
        "geo_enabled": _GEOLOOKUP_ENABLED,
        "sessions": sessions,
    }
