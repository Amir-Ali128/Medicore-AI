from __future__ import annotations

import asyncio

import pytest

from app.domain import canonical_native_trust as trust
from app.domain import native_trust_clinical_ai as clinical_bridge
from app.domain.canonical_lab_model import CANONICAL_ROW_CONTRACT
from app.domain.native_lab_engine import NativeLabUnavailable
from app.domain.openai_lab_clinical_service import OpenAILabClinicalError
from app.domain.universal_lab_ingestion import ingest_manual_payload


def _canonical_case(*, confidence: float = 1.0) -> dict:
    return ingest_manual_payload(
        labs=[
            {
                "raw_parameter_name": "Potassium",
                "canonical_name": "Potassium",
                "raw_value": "4.3",
                "normalized_value": 4.3,
                "raw_unit": "mmol/L",
                "unit": "mmol/L",
                "reference_min": 3.5,
                "reference_max": 5.1,
                "reference_text": "3.5-5.1",
                "confidence": confidence,
            }
        ],
        patient_age=41,
        patient_sex="F",
        report_date="2026-09-08",
        source_record_id="manual-42",
    )


def _native_row(source: dict, *, validation: str = "VALID", needs_review: bool = False) -> dict:
    return {
        **source,
        "display_name": source.get("canonical_name") or source.get("raw_parameter_name"),
        "extraction_confidence": source.get("confidence", 1.0),
        "result_status": "NORMAL",
        "validation_status": validation,
        "needs_review": needs_review,
        "reason": "deterministic comparison complete",
        "rule_applied": "native_value_within_reference",
        "classification_confidence": 1.0 if validation == "VALID" else 0.5,
        "contract_version": trust.LAB_NATIVE_CONTRACT,
        "validation_contract_version": trust.LAB_VALIDATION_CONTRACT,
        "provenance_contract_version": trust.NATIVE_PROVENANCE_CONTRACT,
    }


def _trust_envelope(*, trusted_rows: list[dict], review_rows: list[dict]) -> dict:
    all_rows = [*trusted_rows, *review_rows]
    return {
        "contract_version": trust.NATIVE_TRUST_CONTRACT,
        "canonical_contract_version": "medicore-canonical-lab-v1",
        "native_contract_version": trust.LAB_NATIVE_CONTRACT,
        "validation_contract_version": trust.LAB_VALIDATION_CONTRACT,
        "provenance_contract_version": trust.NATIVE_PROVENANCE_CONTRACT,
        "source_type": "manual",
        "source": {"source_type": "manual", "record_id": "manual-42"},
        "patient_age": 41,
        "patient_sex": "F",
        "report_date": "2026-09-08",
        "warnings": [],
        "input_row_count": len(all_rows),
        "processed_row_count": len(all_rows),
        "deduplicated_row_count": 0,
        "trusted_count": len(trusted_rows),
        "review_count": len(review_rows),
        "trusted_rows": trusted_rows,
        "review_rows": review_rows,
        "all_rows": all_rows,
        "native_ready": True,
        "ai_ready": bool(trusted_rows),
    }


def test_valid_native_row_becomes_trusted_and_preserves_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _canonical_case()
    source = dict(case["labs"][0])

    monkeypatch.setattr(
        trust,
        "process_astra_lab_rows",
        lambda rows: [_native_row(dict(rows[0]))],
    )

    result = trust.process_canonical_lab_case(case)
    assert result["contract_version"] == trust.NATIVE_TRUST_CONTRACT
    assert result["trusted_count"] == 1
    assert result["review_count"] == 0
    row = result["trusted_rows"][0]
    assert row["trusted_for_ai"] is True
    assert row["trust_status"] == "TRUSTED"
    assert row["canonical_row_contract"] == CANONICAL_ROW_CONTRACT
    assert row["source_type"] == "manual"
    assert row["source_record_id"] == "manual-42"
    assert row["raw_unit"] == "mmol/L"


