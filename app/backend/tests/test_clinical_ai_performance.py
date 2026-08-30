import json
from types import SimpleNamespace

from app.domain.claude_clinical_hypothesis_service import (
    ClaudeClinicalHypothesisService,
)
from app.domain.enums import ResultStatus
from app.schemas.clinical_copilot import ClinicalHypothesisGenerationRequest


def test_compact_mode_defaults_to_one_summary_and_120_tokens() -> None:
    request = ClinicalHypothesisGenerationRequest()

    assert request.max_hypotheses == 1
    assert ClaudeClinicalHypothesisService._output_token_budget(1) == 120
    assert ClaudeClinicalHypothesisService._output_token_budget(10) == 120


def test_backend_builds_lab_flag_without_sending_value() -> None:
    result = SimpleNamespace(
        parameter_code="GLUCOSE",
        canonical_name="Glucose",
        raw_parameter_name="AKS",
        normalized_value=110,
        reference_min=60,
        reference_max=100,
        result_status=ResultStatus.HIGH,
        needs_review=False,
    )

    flags = ClaudeClinicalHypothesisService._lab_flags([result])
    prompt = ClaudeClinicalHypothesisService._build_user_prompt(
        ["1 aydır omuz ağrısı"], flags, "tr"
    )
    payload = json.loads(prompt)

    assert flags == ["GLUCOSE_HIGH"]
    assert payload == {
        "symptoms": ["1 aydır omuz ağrısı"],
        "flags": ["GLUCOSE_HIGH"],
        "language": "tr",
    }
    assert "110" not in prompt
    assert "60" not in prompt
    assert "100" not in prompt


def test_normal_lab_does_not_pass_ai_gate() -> None:
    normal = SimpleNamespace(
        result_status=ResultStatus.NORMAL,
        needs_review=False,
    )

    selected = ClaudeClinicalHypothesisService._review_results(
        [normal], ClinicalHypothesisGenerationRequest()
    )

    assert selected == []


def test_backend_converts_vitals_to_routing_flags() -> None:
    flags = ClaudeClinicalHypothesisService._vital_flags(
        {
            "blood_pressure_systolic": 145,
            "blood_pressure_diastolic": 92,
            "pulse_bpm": 80,
            "temperature_c": 36.8,
            "respiratory_rate": 16,
            "oxygen_saturation_percent": 97,
        }
    )

    assert flags == ["BLOOD_PRESSURE_HIGH"]


def test_compact_output_is_bounded() -> None:
    risk, summary = ClaudeClinicalHypothesisService._parse_compact_output(
        {"risk": 2, "summary": "x" * 500},
        flags=["GLUCOSE_HIGH"],
        language="tr",
    )

    assert risk == 2
    assert len(summary) == 120
