from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from app.api.routes import lab_ingestion as lab_routes
from app.domain.canonical_lab_model import (
    CANONICAL_LAB_CONTRACT,
    SOURCE_EMAIL_ATTACHMENT,
    SOURCE_ENABIZ_PDF,
    SOURCE_FILE_UPLOAD,
    SOURCE_INTEGRATION,
    SOURCE_MANUAL,
    SOURCE_PHOTO,
    SOURCE_SCREENSHOT,
)
from app.domain import universal_lab_ingestion as ingestion
from app.infrastructure.database.models.lab_report import LabReport


def _extraction_payload() -> dict:
    return {
        "patient_age": 41,
        "patient_sex": "F",
        "report_date": "2026-09-07",
        "labs": [
            {
                "raw_parameter_name": "Glukoz",
                "canonical_name": "Glucose",
                "raw_value": "105",
                "normalized_value": 105,
                "unit": "mg/dL",
                "reference_min": 70,
                "reference_max": 100,
                "reference_text": "70-100",
                "measured_at": "2026-09-07",
                "needs_review": False,
                "confidence": 0.98,
                "source_file_name": "source.pdf",
                "source_page": 2,
            }
        ],
        "warnings": [],
        "extraction_confidence": 0.98,
    }


def test_capabilities_expose_exactly_seven_ingress_families() -> None:
    payload = ingestion.ingestion_capabilities()
    assert payload["contract_version"] == CANONICAL_LAB_CONTRACT
    assert payload["source_count"] == 7
    assert {item["source_type"] for item in payload["sources"]} == {
        SOURCE_ENABIZ_PDF,
        SOURCE_FILE_UPLOAD,
        SOURCE_PHOTO,
        SOURCE_SCREENSHOT,
        SOURCE_MANUAL,
        SOURCE_EMAIL_ATTACHMENT,
        SOURCE_INTEGRATION,
    }


def test_manual_entry_becomes_canonical_without_clinical_classification() -> None:
    case = ingestion.ingest_manual_payload(
        labs=[
            {
                "raw_parameter_name": "HbA1c",
                "raw_value": "6.4",
                "normalized_value": 6.4,
                "unit": "%",
                "reference_min": 0,
                "reference_max": 5.6,
            }
        ],
        patient_age=0.5,
        patient_sex="M",
        report_date="2026-09-07",
        source_record_id="manual-1",
    )
    assert case["source_type"] == SOURCE_MANUAL
    assert case["patient_age"] == 0.5
    row = case["labs"][0]
    assert row["reference_min"] == 0.0
    assert row["normalized_value"] == 6.4
    assert "result_status" not in row
    assert row["native_ready"] if "native_ready" in row else case["native_ready"]


@pytest.mark.parametrize(
    ("source_type", "media_type", "file_name"),
    [
        (SOURCE_ENABIZ_PDF, "application/pdf", "enabiz.pdf"),
        (SOURCE_PHOTO, "image/jpeg", "photo.jpg"),
        (SOURCE_SCREENSHOT, "image/png", "screen.png"),
        (SOURCE_EMAIL_ATTACHMENT, "application/pdf", "mail.pdf"),
    ],
)
def test_document_sources_share_one_canonical_contract(
    monkeypatch: pytest.MonkeyPatch,
    source_type: str,
    media_type: str,
    file_name: str,
) -> None:
    async def fake_extract(**_: object) -> dict:
        return _extraction_payload()

    monkeypatch.setattr(ingestion, "extract_lab_document_with_openai", fake_extract)
    case = asyncio.run(
        ingestion.ingest_document_bytes(
            content=b"source-bytes",
            media_type=media_type,
            file_name=file_name,
            source_type=source_type,
        )
    )
    assert case["contract_version"] == CANONICAL_LAB_CONTRACT
    assert case["source_type"] == source_type
    assert len(case["source"]["sha256"]) == 64
    assert case["labs"][0]["source_type"] == source_type


def test_generic_csv_file_is_canonicalized_locally() -> None:
    content = (
        b"test_name,value,unit,reference_min,reference_max\n"
        b"Creatinine,0.9,mg/dL,0.6,1.2\n"
    )
    case = asyncio.run(
        ingestion.ingest_generic_file(
            content=content,
            media_type="text/csv",
            file_name="labs.csv",
            source_type=SOURCE_FILE_UPLOAD,
        )
    )
    row = case["labs"][0]
    assert case["source_type"] == SOURCE_FILE_UPLOAD
    assert row["raw_parameter_name"] == "Creatinine"
    assert row["normalized_value"] == 0.9
    assert row["source_file_name"] == "labs.csv"


def test_email_json_attachment_preserves_email_source_family() -> None:
    content = json.dumps(
        {
            "labs": [
                {
                    "test_name": "CRP",
                    "value": 3.2,
                    "unit": "mg/L",
                    "reference_text": "<5",
                }
            ]
        }
    ).encode()
    case = asyncio.run(
        ingestion.ingest_generic_file(
            content=content,
            media_type="application/json",
            file_name="attachment.json",
            source_type=SOURCE_EMAIL_ATTACHMENT,
            source_record_id="mail-42",
        )
    )
    assert case["source_type"] == SOURCE_EMAIL_ATTACHMENT
    assert case["source"]["record_id"] == "mail-42"
    assert case["labs"][0]["reference_text"] == "<5"


