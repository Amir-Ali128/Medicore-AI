from __future__ import annotations

from app.api.routes import lab_common_parameters, lab_derived_parameters


def _names(values: list[dict[str, object]]) -> set[str]:
    return {str(item.get("raw_parameter_name")) for item in values}


def test_bun_creatinine_ratio_is_not_created_when_missing_from_pdf() -> None:
    text = """
KAN URE NITROJENI (BUN) 18 mg/dL 7 - 20
KREATININ 0.80 mg/dL 0.60 - 1.20
"""

    values = lab_derived_parameters._parse_with_derived_ratio(text)

    assert "BUN" in _names(values)
    assert "Kreatinin" in _names(values)
    assert "BUN / Kreatinin" not in _names(values)


def test_bun_creatinine_ratio_can_be_calculated_only_when_source_reports_it() -> None:
    text = """
KAN URE NITROJENI (BUN) 18 mg/dL 7 - 20
KREATININ 0.80 mg/dL 0.60 - 1.20
BUN / KREATININ 22.5 10 - 20
"""

    values = lab_derived_parameters._parse_with_derived_ratio(text)
    ratio = next(
        item for item in values if item.get("raw_parameter_name") == "BUN / Kreatinin"
    )

    assert ratio["normalized_value"] == 22.5
    assert ratio["metadata"]["source_reported_parameter"] is True


def test_k_per_mm3_unit_does_not_create_phantom_potassium() -> None:
    text = """
LOKOSIT 8.40 K/mm3 4.50 - 11.00
NOTROFIL MUTLAK 5.20 K/mm3 1.80 - 7.70
"""

    values = lab_derived_parameters._parse_with_derived_ratio(text)

    assert "Potasyum" not in _names(values)


def test_explicit_potassium_row_still_parses() -> None:
    text = """
POTASYUM 4.6 mmol/L 3.5 - 5.1
"""

    values = lab_derived_parameters._parse_with_derived_ratio(text)
    potassium = next(item for item in values if item.get("raw_parameter_name") == "Potasyum")

    assert potassium["normalized_value"] == 4.6
    assert lab_common_parameters.COMMON_PARAMETERS["Potasyum"]["aliases"] == [
        "POTASYUM",
        "POTASSIUM",
    ]
