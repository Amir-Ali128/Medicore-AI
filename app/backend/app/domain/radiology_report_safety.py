"""Conservative safety layer for radiology report text parsing.

The base parser intentionally uses deterministic keyword extraction. This module
adds a second evidence check so terms mentioned only in clinical history,
indication, pre-diagnosis, or explicitly negated clauses are not presented as
active findings.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

from app.domain.radiology_report_parser import analyze_radiology_report

SAFETY_VERSION = "radiology-evidence-safety-v1"

_CRITICAL_VARIANTS: dict[str, tuple[str, ...]] = {
    "Pnömotoraks": ("pnomotoraks",),
    "Pulmoner emboli": ("pulmoner emboli", "emboli ile uyumlu"),
    "İntrakraniyal kanama": (
        "intrakraniyal kanama",
        "intraserebral kanama",
        "subaraknoid kanama",
        "subdural hematom",
    ),
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
    "klinik",
    "klinik bilgi",
    "klinik bilgiler",
    "endikasyon",
    "istem nedeni",
    "tetkik istem nedeni",
    "on tani",
    "ontani",
    "preoperatif tani",
    "anamnez",
    "oyku",
    "hikaye",
    "hasta hikayesi",
    "sikayet",
}

_ACTIVE_SECTION_HEADINGS = {
    "bulgu",
    "bulgular",
    "findings",
    "sonuc",
    "izlenim",
    "degerlendirme",
    "impression",
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

# These expressions describe a reason for the examination, not a confirmed
# current finding. They are ignored unless the same term also has positive
# evidence in an active findings/result section.
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


def _clauses(sentence: str) -> list[str]:
    """Split a sentence into local clauses to avoid cross-clause negation leaks."""
    normalized = _compact(sentence)
    pieces = re.split(
        r"[.;\n]+|\s*,\s*|\s+(?:ancak|fakat|lakin|bununla birlikte|buna karsin|buna karşılık)\s+",
        normalized,
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
    """Yield clauses with whether they belong to an active finding section."""
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
                # The inline content is intentionally excluded.
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


def _downgrade_unsupported_findings(
    findings: list[dict[str, Any]],
    unsupported_labels: set[str],
) -> None:
    unsupported_terms = {
        variant
        for label in unsupported_labels
        for variant in _CRITICAL_VARIANTS.get(label, ())
    }

    for finding in findings:
        if not finding.get("is_critical"):
            continue
        matched = {_ascii_fold(str(term)) for term in finding.get("matched_terms", [])}
        if matched and not matched.intersection(unsupported_terms):
            continue
        finding["classification"] = "observation"
        finding["is_critical"] = False
        finding["matched_terms"] = [
            term
            for term in finding.get("matched_terms", [])
            if _ascii_fold(str(term)) not in unsupported_terms
        ]
        finding["safety_note"] = (
            "Critical term was mentioned without positive current-report evidence "
            "and was suppressed to prevent a false-positive alert."
        )


def analyze_radiology_report_safely(text: str) -> dict[str, Any]:
    """Run the base parser and suppress unsupported critical-term alerts."""
    result = analyze_radiology_report(text)
    original_labels = list(result.get("critical_findings", []))
    supported_labels = [
        label
        for label in original_labels
        if _term_has_positive_evidence(text, _CRITICAL_VARIANTS.get(label, (label,)))
    ]
    unsupported_labels = set(original_labels) - set(supported_labels)

    result["critical_findings"] = supported_labels
    _downgrade_unsupported_findings(result.get("findings", []), unsupported_labels)

    warnings = list(result.get("warnings", []))
    if unsupported_labels:
        warnings.append(
            "Safety filter suppressed unsupported critical mentions: "
            + ", ".join(sorted(unsupported_labels))
            + "."
        )
    result["warnings"] = warnings
    result["safety_version"] = SAFETY_VERSION

    abnormal_count = sum(
        1
        for finding in result.get("findings", [])
        if finding.get("classification") == "abnormal"
    )
    result["summary"] = (
        f"{result.get('modality', 'UNKNOWN')} / {result.get('body_part', 'OTHER')} report: "
        f"{len(result.get('findings', []))} finding sentences, "
        f"{abnormal_count} non-critical abnormal signals, "
        f"{len(result.get('measurements', []))} measurements and "
        f"{len(supported_labels)} verified critical-term alerts were extracted. "
        "All outputs require physician verification against the original report."
    )
    return result
