"""The only HTTP transport to a hospital information system (HBYS).

Outbound data is limited to read requests and DiagnosticReport resources built by
``app.domain.hbys_integration.diagnostic_report``. Every outbound report passes the
local fail-closed leak check first, mirroring the AI provider boundary.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.domain.hbys_integration import (
    EncounterSummary,
    HbysError,
    HbysNotConfigured,
    ImportedCase,
    case_from_bundle,
    encounter_summaries,
)
from app.domain.privacy_gateway import PrivacyViolation, final_leak_check

class HbysClient:
    def __init__(self, base_url: str | None, api_key: str | None, *, timeout: float = 10.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not base_url or not api_key:
            raise HbysNotConfigured("HBYS entegrasyonu yapılandırılmamış (HBYS_BASE_URL / HBYS_API_KEY).")
        self._base = base_url.rstrip("/")
        self.base_url = self._base
        self._headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/fhir+json"}
        self._timeout = timeout
        self._transport = transport

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self._base, headers=self._headers, timeout=self._timeout,
                                         transport=self._transport) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError:
            raise HbysError("HBYS'ye bağlanılamadı.") from None
        if response.status_code == 401:
            raise HbysError("HBYS API anahtarı reddedildi.")
        if response.status_code == 404:
            raise HbysError("HBYS'de muayene kaydı bulunamadı.")
        if response.status_code >= 400:
            raise HbysError(f"HBYS isteği başarısız oldu (HTTP {response.status_code}).")
        try:
            return response.json()
        except ValueError:
            raise HbysError("HBYS geçersiz JSON döndürdü.") from None

    async def capability(self) -> dict[str, Any]:
        return await self._request("GET", "/fhir/metadata")

    async def encounters(self, status: str | None = None) -> list[EncounterSummary]:
        params = {"status": status} if status else None
        return encounter_summaries(await self._request("GET", "/fhir/Encounter", params=params))

    async def encounter_case(self, encounter_id: str) -> ImportedCase:
        if not encounter_id.replace("-", "").isalnum() or len(encounter_id) > 64:
            raise HbysError("Geçersiz muayene kimliği.")
        return case_from_bundle(await self._request("GET", f"/fhir/Encounter/{encounter_id}/$everything"))

    async def send_report(self, resource: dict[str, Any]) -> dict[str, Any]:
        if resource.get("resourceType") != "DiagnosticReport" or "subject" in resource:
            raise HbysError("HBYS'ye yalnızca hasta kimliği içermeyen DiagnosticReport gönderilebilir.")
        try:
            final_leak_check(str(resource.get("conclusion") or ""))
        except PrivacyViolation:
            raise HbysError("Rapor kişisel bilgi içerebileceği için HBYS'ye gönderilmedi.") from None
        return await self._request("POST", "/fhir/DiagnosticReport", json=resource)
