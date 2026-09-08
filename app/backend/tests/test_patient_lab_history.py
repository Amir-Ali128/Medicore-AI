from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.routes import lab_ingestion
from app.domain import native_trust_clinical_ai as clinical_bridge
from app.domain import patient_lab_history as history
from app.domain.enums import TrendStatus
from app.domain.trend_engine import TrendEngine
from app.schemas.trend import TrendComparisonInput, TrendResult


def _trusted_row(*, name: str = "HbA1c", value: float = 8.1) -> dict:
    return {
        "raw_parameter_name": name,
        "canonical_name": name,
        "display_name": name,
        "loinc_code": "4548-4" if name == "HbA1c" else "",
        "raw_value": str(value),
        "normalized_value": value,
        "unit": "%",
        "reference_min": 4.0,
        "reference_max": 6.5,
        "reference_text": "4.0-6.5",
        "result_status": "HIGH",
        "validation_status": "VALID",
        "needs_review": False,
        "trusted_for_ai": True,
        "trust_status": "TRUSTED",
        "provenance_contract_version": "medicore-lab-provenance-v1",
    }


def _review_row() -> dict:
    row = _trusted_row(name="Potassium", value=71.0)
    row.update(
        {
            "result_status": "HIGH",
            "validation_status": "WARNING",
            "needs_review": True,
            "trusted_for_ai": False,
            "trust_status": "REVIEW",
        }
    )
    return row


def _envelope() -> dict:
    trusted = _trusted_row()
    review = _review_row()
    return {
        "contract_version": "medicore-native-trust-v1",
        "provenance_contract_version": "medicore-lab-provenance-v1",
        "report_date": "2026-09-08",
        "trusted_count": 1,
        "review_count": 1,
        "processed_row_count": 2,
        "trusted_rows": [trusted],
        "review_rows": [review],
        "all_rows": [trusted, review],
    }


def test_identity_prefers_loinc_and_is_stable_for_names() -> None:
    assert history._identity_code(_trusted_row()) == "LOINC:4548-4"
    assert history._identity_code(
        {"canonical_name": "C-Reactive Protein (CRP)"}
    ) == "NAME:c_reactive_protein_crp"
    assert history._identity_code({"canonical_name": "Üre"}) == "NAME:ure"
    assert history._identity_code({"canonical_name": "İdrar Şekeri"}) == "NAME:idrar_sekeri"


def test_native_trend_metrics_exclude_python_fallback() -> None:
    native = {
        "backend": "native_cpp",
        "test": "HbA1c",
        "parameter_code": "LOINC:4548-4",
        "trend_status": "up",
        "previous_value": 7.3,
        "current_value": 8.1,
        "percentage_difference": 10.96,
        "time_difference_days": 88,
    }
    fallback = {**native, "backend": "python_fallback", "test": "CRP"}

    metrics = clinical_bridge._native_trend_metrics([native, fallback])

    assert len(metrics) == 1
    assert metrics[0]["name"] == "HbA1c longitudinal trend"
    assert metrics[0]["value"] == 10.96


def test_trend_engine_reports_actual_fallback_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = TrendEngine()
    monkeypatch.setattr(engine, "_compare_native", lambda _data: None)

    result, backend = engine.compare_with_backend(
        TrendComparisonInput(
            current_value=Decimal("8.1"),
            previous_value=Decimal("7.3"),
            current_date=date(2026, 9, 8),
            previous_date=date(2026, 6, 12),
        )
    )

    assert backend == "python_fallback"
    assert result.trend_status == TrendStatus.UP


def test_longitudinal_builder_uses_only_trusted_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = SimpleNamespace(
        id=uuid.uuid4(),
        normalized_value=Decimal("7.3"),
        measured_at=date(2026, 6, 12),
    )
    lookups: list[str] = []

    class FakeRepository:
        def __init__(self, _session) -> None:
            pass

        async def latest_previous_match(self, _patient_id, **kwargs):
            lookups.append(kwargs["parameter_code"])
            return previous

    class FakeTrendEngine:
        def compare_with_backend(self, data):
            assert data.current_value == Decimal("8.1")
            assert data.previous_value == Decimal("7.3")
            return (
                TrendResult(
                    parameter_code=data.parameter_code,
                    trend_status=TrendStatus.UP,
                    previous_value=Decimal("7.3"),
                    current_value=Decimal("8.1"),
                    absolute_difference=Decimal("0.8"),
                    percentage_difference=10.9589,
                    time_difference_days=88,
                    confidence=1.0,
                    reason="Value increased.",
                    needs_review=False,
                ),
                "native_cpp",
            )

    monkeypatch.setattr(history, "LabResultRepository", FakeRepository)
    monkeypatch.setattr(history, "TrendEngine", FakeTrendEngine)

    trends = asyncio.run(
        history.build_longitudinal_trends(
            object(),
            patient=SimpleNamespace(id=uuid.uuid4()),
            trust_envelope=_envelope(),
        )
    )

    assert lookups == ["LOINC:4548-4"]
    assert len(trends) == 1
    assert trends[0]["backend"] == "native_cpp"
    assert trends[0]["trend_status"] == "up"
    assert trends[0]["previous_value"] == 7.3
    assert trends[0]["current_value"] == 8.1


