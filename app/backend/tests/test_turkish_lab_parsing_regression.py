"""Regression set: Turkish lab rows must keep the reference printed in the source.

UNKNOWN is allowed only when the source has no usable reference (or needs a
patient sex that is not supplied). It is never avoided by inventing a range.
"""

from __future__ import annotations

import pytest

from app.api.routes import lab_analysis
from app.domain import fast_pdf_lab_parser
from app.domain.fast_pdf_lab_parser import _parse_enabiz_table_data
from app.domain.lab_document_ingestion import RawLabRow, validate_merge
from app.domain.canonical_lab_model import SourceContext
from app.domain.lab_result_classification import (
    canonical_lab_unit,
    classify_lab_result,
    describe_lab_status,
    humanize_status_codes,
    parse_lab_observation,
    parse_source_reference,
)
from app.domain.simple_case import normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest
from tests.fixtures.turkish_lab_fixtures import (
    CLASSIFY_CASES,
    ENABIZ_EXPECTED,
    ENABIZ_TABLE,
    HOSPITAL_EXPECTED,
    HOSPITAL_TEXT,
)


@pytest.mark.parametrize(
    ("case_id", "value", "unit", "reference", "sex", "expected", "low", "high"),
    CLASSIFY_CASES,
    ids=[case[0] for case in CLASSIFY_CASES],
)
def test_turkish_reference_formats(case_id, value, unit, reference, sex, expected, low, high):
    result = classify_lab_result(value=value, unit=unit, reference_text=reference, patient_sex=sex)
    assert result.status == expected, result.classification_reason
    if low is None:
        assert result.reference_low is None or expected == "UNKNOWN"
    else:
        assert result.reference_low == pytest.approx(low)
    if high is None:
        assert result.reference_high is None or expected == "UNKNOWN"
    else:
        assert result.reference_high == pytest.approx(high)
    # The printed reference is always preserved verbatim.
    assert result.raw_reference == reference
    if expected == "UNKNOWN":
        assert result.status_explanation and "UNKNOWN" not in result.status_explanation
    else:
        assert result.status_explanation is None


def test_unknown_fixture_cases_are_only_source_limited():
    unknown_ids = {case[0] for case in CLASSIFY_CASES if case[5] == "UNKNOWN"}
    assert unknown_ids == {
        "hgb_cinsiyet_yok", "ref_yok", "ref_tire", "ters_yon_belirsiz",
        "birim_farkli_miu", "pozitif_negatif_ref", "yas_etiketi",
    }


@pytest.mark.parametrize(("text", "unit", "expected"), [
    ("250.000", "/mm3", 250000), ("7.500", "/µL", 7500), ("7.500", "hücre/µL", 7500),
    ("1.234,5", None, 1234.5), ("3,5", None, 3.5), ("1.038", None, 1.038),
    ("7.5", "/uL", 7.5), ("5.2 H", None, 5.2), ("5,2H", None, 5.2), ("7,1*", None, 7.1),
    ("180 ↑", None, 180), ("8 (L)", None, 8), ("94 mg/L", "mg/L", 94),
])
def test_observation_numbers_flags_and_thousands(text, unit, expected):
    parsed = parse_lab_observation(text, unit)
    assert parsed.error is None
    assert float(parsed.number) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["4,500.0", "4.5.6", "3+", "iz"])
def test_ambiguous_observations_stay_unparsed(text):
    assert parse_lab_observation(text).number is None


@pytest.mark.parametrize(("left", "right", "same"), [
    ("K/uL", "10^3/µL", True), ("10³/µL", "x10^3/uL", True), ("10^9/L", "K/mm3", True),
    ("/mm³", "/µL", True), ("hücre/µL", "/uL", True), ("µIU/mL", "mIU/L", True),
    ("mm/saat", "mm/h", True), ("IU/L", "U/L", True), ("ng/mL", "µg/L", True),
    ("mIU/mL", "µIU/mL", False), ("mg/dL", "mmol/L", False), ("g/dL", "g/L", False),
    ("10^3/uL", "/uL", False), ("10^6/uL", "10^3/uL", False),
])
def test_unit_aliases_are_factor_one_only(left, right, same):
    assert (canonical_lab_unit(left) == canonical_lab_unit(right)) is same


