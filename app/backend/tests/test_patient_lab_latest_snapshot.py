from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.api.routes.patient_lab_history import _latest_lab_snapshot


def _row(*, status: str, value: str, name: str, needs_review: bool = False):
    return SimpleNamespace(
        id=uuid.uuid4(),
        result_status=SimpleNamespace(value=status),
        needs_review=needs_review,
        canonical_name=name,
        raw_parameter_name=name,
        parameter_code=f"NAME:{name.lower()}",
        raw_value=value,
        normalized_value=Decimal(value),
        unit="mg/dL",
        reference_min=Decimal("10"),
        reference_max=Decimal("20"),
        metadata_json={"reference_text": "10 - 20"},
        reason=None,
        classification_confidence=1.0,
        measured_at=date(2026, 9, 8),
        parameter_id=None,
        trend_status=SimpleNamespace(value="no_previous_result"),
        alias_confidence=1.0,
        reference_confidence=1.0,
        trend_confidence=1.0,
    )


def test_latest_snapshot_restores_universal_and_clinical_brain_shapes() -> None:
    patient_id = uuid.uuid4()
    report_id = uuid.uuid4()
    report = SimpleNamespace(
        id=report_id,
        patient_id=patient_id,
        source_type="enabiz_pdf",
        file_name="labs.pdf",
        report_date=date(2026, 9, 8),
        created_at=datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc),
        metadata_json={
            "trusted_count": 2,
            "review_count": 1,
            "source": {"file_name": "labs.pdf"},
            "longitudinal_trends": [],
            "clinical_pipeline": {
                "ai_attempted": True,
                "ai_used": True,
                "clinical_assessment": {
                    "headline": "Öncelikli bulgular var",
                    "overview": "Kaydedilmiş klinik özet.",
                },
            },
        },
    )
    rows = [
        _row(status="high", value="25", name="Glukoz"),
        _row(status="normal", value="15", name="Sodyum"),
        _row(status="needs_review", value="18", name="Belirsiz", needs_review=True),
    ]

    snapshot = _latest_lab_snapshot(report, rows)

    assert snapshot["lab_report_id"] == str(report_id)
    assert snapshot["patient_id"] == str(patient_id)
    assert snapshot["processed_row_count"] == 3
    assert len(snapshot["trusted_rows"]) == 2
    assert len(snapshot["review_rows"]) == 1
    assert snapshot["trusted_rows"][0]["result_status"] == "HIGH"
    assert snapshot["results"][0]["result_status"] == "high"
    assert snapshot["clinical_assessment"]["headline"] == "Öncelikli bulgular var"
    assert snapshot["patient_history"]["lab_report_id"] == str(report_id)
