from datetime import date

from app.api.routes import lab_pdf_system_extract


def test_no_reference_numeric_row_does_not_crash() -> None:
    match = lab_pdf_system_extract._NUMERIC_NO_REFERENCE_RE.match(
        "Notrofil Lenfosit Orani 1.585 ---"
    )
    assert match is not None

    row = lab_pdf_system_extract._row_from_numeric_match(
        match,
        date(2025, 12, 17),
    )

    assert row is not None
    assert row["display_name"] == "Notrofil Lenfosit Orani"
    assert row["normalized_value"] == 1.585
    assert row["unit"] == ""
    assert row["extracted_reference_min"] is None
    assert row["extracted_reference_max"] is None


def test_phone_footer_is_filtered() -> None:
    match = lab_pdf_system_extract._NUMERIC_ROW_RE.match("0 850 240 03 03")
    assert match is not None
    assert lab_pdf_system_extract._row_from_numeric_match(
        match,
        date(2025, 12, 17),
    ) is None