def test_hl7_oru_adapter_extracts_obx_but_drops_direct_patient_identifiers() -> None:
    message = (
        "MSH|^~\\&|LAB|HOSP|MEDICORE|HOSP|202609071200||ORU^R01|MSG-1|P|2.5\r"
        "PID|1||SECRET-ID-123||DOE^JANE||19800101|F\r"
        "OBR|1|||LAB PANEL|||202609071159\r"
        "OBX|1|NM|2345-7^Glucose^LN||105|mg/dL|70-100|H\r"
    )
    case = ingestion.ingest_integration_payload(
        integration_type="hl7_oru",
        payload=message,
    )
    assert case["source_type"] == SOURCE_INTEGRATION
    assert case["source"]["integration_type"] == "hl7_oru"
    assert case["patient_sex"] == "F"
    row = case["labs"][0]
    assert row["loinc_code"] == "2345-7"
    assert row["normalized_value"] == 105.0
    encoded = json.dumps(case)
    assert "DOE" not in encoded
    assert "JANE" not in encoded
    assert "SECRET-ID-123" not in encoded
    assert "19800101" not in encoded


def test_fhir_adapter_reads_observations_and_preserves_zero_reference_bound() -> None:
    payload = {
        "resourceType": "Bundle",
        "id": "bundle-1",
        "entry": [
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "subject": {"reference": "Patient/private-123"},
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "1988-5",
                                "display": "C reactive protein",
                            }
                        ]
                    },
                    "valueQuantity": {"value": 4.2, "unit": "mg/L"},
                    "referenceRange": [
                        {"low": {"value": 0}, "high": {"value": 5}}
                    ],
                    "effectiveDateTime": "2026-09-07T10:00:00+03:00",
                }
            }
        ],
    }
    case = ingestion.ingest_integration_payload(
        integration_type="fhir",
        payload=payload,
    )
    row = case["labs"][0]
    assert row["source_record_id"] == "obs-1"
    assert row["loinc_code"] == "1988-5"
    assert row["reference_min"] == 0.0
    assert row["reference_max"] == 5.0
    assert "Patient/private-123" not in json.dumps(case)


def test_rest_integration_accepts_structured_rows() -> None:
    case = ingestion.ingest_integration_payload(
        integration_type="rest",
        source_record_id="api-1",
        payload={
            "patient_age": 77,
            "patient_sex": "F",
            "report_date": "2026-09-07",
            "labs": [
                {
                    "test_name": "Potassium",
                    "value": 4.3,
                    "unit": "mmol/L",
                    "reference_text": "3.5-5.1",
                }
            ],
        },
    )
    assert case["source"]["integration_type"] == "rest"
    assert case["source"]["record_id"] == "api-1"
    assert case["patient_age"] == 77.0
    assert case["labs"][0]["normalized_value"] == 4.3


def test_low_confidence_extraction_is_review_only_not_silently_repaired() -> None:
    payload = _extraction_payload()
    payload["labs"][0]["raw_value"] = "71"
    payload["labs"][0]["normalized_value"] = 71
    payload["labs"][0]["confidence"] = 0.4
    payload["labs"][0]["needs_review"] = True
    case = ingestion.canonicalize_extraction_payload(
        payload,
        source=ingestion._source(source_type=SOURCE_FILE_UPLOAD, file_name="ambiguous.pdf"),
    )
    row = case["labs"][0]
    assert row["normalized_value"] == 71.0
    assert row["needs_review"] is True
    assert "low_input_confidence" in row["ingestion_reasons"]


def test_saved_report_evaluation_uses_persisted_canonical_data(monkeypatch: pytest.MonkeyPatch) -> None:
    report_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    canonical_case = {"contract_version": "persisted-canonical"}
    report = SimpleNamespace(
        id=report_id,
        patient_id=patient_id,
        raw_payload=canonical_case,
        metadata_json={"longitudinal_trends": [{"test": "Ferritin", "trend_status": "STABLE"}]},
        status="analyzed",
    )

    class FakeSession:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False

        async def get(self, model, key):
            assert model is LabReport
            assert key == report_id
            return report

        async def commit(self) -> None:
            self.committed = True

        async def rollback(self) -> None:
            self.rolled_back = True

    async def fake_ensure_patient_access(*_args, **kwargs):
        assert kwargs["patient_id"] == patient_id
        return SimpleNamespace(id=patient_id)

    def fake_process(payload):
        assert payload is canonical_case
        return {
            "contract_version": "trust-v1",
            "processed_row_count": 1,
            "trusted_count": 1,
            "review_count": 0,
        }

    async def fake_pipeline(envelope, *, longitudinal_trends):
        assert envelope["trusted_count"] == 1
        assert longitudinal_trends[0]["test"] == "Ferritin"
        return {
            "contract_version": "clinical-v1",
            "trusted_count": 1,
            "review_count": 0,
            "trusted_rows": [],
            "review_rows": [],
            "longitudinal_trends": list(longitudinal_trends),
            "clinical_assessment": {
                "headline": "Demir eksikliği bulguları",
                "overview": "Kaydedilmiş trusted laboratuvar verileri değerlendirildi.",
            },
            "ai_attempted": True,
            "ai_used": True,
            "native_trends_used_by_ai": 1,
            "doctor_review_required": False,
        }

    monkeypatch.setattr(lab_routes, "ensure_patient_access", fake_ensure_patient_access)
    monkeypatch.setattr(lab_routes, "process_canonical_lab_case", fake_process)
    monkeypatch.setattr(lab_routes, "run_native_trust_clinical_pipeline", fake_pipeline)

    session = FakeSession()
    result = asyncio.run(
        lab_routes.evaluate_saved_lab_report(
            report_id,
            session,
            SimpleNamespace(id=uuid.uuid4()),
        )
    )

    assert session.committed is True
    assert session.rolled_back is False
    assert result["clinical_assessment"]["headline"] == "Demir eksikliği bulguları"
    assert result["patient_history"]["lab_report_id"] == str(report_id)
    assert report.metadata_json["clinical_pipeline"]["ai_used"] is True