def test_sex_specific_reference_never_guesses_without_sex():
    parsed = parse_source_reference("Erkek: 13-17 Kadın: 12-15")
    assert parsed.error == "sex_specific_reference_requires_patient_sex"
    assert parse_source_reference("Erkek: 13-17 Kadın: 12-15", patient_sex="Female").low == 12
    # Structured bounds that contradict the printed sex row are not trusted.
    conflict = classify_lab_result(value=14, reference_text="Erkek: 13-17 Kadın: 12-15",
                                   reference_low=13, reference_high=17, patient_sex="female")
    assert conflict.status == "UNKNOWN" and conflict.classification_reason == "reference_bounds_conflict"


def test_status_explanation_is_human_readable():
    assert describe_lab_status("UNKNOWN", "missing_numeric_reference") == "Referans aralığı raporda yok"
    assert describe_lab_status("HIGH", "above_source_reference") is None
    text = humanize_status_codes("Ferritin: UNKNOWN (missing_numeric_reference)")
    assert "UNKNOWN" not in text and "missing_numeric_reference" not in text
    assert "Referans aralığı raporda yok" in text


# --------------------------------------------------------------------------
# Legacy hospital text parser (bug 1: demo references overwrote the source)
# --------------------------------------------------------------------------

def _legacy_rows(sex="Female"):
    return {row["raw_parameter_name"]: row for row in lab_analysis._parse_lab_values_from_text(HOSPITAL_TEXT, patient_sex=sex)}


def test_legacy_parser_keeps_printed_unit_and_reference():
    rows = _legacy_rows()
    assert set(HOSPITAL_EXPECTED) <= set(rows)
    for name, (value, unit, ref_text, low, high, _status) in HOSPITAL_EXPECTED.items():
        row = rows[name]
        assert row["normalized_value"] == (pytest.approx(value) if value is not None else None), name
        assert canonical_lab_unit(row["unit"]) == canonical_lab_unit(unit), name
        assert row["reference_text"] == ref_text, name
        assert row["reference_min"] == (pytest.approx(low) if low is not None else None), name
        assert row["reference_max"] == (pytest.approx(high) if high is not None else None), name
        assert row["measured_at"] is None


def test_legacy_ft4_and_leukocyte_are_not_rewritten_with_demo_ranges():
    rows = _legacy_rows()
    ft4, wbc = rows["FT4"], rows["Lökosit"]
    assert (ft4["unit"], ft4["reference_min"], ft4["reference_max"]) == ("ng/dL", 0.89, 1.76)
    assert (wbc["unit"], wbc["reference_min"], wbc["reference_max"]) == ("/uL", 4500, 11000)
    assert not hasattr(lab_analysis, "_forced_demo_reference")


def test_legacy_lone_number_is_not_turned_into_a_limit():
    rows = {row["raw_parameter_name"]: row for row in
            lab_analysis._parse_lab_values_from_text("HDL Kolesterol 45 mg/dL 40\n")}
    hdl = rows["HDL"]
    assert hdl["reference_text"] is None
    assert hdl["extracted_reference_min"] is None and hdl["extracted_reference_max"] is None


def test_legacy_parser_prefers_row_with_reference_over_earlier_mention():
    text = "Ozet: Glukoz 98\nGlukoz 112 mg/dL 70-100\n"
    row = {r["raw_parameter_name"]: r for r in lab_analysis._parse_lab_values_from_text(text)}["Glukoz"]
    assert row["normalized_value"] == 112 and row["reference_text"] == "70-100"


def test_normalize_text_keeps_powers_of_ten():
    assert "10^3/uL" in lab_analysis._normalize_text("WBC 7,5 10³/µL")
    assert "1234.5" in lab_analysis._normalize_text("B12 1.234,5 pg/mL")


def _status_through_simple_case(rows, sex):
    labs = []
    for row in rows:
        labs.append({
            "test_name": row["raw_parameter_name"],
            "value": row["raw_value"],
            "unit": row.get("unit"),
            "source_reference": row.get("reference_text"),
            "source_references": [{
                "text": row["reference_text"],
                "minimum": row.get("reference_min"),
                "maximum": row.get("reference_max"),
                "unit": row.get("unit"),
            }] if row.get("reference_text") else [],
        })
    payload = SimpleCaseRequest.model_validate({"clinical": {"sex": sex}, "labs": labs})
    return {lab.test_name: lab for lab in normalize_simple_case(payload).labs}


def test_legacy_rows_classify_from_source_reference_end_to_end():
    rows = _legacy_rows()
    out = _status_through_simple_case([rows[name] for name in HOSPITAL_EXPECTED], "female")
    for name, expected in HOSPITAL_EXPECTED.items():
        assert out[name].status == expected[-1], (name, out[name].classification_reason)
    assert sum(lab.status == "UNKNOWN" for lab in out.values()) == 0


