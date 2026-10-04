"""Canonical lab status regressions; all values/references remain source data."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from app.domain.lab_result_classification import classify_lab_result
from app.domain.simple_case import normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest


@pytest.mark.parametrize(("value", "reference", "expected"), [
    (445, "250–450", "NORMAL"),
    (450, "250–450", "NORMAL"),
    (451, "250–450", "HIGH"),
    (249, "250–450", "LOW"),
    (250, "250–450", "NORMAL"),
    (5, "15–150", "LOW"),
    (5, "15–45", "LOW"),
    (0, "0-5", "NORMAL"),
    ("4,5", "4,5 – 5,5", "NORMAL"),
    ("5,5", "4,5 — 5,5", "NORMAL"),
    ("5,5001", "4,5 — 5,5", "HIGH"),
    (Decimal("4.5"), "4.5-5.5", "NORMAL"),
    (-3, "-5--1", "NORMAL"),
    ("−3", "−5 – −1", "NORMAL"),
    (1e-6, "0-0.01", "NORMAL"),
])
def test_source_interval_includes_both_boundaries(value, reference, expected):
    result = classify_lab_result(value=value, reference_text=reference)
    assert result.status == expected
    assert result.raw_reference == reference


@pytest.mark.parametrize("dash", ["-", "‐", "‑", "‒", "–", "—", "−"])
def test_unicode_range_separators(dash):
    result = classify_lab_result(value=445, reference_text=f"250 {dash} 450")
    assert (result.status, result.reference_low, result.reference_high) == ("NORMAL", 250, 450)


@pytest.mark.parametrize(("value", "reference", "expected"), [
    (39, "<40", "NORMAL"), (40, "<40", "HIGH"),
    (40, "<=40", "NORMAL"), (41, "≤40", "HIGH"),
    (11, ">10", "NORMAL"), (10, ">10", "LOW"),
    (10, ">=10", "NORMAL"), (9, "≥10", "LOW"),
    ("<5", "15–150", "LOW"),
    (">200", "15–150", "HIGH"),
    ("<15", "15–150", "LOW"),
    ("<=15", "15–150", "UNKNOWN"),
    (">150", "15–150", "HIGH"),
    (">=150", "15–150", "UNKNOWN"),
    ("<40", "<40", "NORMAL"),
    ("<=40", "<40", "UNKNOWN"),
    (">=40", "<40", "HIGH"),
    (">10", ">10", "NORMAL"),
    (">=10", ">10", "UNKNOWN"),
    ("<=10", ">10", "LOW"),
    ("<30", "15–150", "UNKNOWN"),
    (">30", "15–150", "UNKNOWN"),
])
def test_one_sided_references_and_only_provable_censored_values(value, reference, expected):
    assert classify_lab_result(value=value, reference_text=reference).status == expected


@pytest.mark.parametrize("value", [None, "negative", "positive", "iz", "hemolysis", "4.5.6", "4,500.0", True, False, float("nan"), float("inf")])
def test_non_numeric_or_ambiguous_observations_are_unknown(value):
    assert classify_lab_result(value=value, reference_text="2–5").status == "UNKNOWN"


@pytest.mark.parametrize("reference", [None, "negative", "Adult: 2–5", "2–5 or 8–10", "", "5–2"])
def test_unusable_reference_never_invents_range(reference):
    assert classify_lab_result(value=3, reference_text=reference).status == "UNKNOWN"


@pytest.mark.parametrize(("unit", "reference_unit", "text", "expected"), [
    ("µg/dL", None, "250–450", "NORMAL"),
    ("µg/dL", None, "250–450 µg/dL", "NORMAL"),
    ("μg/dL", "ug / dL", "250–450", "NORMAL"),
    ("mg/dL", None, "250–450 µg/dL", "UNKNOWN"),
    ("µg/dL", "mg/dL", "250–450", "UNKNOWN"),
    ("µg/dL", "mg/dL", "250–450 µg/dL", "UNKNOWN"),
    (None, "µg/dL", "250–450", "UNKNOWN"),
    ("10^9 / L", None, "250–450 10^9/L", "NORMAL"),
    ("%", None, "15–45 %", "LOW"),
])
def test_units_are_compared_without_converting_measurements(unit, reference_unit, text, expected):
    value = 5 if text.startswith("15") else 445
    result = classify_lab_result(value=value, unit=unit, reference_text=text, reference_unit=reference_unit)
    assert result.status == expected
    if expected == "UNKNOWN":
        assert result.classification_reason == "reference_unit_mismatch"


@pytest.mark.parametrize(("kwargs", "reason"), [
    ({"reference_low": 1, "reference_high": 4, "reference_text": "2–5"}, "reference_bounds_conflict"),
    ({"reference_low": 2, "reference_high": 5, "reference_text": "<5"}, "reference_bounds_conflict"),
    ({"reference_low": "broken", "reference_high": 5}, "invalid_reference_bounds"),
    ({"reference_low": float("inf"), "reference_high": 5}, "invalid_reference_bounds"),
    ({"reference_low": 5, "reference_high": 2}, "invalid_reference_bounds"),
])
def test_conflicting_or_invalid_structured_bounds_are_unknown(kwargs, reason):
    result = classify_lab_result(value=3, **kwargs)
    assert result.status == "UNKNOWN"
    assert result.classification_reason == reason


def test_explicit_structured_bounds_and_selected_demographic_label_are_supported():
    result = classify_lab_result(value=210, unit="U/L", reference_text="Age 10-17: 80-350 U/L",
                                 reference_low=80, reference_high=350, reference_unit="U/L")
    assert result.status == "NORMAL"
    assert classify_lab_result(value="4,5", reference_low="4,5", reference_high="5,5").status == "NORMAL"


@pytest.mark.parametrize("reason", ["numeric_value_conflict", "invalid_reference_bounds", "reference_unit_mismatch", "low_input_confidence", "conflicting_or_repeated_observation"])
def test_transcription_uncertainty_is_not_promoted_to_fact(reason):
    result = classify_lab_result(value=3, reference_text="2–5", ingestion_reasons=[reason])
    assert result.status == "UNKNOWN"
    assert result.classification_reason == "ingestion_review_required"


def test_normalization_recomputes_tibc_status_without_trusting_flag_or_incoming_status():
    payload = SimpleCaseRequest.model_validate({"labs": [{
        "test_name": "TIBC", "value": 445, "unit": "µg/dL", "source_reference": "250–450",
        "status": "HIGH", "source_metadata": {"source_flag": "High", "display_status": "high"},
        "specimen_date": "2026-10-02", "result_date": "2026-10-04", "uploaded_at": "2026-10-04",
    }]})
    before = deepcopy(payload.model_dump())
    output = normalize_simple_case(payload).labs[0]
    assert (output.status, output.reference_low, output.reference_high) == ("NORMAL", 250, 450)
    assert output.raw_reference == "250–450"
    assert output.source_metadata["source_flag"] == "High"
    assert output.specimen_date == date(2026, 10, 2)
    assert output.result_date == output.uploaded_at == date(2026, 10, 4)
    assert payload.model_dump() == before


def test_missing_demographics_never_reuses_unselected_context_specific_reference():
    payload = SimpleCaseRequest.model_validate({"labs": [{
        "test_name": "ALP", "value": 210, "source_reference": "80–350", "reference_low": 80,
        "reference_high": 350, "source_references": [{"text": "80–350", "minimum": 80,
            "maximum": 350, "age_min": 10, "age_max": 17}],
    }]})
    output = normalize_simple_case(payload).labs[0]
    assert output.status == "UNKNOWN"
    assert output.reference_source == "missing"


def test_equally_applicable_conflicting_reference_rows_stay_unknown():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": 3,
        "source_references": [{"text": "2–5", "minimum": 2, "maximum": 5},
                              {"text": "4–8", "minimum": 4, "maximum": 8}]}]})
    assert normalize_simple_case(payload).labs[0].status == "UNKNOWN"


def test_equal_numeric_bounds_do_not_hide_conflicting_strict_comparators():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": 40,
        "source_references": [{"text": "<40", "maximum": 40},
                              {"text": "<=40", "maximum": 40}]}]})
    assert normalize_simple_case(payload).labs[0].status == "UNKNOWN"


@pytest.mark.parametrize(("reference", "status"), [("Adult: <40", "HIGH"), ("Adult: <=40", "NORMAL")])
def test_selected_demographic_labels_preserve_one_sided_boundary_semantics(reference, status):
    result = classify_lab_result(value=40, reference_text=reference, reference_high=40)
    assert result.status == status


def test_source_flag_without_numeric_reference_never_creates_numeric_status():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": 3,
        "source_metadata": {"source_flag": "High"}}]})
    assert normalize_simple_case(payload).labs[0].status == "UNKNOWN"


def test_normalized_roundtrip_preserves_all_demographic_references():
    references = [
        {"text": "80–350", "minimum": 80, "maximum": 350, "age_min": 10, "age_max": 17},
        {"text": "40–130", "minimum": 40, "maximum": 130, "age_min": 18, "age_max": 65},
    ]
    first = normalize_simple_case(SimpleCaseRequest.model_validate({
        "clinical": {"age": 15}, "labs": [{"test_name": "ALP", "value": 210,
        "source_reference": None, "source_references": references}],
    })).labs[0]
    assert first.status == "NORMAL"
    assert first.source_reference is None
    assert first.source_references == SimpleCaseRequest.model_validate({
        "labs": [{"test_name": "ALP", "source_references": references}],
    }).labs[0].source_references
    updated = normalize_simple_case(SimpleCaseRequest.model_validate({
        "clinical": {"age": 44}, "labs": [first.model_dump(mode="json")],
    })).labs[0]
    assert updated.status == "HIGH"
    assert updated.raw_reference == "40–130"


def test_boolean_observation_does_not_coerce_into_numeric_value():
    payload = SimpleCaseRequest.model_validate({"labs": [{"test_name": "test", "value": True,
        "source_reference": "0–2"}]})
    output = normalize_simple_case(payload).labs[0]
    assert output.value == "True"
    assert output.status == "UNKNOWN"
