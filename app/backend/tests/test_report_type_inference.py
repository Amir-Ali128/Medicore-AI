from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.api.routes import radiology_reports
from app.domain.report_type_inference import infer_existing_report_type, infer_report_type
from app.schemas.radiology_report import RadiologyReportCreate, RadiologyReportResponse


@pytest.mark.parametrize(
    ("source_text", "expected"),
    [
        ("Kontrastsız toraks BT incelemesinde fokal konsolidasyon saptanmamıştır.", "CT"),
        ("Abdominal ultrasonografik incelemede karaciğer doğal görünümdedir.", "ULTRASOUND"),
        ("PA akciğer grafisinde infiltrasyon izlenmemiştir.", "X_RAY"),
        ("Kraniyal MR incelemesinde akut patoloji izlenmemiştir.", "MRI"),
        ("TORAKS CT\nBulgular: Her iki akciğer doğal.", "CT"),
        ("ÜST BATIN USG\nBulgular: Safra kesesi duvarı normal.", "ULTRASOUND"),
        ("Histopatoloji raporu\nMikroskopik değerlendirme: adenokarsinom.", "PATHOLOGY"),
        ("Ekokardiyografi raporu\nEjeksiyon fraksiyonu %60.", "ECHOCARDIOGRAPHY"),
        ("Kolonoskopi raporu\nÇekuma kadar ilerlenmiştir.", "ENDOSCOPY"),
        ("PET/CT incelemesi\nPatolojik FDG tutulumu izlenmemiştir.", "OTHER"),
        ("DXA KEMİK MİNERAL YOĞUNLUĞU\nT-score -1.2", "OTHER"),
        ("Karaciğer doğal boyutlarda. Dalak normal. Serbest sıvı yok.", "UNKNOWN"),
    ],
)
def test_content_identifies_current_examination(source_text: str, expected: str) -> None:
    result = infer_report_type(source_text=source_text)
    assert result.report_type == expected
    assert result.confidence >= 0.8 if expected != "UNKNOWN" else result.confidence == 0


@pytest.mark.parametrize(
    "reference",
    [
        "MRI önerilir.",
        "MR ile değerlendirme önerilmektedir.",
        "Further CT examination is recommended.",
        "Ultrasound follow-up suggested.",
        "Önceki BT incelemesi ile karşılaştırılmıştır.",
        "Prior MRI study showed a nodule.",
        "Gerekirse toraks BT çekilmesi uygundur.",
        "Patoloji sonucu alınması önerilir.",
        "CT was not performed.",
    ],
)
def test_recommendation_and_prior_examination_alone_are_unknown(reference: str) -> None:
    assert infer_report_type(source_text=reference).report_type == "UNKNOWN"


def test_follow_up_modality_does_not_replace_current_report_type() -> None:
    text = (
        "ABDOMİNAL ULTRASONOGRAFİ\n"
        "Bulgular: Karaciğerde 12 mm lezyon izlenmiştir.\n"
        "Sonuç: Dinamik kontrastlı karaciğer MRI incelemesi önerilir."
    )
    assert infer_report_type(source_text=text).report_type == "ULTRASOUND"


def test_prior_study_does_not_conflict_with_current_report() -> None:
    assert infer_report_type(
        title="Kraniyal MR",
        source_text="Önceki BT ile karşılaştırıldığında boyutları stabildir.",
    ).report_type == "MRI"


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "BT ve MRI raporu"},
        {"title": "TORAKS BT", "examination": "Kraniyal MRI"},
        {"source_text": "USG İNCELEMESİ\nMRI İNCELEMESİ\nBulgular: Fokal lezyon."},
    ],
)
def test_conflicting_current_examinations_are_unknown(fields: dict[str, str]) -> None:
    result = infer_report_type(**fields)
    assert result.report_type == "UNKNOWN"
    assert "conflicting_examination_types" in result.reasons


def test_fields_and_mri_technique_can_be_used_without_title() -> None:
    assert infer_report_type(examination="PA akciğer grafisi").report_type == "X_RAY"
    assert infer_report_type(technique="T1 ve T2 ağırlıklı sekanslar elde edilmiştir.").report_type == "MRI"
    assert infer_report_type(findings=[{"text": "Abdominal ultrasonografik incelemede kitle izlenmedi."}]).report_type == "ULTRASOUND"
    assert infer_report_type(impression="Kraniyal MR incelemesinde anormal bulgu izlenmedi.").report_type == "MRI"


