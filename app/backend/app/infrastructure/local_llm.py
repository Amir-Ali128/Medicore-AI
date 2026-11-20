"""Self-hosted LLM endpoint (OpenAI-compatible) and the local-only AI policy.

Data sent here never leaves infrastructure the operator controls: the base URL
must be loopback, a private network address, a single-label/internal service
name, or a host explicitly listed in LOCAL_LLM_TRUSTED_HOSTS. A public host is
refused, so a typo cannot quietly turn "local" into an external provider.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from app.core.config import get_settings

LOCAL_PROVIDER = "Local"
_SERVICE_NAME = re.compile(r"[a-z][a-z0-9-]*")
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


def _private_address(address: ipaddress._BaseAddress) -> bool:
    return address.is_loopback or address.is_private or address.is_link_local


def _numeric_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Any form the system resolver accepts as an IPv4 literal: "134744072",
    "0x08080808", "127.1", "0177.0.0.1" ... (inet_aton semantics)."""
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def is_private_host(host: str, trusted: set[str] | None = None) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return False
    if host in (trusted or set()):
        return True
    if host in {"localhost", "host.docker.internal"}:
        return True
    try:
        return _private_address(ipaddress.ip_address(host.strip("[]")))
    except ValueError:
        pass
    numeric = _numeric_ipv4(host)
    if numeric is not None:
        # Alternative numeric spellings are addresses, never service names.
        return _private_address(numeric)
    if "." not in host:
        return bool(_SERVICE_NAME.fullmatch(host))  # an internal service name starts with a letter
    return host.endswith(_INTERNAL_SUFFIXES)


def _resolves_outside(host: str) -> bool:
    """True when a name resolves to any public address (fail open on no answer:
    an offline local server simply fails the request later)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        except ValueError:
            return True
        if not _private_address(address):
            return True
    return False


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def validated_base_url() -> str:
    settings = get_settings()
    base_url = (getattr(settings, "local_llm_base_url", None) or "").strip()
    if not base_url or not getattr(settings, "local_llm_model", None):
        raise LocalLLMNotConfigured(
            "Yerel AI modeli yapılandırılmamış (LOCAL_LLM_BASE_URL ve LOCAL_LLM_MODEL gerekli)."
        )
    parsed = urlparse(base_url)
    trusted = {item.strip().lower() for item in getattr(settings, "local_llm_trusted_hosts", "").split(",") if item.strip()}
    host = (parsed.hostname or "").lower()
    named = host not in trusted and _numeric_ipv4(host) is None and not _is_ip_literal(host)
    if (parsed.scheme not in {"http", "https"} or not is_private_host(host, trusted)
            or (named and host != "localhost" and _resolves_outside(host))):
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
