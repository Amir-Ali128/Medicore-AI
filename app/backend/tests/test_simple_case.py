from app.domain.simple_case import normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest


def test_age_specific_reference_is_selected_without_classification():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 12, "sex": "male"},
            "labs": [
                {
                    "test_name": "ALP",
                    "value": 210,
                    "unit": "U/L",
                    "source_references": [
                        {
                            "text": "Adult: 40-130 U/L",
                            "minimum": 40,
                            "maximum": 130,
                            "unit": "U/L",
                            "age_min": 18,
                        },
                        {
                            "text": "Age 10-17: 80-350 U/L",
                            "minimum": 80,
                            "maximum": 350,
                            "unit": "U/L",
                            "age_min": 10,
                            "age_max": 17,
                        },
                    ],
                }
            ],
            "reports": [
                {
                    "report_type": "ECG",
                    "findings": "Sinus rhythm.",
                }
            ],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text == "Age 10-17: 80-350 U/L"
    assert result.labs[0].reference_source == "report_age_sex_match"
    dumped = result.model_dump()
    assert "classification" not in dumped["labs"][0]
    assert "status" not in dumped["labs"][0]


def test_source_reference_is_preserved_as_is():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 45, "sex": "female"},
            "labs": [
                {
                    "test_name": "TSH",
                    "value": 2.1,
                    "unit": "mIU/L",
                    "source_reference": "0.27 - 4.20",
                }
            ],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text == "0.27 - 4.20"
    assert result.labs[0].reference_source == "report"


def test_missing_reference_creates_warning_but_does_not_invent_one():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 30, "sex": "unknown"},
            "labs": [{"test_name": "Example", "value": 10}],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text is None
    assert result.labs[0].reference_source == "missing"
    assert result.warnings
