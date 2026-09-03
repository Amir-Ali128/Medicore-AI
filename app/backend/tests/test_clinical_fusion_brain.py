from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.clinical_fusion_brain import evaluate_clinical_fusion
from app.schemas.clinical_fusion import ClinicalFusionRequest


def _request(*, evidence: list[dict], source_availability: dict[str, bool] | None = None):
    return ClinicalFusionRequest.model_validate(
        {
            "language": "tr",
            "candidates": [
                {
                    "code": "acute_cholecystitis",
                    "display_name": "Akut kolesistit olasılığı",
                    "category": "hepatobiliary",
                },
                {
                    "code": "alternative",
                    "display_name": "Alternatif açıklama",
                },
            ],
            "evidence": evidence,
            "source_availability": source_availability or {},
        }
    )


def _ev(
    evidence_id: str,
    *,
    source_type: str,
    source_name: str,
    polarity: str = "support",
    finding_code: str | None = None,
    dependency_group: str | None = None,
    hypothesis: str = "acute_cholecystitis",
    confidence: float = 1.0,
    strength: float = 1.0,
    severity: str = "moderate",
    metadata: dict | None = None,
):
    return {
        "id": evidence_id,
        "finding_code": finding_code or evidence_id,
        "label": evidence_id.replace("_", " "),
        "source_type": source_type,
        "source_name": source_name,
        "dependency_group": dependency_group,
        "polarity": polarity,
        "strength": strength,
        "confidence": confidence,
        "severity": severity,
        "hypothesis_codes": [hypothesis],
        "metadata": metadata or {},
    }


def test_cross_modal_support_can_reach_high_compatibility_without_becoming_probability() -> None:
    evidence = [
        _ev(
            "ruq_pain",
            source_type="clinical",
            source_name="clinical-intake",
            dependency_group="clinical-case",
        ),
        _ev(
            "murphy",
            source_type="clinical",
            source_name="physical-exam",
            dependency_group="clinical-case",
        ),
        _ev(
            "crp_high",
            source_type="laboratory",
            source_name="lab-report",
            dependency_group="laboratory",
        ),
        _ev(
            "wall_thickening",
            source_type="imaging",
            source_name="ultrasound",
            dependency_group="study-us-1",
        ),
    ]
    for index, provider in enumerate(("claude", "openai", "gemini", "reader4"), start=1):
        evidence.append(
            _ev(
                f"ai_wall_{index}",
                source_type="ai_reader",
                source_name=provider,
                finding_code="wall_thickening",
                dependency_group="study-us-1",
                confidence=0.9,
            )
        )

    result = evaluate_clinical_fusion(_request(evidence=evidence))
    top = result.candidates[0]

    assert top.code == "acute_cholecystitis"
    assert top.compatibility_level in {"high", "very_high"}
    assert top.support_group_count == 3
    assert top.estimated_probability is None
    assert top.score_type == "deterministic_evidence_compatibility"
    assert result.core_source_coverage == {
        "clinical": True,
        "laboratory": True,
        "imaging": True,
    }
    assert result.data_completeness_percent == 100
    assert result.ai_reader_available is True


def test_four_ai_readers_on_same_image_are_one_dependency_group() -> None:
    evidence = [
        _ev(
            f"ai_{index}",
            source_type="ai_reader",
            source_name=provider,
            finding_code="possible_pneumothorax",
            dependency_group="cxr-study-42",
            confidence=0.95,
        )
        for index, provider in enumerate(("claude", "openai", "gemini", "reader4"), start=1)
    ]

    result = evaluate_clinical_fusion(_request(evidence=evidence))
    top = next(item for item in result.candidates if item.code == "acute_cholecystitis")

    assert top.support_group_count == 1
    assert top.compatibility_level in {"low", "moderate"}
    assert top.compatibility_level not in {"high", "very_high"}
    assert any("AI" in limitation for limitation in top.limitations)


