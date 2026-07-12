"""Deterministic parser for text-based radiology and DXA/DEXA reports.

The parser extracts conservative structured signals for physician review. It does
not interpret image pixels and never produces an automatic diagnosis.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

PARSER_VERSION = "phase2-radiology-text-v3-negation"

_MODALITY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "DEXA",
        (
            "dexa",
            "dxa",
            "dual-energy x-ray absorptiometry",
            "dual energy x ray absorptiometry",
            "kemik mineral yogunlugu",
            "kemik dansitometri",
            "kemik yogunlugu",
        ),
    ),
    ("PET_CT", ("pet/ct", "pet-bt", "pet bt", "pozitron emisyon")),
    ("MRI", ("manyetik rezonans", "mri", " mr ", "mr inceleme", "mr goruntuleme")),
    ("CT", ("bilgisayarli tomografi", "computed tomography", "ct ", " bt ", "bt inceleme")),
    ("ULTRASOUND", ("ultrasonografi", "ultrason", "usg", "sonografi", "doppler")),
    ("XRAY", ("rontgen", "grafi", "x-ray", "xray", "direkt grafi")),
)

_BODY_PART_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BONE_DENSITY", ("kemik mineral yogunlugu", "kemik dansitometri", "dexa", "dxa", "bmd")),
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
    (
        "İntrakraniyal kanama",
        ("intrakraniyal kanama", "intraserebral kanama", "subaraknoid kanama", "subdural hematom"),
    ),
    ("Akut enfarkt", ("akut enfarkt", "akut infarkt", "akut iskemi")),
    ("Aort diseksiyonu", ("aort diseksiyonu", "diseksiyon flebi")),
    ("Serbest hava", ("serbest hava", "pnomoperitoneum")),
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

# Values are matched after Turkish characters are ASCII-folded. Both short past
# tense forms and formal report forms ending in -mıştır/-miştir are included.
_NEGATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
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
        r"\bpatoloji saptanma(?:di|mistir)\b",
    )
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
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>mm|cm|ml|cc|g\s*/\s*cm(?:2|²|\^2))\b",
    flags=re.IGNORECASE,
)
_BMD_RE = re.compile(
    r"(?:(?:bmd|kmy)\s*[:=]?\s*)?(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>g\s*/\s*cm(?:2|²|\^2))",
    flags=re.IGNORECASE,
)
_T_SCORE_RE = re.compile(
    r"(?:t\s*[- ]?\s*(?:score|skor(?:u)?)|t\s*degeri)\s*[:=]?\s*(?P<value>[+-]?\d+(?:[.,]\d+)?)",
    flags=re.IGNORECASE,
)
_Z_SCORE_RE = re.compile(
    r"(?:z\s*[- ]?\s*(?:score|skor(?:u)?)|z\s*degeri)\s*[:=]?\s*(?P<value>[+-]?\d+(?:[.,]\d+)?)",
    flags=re.IGNORECASE,
)

_DEXA_SITE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("LUMBAR_SPINE_L1_L4", ("l1-l4", "l1 l4", "lomber omurga", "lumbar spine", "ap spine")),
    ("FEMORAL_NECK", ("femur boynu", "femoral neck", "boyun femur")),
    ("TOTAL_HIP", ("total kalca", "total hip", "total femur", "toplam kalca")),
    ("FOREARM_33_RADIUS", ("1/3 radius", "33% radius", "distal radius", "on kol", "ön kol", "forearm")),
    ("WHOLE_BODY", ("tum vucut", "tüm vücut", "whole body")),
)

_EXPLICIT_DEXA_CLASSIFICATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("osteoporosis", ("osteoporoz", "osteoporosis")),
    ("low_bone_mass", ("osteopeni", "osteopenia", "dusuk kemik kutlesi", "düşük kemik kütlesi", "low bone mass")),
    ("normal", ("normal kemik", "normal aralik", "normal range")),
    (
        "below_expected_for_age",
        ("yasa gore beklenen araligin altinda", "yaşa göre beklenen aralığın altında", "below expected range for age"),
    ),
    (
        "within_expected_for_age",
        ("yasa gore beklenen aralikta", "yaşa göre beklenen aralıkta", "within expected range for age"),
    ),
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


def _has_negation(value: str) -> bool:
    normalized = _normalized_for_match(value)
    return any(pattern.search(normalized) for pattern in _NEGATION_PATTERNS)


def _is_negated(sentence: str, matched_term: str) -> bool:
    normalized = _normalized_for_match(sentence)
    term = _ascii_fold(matched_term)
    position = normalized.find(term)
    if position < 0:
        return False

    # Radiology reports often place the negation after a coordinated phrase:
    # "Serbest hava veya serbest sıvı saptanmamıştır." Use the whole sentence
    # when it is short, otherwise a generous local window around the finding.
    if len(normalized) <= 240:
        window = normalized
    else:
        window = normalized[max(0, position - 100) : position + len(term) + 120]
    return _has_negation(window)


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
            unit = re.sub(r"\s+", "", match.group("unit").lower()).replace("^", "")
            context = sentence[:500]
            key = (value, unit, context)
            if key in seen:
                continue
            seen.add(key)
            measurements.append({"value": value, "unit": unit, "context": context})
            if len(measurements) >= 100:
                return measurements
    return measurements


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _infer_dexa_site(line: str) -> str:
    normalized = _normalized_for_match(line)
    for code, terms in _DEXA_SITE_PATTERNS:
        if any(_ascii_fold(term) in normalized for term in terms):
            return code
    return "UNSPECIFIED"


def _explicit_dexa_classification(line: str) -> str | None:
    normalized = _normalized_for_match(line)
    for code, terms in _EXPLICIT_DEXA_CLASSIFICATIONS:
        if any(_ascii_fold(term) in normalized for term in terms):
            return code
    return None


def _t_score_band(value: float | None) -> str | None:
    if value is None:
        return None
    if value <= -2.5:
        return "osteoporosis_range"
    if value < -1.0:
        return "low_bone_mass_range"
    return "normal_range"


def _z_score_band(value: float | None) -> str | None:
    if value is None:
        return None
    return "below_expected_for_age" if value <= -2.0 else "within_expected_for_age"


def _extract_unlabelled_scores(
    line: str,
    bmd_match: re.Match[str],
) -> tuple[float | None, float | None]:
    tail = line[bmd_match.end() :]
    numbers = [
        _parse_float(item)
        for item in re.findall(r"(?<![\w.])[+-]?\d+(?:[.,]\d+)?(?![\w.])", tail)
    ]
    values = [item for item in numbers if item is not None]
    if not values:
        return None, None
    return values[0], values[1] if len(values) > 1 else None


def _extract_dexa_metrics(text: str) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float | None, float | None]] = set()
    lines = [_compact(line) for line in text.replace("\r", "\n").split("\n") if _compact(line)]

    for line in lines:
        normalized = _normalized_for_match(line)
        score_tokens = (
            " bmd ",
            " kmy ",
            " t-score ",
            " t score ",
            " t skoru ",
            " z-score ",
            " z score ",
            " z skoru ",
            " g/cm",
        )
        if not any(token in normalized for token in score_tokens):
            continue

        bmd_match = _BMD_RE.search(line)
        t_match = _T_SCORE_RE.search(line)
        z_match = _Z_SCORE_RE.search(line)
        bmd = _parse_float(bmd_match.group("value")) if bmd_match else None
        t_score = _parse_float(t_match.group("value")) if t_match else None
        z_score = _parse_float(z_match.group("value")) if z_match else None

        if bmd_match and t_score is None and z_score is None:
            t_score, z_score = _extract_unlabelled_scores(line, bmd_match)
        if bmd is None and t_score is None and z_score is None:
            continue

        site = _infer_dexa_site(line)
        key = (site, str(bmd), t_score, z_score)
        if key in seen:
            continue
        seen.add(key)
        metrics.append(
            {
                "site": site,
                "bmd": bmd,
                "bmd_unit": "g/cm2" if bmd is not None else None,
                "t_score": t_score,
                "z_score": z_score,
                "t_score_band": _t_score_band(t_score),
                "z_score_band": _z_score_band(z_score),
                "report_classification": _explicit_dexa_classification(line),
                "context": line[:1000],
            }
        )
        if len(metrics) >= 50:
            break
    return metrics


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
    """Return conservative structured signals from radiology or DXA report text."""
    clean_text = text.strip()
    if len(clean_text) < 10:
        raise ValueError("Radiology report text is too short to analyze.")

    sentences = _sentences(clean_text)
    findings, critical_findings = _extract_findings(sentences)
    measurements = _extract_measurements(sentences)
    modality = infer_modality(clean_text)
    body_part = infer_body_part(clean_text)
    impression = _extract_impression(clean_text)
    dexa_metrics = _extract_dexa_metrics(clean_text) if modality == "DEXA" else []

    warnings: list[str] = []
    if modality == "UNKNOWN":
        warnings.append("Modality could not be inferred; physician confirmation is required.")
    if body_part == "OTHER":
        warnings.append("Body region could not be inferred; physician confirmation is required.")
    if not findings:
        warnings.append("No structured finding sentence could be extracted.")
    if modality == "DEXA" and not dexa_metrics:
        warnings.append("DEXA modality was detected but no BMD, T-score, or Z-score row could be extracted.")
    if dexa_metrics:
        warnings.append(
            "DEXA score bands are assistive only. T-score and Z-score interpretation depends on age, sex, menopausal status, skeletal site, scan quality, and clinical context."
        )

    abnormal_count = sum(
        1 for finding in findings if finding["classification"] == "abnormal"
    )
    dexa_fragment = f", {len(dexa_metrics)} DXA measurement rows" if dexa_metrics else ""
    summary = (
        f"{modality} / {body_part} report: {len(findings)} finding sentences, "
        f"{abnormal_count} non-critical abnormal signals, {len(measurements)} measurements"
        f"{dexa_fragment} and {len(critical_findings)} critical-term alerts were extracted. "
        "All outputs require physician verification against the original report."
    )

    return {
        "parser_version": PARSER_VERSION,
        "modality": modality,
        "body_part": body_part,
        "findings": findings,
        "measurements": measurements,
        "dexa_metrics": dexa_metrics,
        "critical_findings": critical_findings,
        "impression": impression,
        "summary": summary,
        "warnings": warnings,
    }
