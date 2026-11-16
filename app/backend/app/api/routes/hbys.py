"""HBYS integration endpoints: list visits, import a de-identified case, send the AI report back."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.api.dependencies import SessionDep
from app.api.routes.auth import get_current_active_user
from app.core.config import get_settings
from app.domain.enums import UserRole
from app.domain.hbys_integration import HbysError, HbysNotConfigured, diagnostic_report
from app.infrastructure.hbys_client import HbysClient
from app.domain.patient_lab_history import ensure_patient_access
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User

router = APIRouter(prefix="/hbys", tags=["hbys"])

_CLINICAL_ROLES = {UserRole.ADMIN, UserRole.DOCTOR, UserRole.LAB_STAFF}


def get_hbys_client() -> HbysClient:
    settings = get_settings()
    try:
        return HbysClient(settings.hbys_base_url, settings.hbys_api_key,
                          timeout=settings.hbys_timeout_seconds)
    except HbysNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


_SIMULATOR_MARKER = "simülasyon"
# Base URLs whose capability statement confirmed the synthetic simulator.
_confirmed_simulators: set[str] = set()


async def _is_simulator(client: HbysClient) -> bool:
    if client.base_url in _confirmed_simulators:
        return True
    try:
        capability = await client.capability()
    except HbysError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    software = str((capability.get("software") or {}).get("name") or "")
    if _SIMULATOR_MARKER in software.casefold():
        _confirmed_simulators.add(client.base_url)
        return True
    return False


def _is_individual(user: User) -> bool:
    return user.role == UserRole.PATIENT


async def hbys_user(
    client: Annotated[HbysClient, Depends(get_hbys_client)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role in _CLINICAL_ROLES:
        return current_user
    if _is_individual(current_user) and get_settings().hbys_individual_access:
        if await _is_simulator(client):
            return current_user
        raise HTTPException(status_code=403, detail=(
            "Bireysel hesaplar yalnızca Sanal HBYS (simülasyon) ile çalışabilir; "
            "gerçek bir HBYS için kurumsal hesap gerekir."
        ))
    raise HTTPException(status_code=403, detail=(
        "HBYS entegrasyonu kurumsal (klinik) hesaplar içindir. Sanal HBYS denemesi için "
        "sunucuda HBYS_INDIVIDUAL_ACCESS=true ayarı açılmalı."
    ))


ClientDep = Annotated[HbysClient, Depends(get_hbys_client)]
ClinicalUser = Annotated[User, Depends(hbys_user)]


def _bad_gateway(exc: HbysError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


async def _linked_cases(session, protocols: list[str], user: User) -> dict[str, dict[str, Any]]:
    """Linked Medicore cases (id + last export state); individual users only see their own."""
    if not protocols:
        return {}
    rows = (await session.execute(
        select(Patient.id, Patient.protocol_no, Patient.metadata_json).where(Patient.protocol_no.in_(protocols))
    )).all()
    return {
        protocol: {"id": str(patient_id), "export": (metadata or {}).get("hbys_export")}
        for patient_id, protocol, metadata in rows
        if not _is_individual(user) or (metadata or {}).get("owner_user_id") == str(user.id)
    }


async def _patient_ids_by_protocol(session, protocols: list[str], user: User) -> dict[str, str]:
    return {key: value["id"] for key, value in (await _linked_cases(session, protocols, user)).items()}


async def _current_ai_report(session, patient, current_user) -> dict[str, Any] | None:
    """The AI report exactly as the case view shows it: None when it is stale.

    Reuses the saved-case endpoint so the fingerprint check (report vs. current
    saved case) can never drift from what the physician sees.
    """
    from app.api.routes.simple_case import get_saved_simple_case

    saved = await get_saved_simple_case(patient.id, session, current_user)
    report = saved.get("ai_report")
    return report if isinstance(report, dict) else None


async def _store_export(session, patient, export: dict[str, Any]) -> None:
    """Write only ``hbys_export`` on top of the LATEST committed patient metadata.

    The export awaits the HBYS over the network; a physician may save the case
    meanwhile. Re-read the row under a row lock and merge just this one key, so a
    concurrent clinical save is never overwritten with the task's stale snapshot.
    """
    await session.refresh(patient, attribute_names=["metadata_json"], with_for_update=True)
    patient.metadata_json = {**(patient.metadata_json or {}), "hbys_export": export}
    await session.commit()


async def _export(client: HbysClient, session, patient, encounter_id: str, report: dict[str, Any],
                  *, trigger: str) -> dict[str, Any]:
    """Send one saved report and record the outcome on the patient. Raises HbysError."""
    resource = diagnostic_report(encounter_id=encounter_id, report_text=report["report_text"],
                                 model=report.get("model"))
    result = await client.send_report(resource)
    export = {
        "status": "sent", "trigger": trigger, "encounter": encounter_id, "report": result.get("id"),
        "sent_at": datetime.now(UTC).isoformat(), "case_fingerprint": report.get("case_fingerprint"),
    }
    await _store_export(session, patient, export)
    return export


def is_hbys_case(metadata: dict[str, Any] | None) -> bool:
    """True when the saved case was imported from the HBYS (source-tagged rows)."""
    case = (metadata or {}).get("simple_case")
    if not isinstance(case, dict):
        return False
    rows = [*(case.get("labs") or []), *(case.get("reports") or [])]
    return any(
        isinstance(row, dict) and "hbys" in (
            (row.get("source_metadata") or {}).get("source_system"),
            (row.get("metadata") or {}).get("source_system"),
        )
        for row in rows
    )


async def auto_export_ai_report(patient_id: uuid.UUID, user: Any) -> None:
    """Background task after an AI report is saved: push it to the HBYS visit.

    Never raises; the outcome (sent / skipped / failed + reason) is stored as
    ``hbys_export`` on the patient so the HBYS page can show it.
    """
    from app.infrastructure.database.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        patient = await session.get(Patient, patient_id)
        if patient is None or not is_hbys_case(patient.metadata_json):
            return

        async def record(status_value: str, detail: str) -> None:
            await _store_export(session, patient, {
                "status": status_value, "trigger": "auto", "detail": detail,
                "at": datetime.now(UTC).isoformat(),
            })

        try:
            client = get_hbys_client()
            await hbys_user(client, user)
            encounter = next((item for item in await client.encounters()
                              if item.protocol_no == patient.protocol_no), None)
            if encounter is None:
                await record("skipped", "HBYS'de bu protokol numarasına ait muayene bulunamadı.")
                return
            report = await _current_ai_report(session, patient, user)
            if not isinstance(report, dict) or not str(report.get("report_text") or "").strip():
                await record("skipped", "Güncel AI raporu yok (vaka rapordan sonra değişmiş).")
                return
            await _export(client, session, patient, encounter.encounter_id, report, trigger="auto")
        except HTTPException as exc:
            await record("failed", str(exc.detail))
        except HbysError as exc:
            await record("failed", str(exc))
        except Exception:
            await record("failed", "Beklenmeyen hata; rapor HBYS'ye gönderilemedi.")


def hbys_configured() -> bool:
    settings = get_settings()
    return bool(settings.hbys_base_url and settings.hbys_api_key)


class HbysReportRequest(BaseModel):
    patient_id: uuid.UUID


@router.get("/status")
async def hbys_status(client: ClientDep, _: ClinicalUser) -> dict[str, Any]:
    try:
        capability = await client.capability()
    except HbysError as exc:
        return {"configured": True, "reachable": False, "detail": str(exc)}
    software = capability.get("software") or {}
    return {"configured": True, "reachable": True, "software": software.get("name"),
            "fhir_version": capability.get("fhirVersion")}


@router.get("/encounters")
async def list_encounters(
    client: ClientDep, session: SessionDep, user: ClinicalUser,
    status: Annotated[str | None, Query(pattern="^(in-progress|finished)$")] = None,
) -> list[dict[str, Any]]:
    try:
        encounters = await client.encounters(status)
    except HbysError as exc:
        raise _bad_gateway(exc) from None
    linked = await _linked_cases(session, [item.protocol_no for item in encounters], user)
    return [{
        **item.__dict__,
        "medicore_patient_id": (linked.get(item.protocol_no) or {}).get("id"),
        "hbys_export": (linked.get(item.protocol_no) or {}).get("export"),
    } for item in encounters]


@router.get("/encounters/{encounter_id}/case")
async def import_case(encounter_id: str, client: ClientDep, session: SessionDep, user: ClinicalUser) -> dict[str, Any]:
    """Return a de-identified case draft; the client saves it through the normal case API."""
    try:
        imported = await client.encounter_case(encounter_id)
    except HbysError as exc:
        raise _bad_gateway(exc) from None
    linked = await _patient_ids_by_protocol(session, [imported.protocol_no], user)
    return {
        "encounter_id": imported.encounter_id,
        "protocol_no": imported.protocol_no,
        "age": imported.age,
        "sex": imported.sex,
        "case": imported.case.model_dump(mode="json"),
        "redaction_counts": imported.redaction_counts,
        "medicore_patient_id": linked.get(imported.protocol_no),
    }


@router.post("/encounters/{encounter_id}/report")
async def send_report(
    encounter_id: str, payload: HbysReportRequest, client: ClientDep, session: SessionDep,
    current_user: ClinicalUser,
) -> dict[str, Any]:
    """Send the patient's saved AI report (never client-supplied text) to the HBYS visit."""
    patient = await ensure_patient_access(session, patient_id=payload.patient_id, current_user=current_user)
    try:
        imported = await client.encounter_case(encounter_id)
    except HbysError as exc:
        raise _bad_gateway(exc) from None
    if imported.protocol_no != patient.protocol_no:
        raise HTTPException(status_code=409, detail="Hasta kaydı bu HBYS muayenesine ait değil.")

    report = await _current_ai_report(session, patient, current_user)
    if not isinstance(report, dict) or not str(report.get("report_text") or "").strip():
        raise HTTPException(status_code=409, detail="Gönderilecek güncel bir AI raporu yok. Önce raporu oluşturun.")
    try:
        export = await _export(client, session, patient, imported.encounter_id, report, trigger="manual")
    except HbysError as exc:
        raise _bad_gateway(exc) from None
    sent_at, result = export["sent_at"], {"id": export["report"]}
    return {"status": "sent", "hbys_report": result.get("id"), "sent_at": sent_at}
