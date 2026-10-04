"""Source dates survive extraction without becoming the file's upload date."""

import asyncio
from datetime import date
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.canonical_lab_model import SourceContext, canonicalize_row
from app.domain.claude_lab_extraction_service import ClaudeLabExtractionService
from app.domain import fast_pdf_lab_parser
from app.domain.lab_document_ingestion import RawLabRow, validate_merge
from app.schemas.extraction import ExtractedLabValue


def source_row(**dates):
    return {
        "raw_parameter_name": "Ferritin",
        "raw_value": "5",
        "normalized_value": 5,
        "unit": "ng/mL",
        "reference_text": "15–150",
        "reference_min": 15,
        "reference_max": 150,
        "confidence": 0.99,
        **dates,
    }


def test_extraction_dto_and_canonical_row_keep_sample_release_and_upload_distinct():
    dto = ExtractedLabValue.model_validate(source_row(
        measured_at="2026-10-02", event_date="2026-10-02",
        specimen_date="2026-10-02", result_date="2026-10-04",
        document_date="2026-10-04", uploaded_at="2026-10-04T10:30:00Z",
    ))
    row = canonicalize_row(dto.model_dump(mode="json"), source=SourceContext("photo"),
                           default_confidence=0.99)
    assert row["specimen_date"] == "2026-10-02"
    assert row["event_date"] == "2026-10-02"
    assert row["result_date"] == row["document_date"] == "2026-10-04"
    assert row["uploaded_at"] == "2026-10-04T10:30:00Z"


def test_unlabeled_measured_at_does_not_invent_semantic_dates():
    row = canonicalize_row(source_row(measured_at="2026-10-02"),
                           source=SourceContext("photo"), default_confidence=0.99)
    assert row["measured_at"] == "2026-10-02"
    assert all(row[key] is None for key in (
        "event_date", "specimen_date", "result_date", "document_date", "uploaded_at",
    ))


def test_unit_typography_survives_ingestion_and_backend_classification():
    from app.api.routes.simple_case import _lab_inputs_from_extracted

    case = validate_merge([RawLabRow(source_row(
        raw_parameter_name="TIBC", raw_value="445", normalized_value=445,
        unit="µg/dL", reference_unit="ug / dL", reference_text="250–450",
        reference_min=250, reference_max=450,
    ), 1, 1)], SourceContext("photo"))
    assert "reference_unit_mismatch" not in case["labs"][0]["ingestion_reasons"]
    labs = _lab_inputs_from_extracted(case, source_file_name="lab.png", extraction_source="test")
    assert labs[0].status == "NORMAL"


@pytest.mark.parametrize("changed_date", ["specimen_date", "result_date", "event_date", "document_date"])
def test_same_observation_text_on_distinct_source_dates_is_not_deduplicated(changed_date):
    first = source_row(**{changed_date: "2026-10-02"})
    second = source_row(**{changed_date: "2026-10-04"})
    case = validate_merge([RawLabRow(first, 1, 1), RawLabRow(second, 2, 1)],
                          SourceContext("photo"))
    assert len(case["labs"]) == 2
    assert [row[changed_date] for row in case["labs"]] == ["2026-10-02", "2026-10-04"]


def test_reuploaded_overlap_keeps_one_observation_and_provenance():
    first = source_row(specimen_date="2026-10-02", result_date="2026-10-04",
                       uploaded_at="2026-10-04T10:00:00Z")
    second = {**first, "uploaded_at": "2026-10-04T10:01:00Z"}
    case = validate_merge([RawLabRow(first, 1, 1), RawLabRow(second, 2, 1)],
                          SourceContext("photo"))
    assert len(case["labs"]) == 1
    assert case["labs"][0]["source_locations"] == [
        {"page": 1, "row": 1}, {"page": 2, "row": 1},
    ]


def fast_case(monkeypatch, text, rows):
    monkeypatch.setattr(fast_pdf_lab_parser, "_extract_text_fast", lambda content: text)
    monkeypatch.setattr(fast_pdf_lab_parser, "_extract_enabiz_table_rows", lambda content: rows)
    return fast_pdf_lab_parser.try_fast_pdf_lab_case(
        content=b"fake PDF; local parser mocked", media_type="application/pdf",
        file_name="enabiz.pdf", source_type="file_upload",
    )


def test_fast_pdf_reads_labeled_header_dates_and_preserves_page_specific_dates(monkeypatch):
    text = "Numune alma tarihi: 02.10.2026\nSonuç onay tarihi: 04.10.2026\n" + "Tetkik Sonuç Birim Referans " * 8
    case = fast_case(monkeypatch, text, [
        source_row(measured_at="04.10.2026"),
        source_row(raw_parameter_name="Serum Demir", specimen_date="2026-10-03"),
    ])
    first, second = case["labs"]
    assert first["specimen_date"] == "2026-10-02"
    assert first["result_date"] == "2026-10-04"
    assert first["measured_at"] == "04.10.2026"
    assert second["specimen_date"] == "2026-10-03"
    assert first["uploaded_at"] is None


def test_fast_pdf_does_not_assign_conflicting_or_unlabeled_dates(monkeypatch):
    text = "Numune tarihi: 02.10.2026\nNumune tarihi: 03.10.2026\n04.10.2026\n" + "Tetkik Sonuç Birim Referans " * 8
    case = fast_case(monkeypatch, text, [source_row(measured_at="04.10.2026")])
    row = case["labs"][0]
    assert row["specimen_date"] is row["result_date"] is row["uploaded_at"] is None


def test_malformed_optional_date_does_not_drop_other_dates_or_table():
    service = object.__new__(ClaudeLabExtractionService)
    result = service._parse_result(json.dumps({"values": [source_row(
        specimen_date="not a date", result_date="2026-10-04",
    )]}), "lab.png")
    assert len(result.values) == 1
    assert result.values[0].specimen_date is None
    assert result.values[0].result_date == date(2026, 10, 4)
    assert result.values[0].needs_review


def test_claude_completeness_merge_does_not_merge_different_specimens():
    def response(sample_date):
        text = json.dumps({"visible_row_count": 2, "values": [source_row(
            specimen_date=sample_date, result_date="2026-10-04",
        )]})
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    service = object.__new__(ClaudeLabExtractionService)
    service._model = "mocked"
    service._client = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=[
        response("2026-10-02"), response("2026-10-03"),
    ])))
    service._guard = SimpleNamespace(call=lambda operation: operation())
    result = asyncio.run(service.extract_from_bytes(b"mock image", "lab.png", "image/png"))
    assert [row.specimen_date for row in result.values] == [date(2026, 10, 2), date(2026, 10, 3)]
