from app.domain.fast_pdf_lab_parser import _parse_enabiz_table_data


def test_enabiz_table_rows_are_reconstructed_from_native_columns() -> None:
    table = [
        ["Tarih", "Tahlil", "Sonuç", "Sonuç\nBirimi", "Referans\nDeğeri"],
        ["17.12.2025\n08:41", "Tam Kan Sayımı (hemogram)", None, None, None],
        ["", "HGB", "14.3", "g/dL", "13,5 - 16,9"],
        ["", "Ferritin", "5.7", "µg/L", "22 - 322"],
        ["", "ALT", "55", "U/L", "< 50"],
        ["", "Bakteri", "Negatif", "---", "Negatif"],
        ["", "Dansite", "1.038", "---", ""],
        ["1,003 - 1,030", None, None, None, None],
    ]

    rows, measured_at = _parse_enabiz_table_data(
        table,
        page_number=1,
        current_measured_at=None,
    )

    assert measured_at == "17.12.2025 08:41"
    assert len(rows) == 5

    hgb = rows[0]
    assert hgb["raw_parameter_name"] == "HGB"
    assert hgb["normalized_value"] == 14.3
    assert hgb["unit"] == "g/dL"
    assert hgb["reference_min"] == 13.5
    assert hgb["reference_max"] == 16.9
    assert hgb["needs_review"] is False

    alt = rows[2]
    assert alt["reference_min"] is None
    assert alt["reference_max"] == 50.0
    assert alt["reference_text"] == "< 50"

    bacteria = rows[3]
    assert bacteria["normalized_value"] is None
    assert bacteria["value_type"] == "qualitative"
    assert bacteria["needs_review"] is True

    density = rows[4]
    assert density["reference_min"] == 1.003
    assert density["reference_max"] == 1.03
