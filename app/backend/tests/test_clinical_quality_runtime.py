from datetime import date
from types import SimpleNamespace

import pytest

from app.domain import clinical_quality_runtime as quality


def _result(
    name: str,
    value: float | None,
    *,
    raw_value: str | None = None,
    unit: str = "",
    reference_max: float | None = None,
    status: str = "normal",
    measured_at: date = date(2025, 12, 17),
):
    return SimpleNamespace(
        raw_parameter_name=name,
        canonical_name=name,
        parameter_code=name,
        normalized_value=value,
        raw_value=raw_value if raw_value is not None else (str(value) if value is not None else None),
        unit=unit,
        reference_min=None,
        reference_max=reference_max,
        result_status=status,
        measured_at=measured_at,
        rule_applied="test_rule",
    )


def test_deterministic_scores_are_calculated_from_raw_values() -> None:
    results = [
        _result("AST", 45, unit="U/L", reference_max=40, status="high"),
        _result("ALT", 55, unit="U/L", reference_max=41, status="high"),
        _result("PLT", 110, unit="x10^9/L", status="low"),
        _result("Demir", 28, unit="ug/dL", status="low"),
        _result("Doymamis Demir Baglama Kapasitesi", 413, unit="ug/dL", status="high"),
        _result("Total Kolesterol", 180, unit="mg/dL"),
        _result("HDL", 30, unit="mg/dL", status="low"),
    ]

    scores = {item["code"]: item for item in quality._derive_scores(results, 50)}

    assert scores["FIB4"]["value"] == pytest.approx(2.758, abs=0.001)
    assert scores["FIB4"]["band"] == "high"
    assert scores["APRI"]["value"] == pytest.approx(1.023, abs=0.001)
    assert scores["APRI"]["band"] == "high"
    assert scores["AST_ALT_RATIO"]["value"] == pytest.approx(0.818, abs=0.001)
    assert scores["TRANSFERRIN_SATURATION"]["value"] == pytest.approx(6.349, abs=0.001)
    assert scores["TRANSFERRIN_SATURATION"]["band"] == "low"
    assert scores["TOTAL_HDL_RATIO"]["value"] == pytest.approx(6.0, abs=0.001)


def test_missing_score_input_is_not_guessed() -> None:
    results = [
        _result("AST", 45, reference_max=40),
        _result("ALT", 55),
        _result("PLT", 110),
    ]

    scores = {item["code"]: item for item in quality._derive_scores(results, None)}

    assert scores["FIB4"]["status"] == "unavailable"
    assert scores["FIB4"]["value"] is None
    assert "yaş" in scores["FIB4"]["missing"]


def test_serum_urine_glucose_unexpected_combination_is_flagged_without_diagnosis() -> None:
    results = [
        _result("Glukoz", 146, unit="mg/dL", status="high"),
        _result(
            "İdrar · Glukoz",
            4,
            raw_value="++++",
            unit="",
            status="high",
        ),
    ]

    checks = quality._cross_checks(results)
    codes = {item["code"] for item in checks}

    assert "SERUM_URINE_GLUCOSE_UNEXPECTED" in codes
    check = next(item for item in checks if item["code"] == "SERUM_URINE_GLUCOSE_UNEXPECTED")
    assert "tanı" in check["message"].lower()


def test_temporal_context_warns_over_ninety_days() -> None:
    results = [_result("AST", 45, measured_at=date(2025, 12, 17))]
    context = quality._temporal_context(
        results,
        {"source_dates": {"ultrasound": "2026-09-01"}},
    )

    assert context["warning"] is True
    assert context["gap_days"] == 258
    assert context["flag"] == "TEMPORAL_GAP_GT_90_DAYS"


def test_imaging_recommendation_is_moved_to_already_performed() -> None:
    metadata = {
        "performed_studies": [
            {
                "canonical_code": "liver_elastography",
                "name": "Karaciğer elastografisi",
                "date": "2026-09-01",
                "source_report_id": "r1",
            }
        ],
        "recommended_laboratory_tests": [],
        "recommended_imaging_tests": [
            {
                "name": "Karaciğer elastografisi",
                "rationale": "Fibrozis değerlendirmesi",
                "priority": "routine",
            },
            {
                "name": "Kontrastlı abdomen BT/MR",
                "rationale": "Gerekirse ileri değerlendirme",
                "priority": "routine",
            },
        ],
    }

    _, kept_imaging, already = quality._filter_recommendations(metadata, [])

    assert [item["name"] for item in kept_imaging] == ["Kontrastlı abdomen BT/MR"]
    assert [item["name"] for item in already] == ["Karaciğer elastografisi"]
    assert already[0]["performed_date"] == "2026-09-01"