def test_legacy_sex_specific_rows_stay_unknown_without_patient_sex():
    rows = _legacy_rows(sex=None)
    out = _status_through_simple_case([rows["Hemoglobin"], rows["HDL"]], "unknown")
    for lab in out.values():
        assert lab.status == "UNKNOWN"
        assert lab.classification_reason == "sex_specific_reference_requires_patient_sex"
        assert "cinsiyet" in lab.status_explanation


# --------------------------------------------------------------------------
# e-Nabız native tables, including wrapped reference cells
# --------------------------------------------------------------------------

def test_enabiz_wrapped_and_turkish_references():
    rows, measured_at = _parse_enabiz_table_data(ENABIZ_TABLE, page_number=1, current_measured_at=None)
    by_name = {row["raw_parameter_name"]: row for row in rows}
    assert measured_at == "17.12.2025 08:41"
    assert set(by_name) == set(ENABIZ_EXPECTED)
    for name, (reference_text, _status) in ENABIZ_EXPECTED.items():
        assert by_name[name]["reference_text"] == reference_text, name
    assert by_name["PLT"]["normalized_value"] == 250000
    assert (by_name["PLT"]["reference_min"], by_name["PLT"]["reference_max"]) == (150000, 400000)
    assert (by_name["Kreatinin"]["reference_min"], by_name["Kreatinin"]["reference_max"]) == (0.5, 1.2)
    assert by_name["Glukoz"]["normalized_value"] == 112
    # Sex-specific text stays text: the classifier selects it with patient sex.
    assert by_name["Hemoglobin"]["reference_min"] is None


def test_enabiz_rows_classify_end_to_end():
    rows, _ = _parse_enabiz_table_data(ENABIZ_TABLE, page_number=1, current_measured_at=None)
    out = _status_through_simple_case(rows, "female")
    for name, (_ref, expected) in ENABIZ_EXPECTED.items():
        assert out[name].status == expected, (name, out[name].classification_reason)
    unknown = [name for name, lab in out.items() if lab.status == "UNKNOWN"]
    assert unknown == ["Nötrofil Lenfosit Oranı"]
    assert out["Nötrofil Lenfosit Oranı"].status_explanation == "Referans aralığı raporda yok"


# --------------------------------------------------------------------------
# Ingestion and fast-path behaviour
# --------------------------------------------------------------------------

def test_ingestion_accepts_reader_value_for_grouped_count():
    output = validate_merge([RawLabRow({
        "raw_parameter_name": "Trombosit", "raw_value": "250.000", "normalized_value": 250000,
        "unit": "10^3/uL", "reference_unit": "K/uL", "reference_text": "150-400",
    }, 1, 1)], SourceContext("file_upload"))
    row = output["labs"][0]
    assert "numeric_value_conflict" not in row["ingestion_reasons"]
    assert "reference_unit_mismatch" not in row["ingestion_reasons"]


def _fast_case(monkeypatch, text):
    monkeypatch.setattr(fast_pdf_lab_parser, "_extract_text_fast", lambda content: text)
    return fast_pdf_lab_parser.try_fast_pdf_lab_case(
        content=b"fake", media_type="application/pdf", file_name="hastane.pdf", source_type="file_upload",
    )


def test_fast_path_legacy_uses_document_dates_and_quality_confidence(monkeypatch):
    text = "Numune alma tarihi: 02.10.2026\n" + HOSPITAL_TEXT
    case = _fast_case(monkeypatch, text)
    assert case is not None
    assert case["report_date"] == "2026-10-02"
    assert all(row["measured_at"] is None for row in case["labs"])
    assert all(row["specimen_date"] == "2026-10-02" for row in case["labs"])
    assert 0.7 <= case["extraction_confidence"] < 0.99
    ft4 = next(row for row in case["labs"] if row["raw_parameter_name"] == "FT4")
    assert (ft4["unit"], ft4["reference_min"], ft4["reference_max"]) == ("ng/dL", 0.89, 1.76)


def test_fast_path_defers_to_ai_when_rows_lack_references(monkeypatch):
    text = "\n".join([
        "Laboratuvar sonuc raporu " * 4,
        "Glukoz 98 mg/dL", "Kreatinin 0,9 mg/dL", "ALT 31 U/L", "AST 22 U/L",
        "TSH 2,1 uIU/mL", "Hemoglobin 13,2 g/dL",
    ])
    assert _fast_case(monkeypatch, text) is None