def test_warning_row_is_never_promoted_to_trusted_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _canonical_case(confidence=0.4)

    def fake_native(rows: list[dict]) -> list[dict]:
        row = _native_row(dict(rows[0]), validation="WARNING", needs_review=True)
        row["result_status"] = "HIGH"
        row["normalized_value"] = 71.0
        row["raw_value"] = "71"
        return [row]

    monkeypatch.setattr(trust, "process_astra_lab_rows", fake_native)
    result = trust.process_canonical_lab_case(case)

    assert result["trusted_count"] == 0
    assert result["review_count"] == 1
    row = result["review_rows"][0]
    assert row["normalized_value"] == 71.0
    assert row["raw_value"] == "71"
    assert row["result_status"] == "HIGH"
    assert row["trusted_for_ai"] is False
    assert row["trust_status"] == "REVIEW"
    assert row["trust_reason"] == "native_validation_warning"


def test_native_dedupe_count_is_reported_without_guessing_source_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _canonical_case()
    duplicate = dict(case["labs"][0])
    case["labs"].append(duplicate)

    monkeypatch.setattr(
        trust,
        "process_astra_lab_rows",
        lambda rows: [_native_row(dict(rows[0]))],
    )
    result = trust.process_canonical_lab_case(case)
    assert result["input_row_count"] == 2
    assert result["processed_row_count"] == 1
    assert result["deduplicated_row_count"] == 1


def test_missing_native_provenance_contract_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _canonical_case()

    def old_native(rows: list[dict]) -> list[dict]:
        row = _native_row(dict(rows[0]))
        row.pop("provenance_contract_version")
        return [row]

    monkeypatch.setattr(trust, "process_astra_lab_rows", old_native)
    with pytest.raises(NativeLabUnavailable, match="provenance contract"):
        trust.process_canonical_lab_case(case)


def test_noncanonical_row_cannot_enter_native_trust_boundary() -> None:
    case = _canonical_case()
    case["labs"][0]["canonical_row_contract"] = "wrong-contract"
    with pytest.raises(ValueError, match="contract sürümü uyumsuz"):
        trust.process_canonical_lab_case(case)


def test_clinical_bridge_metrics_receive_only_native_trusted_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = dict(_canonical_case()["labs"][0])
    trusted = _native_row(source)
    trusted.update({"trusted_for_ai": True, "trust_status": "TRUSTED", "trust_reason": "native_validation_valid"})

    review_source = dict(source)
    review_source["raw_parameter_name"] = "Untrusted-but-valid-looking"
    review_source["canonical_name"] = "Untrusted-but-valid-looking"
    review = _native_row(review_source)
    review.update({
        "result_status": "UNKNOWN",
        "validation_status": "VALID",
        "needs_review": False,
        "trusted_for_ai": False,
        "trust_status": "REVIEW",
        "trust_reason": "native_result_not_trustable",
    })
    envelope = _trust_envelope(trusted_rows=[trusted], review_rows=[review])

    metric_inputs: list[dict] = []
    ai_rows: list[dict] = []

    def fake_metrics(rows, *, patient_age, patient_sex):
        metric_inputs.extend(dict(row) for row in rows)
        assert patient_age == 41
        assert patient_sex == "F"
        return [{
            "code": "safe_metric",
            "name": "Safe Metric",
            "value": 1.0,
            "unit": "",
            "formula": "native",
            "input_labels": ["Potassium"],
            "note": "native",
            "metrics_version": clinical_bridge.LAB_METRICS_CONTRACT,
        }]

    async def fake_ai(*, rows, derived_metrics, patient_age, patient_sex):
        ai_rows.extend(dict(row) for row in rows)
        assert derived_metrics[0]["code"] == "safe_metric"
        assert patient_age == 41
        assert patient_sex == "F"
        return {
            "headline": "ok",
            "overview": "ok",
            "priority_findings": [],
            "systems": [],
            "reassuring_findings": [],
            "priority_actions": [],
            "limitations": [],
            "narrative_tr": "ok",
            "model": "test-model",
            "synthesis_source": "ai_after_native_cpp",
        }

    monkeypatch.setattr(clinical_bridge, "compute_native_lab_metrics", fake_metrics)
    monkeypatch.setattr(clinical_bridge, "synthesize_lab_clinical_assessment", fake_ai)

    result = asyncio.run(clinical_bridge.run_native_trust_clinical_pipeline(envelope))

    assert [row["canonical_name"] for row in metric_inputs] == ["Potassium"]
    assert result["contract_version"] == clinical_bridge.NATIVE_TRUST_CLINICAL_AI_CONTRACT
    assert result["ai_used"] is True
    assert result["metrics_policy"] == clinical_bridge.TRUSTED_METRICS_POLICY
    assert ai_rows[0]["trusted_for_ai"] is True
    assert ai_rows[1]["trusted_for_ai"] is False
    assert ai_rows[1]["validation_status"] == "VALID"
    assert ai_rows[1]["result_status"] == "UNKNOWN"
    assert ai_rows[1]["needs_review"] is True
    assert ai_rows[1]["ai_policy_review_only"] is True


