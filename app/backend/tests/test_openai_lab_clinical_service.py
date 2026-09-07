from app.domain.openai_lab_clinical_service import (
    build_fallback_clinical_assessment,
    partition_rows_for_ai,
)
from app.schemas.lab_analysis import LabClinicalAssessmentOutput


def test_fallback_clinical_assessment_preserves_native_status_and_metrics() -> None:
    rows = [
        {
            "display_name": "HbA1c",
            "normalized_value": 9.4,
            "unit": "%",
            "result_status": "HIGH",
            "needs_review": False,
            "reason": "Değer kaynak rapordaki referans üst sınırının üzerinde.",
        },
        {
            "display_name": "AST",
            "normalized_value": 15,
            "unit": "U/L",
            "result_status": "NORMAL",
            "needs_review": False,
            "reason": "Değer kaynak rapordaki mevcut referans sınırları içinde.",
        },
    ]
    metrics = [
        {
            "code": "estimated_average_glucose",
            "name": "Estimated Average Glucose",
            "value": 223.08,
            "unit": "mg/dL",
            "formula": "28.7 × HbA1c - 46.7",
            "input_labels": ["HbA1c"],
            "note": "Calculated estimate.",
        }
    ]

    payload = build_fallback_clinical_assessment(rows=rows, derived_metrics=metrics)
    validated = LabClinicalAssessmentOutput.model_validate(payload)

    assert validated.synthesis_source == "deterministic_fallback"
    assert "HbA1c" in validated.narrative_tr
    assert "223.08" in validated.narrative_tr
    assert validated.priority_findings[0].severity == "moderate"
    assert validated.reassuring_findings == ["AST: 15 U/L"]


def test_partition_rows_for_ai_keeps_only_cpp_valid_rows_as_trusted_facts() -> None:
    rows = [
        {
            "display_name": "HbA1c",
            "normalized_value": 9.4,
            "unit": "%",
            "result_status": "HIGH",
            "validation_status": "VALID",
            "needs_review": False,
        },
        {
            "display_name": "Potassium",
            "normalized_value": 71.0,
            "unit": "mmol/L",
            "result_status": "HIGH",
            "validation_status": "WARNING",
            "needs_review": True,
            "reason": "Çıkarım güveni düşük.",
        },
        {
            "display_name": "Broken Range",
            "normalized_value": 50.0,
            "unit": "mg/dL",
            "result_status": "NEEDS_REVIEW",
            "validation_status": "INVALID",
            "needs_review": True,
        },
    ]

    trusted, review = partition_rows_for_ai(rows)

    assert [row["test"] for row in trusted] == ["HbA1c"]
    assert {row["test"] for row in review} == {"Potassium", "Broken Range"}
    assert all(row["validation_status"] != "VALID" for row in review)


def test_fallback_does_not_promote_warning_abnormal_row_to_clinical_finding() -> None:
    rows = [
        {
            "display_name": "Potassium",
            "normalized_value": 71.0,
            "unit": "mmol/L",
            "result_status": "HIGH",
            "validation_status": "WARNING",
            "needs_review": True,
            "reason": "Kaynak doğrulaması gerekiyor.",
        }
    ]

    payload = build_fallback_clinical_assessment(rows=rows, derived_metrics=[])
    validated = LabClinicalAssessmentOutput.model_validate(payload)

    assert validated.priority_findings == []
    assert "1 sonuç C++ doğrulama katmanı" in validated.narrative_tr
    assert any("klinik kanıta dahil edilmedi" in item for item in validated.limitations)


def test_legacy_rows_remain_compatible_without_validation_status() -> None:
    rows = [
        {
            "display_name": "CRP",
            "normalized_value": 8.0,
            "unit": "mg/L",
            "result_status": "HIGH",
            "needs_review": False,
        }
    ]

    trusted, review = partition_rows_for_ai(rows)

    assert len(trusted) == 1
    assert review == []
    assert trusted[0]["validation_status"] == "VALID"
