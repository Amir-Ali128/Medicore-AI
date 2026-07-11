"""Deterministic parser for text-based radiology reports.

Phase 2 deliberately starts with report text, not pixel/image interpretation. The
parser extracts conservative structured signals for physician review and never
turns report text into an automatic diagnosis or treatment recommendation.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

PARSER_VERSION = "phase2-radiology-text-v1"

_MODALITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PET_CT", ("pet/ct", "pet-bt", "pet bt", "pozitron emisyon")),
    ("MRI", ("manyetik rezonans", "mri", " mr ", "mr inceleme", "mr goruntuleme")),
    ("CT", ("bilgisayarli tomografi", "computed tomography", "ct ", " bt ", "bt inceleme")),
    ("ULTRASOUND", ("ultrasonografi", "ultrason", "usg", "sonografi", "doppler")),
    ("XRAY", ("rontgen", "grafi", "x-ray", "xray", "direkt grafi")),
)

_BODY_PART_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BRAIN", ("beyin", "kraniyal", "kranial", "intrakraniyal", "serebral", "kafa")),
    ("CHEST", ("toraks", "akciger", "pulmoner", "mediasten", "gogus")),
    ("ABDOMEN", ("abdomen", "batin", "karaciger", "pankreas", "dalak", "bobrek")),
    ("PELVIS", ("pelvis", "pelvik", "uterus", "over", "mesane", "prostat")),
    ("SPINE", ("servikal", "torakal vertebra", "lomber", "vertebra", "spinal", "omurga")),
    ("NECK", ("boyun", "tiroid", "servikal lenf")),
    ("BREAST", ("meme", "mammografi", "mamografi")),
    ("CARDIAC", ("kardiyak", "kalp", "koroner")),
    ("MUSCULOSKELETAL", ("diz", "omuz", "kalca", "dirsek", "ayak bilegi", "eklem", "kemik")),
    ("WHOLE_BODY", ("tum vucut", "whole body")),
)

_CRITICAL_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Pnömotoraks", ("pnomotoraks",)),
    ("Pulmoner emboli", ("pulmoner emboli", "emboli ile uyumlu")),
    ("İntrakraniyal kanama", ("intrakraniyal kanama", "intraserebral kanama", "subaraknoid kanama", "subdural hematom")),
    ("Akut enfarkt", ("akut enfarkt", "akut infarkt", "akut iskemi")),
    ("Aort diseksiyonu", ("aort diseksiyonu", "diseksiyon flebi")),
    ("Serbest hava", ("serbest hava", "pnömoperitoneum", "pnomoperitoneum")),
    ("Akut obstrüksiyon", ("akut obstruksiyon", "barsak obstruksiyonu", "ileus")),
    ("Aktif kanama", ("aktif kanama", "ekstravazasyon")),
    ("Malignite şüphesi", ("malignite supheli", "malignite acisindan supheli", "malign kitle")),
)

_ABNORMAL_TERMS: tuple[str, ...] = (
    "lezyon",
    "nodul",
    "kitle",
    "efüzyon",
    "efuzyon",
    "ödem",
    "odem",
    "konsolidasyon",
    "atelektazi",
    "fraktur",
    "kırık",
    "kirik",
    "stenoz",
    "dilatasyon",
    "lenfadenopati",
    "hematom",
    "kanama",
    "infiltrasyon",
    "trombus",
    "tromboz",
    "koleksiyon",
    "metastaz",
    "hipodens",
    "hiperdens",
    "hiperintens",
    "hipointens",
)

_NEGATION_TERMS: tuple[str, ...] = (
    "saptanmadi",
    "izlenmedi",
    "gorulmedi",
    "rastlanmadi",
    "mevcut degildir",
    "tespit edilmedi",
    "yoktur",
    "yok ",
    "negatif",
    "lehine bulgu yok",
)

_SECTION_HEADINGS = {
    "bulgular",
    "bulgu",
    "findings",
    "sonuc",
    "sonuç",
    "izlenim",
    "degerlendirme",
    "değerlendirme",
    "impression",
    "teknik",
    "klinik bilgi",
    "klinik",
    "endikasyon",
}

_MEASUREMENT_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>mm|cm|ml|cc)\b",
    flags=re.IGNORECASE,
)


def _ascii_fold(value: str) -> str:
    replacements = str.maketrans(
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
    translated = value.translate(replacements)
    normalized = unicodedata.normalize("NFKD", translated)
    return "".join(character for character in normalized if not unicodedata.combining(character)).lower()


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalized_for_match(value: str) -> str:
    return f" {_compact(_ascii_fold(value))} "


def _sentences(text: str) -> list[str]:
    cleaned = text.replace("\r", "\n")
    parts = re.split(r"(?<=[.!?;])\s+|\n+", cleaned)
    output: list[str] = []
    normalized_headings = {_ascii_fold(item) for item in _SECTION_HEADINGS}
    for part in parts:
        sentence = _compact(part.strip(" •\t-"))
        if len(sentence) < 3:
            continue
        if _ascii_fold(sentence).strip(":") in normalized_headings:
            continue
        output.append(sentence)
    return output


def _contains_any(value: str, terms: Iterable[str]) -> list[str]:
    normalized = _normalized_for_match(value)
    return [term for term in terms if _ascii_fold(term) in normalized]


def _is_negated(sentence: str, matched_term: str) -> bool:
    normalized = _normalized_for_match(sentence)
    term = _ascii_fold(matched_term)
    position = normalized.find(term)
    if position < 0:
        return False
    window = normalized[max(0, position - 60) : position + len(term) + 45]
    return any(negation in window for negation in _NEGATION_TERMS)


def infer_modality(text: str) -> str:
    normalized = _normalized_for_match(text)
    for code, terms in _MODALITY_PATTERNS:
        if any(term in normalized for term in terms):
            return code
    return "UNKNOWN"


def infer_body_part(text: str) -> str:
    normalized = _normalized_for_match(text)
    scores: dict[str, int] = {}
    for code, terms in _BODY_PART_PATTERNS:
        score = sum(normalized.count(term) for term in terms)
        if score:
            scores[code] = score
    return max(scores, key=scores.get) if scores else "OTHER"


def _extract_impression(text: str) -> str | None:
    lines = [line.strip() for line in text.replace("\r", "\n").split("\n")]
    start: int | None = None
    normalized_headings = {_ascii_fold(item) for item in _SECTION_HEADINGS}
    for index, line in enumerate(lines):
        heading = _ascii_fold(line).strip(" :.-")
        if heading in {"sonuc", "izlenim", "degerlendirme", "impression"}:
            start = index + 1
            break
        for prefix in ("sonuc:", "izlenim:", "degerlendirme:", "impression:"):
            if heading.startswith(prefix):
                inline = line.split(":", 1)[1].strip()
                return inline or None
    if start is None:
        return None
    collected: list[str] = []
    for line in lines[start:]:
        if not line:
            if collected:
                break
            continue
        folded = _ascii_fold(line).strip(" :.-")
        if folded in normalized_headings:
            break
        collected.append(line)
    impression = _compact(" ".join(collected))
    return impression or None


def _extract_measurements(sentences: list[str]) -> list[dict[str, Any]]:
    measurements: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for sentence in sentences:
        for match in _MEASUREMENT_RE.finditer(sentence):
            value = match.group("value").replace(",", ".")
            unit = match.group("unit").lower()
            context = sentence[:500]
            key = (value, unit, context)
            if key in seen:
                continue
            seen.add(key)
            measurements.append({"value": value, "unit": unit, "context": context})
            if len(measurements) >= 100:
                return measurements
    return measurements


def _extract_findings(sentences: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    critical_labels: list[str] = []

    for sentence in sentences[:160]:
        normalized = _normalized_for_match(sentence)
        matched_critical_labels: list[str] = []
        matched_terms: list[str] = []

        for label, variants in _CRITICAL_TERMS:
            for variant in variants:
                if variant in normalized and not _is_negated(sentence, variant):
                    matched_critical_labels.append(label)
                    matched_terms.append(variant)
                    break

        abnormal_matches = _contains_any(sentence, _ABNORMAL_TERMS)
        negated_abnormal = bool(abnormal_matches) and all(
            _is_negated(sentence, term) for term in abnormal_matches
        )

        if matched_critical_labels:
            classification = "critical"
        elif abnormal_matches and not negated_abnormal:
            classification = "abnormal"
            matched_terms.extend(abnormal_matches)
        else:
            classification = "observation"

        findings.append(
            {
                "text": sentence[:2000],
                "classification": classification,
                "is_critical": bool(matched_critical_labels),
                "matched_terms": sorted(set(matched_terms)),
            }
        )

        for label in matched_critical_labels:
            if label not in critical_labels:
                critical_labels.append(label)

    return findings, critical_labels


def analyze_radiology_report(text: str) -> dict[str, Any]:
    """Return conservative, structured signals from radiology report text."""
    clean_text = text.strip()
    if len(clean_text) < 10:
        raise ValueError("Radiology report text is too short to analyze.")

    sentences = _sentences(clean_text)
    findings, critical_findings = _extract_findings(sentences)
    measurements = _extract_measurements(sentences)
    modality = infer_modality(clean_text)
    body_part = infer_body_part(clean_text)
    impression = _extract_impression(clean_text)

    warnings: list[str] = []
    if modality == "UNKNOWN":
        warnings.append("Modality could not be inferred; physician confirmation is required.")
    if body_part == "OTHER":
        warnings.append("Body region could not be inferred; physician confirmation is required.")
    if not findings:
        warnings.append("No structured finding sentence could be extracted.")

    abnormal_count = sum(
        1 for finding in findings if finding["classification"] == "abnormal"
    )
    summary = (
        f"{modality} / {body_part} report: {len(findings)} finding sentences, "
        f"{abnormal_count} non-critical abnormal signals, {len(measurements)} measurements "
        f"and {len(critical_findings)} critical-term alerts were extracted. "
        "All outputs require physician verification against the original report."
    )

    return {
        "parser_version": PARSER_VERSION,
        "modality": modality,
        "body_part": body_part,
        "findings": findings,
        "measurements": measurements,
        "critical_findings": critical_findings,
        "impression": impression,
        "summary": summary,
        "warnings": warnings,
    }
