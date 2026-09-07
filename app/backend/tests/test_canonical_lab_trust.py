from __future__ import annotations

import pytest

from app.domain import canonical_lab_trust as trust
from app.domain import native_lab_engine as native
from app.domain.canonical_lab_model import (
    CANONICAL_LAB_CONTRACT,
    CANONICAL_ROW_CONTRACT,
    SOURCE_MANUAL,
    SourceContext,
    build_canonical_case,
)


class _FakeTrustModule:
    CANONICAL_ROW_VERSION = CANONICAL_ROW_CONTRACT
    TRUST_VERSION = trust.CPP_TRUST_CONTRACT

    def process_canonical_rows(self, rows):
        output = []
        for source in rows:
            row = dict(source)
            value = float(row["normalized_value"])
            high = row.get("reference_max")
            low = row.get("reference_min")
            if high is not None and value > float(high):
                status = "HIGH"
            elif low is not None and value < float(low):
                status = "LOW"
            else:
                status = "NORMAL"
            row.update(
                {
                    "display_name": row.get("canonical_name") or row["raw_parameter_name"],
                    "result_status": status,
                    "validation_status": "VALID",
                    "needs_review": False,
                    "reason": "native comparison complete",
                    "rule_applied": "fake_native_rule",
                    "classification_confidence": row.get("confidence", 1.0),
                    "contract_version": native.LAB_NATIVE_CONTRACT,
                    "validation_contract_version": native.LAB_VALIDATION_CONTRACT,
                    "trust_contract_version": trust.CPP_TRUST_CONTRACT,
                    "trusted_for_ai": True,
                    "extraction_confidence": row.get("confidence", 1.0),
                }
            )
            output.append(row)
        return output


class _FakeExtensions:
    def parse_reference_text(self, text: str):
        return {
            "type": "range",
            "minimum": None,
            "maximum": None,
            "parsed": False,
            "needs_review": True,
            "reason": "not needed in this test",
            "extensions_version": native.LAB_EXTENSIONS_CONTRACT,
        }

    def validate_plausibility(self, analyte: str, value: float, unit: str):
        if analyte == "Potassium" and value == 71.0:
            return {
                "status": "WARNING",
                "needs_review": True,
                "rule_applied": "plausibility_potassium_extreme",
                "reason": "verify source",
                "extensions_version": native.LAB_EXTENSIONS_CONTRACT,
            }
        return {
            "status": "VALID",
            "needs_review": False,
            "rule_applied": "plausibility_ok",
            "reason": "",
            "extensions_version": native.LAB_EXTENSIONS_CONTRACT,
        }


def _case():
    return build_canonical_case(
        source=SourceContext(
            source_type=SOURCE_MANUAL,
            source_record_id="manual-42",
        ),
        rows=[
            {
                "raw_parameter_name": "Glucose",
                "canonical_name": "Glucose",
                "raw_value": "105",
                "normalized_value": 105,
                "raw_unit": "mg/dL",
                "unit": "mg/dL",
                "reference_min": 70,
                "reference_max": 100,
                "confidence": 0.99,
            },
            {
                "raw_parameter_name": "Potassium",
                "canonical_name": "Potassium",
                "raw_value": "71",
                "normalized_value": 71,
                "raw_unit": "mmol/L",
                "unit": "mmol/L",
                "reference_min": 3.5,
                "reference_max": 5.1,
                "confidence": 0.99,
            },
        ],
        patient_age=41,
        patient_sex="F",
        report_date="2026-09-08",
        default_confidence=1.0,
    )


def test_canonical_case_is_partitioned_by_final_native_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(native, "_require_module", lambda: _FakeTrustModule())
    monkeypatch.setattr(native, "native_lab_extensions_available", lambda: True)
    monkeypatch.setattr(native, "_load_extensions_module", lambda: _FakeExtensions())

    result = trust.process_canonical_lab_case(_case())

    assert result["trust_contract_version"] == trust.CPP_TRUST_CONTRACT
    assert result["canonical_contract_version"] == CANONICAL_LAB_CONTRACT
    assert result["counts"] == {
        "input": 2,
        "processed": 2,
        "trusted": 1,
        "review": 1,
        "invalid": 0,
        "deduplicated": 0,
    }

    trusted = result["trusted_rows"][0]
    assert trusted["raw_parameter_name"] == "Glucose"
    assert trusted["result_status"] == "HIGH"
    assert trusted["trusted_for_ai"] is True
    assert trusted["source_type"] == SOURCE_MANUAL
    assert trusted["source_record_id"] == "manual-42"
    assert trusted["raw_unit"] == "mg/dL"

    review = result["review_rows"][0]
    assert review["raw_parameter_name"] == "Potassium"
    assert review["normalized_value"] == 71.0
    assert review["result_status"] == "HIGH"
    assert review["validation_status"] == "WARNING"
    assert review["trusted_for_ai"] is False
    assert review["plausibility_rule"] == "plausibility_potassium_extreme"


def test_bad_canonical_row_contract_is_rejected_before_native(monkeypatch: pytest.MonkeyPatch) -> None:
    case = _case()
    case["labs"][0]["canonical_row_contract"] = "wrong-version"
    monkeypatch.setattr(native, "_require_module", lambda: _FakeTrustModule())

    with pytest.raises(ValueError, match="satır contract"):
        trust.process_canonical_lab_case(case)


def test_native_trust_contract_mismatch_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _WrongModule(_FakeTrustModule):
        TRUST_VERSION = "wrong-trust-version"

    monkeypatch.setattr(native, "_require_module", lambda: _WrongModule())

    with pytest.raises(native.NativeLabUnavailable, match="trust contract"):
        trust.process_canonical_lab_case(_case())