def test_missing_current_date_never_consumes_a_previous_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _envelope()
    envelope["report_date"] = None
    lookups = 0

    class FakeRepository:
        def __init__(self, _session) -> None:
            pass

        async def latest_previous_match(self, *_args, **_kwargs):
            nonlocal lookups
            lookups += 1
            raise AssertionError("undated current result must not query previous history")

    class FakeTrendEngine:
        def compare_with_backend(self, data):
            assert data.current_date is None
            assert data.previous_value is None
            return (
                TrendResult(
                    parameter_code=data.parameter_code,
                    trend_status=TrendStatus.NO_PREVIOUS_RESULT,
                    current_value=Decimal("8.1"),
                    confidence=0.0,
                    reason="No previous result available for comparison.",
                ),
                "python_fallback",
            )

    monkeypatch.setattr(history, "LabResultRepository", FakeRepository)
    monkeypatch.setattr(history, "TrendEngine", FakeTrendEngine)

    trends = asyncio.run(
        history.build_longitudinal_trends(
            object(),
            patient=SimpleNamespace(id=uuid.uuid4()),
            trust_envelope=envelope,
        )
    )

    assert lookups == 0
    assert trends[0]["previous_result_id"] is None
    assert trends[0]["trend_status"] == "no_previous_result"


def test_finalize_persists_patient_history_and_passes_trends_to_ai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = _envelope()
    patient = SimpleNamespace(id=uuid.uuid4())
    current_user = SimpleNamespace(id=uuid.uuid4())
    seen: dict = {}

    monkeypatch.setattr(lab_ingestion, "process_canonical_lab_case", lambda case: envelope)

    async def fake_access(session, *, patient_id, current_user):
        seen["patient_id"] = patient_id
        return patient

    async def fake_trends(session, *, patient, trust_envelope):
        return [
            {
                "backend": "native_cpp",
                "test": "HbA1c",
                "parameter_code": "LOINC:4548-4",
                "trend_status": "up",
                "percentage_difference": 10.96,
            }
        ]

    async def fake_ai(trust_envelope, *, longitudinal_trends):
        seen["ai_trends"] = longitudinal_trends
        return {
            "contract_version": "medicore-native-trust-clinical-ai-v1",
            "ai_used": True,
            "longitudinal_trends": longitudinal_trends,
        }

    async def fake_persist(session, **kwargs):
        seen["persist_trends"] = kwargs["longitudinal_trends"]
        return {
            "contract_version": history.PATIENT_LAB_HISTORY_CONTRACT,
            "lab_report_id": str(uuid.uuid4()),
        }

    monkeypatch.setattr(lab_ingestion, "ensure_patient_access", fake_access)
    monkeypatch.setattr(lab_ingestion, "build_longitudinal_trends", fake_trends)
    monkeypatch.setattr(lab_ingestion, "run_native_trust_clinical_pipeline", fake_ai)
    monkeypatch.setattr(lab_ingestion, "persist_patient_lab_case", fake_persist)

    patient_id = uuid.uuid4()
    result = asyncio.run(
        lab_ingestion._finalize_canonical_case(
            {"contract_version": "medicore-canonical-lab-v1"},
            clinical_ai=True,
            patient_id=patient_id,
            session=object(),
            current_user=current_user,
        )
    )

    assert seen["patient_id"] == patient_id
    assert seen["ai_trends"][0]["trend_status"] == "up"
    assert seen["persist_trends"] == seen["ai_trends"]
    assert result["history_contract_version"] == history.PATIENT_LAB_HISTORY_CONTRACT
    assert "patient_history" in result
