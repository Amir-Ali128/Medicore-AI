from __future__ import annotations

import pytest

from app.domain import canonical_native_trust as trust
from app.domain.canonical_lab_model import CANONICAL_ROW_CONTRACT
from app.domain.native_lab_engine import NativeLabUnavailable
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