def test_positive_and_negative_evidence_are_not_merged_and_raise_conflict() -> None:
    evidence = [
        _ev(
            "imaging_positive",
            source_type="imaging",
            source_name="radiology-primary",
            finding_code="pneumothorax",
            dependency_group="cxr-1",
            polarity="support",
        ),
        _ev(
            "openai_negative",
            source_type="ai_reader",
            source_name="openai",
            finding_code="pneumothorax",
            dependency_group="cxr-1",
            polarity="oppose",
        ),
    ]

    result = evaluate_clinical_fusion(_request(evidence=evidence))
    candidate = next(item for item in result.candidates if item.code == "acute_cholecystitis")

    assert candidate.supporting_evidence_ids == ["imaging_positive"]
    assert candidate.contradicting_evidence_ids == ["openai_negative"]
    kinds = {item.kind for item in result.disagreements}
    assert "cross_source_conflict" in kinds
    assert "ai_vs_primary_evidence" in kinds


def test_ai_model_disagreement_is_explicit() -> None:
    evidence = [
        _ev(
            "claude_support",
            source_type="ai_reader",
            source_name="claude",
            dependency_group="study-7",
            polarity="support",
        ),
        _ev(
            "openai_oppose",
            source_type="ai_reader",
            source_name="openai",
            dependency_group="study-7",
            polarity="oppose",
        ),
    ]

    result = evaluate_clinical_fusion(_request(evidence=evidence))
    assert "ai_model_disagreement" in {item.kind for item in result.disagreements}


def test_uncertain_evidence_does_not_increase_support_score() -> None:
    uncertain_only = _request(
        evidence=[
            _ev(
                "diaphragm_not_in_field",
                source_type="ai_reader",
                source_name="openai",
                polarity="uncertain",
                dependency_group="cxr-9",
            )
        ]
    )
    result = evaluate_clinical_fusion(uncertain_only)
    candidate = next(item for item in result.candidates if item.code == "acute_cholecystitis")

    assert candidate.compatibility_score == 0
    assert candidate.support_group_count == 0
    assert candidate.uncertain_evidence_ids == ["diaphragm_not_in_field"]


def test_critical_signal_surfaces_even_without_candidate_mapping() -> None:
    payload = _request(
        evidence=[
            {
                "id": "oxygen_critical",
                "finding_code": "oxygen_saturation_critical",
                "label": "Oxygen saturation critical review",
                "source_type": "vital",
                "source_name": "triage",
                "polarity": "support",
                "severity": "critical",
                "hypothesis_codes": [],
            }
        ]
    )
    result = evaluate_clinical_fusion(payload)
    assert result.critical_signal_ids == ["oxygen_critical"]


def test_explicit_source_availability_false_is_authoritative() -> None:
    payload = _request(
        evidence=[
            _ev(
                "crp_high",
                source_type="laboratory",
                source_name="lab",
            )
        ],
        source_availability={"laboratory": False},
    )
    result = evaluate_clinical_fusion(payload)
    assert result.core_source_coverage["laboratory"] is False
    assert result.core_source_count == 0
    assert result.data_completeness_percent == 0


def test_unknown_hypothesis_reference_is_reported_not_promoted() -> None:
    payload = _request(
        evidence=[
            _ev(
                "unknown_link",
                source_type="laboratory",
                source_name="lab",
                hypothesis="not_supplied_candidate",
            )
        ]
    )
    result = evaluate_clinical_fusion(payload)
    assert result.unmapped_hypothesis_codes == ["not_supplied_candidate"]
    assert result.warnings
    assert all(item.compatibility_score == 0 for item in result.candidates)


def test_duplicate_candidate_codes_and_evidence_ids_fail_validation() -> None:
    with pytest.raises(ValidationError):
        ClinicalFusionRequest.model_validate(
            {
                "candidates": [
                    {"code": "same", "display_name": "A"},
                    {"code": "SAME", "display_name": "B"},
                ],
                "evidence": [],
            }
        )

    with pytest.raises(ValidationError):
        ClinicalFusionRequest.model_validate(
            {
                "candidates": [{"code": "a", "display_name": "A"}],
                "evidence": [
                    _ev(
                        "dup",
                        source_type="clinical",
                        source_name="one",
                        hypothesis="a",
                    ),
                    _ev(
                        "DUP",
                        source_type="laboratory",
                        source_name="two",
                        hypothesis="a",
                    ),
                ],
            }
        )
