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


def clinical_user(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    if current_user.role not in _CLINICAL_ROLES:
        raise HTTPException(status_code=403, detail="HBYS entegrasyonu yalnızca klinik kullanıcılar içindir.")
    return current_user


ClientDep = Annotated[HbysClient, Depends(get_hbys_client)]
ClinicalUser = Annotated[User, Depends(clinical_user)]


def _bad_gateway(exc: HbysError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


async def _patient_ids_by_protocol(session, protocols: list[str]) -> dict[str, str]:
    if not protocols:
        return {}
    rows = (await session.execute(
        select(Patient.id, Patient.protocol_no).where(Patient.protocol_no.in_(protocols))
    )).all()
    return {protocol: str(patient_id) for patient_id, protocol in rows}


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
    client: ClientDep, session: SessionDep, _: ClinicalUser,
    status: Annotated[str | None, Query(pattern="^(in-progress|finished)$")] = None,
) -> list[dict[str, Any]]:
    try:
        encounters = await client.encounters(status)
    except HbysError as exc:
        raise _bad_gateway(exc) from None
    linked = await _patient_ids_by_protocol(session, [item.protocol_no for item in encounters])
    return [{**item.__dict__, "medicore_patient_id": linked.get(item.protocol_no)} for item in encounters]


@router.get("/encounters/{encounter_id}/case")
async def import_case(encounter_id: str, client: ClientDep, session: SessionDep, _: ClinicalUser) -> dict[str, Any]:
    """Return a de-identified case draft; the client saves it through the normal case API."""
    try:
        imported = await client.encounter_case(encounter_id)
    except HbysError as exc:
        raise _bad_gateway(exc) from None
    linked = await _patient_ids_by_protocol(session, [imported.protocol_no])
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

    metadata = dict(patient.metadata_json or {})
    report = metadata.get("simple_case_ai_report")
    if not isinstance(report, dict) or not str(report.get("report_text") or "").strip():
        raise HTTPException(status_code=409, detail="Gönderilecek güncel bir AI raporu yok. Önce raporu oluşturun.")

    resource = diagnostic_report(encounter_id=imported.encounter_id, report_text=report["report_text"],
                                 model=report.get("model"))
    try:
        result = await client.send_report(resource)
    except HbysError as exc:
        raise _bad_gateway(exc) from None

    sent_at = datetime.now(UTC).isoformat()
    metadata["hbys_export"] = {
        "encounter": imported.encounter_id, "report": result.get("id"), "sent_at": sent_at,
        "case_fingerprint": report.get("case_fingerprint"),
    }
    patient.metadata_json = metadata
    await session.commit()
    return {"status": "sent", "hbys_report": result.get("id"), "sent_at": sent_at}
