"""Fast local parsing for text-based laboratory PDFs.

This module provides a low-latency first pass for e-Nabiz/text PDFs before the
multimodal AI extractor is used. It is deliberately conservative: standard
e-Nabiz PDFs are parsed from their native table geometry; other text PDFs fall
back to the legacy deterministic text parser, then to AI when confidence is low.
"""

from __future__ import annotations

import io
from pathlib import Path
import re
from typing import Any

from app.domain.canonical_lab_model import SourceContext, build_canonical_case, content_sha256
from app.domain.document_dates import extract_document_dates, calendar_day
from app.domain.lab_result_classification import parse_lab_observation, parse_source_reference

FAST_PDF_WARNING = "fast_pdf_local_parser_v1"
ENABIZ_TABLE_WARNING = "enabiz_native_table_parser_v2"
_MIN_TEXT_CHARS = 180
_MIN_ENABIZ_ROWS = 3
_MIN_GENERIC_ROWS = 5

_DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")
_TIME_RE = re.compile(r"\b\d{2}:\d{2}\b")


def _fold(value: str) -> str:
    replacements = str.maketrans(
        {
            "İ": "I",
            "ı": "I",
            "Ş": "S",
            "ş": "S",
            "Ğ": "G",
            "ğ": "G",
            "Ü": "U",
            "ü": "U",
            "Ö": "O",
            "ö": "O",
            "Ç": "C",
            "ç": "C",
        }
    )
    return re.sub(r"\s+", " ", value.translate(replacements).upper()).strip()


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _is_pdf(media_type: str | None, file_name: str | None) -> bool:
    declared = (media_type or "").split(";", 1)[0].strip().lower()
    return declared == "application/pdf" or Path(file_name or "").suffix.lower() == ".pdf"


def _extract_text_fast(content: bytes) -> str:
    """Extract selectable text locally, preferring PyMuPDF for speed."""
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=content, filetype="pdf") as document:
            return "\n".join(page.get_text("text") or "" for page in document)
    except Exception:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _looks_like_enabiz(text: str, file_name: str) -> bool:
    folded_text = _fold(text)
    folded_name = _fold(file_name)
    name_hint = "E NABIZ" in folded_name or "ENABIZ" in folded_name or "NABIZ" in folded_name
    table_markers = sum(
        marker in folded_text
        for marker in ("TETKIK", "SONUC", "BIRIM", "REFERANS")
    )
    content_hint = "E NABIZ" in folded_text or "ENABIZ" in folded_text
    return name_hint or content_hint or table_markers >= 3


def _parse_numeric_value(raw_value: str, unit: str | None = None) -> tuple[float | None, str | None]:
    parsed = parse_lab_observation(raw_value, unit)
    return (float(parsed.number), parsed.comparator) if parsed.number is not None else (None, None)


def _parse_reference(reference_text: str) -> tuple[float | None, float | None, str | None]:
    text = _clean_cell(reference_text)
    parsed = parse_source_reference(text)
    if parsed.error:
        return None, None, text or None
    return (float(parsed.low) if parsed.low is not None else None,
            float(parsed.high) if parsed.high is not None else None, text)


def _merge_measured_at(current: str | None, cell: str) -> str | None:
    text = _clean_cell(cell)
    if not text:
        return current

    date_match = _DATE_RE.search(text)
    time_match = _TIME_RE.search(text)
    if date_match and time_match:
        return f"{date_match.group(0)} {time_match.group(0)}"
    if date_match:
        return date_match.group(0)
    if time_match and current:
        current_date = _DATE_RE.search(current)
        if current_date:
            return f"{current_date.group(0)} {time_match.group(0)}"
    return current


def _looks_like_table_header(row: list[Any]) -> bool:
    cells = [_fold(_clean_cell(cell)) for cell in row[:5]]
    if len(cells) < 5:
        return False
    return (
        cells[1] == "TAHLIL"
        and "SONUC" in cells[2]
        and ("BIRIM" in cells[3] or "SONUC" in cells[3])
        and "REFERANS" in cells[4]
    )


