from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.clinical_fusion_case_adapter import evaluate_clinical_case_fusion
from app.schemas.clinical_fusion_case import ClinicalFusionCaseRequest


def _base(**overrides):
    payload = {
        "case_id": "case-42",
        "language": "tr",
        "candidates": [
            {
                "code": "pneumothorax",
                "display_name": "Pnömotoraks olasılığı",
                "category": "thoracic",
            },
            {
                "code": "alternative",
                "display_name": "Alternatif açıklama",
            },
        ],
        "clinical_signals": [],
        "laboratory_signals": [],
        "imaging_signals": [],
        "ai_reader_signals": [],
        "onnx_runs": [],
    }
    payload.update(overrides)
    return ClinicalFusionCaseRequest.model_validate(payload)


def test_full_case_is_normalized_into_three_core_source_groups() -> None:
    request = _base(
        clinical_signals=[
            {
                "id": "dyspnea",
                "kind": "symptom",
                "finding_code": "acute_dyspnea",
                "label": "Ani dispne",
                "hypothesis_codes": ["pneumothorax"],
            }
        ],
        laboratory_signals=[
            {
                "id": "oxygen",
                "finding_code": "hypoxemia_marker",
                "label": "Hipoksemi ile uyumlu laboratuvar bulgusu",
                "report_id": "lab-1",
                "hypothesis_codes": ["pneumothorax"],
                "confidence": 0.8,
            }
        ],
        imaging_signals=[
            {
                "id": "pleural-line",
                "study_id": "cxr-1",
                "kind": "primary",
                "finding_code": "pleural_line",
                "label": "Plevral çizgi bulgusu",
                "hypothesis_codes": ["pneumothorax"],
                "location": {"bbox_xyxy": [120, 30, 420, 390]},
            }
        ],
        ai_reader_signals=[
            {
                "id": "openai-read",
                "study_id": "cxr-1",
                "provider": "openai",
                "model_id": "vision-model",
                "finding_code": "pneumothorax",
                "label": "Pnömotoraks lehine görünüm",
                "hypothesis_codes": ["pneumothorax"],
                "confidence": 0.9,
            }
        ],
        onnx_runs=[
            {
                "run_id": "onnx-run-1",
                "study_id": "cxr-1",
                "model_id": "chest-xray-net",
                "model_version": "1.2.0",
                "findings": [
                    {
                        "label": "pneumothorax",
                        "score": 0.91,
                        "threshold": 0.65,
                        "above_threshold": True,
                    }
                ],
                "hypothesis_map": {"pneumothorax": ["pneumothorax"]},
                "location_by_label": {
                    "pneumothorax": {"bbox_xyxy": [118, 28, 425, 395]}
                },
            }
        ],
    )

    result = evaluate_clinical_case_fusion(request)
    top = result.fusion.candidates[0]

    assert top.code == "pneumothorax"
    assert top.support_group_count == 3
    assert top.compatibility_level in {"high", "very_high"}
    assert top.estimated_probability is None
    assert result.fusion.core_source_coverage == {
        "clinical": True,
        "laboratory": True,
        "imaging": True,
    }
    assert result.fusion.data_completeness_percent == 100
    assert result.fusion.ai_reader_available is True
    assert result.source_evidence_counts["ai_detector"] == 1
    assert result.source_evidence_counts["ai_reader"] == 1
    assert any(node.kind == "dependency_group" for node in result.graph_nodes)
    assert any(edge.relation == "supports" for edge in result.graph_edges)


def test_all_image_models_from_same_study_remain_one_dependency_group() -> None:
    request = _base(
        ai_reader_signals=[
            {
                "id": "reader-1",
                "study_id": "cxr-9",
                "provider": "claude",
                "finding_code": "pneumothorax",
                "label": "possible pneumothorax",
                "hypothesis_codes": ["pneumothorax"],
                "confidence": 0.95,
            },
            {
                "id": "reader-2",
                "study_id": "cxr-9",
                "provider": "openai",
                "finding_code": "pneumothorax",
                "label": "possible pneumothorax",
                "hypothesis_codes": ["pneumothorax"],
                "confidence": 0.95,
            },
        ],
        onnx_runs=[
            {
                "run_id": "run-9",
                "study_id": "cxr-9",
                "model_id": "xray-net",
                "findings": [
                    {
                        "label": "pneumothorax",
                        "score": 0.96,
                        "threshold": 0.60,
                        "above_threshold": True,
                    }
                ],
                "hypothesis_map": {"pneumothorax": ["pneumothorax"]},
            }
        ],
    )

    result = evaluate_clinical_case_fusion(request)
    candidate = next(
        item for item in result.fusion.candidates if item.code == "pneumothorax"
    )
    assert candidate.support_group_count == 1
    assert candidate.compatibility_level not in {"high", "very_high"}


