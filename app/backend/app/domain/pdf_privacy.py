"""Privacy helpers for laboratory PDF archival.

The analyzer may inspect a source PDF transiently, but archived bytes should not
retain direct patient identifiers that are unnecessary for later review.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

import fitz  # PyMuPDF


_DIRECT_IDENTIFIER_MARKERS = (
    "HASTANIN ADI",
    "HASTA ADI",
    "AD SOYAD",
    "ADI SOYADI",
    "AD SOYAD",
    "TC KIMLIK",
    "T C KIMLIK",
    "T.C. KIMLIK",
    "T.C KIMLIK",
    "KIMLIK NO",
    "DOGUM TARIHI",
    "D TARIHI",
    "D.TARIHI",
    "TELEFON",
    "CEP TELEFONU",
    "E POSTA",
    "E-POSTA",
    "EMAIL",
    "ADRES",
    "DOSYA NUMARASI",
    "DOSYA NO",
    "KAYIT NUMARASI",
    "KAYIT NO",
    "PROTOKOL NUMARASI",
    "PROTOKOL NO",
    "HASTA NUMARASI",
    "HASTA NO",
)

_TCKN_RE = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?90\s*)?(?:\(?0?5\d{2}\)?[\s.-]*)\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)")
_DATE_RE = re.compile(r"(?<!\d)(?:0?[1-9]|[12]\d|3[01])[./-](?:0?[1-9]|1[0-2])[./-](?:19|20)\d{2}(?!\d)")

_NAME_LABEL_RE = re.compile(
    r"(?:HASTANIN\s+ADI(?:\s*,?\s*SOYADI)?|HASTA\s+AD(?:I|\s+SOYAD)|ADI\s+SOYADI|AD\s+SOYAD)\s*[:.-]?\s*([^\n\r]{2,100})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PdfAnonymizationResult:
    content: bytes
    redaction_count: int


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text).strip().upper()


def _candidate_names(text: str) -> set[str]:
    names: set[str] = set()
    for match in _NAME_LABEL_RE.finditer(text):
        candidate = re.split(
            r"\b(?:TC\s*KIMLIK|T\.?\s*C\.?\s*KIMLIK|D(?:OGUM)?\s*TARIHI|DOSYA|KAYIT|PROTOKOL)\b",
            match.group(1),
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" :-.,")
        if 2 <= len(candidate) <= 100 and not any(char.isdigit() for char in candidate):
            names.add(candidate)
    return names


def _line_rects_for_markers(page: fitz.Page) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            line_text = " ".join(str(span.get("text", "")) for span in spans).strip()
            if not line_text:
                continue
            folded = _fold(line_text)
            if any(marker in folded for marker in _DIRECT_IDENTIFIER_MARKERS):
                bbox = line.get("bbox")
                if bbox:
                    rects.append(fitz.Rect(bbox))
    return rects


def _search_rects(page: fitz.Page, values: set[str]) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    for value in values:
        if not value.strip():
            continue
        rects.extend(page.search_for(value, quads=False))
    return rects


def anonymize_lab_pdf(content: bytes) -> PdfAnonymizationResult:
    """Remove common direct identifiers from a text-based laboratory PDF.

    Redactions are applied to the PDF content itself, not merely covered by a
    visual overlay, so the removed text is not left searchable underneath.
    The function fails closed when the document cannot be processed.
    """
    if not content:
        raise ValueError("Boş PDF anonimleştirilemez.")

    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # pragma: no cover - library-specific parser errors
        raise ValueError("PDF anonimleştirme için açılamadı.") from exc

    if document.page_count == 0:
        document.close()
        raise ValueError("PDF sayfa içermiyor.")

    full_text = "\n".join(page.get_text("text") for page in document)
    if not full_text.strip():
        document.close()
        raise ValueError(
            "PDF metin tabanlı değil; kişisel bilgiler güvenli biçimde anonimleştirilemedi."
        )

    names = _candidate_names(full_text)
    exact_values: set[str] = set(names)
    exact_values.update(_TCKN_RE.findall(full_text))
    exact_values.update(_EMAIL_RE.findall(full_text))
    exact_values.update(_PHONE_RE.findall(full_text))

    # Exact dates are direct identifiers in this archive context. Age, when
    # separately extracted by the analyzer, remains available as coarse metadata.
    exact_values.update(_DATE_RE.findall(full_text))

    redaction_count = 0
    for page in document:
        rects = _line_rects_for_markers(page)
        rects.extend(_search_rects(page, exact_values))

        seen: set[tuple[float, float, float, float]] = set()
        for rect in rects:
            key = tuple(round(value, 2) for value in (rect.x0, rect.y0, rect.x1, rect.y1))
            if key in seen:
                continue
            seen.add(key)
            padded = fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)
            page.add_redact_annot(padded, fill=(1, 1, 1))
            redaction_count += 1

        if seen:
            page.apply_redactions()

    output = io.BytesIO()
    document.save(output, garbage=4, deflate=True, clean=True)
    document.close()
    sanitized = output.getvalue()

    # Verify the strongest machine-detectable identifiers were actually removed.
    try:
        verification_document = fitz.open(stream=sanitized, filetype="pdf")
        verification_text = "\n".join(page.get_text("text") for page in verification_document)
        verification_document.close()
    except Exception as exc:  # pragma: no cover
        raise ValueError("Anonimleştirilmiş PDF doğrulanamadı.") from exc

    if _TCKN_RE.search(verification_text) or _EMAIL_RE.search(verification_text):
        raise ValueError("PDF içindeki doğrudan kişisel bilgiler tamamen kaldırılamadı.")

    for name in names:
        if name and name.casefold() in verification_text.casefold():
            raise ValueError("PDF içindeki hasta adı tamamen kaldırılamadı.")

    return PdfAnonymizationResult(content=sanitized, redaction_count=redaction_count)
