from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.domain import clinical_rule_extensions_fix_runtime as _fix  # noqa: F401
from app.domain import clinical_rule_extensions_runtime as rules
from app.domain import lab_urinalysis_runtime as urine


def result(
    name: str,
    value: float,
    *,
    status: str = "normal",
    raw_value: str | None = None,
    reference_max: float | None = None,
    unit: str | None = None,
):
    return SimpleNamespace(
        raw_parameter_name=name,
        canonical_name=name,
        parameter_code=None,
        normalized_value=value,
        raw_value=raw_value or str(value),
        result_status=status,
        reference_min=None,
        reference_max=reference_max,
        unit=unit,
        rule_applied="test",
        previous_value=None,
        absolute_difference=None,
        percentage_difference=None,
        time_difference_days=None,
    )


def test_fib4_apri_and_ratios_are_deterministic():
    rows = [
        result("AST", 45, status="high", reference_max=40, unit="U/L"),
        result("ALT", 55, status="high", reference_max=50, unit="U/L"),
        result("PLT", 120, status="low", unit="10^9/L"),
        result("Demir", 40, status="low"),
        result("DDBK", 260, status="high"),
        result("Total Kolesterol", 180),
        result("HDL", 30, status="low"),
    ]

    scores = {item["code"]: item for item in rules.compute_deterministic_scores(rows, 52)}

    assert scores["FIB4"]["status"] == "computed"
    assert scores["FIB4"]["formula"] == "(yaş × AST) / (PLT × √ALT)"
    assert scores["APRI"]["status"] == "computed"
    assert scores["AST_ALT"]["status"] == "computed"
    assert scores["TSAT"]["status"] == "computed"
    assert round(scores["TSAT"]["value"], 2) == 13.33
    assert scores["TOTAL_HDL"]["value"] == 6.0


def test_missing_score_input_is_not_imputed():
    scores = {item["code"]: item for item in rules.compute_deterministic_scores([], None)}
    assert scores["FIB4"]["status"] == "unavailable"
    assert "yaş" in scores["FIB4"]["missing"]
    assert scores["FIB4"]["value"] is None


def test_serum_urine_glucose_discordance_flag_is_non_diagnostic():
    rows = [
        result("Glukoz", 146, status="high", unit="mg/dL"),
        result("İdrar Glukoz", 4, status="high", raw_value="++++"),
    ]
    checks = rules.compute_cross_consistency(rows)
    check = next(item for item in checks if item["code"] == "SERUM_URINE_GLUCOSE_DISCORDANCE")
    assert check["severity"] == "review"
    assert "tanı" not in check["title"].lower()
    assert "146" in check["message"]


def test_performed_study_inventory_filters_synonymous_abdominal_us():
    metadata = {
        "source_summaries": {
            "ultrasound": "01.09.2026 · Hepatomegali, portal ven dilatasyonu, METAVIR F4 ile uyumlu elastografi bulguları."
        },
        "performed_studies": [
            {"code": "US_ABDOMEN", "name": "Üst abdomen USG", "date": "2026-09-01"},
            {"code": "LIVER_ELASTOGRAPHY", "name": "Karaciğer elastografisi", "date": "2026-09-01"},
        ],
    }
    performed = rules._performed_studies(metadata)
    codes = {item["code"] for item in performed}
    assert "US_ABDOMEN" in codes
    assert "LIVER_ELASTOGRAPHY" in codes
    assert rules._suggested_study_code("Hepatobilier ultrasonografi") == "US_ABDOMEN"
    assert rules._suggested_study_code("Üst abdomen ultrasonografisi") == "US_ABDOMEN"
    assert rules._suggested_study_code("Karaciğer elastografisi") == "LIVER_ELASTOGRAPHY"


def test_urinalysis_numeric_and_semiquantitative_rows_are_preserved():
    text = """
TAM İDRAR ANALİZİ
Dansite 1.038 --- 1.005 - 1.030
Glukoz ++++ --- Negatif
Sayfa 2 / 2
"""
    rows = urine._parse_urinalysis_rows(text, date(2025, 12, 17))
    by_name = {item["display_name"]: item for item in rows}
    assert by_name["İdrar Dansite"]["normalized_value"] == 1.038
    assert by_name["İdrar Glukoz"]["raw_value"] == "++++"
    assert by_name["İdrar Glukoz"]["normalized_value"] == 4.0
    assert by_name["İdrar Glukoz"]["extracted_reference_max"] == 0.0


def test_new_clinical_dictionary_covers_requested_parameters():
    for name in ("MPV", "PDW", "PCT", "RDW-CV", "DDBK", "IgG", "Lipaz", "Total Protein"):
        interpretation, causes, source = rules._interpretation_for(name, "high")
        assert interpretation
        assert causes
        assert source
