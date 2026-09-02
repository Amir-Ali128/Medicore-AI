from datetime import date

from app.api.routes import urinalysis_runtime


def test_urinalysis_parser_keeps_numeric_and_semiquantitative_abnormal_rows() -> None:
    text = """
TAM İDRAR ANALİZİ
Dansite 1.038 --- 1.005 - 1.030
Glukoz ++++ --- Negatif
Protein Negatif --- Negatif
TAM KAN SAYIMI
Hemoglobin 14.5 g/dL 12.0 - 16.0
"""

    rows = urinalysis_runtime._parse_urine_rows(text, date(2025, 12, 17))
    by_name = {row["display_name"]: row for row in rows}

    density = by_name["İdrar · Dansite"]
    assert density["normalized_value"] == 1.038
    assert density["extracted_reference_min"] == 1.005
    assert density["extracted_reference_max"] == 1.03
    assert density["measured_at"] == "2025-12-17"

    glucose = by_name["İdrar · Glukoz"]
    assert glucose["raw_value"] == "++++"
    assert glucose["normalized_value"] == 4.0
    assert glucose["extracted_reference_min"] == 0.0
    assert glucose["extracted_reference_max"] == 0.0
    assert glucose["semiquantitative"] is True

    protein = by_name["İdrar · Protein"]
    assert protein["raw_value"].lower().startswith("negatif")
    assert protein["normalized_value"] == 0.0


def test_urinalysis_parser_stops_at_next_blood_section() -> None:
    text = """
TAM IDRAR ANALIZI
Glukoz ++++ --- Negatif
TAM KAN SAYIMI
PCT 0.14 % 0.17 - 0.32
"""

    rows = urinalysis_runtime._parse_urine_rows(text, date(2025, 12, 17))
    names = {row["display_name"] for row in rows}

    assert "İdrar · Glukoz" in names
    assert "İdrar · PCT" not in names
