from app.domain.native_lab_direct_ai import (
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