def _parse_enabiz_table_data(
    table_data: list[list[Any]],
    *,
    page_number: int,
    current_measured_at: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Convert one e-Nabiz five-column table into canonical-ready rows."""
    if not table_data or not _looks_like_table_header(table_data[0]):
        return [], current_measured_at

    rows: list[dict[str, Any]] = []
    previous_result: dict[str, Any] | None = None

    for raw_row in table_data[1:]:
        padded = list(raw_row[:5]) + [None] * max(0, 5 - len(raw_row))
        date_cell, name_cell, result_cell, unit_cell, reference_cell = padded[:5]

        date_text = _clean_cell(date_cell)
        name = _clean_cell(name_cell)
        raw_value = _clean_cell(result_cell)
        unit = _clean_cell(unit_cell)
        reference = _clean_cell(reference_cell)

        current_measured_at = _merge_measured_at(current_measured_at, date_text)

        # Wrapped references can appear in the first column on a continuation row.
        if not name and not raw_value and date_text and previous_result is not None:
            if not previous_result.get("reference_text"):
                ref_min, ref_max, ref_text = _parse_reference(date_text)
                if ref_text and not _DATE_RE.search(date_text) and not _TIME_RE.fullmatch(date_text):
                    previous_result["reference_min"] = ref_min
                    previous_result["reference_max"] = ref_max
                    previous_result["reference_text"] = ref_text
            continue

        # Section/group rows carry a date/title but no observed value.
        if name and not raw_value:
            previous_result = None
            continue

        if not name or not raw_value:
            continue

        normalized_value, comparator = _parse_numeric_value(raw_value, unit)
        ref_min, ref_max, ref_text = _parse_reference(reference)
        qualitative = normalized_value is None

        row = {
            "raw_parameter_name": name,
            "raw_value": raw_value,
            "normalized_value": normalized_value if not comparator else None,
            "unit": None if unit in {"", "---"} else unit,
            "reference_min": ref_min,
            "reference_max": ref_max,
            "reference_text": ref_text,
            "measured_at": current_measured_at,
            "source_page": page_number,
            "value_type": "censored" if comparator else "qualitative" if qualitative else "numeric",
            # Comparator values are not exact measurements; qualitative results
            # stay visible but remain on the review side of the trust boundary.
            "needs_review": qualitative or comparator is not None,
            "confidence": 0.95 if qualitative or comparator is not None else 0.995,
        }
        rows.append(row)
        previous_result = row

    return rows, current_measured_at


def _extract_enabiz_table_rows(content: bytes) -> list[dict[str, Any]]:
    """Parse standard e-Nabiz PDF tables directly from local PDF geometry."""
    try:
        import fitz  # PyMuPDF

        rows: list[dict[str, Any]] = []
        current_measured_at: str | None = None
        with fitz.open(stream=content, filetype="pdf") as document:
            for page_number, page in enumerate(document, start=1):
                page_dates = extract_document_dates(page.get_text("text") or "")
                finder = page.find_tables()
                for table in finder.tables:
                    parsed, current_measured_at = _parse_enabiz_table_data(
                        table.extract(),
                        page_number=page_number,
                        current_measured_at=current_measured_at,
                    )
                    for row in parsed:
                        row.update({key: value.isoformat() for key, value in page_dates.items()
                                    if key in {"event_date", "specimen_date", "result_date", "document_date"}})
                    rows.extend(parsed)
        return rows
    except Exception:
        return []


def _extract_source_reference_rows(content: bytes) -> list[dict[str, Any]]:
    """Read explicit 3/4-column source tables, never diagnostic prose.

    Unsupported lab layouts defer the entire local result to existing readers;
    no partial table or inferred date/reference is returned as a complete read.
    """
    import pymupdf
    names = {'TEST', 'TETKIK', 'TAHLIL', 'PARAMETRE'}
    results = {'SONUC', 'RESULT', 'VALUE'}
    references = {'REFERANS', 'REFERANS ARALIGI', 'REFERENCE', 'REFERENCE RANGE'}
    units = {'BIRIM', 'UNIT'}
    output = []
    try:
        with pymupdf.open(stream=content, filetype='pdf') as document:
            for number, page in enumerate(document, 1):
                if page.get_images(full=True):
                    return []
                dates = extract_document_dates(page.get_text() or '')
                tables = [table.extract() for table in page.find_tables().tables]
                document_days = {dates['document_date']} if dates.get('document_date') else set()
                for cells in tables:
                    if not cells or len(cells[0]) != 2 or _fold(_clean_cell(cells[0][0])) != 'BELGE':
                        continue
                    if not any(_fold(_clean_cell(row[0])) == 'BELGE TURU' for row in cells if len(row) == 2):
                        continue
                    for row in cells:
                        if len(row) == 2 and _fold(_clean_cell(row[0])) == 'TARIH / SAAT':
                            stamp = _clean_cell(row[1]).split()
                            if stamp and (day := calendar_day(stamp[0])) is not None:
                                document_days.add(day)
                if len(document_days) > 1:
                    return []
                if document_days:
                    dates['document_date'] = next(iter(document_days))
                for cells in tables:
                    if not cells:
                        continue
                    header = [_fold(_clean_cell(cell)) for cell in cells[0]]
                    if not header or header[0] not in names:
                        continue
                    if len(header) not in (3, 4) or header[1] not in results or header[-1] not in references:
                        return []
                    if len(header) == 4 and header[2] not in units:
                        return []
                    for source_row in cells[1:]:
                        if not any(_clean_cell(cell) for cell in source_row):
                            continue
                        if len(source_row) != len(header):
                            return []
                        name, value = map(_clean_cell, source_row[:2])
                        if not name or not value:
                            return []
                        unit = _clean_cell(source_row[2]) if len(header) == 4 else None
                        parsed = parse_lab_observation(value, unit)
                        unit = unit or parsed.inline_unit
                        raw_reference = _clean_cell(source_row[-1]) or None
                        ref = parse_source_reference(raw_reference)
                        output.append({
                            'raw_parameter_name': name, 'raw_value': value,
                            'normalized_value': float(parsed.number) if parsed.number is not None and not parsed.comparator else None,
                            'unit': unit, 'reference_text': raw_reference,
                            'reference_min': float(ref.low) if ref.low is not None else None,
                            'reference_max': float(ref.high) if ref.high is not None else None,
                            'source_page': number, 'measured_at': None,
                            'needs_review': bool(parsed.error or parsed.comparator or ref.error),
                            'confidence': .995,
                            **{key: value.isoformat() for key, value in dates.items()
                               if key in {'event_date', 'specimen_date', 'result_date', 'document_date'}},
                        })
    except (RuntimeError, ValueError, TypeError):
        return []
    return output


def _canonical_rows(parsed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in parsed_rows:
        rows.append(
            {
                "raw_parameter_name": row.get("raw_parameter_name"),
                "raw_value": row.get("raw_value"),
                "normalized_value": row.get("normalized_value"),
                "unit": row.get("unit") or row.get("extracted_unit"),
                "reference_min": row.get("reference_min", row.get("extracted_reference_min")),
                "reference_max": row.get("reference_max", row.get("extracted_reference_max")),
                "reference_text": row.get("reference_text"),
                "measured_at": row.get("measured_at"),
                "event_date": row.get("event_date"),
                "specimen_date": row.get("specimen_date"),
                "result_date": row.get("result_date"),
                "document_date": row.get("document_date"),
                "uploaded_at": row.get("uploaded_at"),
                "source_page": row.get("source_page"),
                "value_type": row.get("value_type") or "numeric",
                "confidence": row.get("confidence", 0.99),
                "needs_review": bool(row.get("needs_review", False)),
            }
        )
    return rows


def try_fast_pdf_lab_case(
    *,
    content: bytes,
    media_type: str,
    file_name: str,
    source_type: str,
    source_record_id: str | None = None,
) -> dict[str, Any] | None:
    """Return a canonical case for a confidently parsed text PDF, else ``None``."""
    if not content or not _is_pdf(media_type, file_name):
        return None

    text = _extract_text_fast(content)
    if len(text.strip()) < _MIN_TEXT_CHARS:
        return None

    enabiz_like = _looks_like_enabiz(text, file_name)
    document_dates = extract_document_dates(text)

    def preserve_explicit_dates(rows: list[dict[str, Any]]) -> None:
        # A unique labeled date in the document can apply to its rows. Per-page
        # explicit dates remain authoritative when a PDF contains several sets.
        for row in rows:
            for key in ("event_date", "specimen_date", "result_date", "document_date"):
                if not row.get(key) and key in document_dates:
                    row[key] = document_dates[key].isoformat()

    source = SourceContext(
        source_type=source_type,
        file_name=file_name[:512],
        source_sha256=content_sha256(content),
        source_record_id=(str(source_record_id).strip()[:256] if source_record_id else None),
        integration_type=None,
    )

    # Standard selectable-text e-Nabiz exports are digitally generated tables.
    # Parse table geometry locally instead of sending the whole PDF to Astra.
    if enabiz_like:
        table_rows = _extract_enabiz_table_rows(content)
        if table_rows:
            patient = None
            try:
                from app.api.routes.lab_analysis import _parse_patient_metadata_from_text

                patient = _parse_patient_metadata_from_text(text)
            except Exception:
                patient = None

            rows = _canonical_rows(table_rows)
            preserve_explicit_dates(rows)
            return build_canonical_case(
                source=source,
                rows=rows,
                patient_age=getattr(patient, "age", None),
                patient_sex=getattr(patient, "sex", None),
                report_date=rows[0].get("measured_at") if rows else None,
                warnings=[
                    FAST_PDF_WARNING,
                    ENABIZ_TABLE_WARNING,
                    f"local_parser_rows={len(rows)}",
                ],
                extraction_confidence=0.995,
                default_confidence=0.995,
            )

    source_rows = _extract_source_reference_rows(content)
    if source_rows:
        rows = _canonical_rows(source_rows)
        preserve_explicit_dates(rows)
        result = build_canonical_case(
            source=source, rows=rows, warnings=[FAST_PDF_WARNING, 'source_reference_table_parser_v1',
                                              f'local_parser_rows={len(rows)}'],
            extraction_confidence=.995, default_confidence=.995,
        )
        result['visible_row_count'] = len(rows)
        return result

    # Legacy deterministic parser remains useful for non-standard text PDFs.
    try:
        from app.api.routes.lab_analysis import (
            _parse_lab_values_from_text,
            _parse_patient_metadata_from_text,
        )

        parsed_rows = _parse_lab_values_from_text(text)
        patient = _parse_patient_metadata_from_text(text)
    except Exception:
        return None

    minimum_rows = _MIN_ENABIZ_ROWS if enabiz_like else _MIN_GENERIC_ROWS
    if len(parsed_rows) < minimum_rows:
        return None

    rows = _canonical_rows(parsed_rows)
    preserve_explicit_dates(rows)
    if not rows:
        return None

    return build_canonical_case(
        source=source,
        rows=rows,
        patient_age=getattr(patient, "age", None),
        patient_sex=getattr(patient, "sex", None),
        report_date=rows[0].get("measured_at"),
        warnings=[FAST_PDF_WARNING, f"local_parser_rows={len(rows)}"],
        extraction_confidence=0.99,
        default_confidence=0.99,
    )
