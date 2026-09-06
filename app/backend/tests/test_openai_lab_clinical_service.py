from app.domain.openai_lab_clinical_service import build_fallback_clinical_assessment
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
