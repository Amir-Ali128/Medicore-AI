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
from app.domain.document_dates import extract_document_dates
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


def _parse_reference(reference_text: str, unit: str | None = None) -> tuple[float | None, float | None, str | None]:
    """Parse a printed reference; the source text is always preserved.

    Sex-specific or otherwise unparsed text keeps ``reference_text`` with no
    bounds so the deterministic classifier can select it with patient context.
    """
    text = _clean_cell(reference_text)
    if text in {"---", "--", "-"}:
        return None, None, None
    parsed = parse_source_reference(text, unit=unit)
    if parsed.error:
        return None, None, text or None
    return (float(parsed.low) if parsed.low is not None else None,
            float(parsed.high) if parsed.high is not None else None, text)


_SEX_LABEL_HINT = re.compile(r"(?i)\b(?:erkek|kad[ıi]n|male|female)\b|(?<![A-Za-z])[EK]\s*:")


def _append_wrapped_reference(previous: dict[str, Any], fragment: str) -> None:
    """Attach a reference fragment wrapped onto the next e-Nabız table line."""
    fragment = _clean_cell(fragment)
    if not fragment or _DATE_RE.search(fragment) or _TIME_RE.fullmatch(fragment):
        return
    current = previous.get("reference_text")
    if not current:
        combined = fragment
    elif (
        previous.get("reference_min") is None and previous.get("reference_max") is None
    ) or _SEX_LABEL_HINT.search(current) or _SEX_LABEL_HINT.search(fragment):
        # e.g. "0,5 -" + "1,5" or "Erkek: 13-17" + "Kadın: 12-15".
        combined = f"{current} {fragment}"
    else:
        return
    ref_min, ref_max, ref_text = _parse_reference(combined, previous.get("unit"))
    previous["reference_min"] = ref_min
    previous["reference_max"] = ref_max
    previous["reference_text"] = ref_text


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

        # Wrapped references can appear in the first column or in the reference
        # column of a continuation row (long or sex-specific references).
        if not name and not raw_value and previous_result is not None and (date_text or reference):
            for fragment in (date_text, reference):
                if fragment:
                    _append_wrapped_reference(previous_result, fragment)
            continue

        # Section/group rows carry a date/title but no observed value.
        if name and not raw_value:
            previous_result = None
            continue

        if not name or not raw_value:
            continue

        normalized_value, comparator = _parse_numeric_value(raw_value, unit)
        ref_min, ref_max, ref_text = _parse_reference(reference, None if unit in {"", "---"} else unit)
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
                "source_flag": row.get("source_flag"),
            }
        )
    return rows


_MIN_LEGACY_QUALITY = 0.6


def legacy_parse_quality(rows: list[dict[str, Any]]) -> float:
    """Share of rows that carry both a printed unit and a usable reference."""
    if not rows:
        return 0.0
    good = sum(
        1
        for row in rows
        if row.get("unit") and row.get("reference_text")
        and not row.get("needs_review")
    )
    return good / len(rows)


def _first_document_date(rows: list[dict[str, Any]]) -> str | None:
    for row in rows:
        for key in ("specimen_date", "event_date", "result_date", "document_date"):
            if row.get(key):
                return row[key]
    return None


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

    # Legacy deterministic parser remains useful for non-standard text PDFs.
    try:
        from app.api.routes.lab_analysis import (
            _parse_lab_values_from_text,
            _parse_patient_metadata_from_text,
        )

        patient = _parse_patient_metadata_from_text(text)
        parsed_rows = _parse_lab_values_from_text(text, patient_sex=getattr(patient, "sex", None))
    except Exception:
        return None

    minimum_rows = _MIN_ENABIZ_ROWS if enabiz_like else _MIN_GENERIC_ROWS
    if len(parsed_rows) < minimum_rows:
        return None

    rows = _canonical_rows(parsed_rows)
    preserve_explicit_dates(rows)
    if not rows:
        return None

    quality = legacy_parse_quality(rows)
    if quality < _MIN_LEGACY_QUALITY:
        # Too many rows lack a printed reference/unit: let the AI reader try
        # instead of locking in a low-quality local read.
        return None

    return build_canonical_case(
        source=source,
        rows=rows,
        patient_age=getattr(patient, "age", None),
        patient_sex=getattr(patient, "sex", None),
        report_date=_first_document_date(rows),
        warnings=[FAST_PDF_WARNING, f"local_parser_rows={len(rows)}", f"local_parser_quality={quality:.2f}"],
        extraction_confidence=round(0.7 + 0.29 * quality, 3),
        default_confidence=0.9,
    )
