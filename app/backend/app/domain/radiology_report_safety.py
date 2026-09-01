"""Conservative safety and presentation layer for radiology text parsing.

Only the explicit BULGULAR/FINDINGS section is used for structured report
findings. Clinical history, indication, technique, conclusion/impression and
other sections are never copied into the finding list.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from app.domain.radiology_report_parser import analyze_radiology_report

SAFETY_VERSION = "radiology-findings-only-v3"

_CRITICAL_VARIANTS: dict[str, tuple[str, ...]] = {
    "Pnömotoraks": ("pnomotoraks",),
    "Pulmoner emboli": ("pulmoner emboli", "emboli ile uyumlu"),
    "İntrakraniyal kanama": (
        "intrakraniyal kanama",
        "intraserebral kanama",
        "intraparenkimal hemoraji",
        "intraparenkimal hematom",
        "subaraknoid kanama",
        "subdural hematom",
        "epidural hematom",
    ),
    "Orta hat şifti": ("orta hat sifti", "midline shift"),
    "Kitle etkisi": ("kitle etkisi", "mass effect"),
    "Akut enfarkt": ("akut enfarkt", "akut infarkt", "akut iskemi"),
    "Aort diseksiyonu": ("aort diseksiyonu", "diseksiyon flebi"),
    "Serbest hava": ("serbest hava", "pnomoperitoneum"),
    "Akut obstrüksiyon": ("akut obstruksiyon", "barsak obstruksiyonu", "ileus"),
    "Aktif kanama": ("aktif kanama", "ekstravazasyon"),
    "Malignite şüphesi": (
        "malignite supheli",
        "malignite acisindan supheli",
        "malign kitle",
    ),
}

_FINDINGS_HEADINGS = {"bulgu", "bulgular", "findings"}
_STOP_HEADINGS = {
    "sonuc",
    "izlenim",
    "degerlendirme",
    "impression",
    "teknik",
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
    "öneriler",
}

_NEGATION_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bsaptanma(?:di|mistir|maktadir)\b",
        r"\bizlenme(?:di|mistir|mektedir)\b",
        r"\bgorulme(?:di|mistir|mektedir)\b",
        r"\brastlanma(?:di|mistir)\b",
        r"\btespit edilme(?:di|mistir)\b",
        r"\bmevcut degildir\b",
        r"\bmevcut degil\b",
        r"\byoktur\b",
        r"\byok\b",
        r"\bnegatif\b",
        r"\blehine bulgu yok\b",
        r"\bekarte edilmistir\b",
        r"\bdislanmistir\b",
    )
)


def _ascii_fold(value: str) -> str:
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
    return _compact(_ascii_fold(value)).strip(" :.-")


def _is_negated_clause(clause: str) -> bool:
    folded = f" {_compact(_ascii_fold(clause))} "
    return any(pattern.search(folded) for pattern in _NEGATION_PATTERNS)


def _extract_findings_section(text: str) -> str | None:
    """Return only the explicit Bulgular/Findings block.

    Supports both a standalone heading and an inline form such as
    ``Bulgular: Karaciğer ...``. Collection stops at the next known report
    section. If no findings heading exists, no other section is substituted.
    """
    lines = text.replace("\r", "\n").split("\n")
    collecting = False
    collected: list[str] = []

    for raw_line in lines:
        line = _compact(raw_line)
        if not line:
            if collecting and collected:
                # Keep section continuity across a single blank line; many PDFs
                # insert visual spacing inside the findings block.
                continue
            continue

        heading_candidate, separator, inline = line.partition(":")
        normalized_heading = _heading(heading_candidate)

        if not collecting:
            if normalized_heading in _FINDINGS_HEADINGS:
                collecting = True
                if separator and inline.strip():
                    collected.append(inline.strip())
                continue
            # Also accept headings rendered as "BULGULAR - ...".
            dash_match = re.match(r"^\s*(bulgu(?:lar)?|findings)\s*[-–—]\s*(.+)$", line, flags=re.IGNORECASE)
            if dash_match:
                collecting = True
                collected.append(dash_match.group(2).strip())
            continue

        # Once inside findings, stop before conclusion/technique/history/etc.
        if normalized_heading in _STOP_HEADINGS or normalized_heading in _FINDINGS_HEADINGS:
            if normalized_heading in _FINDINGS_HEADINGS and separator and inline.strip():
                collected.append(inline.strip())
            elif normalized_heading in _FINDINGS_HEADINGS:
                continue
            else:
                break
        else:
            # Handle headings without a colon, e.g. a line containing only
            # "SONUÇ" or "İZLENİM".
            whole_heading = _heading(line)
            if whole_heading in _STOP_HEADINGS:
                break
            collected.append(line)

    findings_text = "\n".join(collected).strip()
    return findings_text or None


def _clauses(text: str) -> list[str]:
    pieces = re.split(
        r"[.;\n]+|\s*,\s*|\s+(?:ancak|fakat|lakin|bununla birlikte|buna karsin|buna karşılık)\s+",
        _compact(text),
        flags=re.IGNORECASE,
    )
    return [piece.strip() for piece in pieces if piece.strip()]


def _term_has_positive_evidence(text: str, variants: Iterable[str]) -> bool:
    folded_variants = tuple(_ascii_fold(item) for item in variants)
    for clause in _clauses(text):
        folded_clause = f" {_compact(_ascii_fold(clause))} "
        if not any(variant in folded_clause for variant in folded_variants):
            continue
        if _is_negated_clause(clause):
            continue
        return True
    return False


def _apply_critical_evidence(text: str, findings: list[dict[str, Any]]) -> list[str]:
    supported = [
        label
        for label, variants in _CRITICAL_VARIANTS.items()
        if _term_has_positive_evidence(text, variants)
    ]

    for finding in findings:
        finding_text = f" {_compact(_ascii_fold(str(finding.get('text', ''))))} "
        matched_labels = [
            label
            for label in supported
            if any(
                _ascii_fold(variant) in finding_text
                for variant in _CRITICAL_VARIANTS[label]
            )
            and not _is_negated_clause(str(finding.get("text", "")))
        ]
        if matched_labels:
            finding["classification"] = "critical"
            finding["is_critical"] = True
            finding["matched_terms"] = sorted(
                set(finding.get("matched_terms", []) + matched_labels)
            )
    return supported


def _findings_summary(findings: list[dict[str, Any]]) -> str:
    texts = [_compact(str(item.get("text", ""))) for item in findings]
    texts = [item for item in texts if item]
    if not texts:
        return "Bulgular bölümü bulundu ancak yapılandırılabilir bulgu çıkarılamadı."
    summary = " ".join(texts)
    return summary[:1800] + ("…" if len(summary) > 1800 else "")


def analyze_radiology_report_safely(text: str) -> dict[str, Any]:
    """Parse report metadata but expose only explicit findings-section content."""
    # Whole text is used only for modality/body-region inference. It is never
    # used as the source of structured findings.
    result = analyze_radiology_report(text)
    findings_text = _extract_findings_section(text)

    warnings = list(result.get("warnings", []))
    if findings_text is None:
        result["findings"] = []
        result["measurements"] = []
        result["critical_findings"] = []
        result["impression"] = None
        result["summary"] = "Raporda açık bir Bulgular/Findings bölümü bulunamadı."
        result["safety_version"] = SAFETY_VERSION
        warnings.append(
            "Yalnızca Bulgular/Findings bölümü işlenir; diğer rapor bölümleri bulgu olarak kullanılmadı."
        )
        result["warnings"] = warnings
        return result

    section_result = analyze_radiology_report(findings_text)
    findings = list(section_result.get("findings", []))
    supported_labels = _apply_critical_evidence(findings_text, findings)

    result["findings"] = findings
    result["measurements"] = list(section_result.get("measurements", []))
    result["dexa_metrics"] = list(section_result.get("dexa_metrics", []))
    result["critical_findings"] = supported_labels
    # Conclusion/impression is deliberately suppressed: the report surface is
    # now findings-only by product requirement.
    result["impression"] = None
    result["summary"] = _findings_summary(findings)
    result["safety_version"] = SAFETY_VERSION

    warnings.append(
        "Yapılandırılmış rapor çıktısı yalnızca Bulgular/Findings bölümünden oluşturuldu."
    )
    if supported_labels:
        warnings.append("Bulgular bölümünde kritik ifade saptandı; hekim değerlendirmesi gerekir.")
    result["warnings"] = warnings
    return result
