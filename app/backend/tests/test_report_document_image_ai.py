from app.domain.report_document_image_ai import (
    _detected_modality,
    _document_kind,
    _extract_json,
    _string_list,
)


def test_report_document_kind_and_modalities_are_normalized():
    assert _document_kind("report document") == "REPORT_DOCUMENT"
    assert _document_kind("medical-image") == "MEDICAL_IMAGE"
    assert _detected_modality("USG") == "ULTRASOUND"
    assert _detected_modality("BT") == "CT"
    assert _detected_modality("MR") == "MRI"
    assert _detected_modality("PETCT") == "PET_CT"


def test_json_parser_accepts_fenced_report_payload():
    payload = _extract_json(
        """```json
        {"document_kind":"REPORT_DOCUMENT","result_text":"Sonuç metni","result_items":["A","B"]}
        ```"""
    )
    assert payload["document_kind"] == "REPORT_DOCUMENT"
    assert payload["result_text"] == "Sonuç metni"


def test_string_list_deduplicates_and_limits_items():
    assert _string_list(["  kist  ", "kist", "dilatasyon"], limit=10) == [
        "kist",
        "dilatasyon",
    ]
