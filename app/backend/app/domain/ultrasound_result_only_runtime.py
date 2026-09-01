"""Use only the explicit result/impression section for ultrasound reports.

For ultrasound, MediCore intentionally ignores technique, indication and detailed
findings when building the structured report surface used by case evaluation. The
radiologist's explicit SONUÇ/İZLENİM/DEĞERLENDİRME/KANAAT section is the only
clinical text retained. Other modalities continue to use the existing conservative
radiology safety parser.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.api.routes import radiology_reports
from app.domain.radiology_report_parser import analyze_radiology_report

_original_analyze = radiology_reports.analyze_radiology_report

_RESULT_HEADINGS = {
    "sonuc",
    "sonuc ve oneri",
    "sonuc ve oneriler",
    "sonuc onerileri",
    "izlenim",
    "degerlendirme",
    "kanaat",
    "yorum",
    "impression",
    "conclusion",
}
_OTHER_SECTION_HEADINGS = {
    "bulgu",
    "bulgular",
    "findings",
    "teknik",
    "technique",
    "klinik",
    "klinik bilgi",
    "klinik bilgiler",
    "endikasyon",
    "istem nedeni",
    "tetkik istem nedeni",
    "on tani",
    "ontani",
    "anamnez",
    "oyku",
    "hikaye",
    "hasta hikayesi",
    "sikayet",
    "oneriler",
}
_ALL_HEADINGS = _RESULT_HEADINGS | _OTHER_SECTION_HEADINGS


def _fold(value: str) -> str:
    translated = value.translate(
        str.maketrans(
            {
                "ı": "i",
                "İ": "i",
                "ş": "s",
                "Ş": "s",
                "ğ": "g",
                "Ğ": "g",
                "ü": "u",
                "Ü": "u",
                "ö": "o",
                "Ö": "o",
                "ç": "c",
                "Ç": "c",
            }
        )
    )
    normalized = unicodedata.normalize("NFKD", translated)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _heading(value: str) -> str:
    return _compact(_fold(value)).strip(" :.-–—")


def _extract_result_section(text: str) -> str | None:
    """Extract an explicit result section without falling back to other sections."""
    collecting = False
    collected: list[str] = []

    for raw_line in text.replace("\r", "\n").split("\n"):
        line = _compact(raw_line)
        if not line:
            continue

        candidate, separator, inline = line.partition(":")
        candidate_heading = _heading(candidate)
        whole_heading = _heading(line)

        if not collecting:
            if candidate_heading in _RESULT_HEADINGS:
                collecting = True
                if separator and inline.strip():
                    collected.append(inline.strip())
                continue

            dash_match = re.match(r"^(.+?)\s*[-–—]\s*(.+)$", line)
            if dash_match and _heading(dash_match.group(1)) in _RESULT_HEADINGS:
                collecting = True
                collected.append(dash_match.group(2).strip())
            continue

        # A new named section ends the result block. Repeated result headings are
        # allowed because some hospital PDFs split SONUÇ across page fragments.
        if candidate_heading in _ALL_HEADINGS:
            if candidate_heading in _RESULT_HEADINGS:
                if separator and inline.strip():
                    collected.append(inline.strip())
                continue
            break
        if whole_heading in _ALL_HEADINGS:
            if whole_heading in _RESULT_HEADINGS:
                continue
            break

        collected.append(line)

    result_text = "\n".join(collected).strip()
    return result_text or None


def _is_ultrasound(parsed: dict[str, Any]) -> bool:
    modality = str(parsed.get("modality") or "").upper()
    return modality == "ULTRASOUND" or "ULTRASOUND" in modality or "ULTRASON" in modality


def analyze_with_ultrasound_result_only(text: str) -> dict[str, Any]:
    base = analyze_radiology_report(text)
    if not _is_ultrasound(base):
        return _original_analyze(text)

    warnings = list(base.get("warnings", []))
    result_text = _extract_result_section(text)
    if not result_text:
        base["findings"] = []
        base["measurements"] = []
        base["dexa_metrics"] = []
        base["critical_findings"] = []
        base["impression"] = None
        base["summary"] = "Ultrason raporunda açık bir Sonuç/İzlenim bölümü bulunamadı."
        base["safety_version"] = "ultrasound-result-only-v1"
        warnings.append(
            "Ultrason için yalnızca Sonuç/İzlenim bölümü kullanılır; başka bölümden klinik metin alınmadı."
        )
        base["warnings"] = warnings
        return base

    section = analyze_radiology_report(result_text)
    clean_result = _compact(result_text)
    base["findings"] = list(section.get("findings", []))
    base["measurements"] = list(section.get("measurements", []))
    base["dexa_metrics"] = list(section.get("dexa_metrics", []))
    base["critical_findings"] = list(section.get("critical_findings", []))
    base["impression"] = clean_result[:1800]
    base["summary"] = clean_result[:1800]
    base["safety_version"] = "ultrasound-result-only-v1"
    warnings.append(
        "Ultrason çıktısı yalnızca raporun Sonuç/İzlenim bölümünden oluşturuldu."
    )
    base["warnings"] = warnings
    return base


# radiology_reports endpoints resolve this module global at request time, so the
# late runtime patch is sufficient even though api_router was imported earlier.
radiology_reports.analyze_radiology_report = analyze_with_ultrasound_result_only
