"""Canonical classification and clinical date fidelity at the mocked AI boundary.

These tests exercise the actual provider request without a live AI call. They
validate supplied data and instructions, not a model's medical conclusions.
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain import simple_case_ai
from app.schemas.simple_case import SimpleCaseRequest


_REPORT = """KLİNİK ÖZET
Menoraji ve halsizlik.

ÖNE ÇIKAN LABORATUVAR BULGULARI
Demir depolarında azalma ile mikrositer anemi paterni.

TETKİK / RAPOR BULGULARI
Kaynak USG raporunda intramural myom.

ENTEGRE KLİNİK DEĞERLENDİRME
Demir eksikliği anemisi ile uyumlu olabilir.

OLASI KLİNİK DURUMLAR / AYIRICI TANI
1. Demir eksikliği anemisi — Kanıt gücü: güçlü. Öncelik: birincil.

ÖNERİLEN İLERİ TETKİK / İZLEM
Kanama öyküsü hekim tarafından değerlendirilebilir.

SONUÇ / KANAAT
Menstrual kan kaybı olası kaynak olarak değerlendirilebilir.

HEKİM NOTU
Hekim değerlendirmesi gerekir.
""".strip()


@pytest.fixture
def mocked_provider(monkeypatch):
    create = AsyncMock(
        return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text=_REPORT)],
        ),
    )
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    constructor = lambda **kwargs: client
    monkeypatch.setattr(simple_case_ai, "AsyncAnthropic", constructor)
    monkeypatch.setattr(
        simple_case_ai,
        "get_settings",
        lambda: SimpleNamespace(
            claude_hypothesis_model="mock-clinical-model",
            claude_extraction_model=None,
            claude_vision_model=None,
            anthropic_api_key="mock-only-not-a-real-key",
        ),
    )
    return create


def _vaka1_request() -> SimpleCaseRequest:
    readings = [
        ("Hb", 10.2, "g/dL", "12–16"),
        ("MCV", 73, "fL", "80–100"),
        ("MCH", 23, "pg", "27–33"),
        ("RDW", 17.8, "%", "11.5–14.5"),
        ("Ferritin", 5, "ng/mL", "15–150"),
        ("Serum demir", 22, "µg/dL", "50–170"),
        ("Transferrin sat.", 5, "%", "15–45"),
        ("TIBC", 445, "µg/dL", "250–450"),
    ]
    labs = [
        {
            "test_name": name,
            "value": value,
            "unit": unit,
            "source_reference": reference,
            "specimen_date": "2026-10-02",
            "result_date": "2026-10-04",
            "uploaded_at": "2026-10-04T09:00:00+03:00",
        }
        for name, value, unit, reference in readings
    ]
    labs += [
        {"test_name": f"Other result {index}", "value": index, "unit": "U/L"}
        for index in range(42)
    ]
    # A copied or incorrectly displayed source flag must never determine status.
    labs[7]["source_metadata"] = {
        "source_flag": "HIGH",
        "status": "HIGH",
        "display_status": "high",
        "display_direction": "high",
    }
    return SimpleCaseRequest.model_validate(
        {
            "clinical": {
                "age": 38,
                "sex": "female",
                "complaints": ["Menoraji", "Halsizlik"],
                "history": ["Uzamış ve yoğun menstrual kanama"],
            },
            "labs": labs,
            "reports": [
                {
                    "report_type": "USG",
                    "findings": "Uterusta intramural myom izlenmiştir.",
                    "raw_text": "Pelvik USG: uterusta intramural myom.",
                    "metadata": {
                        "exam_date": "2026-10-02",
                        "uploaded_at": "2026-10-04T09:00:00+03:00",
                    },
                },
                {
                    "report_type": "Jinekoloji konsültasyonu",
                    "raw_text": "Menoraji nedeniyle değerlendirilmiştir.",
                    "metadata": {
                        "consultation_date": "2026-10-03",
                        "document_date": "2026-10-03",
                        "uploaded_at": "2026-10-04T09:00:00+03:00",
                    },
                },
            ],
        },
    )


def test_vaka1_provider_receives_all_results_and_backend_statuses(mocked_provider):
    result = asyncio.run(simple_case_ai.interpret_simple_case(_vaka1_request()))

    assert result.report_text == _REPORT
    assert result.model == "mock-clinical-model"
    mocked_provider.assert_awaited_once()
    call = mocked_provider.call_args.kwargs
    supplied = json.loads(call["messages"][0]["content"][0]["text"])
    assert len(supplied["labs"]) == 50
    assert [row["test_name"] for row in supplied["labs"]][-1] == "Other result 41"
    by_name = {row["test_name"]: row for row in supplied["labs"]}
    expected = {
        "Hb": "LOW", "MCV": "LOW", "MCH": "LOW", "RDW": "HIGH",
        "Ferritin": "LOW", "Serum demir": "LOW", "Transferrin sat.": "LOW",
        "TIBC": "NORMAL",
    }
    assert {name: by_name[name]["status"] for name in expected} == expected
    tibc = by_name["TIBC"]
    assert tibc["value"] == 445
    assert tibc["unit"] == "µg/dL"
    assert tibc["reference_low"] == 250
    assert tibc["reference_high"] == 450
    assert tibc["raw_reference"] == "250–450"
    assert tibc["reference_text"] == "250–450"
    assert tibc["source_flag"] == "HIGH"
    assert "display_status" not in tibc
    assert "display_direction" not in tibc
    assert by_name["Other result 41"]["status"] == "UNKNOWN"
    assert by_name["Other result 41"]["classification_reason"]
    assert supplied["clinical"]["complaints"] == ["Menoraji", "Halsizlik"]
    assert supplied["reports"][0]["raw_text"] == "Pelvik USG: uterusta intramural myom."
    # This checks the real provider instruction boundary, not a simulated medical
    # ranking result: canonical status is authoritative, with no JSON redesign.
    assert "do not recompute, override or relabel" in call["system"]
    assert "conditional secondary differentials" in call["system"]
    assert "Return only the finished Turkish medical report" in call["system"]


def test_provider_keeps_specimen_release_exam_consultation_and_upload_dates(mocked_provider):
    asyncio.run(simple_case_ai.interpret_simple_case(_vaka1_request()))
    supplied = json.loads(
        mocked_provider.call_args.kwargs["messages"][0]["content"][0]["text"],
    )
    lab = supplied["labs"][0]
    assert lab["specimen_date"] == "2026-10-02"
    assert lab["result_date"] == "2026-10-04"
    assert lab["uploaded_at"] == "2026-10-04T09:00:00+03:00"
    usg, consultation = supplied["reports"]
    assert usg["exam_date"] == "2026-10-02"
    assert consultation["consultation_date"] == "2026-10-03"
    assert consultation["document_date"] == "2026-10-03"
    assert all(report["uploaded_at"].startswith("2026-10-04") for report in supplied["reports"])


def test_legacy_metadata_dates_survive_ai_boundary_without_filling_missing_dates():
    request = SimpleCaseRequest.model_validate(
        {
            "labs": [
                {
                    "test_name": "Ferritin", "value": "5", "source_reference": "15–150",
                    "source_metadata": {
                        "specimen_date": "2026-10-02", "result_date": "2026-10-04",
                    },
                },
                {"test_name": "Undated result", "value": "negatif"},
            ],
            "reports": [{"report_type": "Rapor", "raw_text": "Tarihsiz rapor"}],
        },
    )
    supplied = simple_case_ai._build_case_payload(request)
    dated, undated = supplied["labs"]
    assert dated["specimen_date"] == "2026-10-02"
    assert dated["result_date"] == "2026-10-04"
    assert dated["uploaded_at"] is None
    assert undated["status"] == "UNKNOWN"
    assert all(undated[field] is None for field in simple_case_ai._SEMANTIC_DATE_FIELDS)
    assert all(supplied["reports"][0][field] is None for field in simple_case_ai._SEMANTIC_DATE_FIELDS)


def test_full_input_too_large_fails_before_provider_call(mocked_provider):
    request = SimpleCaseRequest.model_validate(
        {"reports": [{"report_type": "Rapor", "raw_text": "x" * 160_001}]},
    )
    with pytest.raises(RuntimeError, match="sessizce kırpılmadı"):
        asyncio.run(simple_case_ai.interpret_simple_case(request))
    mocked_provider.assert_not_awaited()