def test_clinical_bridge_falls_back_when_external_ai_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = dict(_canonical_case()["labs"][0])
    trusted = _native_row(source)
    trusted.update({"trusted_for_ai": True, "trust_status": "TRUSTED", "trust_reason": "native_validation_valid"})
    envelope = _trust_envelope(trusted_rows=[trusted], review_rows=[])

    monkeypatch.setattr(clinical_bridge, "compute_native_lab_metrics", lambda *args, **kwargs: [])

    async def unavailable(**kwargs):
        raise OpenAILabClinicalError("offline")

    monkeypatch.setattr(clinical_bridge, "synthesize_lab_clinical_assessment", unavailable)
    result = asyncio.run(clinical_bridge.run_native_trust_clinical_pipeline(envelope))

    assert result["ai_attempted"] is True
    assert result["ai_used"] is False
    assert result["clinical_assessment"]["synthesis_source"] == "deterministic_fallback"
    assert result["clinical_assessment"]["fallback_reason"].startswith("clinical_ai_unavailable:")


def test_clinical_bridge_does_not_call_ai_without_trusted_native_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = dict(_canonical_case()["labs"][0])
    review = _native_row(source, validation="WARNING", needs_review=True)
    review.update({"trusted_for_ai": False, "trust_status": "REVIEW", "trust_reason": "native_validation_warning"})
    envelope = _trust_envelope(trusted_rows=[], review_rows=[review])

    def metrics_must_not_run(*args, **kwargs):
        raise AssertionError("metrics must not run without trusted rows")

    async def ai_must_not_run(**kwargs):
        raise AssertionError("AI must not run without trusted rows")

    monkeypatch.setattr(clinical_bridge, "compute_native_lab_metrics", metrics_must_not_run)
    monkeypatch.setattr(clinical_bridge, "synthesize_lab_clinical_assessment", ai_must_not_run)

    result = asyncio.run(clinical_bridge.run_native_trust_clinical_pipeline(envelope))
    assert result["ai_attempted"] is False
    assert result["ai_used"] is False
    assert result["doctor_review_required"] is True
    assert result["clinical_assessment"]["fallback_reason"] == "no_trusted_native_evidence"


def test_clinical_bridge_rejects_partition_tampering() -> None:
    source = dict(_canonical_case()["labs"][0])
    bad = _native_row(source)
    bad.update({"trusted_for_ai": True, "trust_status": "TRUSTED"})
    envelope = _trust_envelope(trusted_rows=[], review_rows=[bad])

    with pytest.raises(ValueError, match="Review satırı trusted evidence"):
        clinical_bridge.validate_native_trust_envelope(envelope)