def test_weak_existing_modality_is_not_accepted_without_current_content() -> None:
    assert infer_report_type(modality="CT", source_text="MRI önerilir.").report_type == "UNKNOWN"
    assert infer_report_type(modality="MRI", source_text="Karaciğer doğal boyutlarda.").report_type == "UNKNOWN"


def test_previous_generated_type_metadata_is_not_treated_as_document_title() -> None:
    result = infer_existing_report_type({
        "metadata_json": {"report_type": "CT"},
        "original_text": "Karaciğer doğal boyutlarda. CT önerilir.",
    })
    assert result.report_type == "UNKNOWN"


def test_ordinary_pathology_word_does_not_create_pathology_report() -> None:
    assert infer_report_type(source_text="Akut patoloji saptanmamıştır.").report_type == "UNKNOWN"
    assert infer_report_type(findings="Patolojik lenf nodu izlenmedi.").report_type == "UNKNOWN"


@pytest.mark.parametrize(
    ("source_text", "expected"),
    [
        ("Toraks BT incelemesinde patoloji mevcuttur.", "CT"),
        ("MRI study shows intracranial pathology.", "MRI"),
        ("Bulgular: Pulmonary pathology is observed.", "UNKNOWN"),
    ],
)
def test_pathology_in_a_finding_is_not_a_separate_report_type(source_text: str, expected: str) -> None:
    assert infer_report_type(source_text=source_text).report_type == expected


def test_echocardiography_is_more_specific_than_ultrasound_technique() -> None:
    assert infer_report_type(title="Ultrasound echocardiography report").report_type == "ECHOCARDIOGRAPHY"


def test_source_and_metadata_are_not_mutated() -> None:
    original_text = "  KRANİYAL MR\nBulgular: Doğal.  "
    original_metadata = {"title": "Kraniyal MR", "custom": "retained"}
    record = {"original_text": original_text, "metadata_json": original_metadata}
    result = infer_existing_report_type(record)
    assert result.report_type == "MRI"
    assert record["original_text"] == original_text
    assert original_metadata == {"title": "Kraniyal MR", "custom": "retained"}
    assert result.to_metadata()["inferred_report_type"] == "MRI"
    assert result.to_metadata()["report_type_confidence"] >= 0.8


def test_response_derives_type_for_legacy_reports_without_saved_metadata() -> None:
    now = datetime.now(timezone.utc)
    record = RadiologyReportResponse.model_validate(
        {
            "id": uuid.uuid4(), "patient_id": uuid.uuid4(), "uploaded_by_user_id": None,
            "source_type": "legacy", "file_name": None, "report_date": None,
            "modality": "UNKNOWN", "body_part": "OTHER",
            "original_text": "Kontrastsız toraks BT incelemesinde konsolidasyon yok.",
            "impression": None, "summary": "Original report", "status": "analyzed",
            "metadata_json": {}, "created_at": now, "updated_at": now,
        }
    )
    response = record.model_dump()
    assert response["inferred_report_type"] == "CT"
    assert response["report_type_confidence"] >= 0.8
    assert response["metadata_json"] == {}


def test_report_persistence_adds_metadata_without_rewriting_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(radiology_reports, "_ensure_phase2_table", AsyncMock())
    monkeypatch.setattr(radiology_reports, "_get_accessible_patient", AsyncMock())
    session = SimpleNamespace(add=Mock(), commit=AsyncMock(), refresh=AsyncMock())
    source = "  PA AKCİĞER GRAFİSİ\nBulgular: Akut kardiyopulmoner patoloji yok.  "
    payload = RadiologyReportCreate(
        patient_id=uuid.uuid4(), report_text=source, metadata_json={"custom": "retained"},
    )
    user = SimpleNamespace(id=uuid.uuid4())
    result = asyncio.run(radiology_reports._persist_report(
        payload=payload, source_type="manual_text", session=session, current_user=user,
    ))
    assert result.original_text == source
    assert result.metadata_json["inferred_report_type"] == "X_RAY"
    assert result.metadata_json["custom"] == "retained"
    assert result.patient_id == payload.patient_id
    session.commit.assert_awaited_once()
