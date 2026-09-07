from __future__ import annotations

from app.domain import native_lab_engine as native


class _FakeExtensions:
    def parse_reference_text(self, text: str):
        assert text == "< 5 mg/L"
        return {
            "type": "less_than",
            "minimum": None,
            "maximum": 5.0,
            "parsed": True,
            "needs_review": False,
            "reason": "parsed",
            "extensions_version": native.LAB_EXTENSIONS_CONTRACT,
        }

    def validate_plausibility(self, analyte: str, value: float, unit: str):
        assert analyte == "Potassium"
        assert value == 71.0
        assert unit == "mmol/L"
        return {
            "status": "WARNING",
            "needs_review": True,
            "rule_applied": "plausibility_potassium_extreme",
            "reason": "verify source",
            "extensions_version": native.LAB_EXTENSIONS_CONTRACT,
        }


def test_reference_hydration_only_fills_missing_fields() -> None:
    source = {
        "reference_text": "< 5 mg/L",
        "reference_min": None,
        "reference_max": None,
        "reference_type": "unknown",
    }
    result = native._hydrate_reference_with_native(dict(source), _FakeExtensions())
    assert result["reference_type"] == "less_than"
    assert result["reference_max"] == 5.0
    assert result["reference_min"] is None

    already_structured = {
        "reference_text": "< 5 mg/L",
        "reference_min": 1.0,
        "reference_max": 9.0,
        "reference_type": "range",
    }
    result = native._hydrate_reference_with_native(dict(already_structured), _FakeExtensions())
    assert result["reference_type"] == "range"
    assert result["reference_min"] == 1.0
    assert result["reference_max"] == 9.0


def test_plausibility_tightens_validation_without_changing_value() -> None:
    source = {
        "canonical_name": "Potassium",
        "normalized_value": 71.0,
        "unit": "mmol/L",
        "result_status": "HIGH",
        "validation_status": "VALID",
        "needs_review": False,
        "reason": "reference comparison complete",
    }
    result = native._attach_plausibility(dict(source), _FakeExtensions())
    assert result["normalized_value"] == 71.0
    assert result["result_status"] == "HIGH"
    assert result["validation_status"] == "WARNING"
    assert result["needs_review"] is True
    assert result["plausibility_rule"] == "plausibility_potassium_extreme"
