"""Conservative safety and presentation layer for radiology text parsing."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from app.domain.radiology_report_parser import analyze_radiology_report

SAFETY_VERSION = "radiology-evidence-safety-v2"

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

_EXCLUDED_SECTION_HEADINGS = {
    "klinik", "klinik bilgi", "klinik bilgiler", "endikasyon", "istem nedeni",
    "tetkik istem nedeni", "on tani", "ontani", "preoperatif tani", "anamnez",
    "oyku", "hikaye", "hasta hikayesi", "sikayet", "teknik", "tetkik",
}

_ACTIVE_SECTION_HEADINGS = {
    "bulgu", "bulgular", "findings", "sonuc", "izlenim", "degerlendirme", "impression",
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

_INDICATION_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b(?:suphesi|on tanisi|ontanisi|dusuncesi)\s+(?:ile|nedeniyle)\b",
        r"\b(?:acisindan|yonunden)\s+(?:degerlendirme|tetkik)\b",
        r"\b(?:ekarte etmek|dislamak)\s+(?:icin|amaciyla)\b",
        r"\b(?:arastirilmasi|degerlendirilmesi)\s+(?:icin|amaciyla)\b",
    )
)


def _ascii_fold(value: str) -> str:
    translated = value.translate(str.maketrans({
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    }))
    normalized = unicodedata.normalize("NFKD", translated)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _heading(value: str) -> str:
    return _compact(_ascii_fold(value)).strip(" :.-")


def _clauses(sentence: str) -> list[str]:
    pieces = re.split(
        r"[.;\n]+|\s*,\s*|\s+(?:ancak|fakat|lakin|bununla birlikte|buna karsin|buna karşılık)\s+",
        _compact(sentence),
        flags=re.IGNORECASE,
    )
    return [piece.strip() for piece in pieces if piece.strip()]


def _is_negated_clause(clause: str) -> bool:
    folded = f" {_compact(_ascii_fold(clause))} "
    return any(pattern.search(folded) for pattern in _NEGATION_PATTERNS)


def _looks_like_indication(clause: str) -> bool:
    folded = f" {_compact(_ascii_fold(clause))} "
    return any(pattern.search(folded) for pattern in _INDICATION_PATTERNS)


def _iter_evidence_clauses(text: str) -> Iterable[tuple[str, bool]]:
    excluded_section = False
    active_section = False

    for raw_line in text.replace("\r", "\n").split("\n"):
        line = _compact(raw_line)
        if not line:
            continue

        heading_candidate, separator, inline = line.partition(":")
        normalized_heading = _heading(heading_candidate)

        if normalized_heading in _EXCLUDED_SECTION_HEADINGS:
            excluded_section = True
            active_section = False
            if separator and inline.strip():
                continue
            continue

        if normalized_heading in _ACTIVE_SECTION_HEADINGS:
            excluded_section = False
            active_section = True
            if separator and inline.strip():
                line = inline.strip()
            else:
                continue

        if excluded_section:
            continue

        for sentence in re.split(r"(?<=[.!?])\s+", line):
            for clause in _clauses(sentence):
                yield clause, active_section


def _term_has_positive_evidence(text: str, variants: Iterable[str]) -> bool:
    folded_variants = tuple(_ascii_fold(item) for item in variants)
    fallback_candidate = False
    for clause, active_section in _iter_evidence_clauses(text):
        folded_clause = f" {_compact(_ascii_fold(clause))} "
        if not any(variant in folded_clause for variant in folded_variants):
            continue
        if _is_negated_clause(clause):
            continue
        if _looks_like_indication(clause) and not active_section:
            continue
        if active_section:
            return True
        fallback_candidate = True
    return fallback_candidate


def _active_clause_keys(text: str) -> set[str]:
    active = {_heading(clause) for clause, is_active in _iter_evidence_clauses(text) if is_active}
    return {item for item in active if item}


def _filter_findings_to_active_sections(text: str, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_keys = _active_clause_keys(text)
    if not active_keys:
        return findings

    filtered: list[dict[str, Any]] = []
    for finding in findings:
        finding_text = str(finding.get("text", ""))
        key = _heading(finding_text)
        if key in active_keys or any(key in active or active in key for active in active_keys if len(active) > 8):
            filtered.append(finding)
    return filtered


def _apply_critical_evidence(text: str, findings: list[dict[str, Any]]) -> list[str]:
    supported = [
        label for label, variants in _CRITICAL_VARIANTS.items()
        if _term_has_positive_evidence(text, variants)
    ]

    for finding in findings:
        finding_text = f" {_compact(_ascii_fold(str(finding.get('text', ''))))} "
        matched_labels = [
            label for label in supported
            if any(_ascii_fold(variant) in finding_text for variant in _CRITICAL_VARIANTS[label])
            and not _is_negated_clause(str(finding.get("text", "")))
        ]
        if matched_labels:
            finding["classification"] = "critical"
            finding["is_critical"] = True
            finding["matched_terms"] = sorted(set(finding.get("matched_terms", []) + matched_labels))
    return supported


def analyze_radiology_report_safely(text: str) -> dict[str, Any]:
    """Return section-aware, conservative findings and verified emergency alerts."""
    result = analyze_radiology_report(text)
    findings = _filter_findings_to_active_sections(text, list(result.get("findings", [])))
    supported_labels = _apply_critical_evidence(text, findings)

    result["findings"] = findings
    result["critical_findings"] = supported_labels
    result["safety_version"] = SAFETY_VERSION

    abnormal_count = sum(1 for item in findings if item.get("classification") == "abnormal")
    critical_count = sum(1 for item in findings if item.get("is_critical"))
    result["summary"] = (
        f"{result.get('modality', 'UNKNOWN')} / {result.get('body_part', 'OTHER')} raporu: "
        f"{len(findings)} klinik bulgu cümlesi, {abnormal_count} dikkat gerektiren bulgu, "
        f"{len(result.get('measurements', []))} ölçüm ve {len(supported_labels)} doğrulanmış kritik uyarı çıkarıldı. "
        "Sonuçlar orijinal raporla hekim tarafından doğrulanmalıdır."
    )

    warnings = list(result.get("warnings", []))
    if critical_count:
        warnings.append("Acil/kritik ifadeler saptandı; gecikmeden hekim değerlendirmesi gerekir.")
    result["warnings"] = warnings
    return result
