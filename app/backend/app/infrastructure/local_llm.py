"""Self-hosted LLM endpoint (OpenAI-compatible) and the local-only AI policy.

Data sent here never leaves infrastructure the operator controls: the base URL
must be loopback, a private network address, a single-label/internal service
name, or a host explicitly listed in LOCAL_LLM_TRUSTED_HOSTS. A public host is
refused, so a typo cannot quietly turn "local" into an external provider.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.core.config import get_settings

LOCAL_PROVIDER = "Local"
_INTERNAL_SUFFIXES = (".internal", ".local", ".lan", ".home.arpa", ".svc", ".cluster.local")


class LocalLLMNotConfigured(RuntimeError):
    """Safe, user-facing configuration error."""


class ExternalAIBlocked(RuntimeError):
    """Raised when AI_LOCAL_ONLY is on and an external provider is requested."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            "Yalnızca yerel AI modu açık (AI_LOCAL_ONLY): dış AI servisleri kapalı, "
            f"bu işlem ({provider}) yapılmadı. Veri dışarı gönderilmedi."
        )


def local_only() -> bool:
    return bool(getattr(get_settings(), "ai_local_only", False))


def local_mode() -> bool:
    """Clinical report generation uses the local model."""
    settings = get_settings()
    return local_only() or bool(getattr(settings, "local_llm_base_url", None) and getattr(settings, "local_llm_model", None))


def is_private_host(host: str, trusted: set[str] | None = None) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host in (trusted or set()):
        return True
    if host in {"localhost", "host.docker.internal"}:
        return True
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return "." not in host or host.endswith(_INTERNAL_SUFFIXES)
    return address.is_loopback or address.is_private or address.is_link_local


def validated_base_url() -> str:
    settings = get_settings()
    base_url = (getattr(settings, "local_llm_base_url", None) or "").strip()
    if not base_url or not getattr(settings, "local_llm_model", None):
        raise LocalLLMNotConfigured(
            "Yerel AI modeli yapılandırılmamış (LOCAL_LLM_BASE_URL ve LOCAL_LLM_MODEL gerekli)."
        )
    parsed = urlparse(base_url)
    trusted = {item.strip().lower() for item in getattr(settings, "local_llm_trusted_hosts", "").split(",") if item.strip()}
    if parsed.scheme not in {"http", "https"} or not is_private_host(parsed.hostname or "", trusted):
        raise LocalLLMNotConfigured(
            "LOCAL_LLM_BASE_URL yerel/özel bir adres olmalı (localhost, iç ağ IP'si veya iç servis adı). "
            "Kendi sunucunuzsa LOCAL_LLM_TRUSTED_HOSTS ile açıkça belirtin."
        )
    return base_url.rstrip("/")


def local_client():
    """OpenAI-compatible async client bound to the validated local endpoint."""
    from openai import AsyncOpenAI

    settings = get_settings()
    return AsyncOpenAI(
        base_url=validated_base_url(),
        api_key=getattr(settings, "local_llm_api_key", None) or "local",
        timeout=float(getattr(settings, "local_llm_timeout_seconds", 300.0)),
        max_retries=0,
    )
