from __future__ import annotations

from app.api.routes import lab_derived_parameters


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
