from __future__ import annotations

from datetime import datetime
import uuid

from app.domain.clinical_brain import evaluate_clinical_brain
from app.schemas.clinical_brain import ClinicalBrainRequest


REPORT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PATIENT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _lab(name: str, value: float, status: str, unit: str = "") -> dict:
    return {
        "lab_result_id": None,
        "raw_parameter_name": name,
        "canonical_name": name,
        "normalized_value": value,
        "unit": unit or None,
        "result_status": status,
        "trend_status": "no_previous_result",
        "needs_review": status != "normal",
    }


def _ultrasound(text: str, *, impression: str | None = None, abnormal: bool = True) -> dict:
    now = datetime(2026, 9, 4, 9, 0, 0)
    return {
        "id": str(REPORT_ID),
        "patient_id": str(PATIENT_ID),
        "uploaded_by_user_id": None,
        "source_type": "manual",
        "file_name": "abdomen-usg.txt",
        "report_date": "2026-09-04",
        "modality": "ULTRASOUND",
        "body_part": "ABDOMEN",
        "original_text": text,
        "findings": [
            {
                "text": "Safra kesesi duvar kalınlaşması",
                "classification": "abnormal" if abnormal else "observation",
                "is_critical": False,
                "matched_terms": [],
            }
        ],
        "measurements": [],
        "dexa_metrics": [],
        "critical_findings": [],
        "impression": impression,
        "summary": impression or text[:120],
        "status": "analyzed",
        "metadata_json": {},
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


def _request(**overrides) -> ClinicalBrainRequest:
    payload = {
        "clinical_context": {
            "patient_information": {},
            "presenting_complaint": {
                "chief_complaint": "Sağ üst kadran ağrısı",
                "complaint_duration": "12 saat",
                "associated_symptoms": "Ateş ve bulantı",
            },
            "clinical_history_details": {},
            "physical_exam": {
                "temperature_c": 38.2,
                "examination_findings": "Murphy pozitif, sağ üst kadranda hassasiyet",
            },
            "imaging_results": {},
            "attachments": [],
        },
        "lab_results": [
            _lab("WBC", 14.2, "high", "10^9/L"),
            _lab("CRP", 55, "high", "mg/L"),
            _lab("ALT", 20, "normal", "U/L"),
        ],
        "radiology_reports": [
            _ultrasound(
                "BULGULAR: Safra kesesi boynunda impakte taş. Duvar kalınlığı 4.5 mm. "
                "Sonografik Murphy pozitiftir. SONUÇ: Akut inflamasyon lehine safra kesesi bulguları."
            )
        ],
    }
    payload.update(overrides)
    return ClinicalBrainRequest.model_validate(payload)


def test_brain_prepares_sources_and_moves_compatibility_to_python() -> None:
    result = evaluate_clinical_brain(_request())

    assert result.contract_version == "clinical-brain-v1"
    assert result.source_availability.clinical is True
    assert result.source_availability.laboratory is True
    assert result.source_availability.ultrasound is True
    assert result.selected_ultrasound_report_id == REPORT_ID
    assert "ULTRASOUND_ABNORMAL_REVIEW" in result.ultrasound_context_flags
    assert "Sağ üst kadran" in result.source_summaries.clinical
    assert "WBC" in result.source_summaries.laboratory
    assert result.compatibility.score >= 50
    assert result.compatibility.estimated_probability is None
    assert result.compatibility.requires_clinician_review is True
    assert result.requires_physician_review is True


def test_doctor_interpreter_is_backend_owned_and_groups_inflammation() -> None:
    result = evaluate_clinical_brain(_request())
    by_id = {item.id: item for item in result.doctor_interpretation.items}

    assert result.doctor_interpretation.high_count == 2
    assert "inflammation" in by_id
    assert "CRP" in " ".join(by_id["inflammation"].markers)
    assert "tanı" in result.doctor_interpretation.safety_note.lower()


def test_negative_murphy_is_not_promoted_as_positive_evidence() -> None:
    request = _request()
    payload = request.model_dump(mode="json")
    payload["clinical_context"]["physical_exam"]["examination_findings"] = "Murphy negatif"
    payload["clinical_context"]["presenting_complaint"]["chief_complaint"] = "Karın ağrısı"
    result = evaluate_clinical_brain(ClinicalBrainRequest.model_validate(payload))

    murphy = next(item for item in result.compatibility.evidence if item.code == "clinical_murphy")
    assert murphy.matched is False
    assert murphy.points == 0


def test_demographics_alone_do_not_make_clinical_source_ready() -> None:
    request = _request(
        clinical_context={
            "patient_information": {"age": 42, "sex": "female"},
            "presenting_complaint": {},
            "clinical_history_details": {},
            "physical_exam": {},
            "imaging_results": {},
            "attachments": [],
        },
        lab_results=[],
        radiology_reports=[],
    )
    result = evaluate_clinical_brain(request)

    assert result.source_availability.clinical is False
    assert result.source_availability.laboratory is False
    assert result.source_availability.ultrasound is False
    assert result.compatibility.score == 0
    assert result.compatibility.data_completeness_percent == 0


def test_latest_ultrasound_prefers_report_with_result_text() -> None:
    old = _ultrasound("BULGULAR: Eski ultrason kaydı", impression=None)
    old["id"] = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    old["created_at"] = "2026-09-03T12:00:00"
    old["updated_at"] = "2026-09-03T12:00:00"
    old["report_date"] = "2026-09-03"
    old["summary"] = "Eski kayıt"

    newer_result = _ultrasound("BULGULAR: Yeni. SONUÇ: Safra kesesi duvarı doğal.")
    newer_result["id"] = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    newer_result["created_at"] = "2026-09-04T12:00:00"
    newer_result["updated_at"] = "2026-09-04T12:00:00"
    newer_result["findings"] = []

    result = evaluate_clinical_brain(
        _request(radiology_reports=[old, newer_result], lab_results=[])
    )
    assert str(result.selected_ultrasound_report_id) == newer_result["id"]
    assert "Safra kesesi duvarı doğal" in result.source_summaries.ultrasound
