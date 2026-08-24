"""Authenticated manual laboratory entry and option discovery.

Manual values use the same deterministic laboratory pipeline as PDF extraction,
but the selected patient and uploader are taken from the authenticated session.
The option endpoint reflects the live parser registry so the UI stays aligned
with currently supported laboratory parameters.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text as sql_text

from app.api.dependencies import AnalysisPipelineDep, SessionDep
from app.api.routes import lab_analysis
from app.api.routes.auth import get_current_active_user
from app.domain.enums import UserRole
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.schemas.lab_analysis import AnalysisPipelineResult, MockLabReportInput

router = APIRouter(prefix="/lab-analysis", tags=["lab-analysis"])

_COMMON_UNIT_OPTIONS: tuple[str, ...] = (
    "",
    "%",
    "mg/dL",
    "g/dL",
    "mg/L",
    "mmol/L",
    "mEq/L",
    "ng/mL",
    "pg/mL",
    "ug/dL",
    "ug/L",
    "U/L",
    "IU/L",
    "mIU/L",
    "uIU/mL",
    "pmol/L",
    "nmol/L",
    "K/mm3",
    "M/mm3",
    "fL",
    "pg",
    "mL/dk/1.73m2",
    "mm/S",
    "/100WBC",
)


def _ensure_patient_access(patient: Patient, current_user: User) -> None:
    if current_user.role != UserRole.PATIENT:
        return

    owner_user_id = (patient.metadata_json or {}).get("owner_user_id")
    if owner_user_id != str(current_user.id):
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")


@router.get("/manual-options")
async def list_manual_lab_options() -> dict[str, list[dict[str, Any]]]:
    """Return the live parser-supported tests and selectable units."""
    parameters: list[dict[str, Any]] = []

    for name, config in sorted(
        lab_analysis.LAB_PARAMETER_ALIASES.items(),
        key=lambda item: item[0].casefold(),
    ):
        default_unit = str(config.get("default_unit") or "")
        unit_options = [default_unit]
        unit_options.extend(unit for unit in _COMMON_UNIT_OPTIONS if unit != default_unit)
        parameters.append(
            {
                "name": name,
                "default_unit": default_unit,
                "unit_options": unit_options,
            }
        )

    return {"parameters": parameters}


@router.post(
    "/manual",
    response_model=AnalysisPipelineResult,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_manual_lab_report(
    payload: MockLabReportInput,
    pipeline: AnalysisPipelineDep,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> AnalysisPipelineResult:
    """Analyze manually entered values for an accessible saved patient."""
    patient = await session.get(Patient, payload.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Hasta kaydı bulunamadı.")
    _ensure_patient_access(patient, current_user)

    if not payload.values:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En az bir laboratuvar sonucu girilmelidir.",
        )

    # Keep manual entry aligned with the PDF flow: all runtime parser additions
    # and their database records must exist before the deterministic pipeline runs.
    await lab_analysis._ensure_demo_patient_and_user()

    report_date = payload.report_date
    secured_payload = payload.model_copy(
        update={
            "uploaded_by_user_id": current_user.id,
            "file_name": payload.file_name
            or f"manual-entry-{report_date.isoformat() if report_date else 'undated'}.json",
        }
    )

    try:
        result = await pipeline.run(secured_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    # Analyse against the selected patient's demographics, but preserve the same
    # explicit Analyse -> Save workflow used by PDF uploads. Until Save is pressed,
    # move the generated rows back to the demo holding patient so they do not
    # appear in the selected patient's archive prematurely.
    hold_params = {
        "patient_id": str(lab_analysis.DEMO_PATIENT_ID),
        "lab_report_id": str(result.lab_report_id),
    }
    await session.execute(
        sql_text(
            "UPDATE lab_reports SET patient_id = :patient_id "
            "WHERE id = :lab_report_id"
        ),
        hold_params,
    )
    await session.execute(
        sql_text(
            "UPDATE analysis_runs SET patient_id = :patient_id "
            "WHERE lab_report_id = :lab_report_id"
        ),
        hold_params,
    )
    await session.execute(
        sql_text(
            "UPDATE lab_results SET patient_id = :patient_id "
            "WHERE lab_report_id = :lab_report_id"
        ),
        hold_params,
    )
    await session.execute(
        sql_text(
            "UPDATE clinical_hypotheses SET patient_id = :patient_id "
            "WHERE lab_report_id = :lab_report_id"
        ),
        hold_params,
    )
    await session.commit()

    return result
