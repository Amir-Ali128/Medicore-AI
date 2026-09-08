"""Fast local parsing for text-based laboratory PDFs.

This module provides a low-latency first pass for e-Nabiz/text PDFs before the
multimodal AI extractor is used. It is deliberately conservative: if the PDF is
not clearly text-based or the deterministic parser does not recover enough lab
rows, callers should fall back to the existing AI extraction path.
"""

from __future__ import annotations

import io
from pathlib import Path
import re
from typing import Any

from app.domain.canonical_lab_model import SourceContext, build_canonical_case, content_sha256

FAST_PDF_WARNING = "fast_pdf_local_parser_v1"
_MIN_TEXT_CHARS = 180
_MIN_ENABIZ_ROWS = 3
_MIN_GENERIC_ROWS = 5


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
                "value_type": "numeric",
                "confidence": 0.99,
                "needs_review": False,
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
    """Return a canonical case for a confidently parsed text PDF, else ``None``.

    Returning ``None`` is intentional and means the caller should continue with
    the existing AI extractor. No clinical interpretation happens here.
    """
    if not content or not _is_pdf(media_type, file_name):
        return None

    text = _extract_text_fast(content)
    if len(text.strip()) < _MIN_TEXT_CHARS:
        return None

    enabiz_like = _looks_like_enabiz(text, file_name)

    # Reuse the mature deterministic text-row parser already used by the legacy
    # text-PDF endpoint. Kept as a lazy import to avoid route import cycles at
    # application startup. A later cleanup can move that parser fully into domain.
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

    source = SourceContext(
        source_type=source_type,
        file_name=file_name[:512],
        source_sha256=content_sha256(content),
        source_record_id=(str(source_record_id).strip()[:256] if source_record_id else None),
        integration_type=None,
    )

    rows = _canonical_rows(parsed_rows)
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