def test_below_threshold_onnx_score_is_uncertain_not_negative() -> None:
    request = _base(
        onnx_runs=[
            {
                "run_id": "run-low",
                "study_id": "cxr-low",
                "model_id": "xray-net",
                "findings": [
                    {
                        "label": "pneumothorax",
                        "score": 0.20,
                        "threshold": 0.65,
                        "above_threshold": False,
                    }
                ],
                "hypothesis_map": {"pneumothorax": ["pneumothorax"]},
            }
        ]
    )

    result = evaluate_clinical_case_fusion(request)
    candidate = next(
        item for item in result.fusion.candidates if item.code == "pneumothorax"
    )
    assert candidate.supporting_evidence_ids == []
    assert candidate.contradicting_evidence_ids == []
    assert len(candidate.uncertain_evidence_ids) == 1
    assert candidate.compatibility_score == 0


def test_onnx_score_is_preserved_as_model_score_not_probability() -> None:
    request = _base(
        onnx_runs=[
            {
                "run_id": "run-score",
                "study_id": "cxr-score",
                "model_id": "xray-net",
                "findings": [
                    {
                        "label": "pneumothorax",
                        "score": 0.87,
                        "threshold": 0.60,
                        "above_threshold": True,
                    }
                ],
                "hypothesis_map": {"pneumothorax": ["pneumothorax"]},
            }
        ]
    )

    result = evaluate_clinical_case_fusion(request)
    evidence = result.normalized_evidence[0]
    assert evidence.value == pytest.approx(0.87)
    assert evidence.metadata["model_score"] == pytest.approx(0.87)
    assert evidence.metadata["score_semantics"] == "model_score_not_disease_probability"
    assert result.fusion.candidates[0].estimated_probability is None


def test_above_threshold_unmapped_onnx_finding_is_not_silently_promoted() -> None:
    request = _base(
        onnx_runs=[
            {
                "run_id": "run-unmapped",
                "study_id": "cxr-unmapped",
                "model_id": "xray-net",
                "findings": [
                    {
                        "label": "pleural_effusion",
                        "score": 0.90,
                        "threshold": 0.50,
                        "above_threshold": True,
                    }
                ],
                "hypothesis_map": {},
            }
        ]
    )

    result = evaluate_clinical_case_fusion(request)
    assert result.adapter_warnings
    assert "no explicit hypothesis mapping" in result.adapter_warnings[0]
    assert all(item.compatibility_score == 0 for item in result.fusion.candidates)


def test_critical_signal_surfaces_even_without_candidate_link() -> None:
    request = _base(
        clinical_signals=[
            {
                "id": "critical-vital",
                "kind": "vital",
                "finding_code": "critical_vital",
                "label": "Kritik vital bulgu",
                "severity": "critical",
                "hypothesis_codes": [],
            }
        ]
    )
    result = evaluate_clinical_case_fusion(request)
    assert result.fusion.critical_signal_ids == ["critical-vital"]
    assert result.review_priority == "critical"


def test_explicit_source_availability_false_remains_authoritative() -> None:
    request = _base(
        laboratory_signals=[
            {
                "id": "lab-one",
                "finding_code": "lab_one",
                "label": "Lab one",
                "hypothesis_codes": ["pneumothorax"],
            }
        ],
        source_availability={"laboratory": False},
    )
    result = evaluate_clinical_case_fusion(request)
    assert result.fusion.core_source_coverage["laboratory"] is False


def test_ai_primary_conflict_is_exposed_for_review() -> None:
    request = _base(
        imaging_signals=[
            {
                "id": "primary-positive",
                "study_id": "cxr-conflict",
                "kind": "primary",
                "finding_code": "pneumothorax",
                "label": "Primary finding supports pneumothorax",
                "polarity": "support",
                "hypothesis_codes": ["pneumothorax"],
            }
        ],
        ai_reader_signals=[
            {
                "id": "reader-negative",
                "study_id": "cxr-conflict",
                "provider": "openai",
                "finding_code": "pneumothorax",
                "label": "Reader does not support pneumothorax",
                "polarity": "oppose",
                "hypothesis_codes": ["pneumothorax"],
            }
        ],
    )
    result = evaluate_clinical_case_fusion(request)
    assert result.needs_conflict_review is True
    assert "ai_vs_primary_evidence" in {
        item.kind for item in result.fusion.disagreements
    }


def test_duplicate_direct_signal_ids_fail_case_validation() -> None:
    with pytest.raises(ValidationError):
        _base(
            clinical_signals=[
                {
                    "id": "dup",
                    "kind": "symptom",
                    "finding_code": "a",
                    "label": "A",
                }
            ],
            laboratory_signals=[
                {
                    "id": "DUP",
                    "finding_code": "b",
                    "label": "B",
                }
            ],
        )


def test_duplicate_candidate_codes_fail_case_validation() -> None:
    with pytest.raises(ValidationError):
        _base(
            candidates=[
                {"code": "same", "display_name": "A"},
                {"code": "SAME", "display_name": "B"},
            ]
        )
