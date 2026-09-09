from app.domain.native_lab_direct_ai import (
    _apply_ai_classifications_to_rows,
    _extract_responses_output_text,
    _validate_assessment_shape,
)
from app.domain.openai_lab_clinical_service import OpenAILabClinicalError


def _assessment() -> dict:
    return {
        "headline": "Özet",
        "overview": "Genel değerlendirme",
        "priority_findings": [],
        "systems": [],
        "reassuring_findings": [],
        "priority_actions": [],
        "limitations": [],
        "narrative_tr": "Klinik karar desteği özeti.",
        "lab_classifications": [
            {"test": "Glucose", "status": "HIGH", "reason": "Referans üstünde."}
        ],
    }


def _row(*, status: str = "HIGH") -> dict:
    return {
        "display_name": "Glucose",
        "raw_parameter_name": "Glucose",
        "normalized_value": 105.0,
        "unit": "mg/dL",
        "reference_min": 70.0,
        "reference_max": 100.0,
        "result_status": status,
        "validation_status": "VALID",
        "needs_review": False,
        "reason": "Native kaynak referans karşılaştırması.",
        "rule_applied": "native_value_above_max" if status == "HIGH" else "native_value_within_reference",
        "classification_confidence": 0.98,
    }


def test_extract_responses_output_text_from_message_content() -> None:
    payload = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"headline":"ok"}',
                    }
                ],
            }
        ]
    }

    assert _extract_responses_output_text(payload) == '{"headline":"ok"}'


def test_extract_responses_output_text_prefers_direct_field() -> None:
    payload = {
        "output_text": " direct ",
        "output": [
            {
                "content": [
                    {"type": "output_text", "text": "nested"},
                ]
            }
        ],
    }

    assert _extract_responses_output_text(payload) == "direct"


def test_validate_assessment_shape_keeps_structured_classifications() -> None:
    value = _assessment()
    validated = _validate_assessment_shape(value)

    assert validated["headline"] == "Özet"
    assert validated["lab_classifications"][0]["status"] == "HIGH"


def test_validate_assessment_shape_rejects_missing_required_fields() -> None:
    try:
        _validate_assessment_shape({"headline": "eksik"})
    except OpenAILabClinicalError as exc:
        assert "zorunlu alanlar eksik" in str(exc)
    else:
        raise AssertionError("Eksik AI assessment şeması reddedilmeliydi")


def test_ai_classification_becomes_primary_status_when_it_matches_native() -> None:
    rows = [_row(status="HIGH")]
    assessment = _assessment()

    assert _apply_ai_classifications_to_rows(rows, assessment) is True
    assert rows[0]["result_status"] == "HIGH"
    assert rows[0]["native_result_status"] == "HIGH"
    assert rows[0]["ai_result_status"] == "HIGH"
    assert rows[0]["needs_review"] is False
    assert rows[0]["rule_applied"] == "native_cpp_direct_ai_classification"
    assert "Native C++ ön sınıflaması: HIGH" in rows[0]["reason"]


def test_cpp_ai_disagreement_forces_review_and_zero_classification_confidence() -> None:
    rows = [_row(status="NORMAL")]
    assessment = _assessment()

    assert _apply_ai_classifications_to_rows(rows, assessment) is True
    assert rows[0]["result_status"] == "HIGH"
    assert rows[0]["native_result_status"] == "NORMAL"
    assert rows[0]["ai_result_status"] == "HIGH"
    assert rows[0]["needs_review"] is True
    assert rows[0]["classification_confidence"] == 0.0
    assert rows[0]["rule_applied"] == "native_cpp_direct_ai_disagreement"
    assert "farklı" in rows[0]["reason"]


def test_undetermined_ai_status_routes_row_to_review() -> None:
    rows = [_row(status="HIGH")]
    assessment = _assessment()
    assessment["lab_classifications"][0]["status"] = "UNDETERMINED"

    assert _apply_ai_classifications_to_rows(rows, assessment) is True
    assert rows[0]["result_status"] == "NEEDS_REVIEW"
    assert rows[0]["needs_review"] is True
    assert rows[0]["classification_confidence"] == 0.0


def test_name_mismatch_is_transactional_and_keeps_native_status() -> None:
    rows = [_row(status="HIGH")]
    assessment = _assessment()
    assessment["lab_classifications"][0]["test"] = "Potassium"

    assert _apply_ai_classifications_to_rows(rows, assessment) is False
    assert rows[0]["result_status"] == "HIGH"
    assert "native_result_status" not in rows[0]
    assert any("uyuşmadı" in item for item in assessment["limitations"])
