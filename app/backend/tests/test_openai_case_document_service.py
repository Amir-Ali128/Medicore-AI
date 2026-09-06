from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.domain import openai_case_document_service as case_reader


def _payload() -> dict[str, object]:
    return {
        "content_types": ["clinical_history", "laboratory", "medications"],
        "document_summary": "Klinik öykü, ilaç listesi ve laboratuvar sonuçları içeriyor.",
        "patient_age": 77,
        "patient_sex": "female",
        "report_date": "2026-09-06",
        "clinical": {
            "reason_for_visit": "Kontrol",
            "chief_complaint": None,
            "complaint_duration": None,
            "associated_symptoms": None,
            "history_of_present_illness": "Diyabet takibi.",
            "current_medical_conditions": "Diabetes mellitus",
            "past_medical_history": None,
            "family_history": None,
            "allergies": None,
            "tobacco_alcohol": None,
            "past_surgeries": None,
            "examination_findings": None,
            "height_cm": None,
            "weight_kg": None,
        },
        "vitals": {
            "blood_pressure_systolic": None,
            "blood_pressure_diastolic": None,
            "pulse_bpm": None,
            "temperature_c": None,
            "respiratory_rate": None,
            "oxygen_saturation_percent": None,
        },
        "medications": [
            {
                "name": "Metformin",
                "dose": "500 mg",
                "frequency": "günde 2",
                "route": "oral",
                "status": "aktif",
                "source_page": 1,
            }
        ],
        "labs": [
            {
                "raw_parameter_name": "HbA1c",
                "canonical_name": "HbA1c",
                "raw_value": "9.4",
                "normalized_value": 9.4,
                "unit": "%",
                "reference_min": None,
                "reference_max": 6.5,
                "reference_text": "< 6.5",
                "measured_at": "2026-09-06",
                "needs_review": False,
                "confidence": 0.99,
                "source_file_name": "case.pdf",
                "source_page": 2,
            }
        ],
        "radiology": [],
        "other_findings": [],
        "warnings": [],
        "extraction_confidence": 0.97,
    }


def test_pdf_page_is_read_without_fixed_section_requirements(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps(_payload()))

    class FakeClient:
        def __init__(self, *, api_key):
            captured["api_key"] = api_key
            self.responses = FakeResponses()

    monkeypatch.setattr(case_reader, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        case_reader,
        "get_settings",
        lambda: SimpleNamespace(
            lab_extraction_max_bytes=15 * 1024 * 1024,
            openai_api_key="test-key",
            openai_lab_model="gpt-6-astra",
        ),
    )

    result = asyncio.run(
        case_reader.extract_case_documents_with_openai(
            documents=[(b"%PDF-test", "application/pdf", "case.pdf")]
        )
    )

    assert result["content_types"] == ["clinical_history", "laboratory", "medications"]
    assert result["labs"][0]["normalized_value"] == 9.4
    assert captured["store"] is False
    assert captured["model"] == "gpt-6-astra"
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert "whatever clinically relevant content" in str(captured["input"]).lower()

    parts = captured["input"][0]["content"]
    pdf = next(part for part in parts if part["type"] == "input_file")
    assert pdf["filename"] == "case.pdf"
    assert pdf["file_data"].startswith("data:application/pdf;base64,")


def test_image_page_is_supported(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=json.dumps(_payload()))

    class FakeClient:
        def __init__(self, *, api_key):
            self.responses = FakeResponses()

    monkeypatch.setattr(case_reader, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        case_reader,
        "get_settings",
        lambda: SimpleNamespace(
            lab_extraction_max_bytes=15 * 1024 * 1024,
            openai_api_key="test-key",
            openai_lab_model="gpt-6-astra",
        ),
    )

    asyncio.run(
        case_reader.extract_case_documents_with_openai(
            documents=[(b"image", "image/jpeg", "page.jpg")]
        )
    )
    image = next(
        part for part in captured["input"][0]["content"] if part["type"] == "input_image"
    )
    assert image["image_url"].startswith("data:image/jpeg;base64,")
    assert image["detail"] == "high"
