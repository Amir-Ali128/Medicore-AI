"""Privacy helpers for laboratory PDF archival.

The analyzer may inspect a source PDF transiently, but archived bytes must not
retain direct patient identifiers. Archival reuses the same fail-closed
sanitizer as the AI provider boundary (``privacy_gateway._sanitize_pdf``):

* every page is rebuilt into a new document (no attachments/embedded files,
  annotations, form widgets, links, document metadata or XMP are carried over);
* text pages are redacted in the content stream (not just covered);
* scanned/image pages are rasterized, OCR-masked locally and re-checked;
* the final bytes go through ``final_leak_check`` (names, TCKN, phone, e-mail,
  IBAN, labelled TCKN residue, metadata and attachments).

Any failure raises ``ValueError`` so the route keeps its 422 contract and never
stores the original upload.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.privacy_gateway import PrivacyViolation, _sanitize_pdf


@dataclass(frozen=True)
class PdfAnonymizationResult:
    content: bytes
    redaction_count: int


def anonymize_lab_pdf(content: bytes, *, known_identifiers: Sequence[str] = ()) -> PdfAnonymizationResult:
    """Return an archive-safe copy of a laboratory PDF or raise ``ValueError``.

    ``known_identifiers`` should be the patient's DB identifiers (see
    ``load_patient_identifiers``); without them names are found only via labels.
    """
    if not content:
        raise ValueError("Boş PDF anonimleştirilemez.")
    if not content.lstrip()[:5].startswith(b"%PDF"):
        raise ValueError("PDF anonimleştirme için açılamadı.")
    try:
        sanitized, counts = _sanitize_pdf(content, known_identifiers)
    except PrivacyViolation:
        # Never include document content or identifiers in the message.
        raise ValueError(
            "PDF içindeki kişisel bilgiler güvenli biçimde kaldırılamadı."
        ) from None
    return PdfAnonymizationResult(content=sanitized, redaction_count=sum(counts.values()))
