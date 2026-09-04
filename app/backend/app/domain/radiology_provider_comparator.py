"""Deterministic comparison of independent radiology language-model readers.

This comparator does not decide which model is correct. It only surfaces concept
agreement, polarity conflict and clinically important asymmetry so a physician can
see where independent readers converged or where they require reconciliation.
"""

from __future__ import annotations

import unicodedata

from app.domain.report_document_image_ai import RadiologyMediaReview


_CONCEPT_MARKERS: dict[str, tuple[str, ...]] = {
    "pneumothorax": ("pnömotoraks", "pnomotoraks", "pneumothorax"),
    "pleural_effusion": ("plevral efüzyon", "plevral sivi", "pleural effusion"),
    "airspace_opacity": ("opasite", "airspace opacity", "hava sahasi opasitesi"),
    "consolidation": ("konsolidasyon", "consolidation"),
    "atelectasis": ("atelektazi", "atelectasis"),
    "cardiomegaly": ("kardiyomegali", "kalp silueti genis", "cardiomegaly"),
    "pulmonary_edema": ("pulmoner ödem", "pulmoner odem", "pulmonary edema"),
    "free_air": (
        "serbest hava",
        "subdiyafragmatik hava",
        "subdiafragmatik hava",
        "free intraperitoneal air",
        "pneumoperitoneum",
    ),
    "bowel_dilatation": (
        "barsak dilat",
        "bağırsak dilat",
        "bagirsak dilat",
        "bowel dilat",
        "dilated bowel",
    ),
    "air_fluid_levels": ("hava-sıvı", "hava sivi", "air-fluid", "air fluid"),
    "fecal_burden": ("fekal yük", "fekal yuk", "dışkı yük", "diski yuk", "stool burden"),
    "fracture": ("kırık", "kirik", "fracture"),
    "dislocation": ("çıkık", "cikik", "dislocation"),
    "foreign_body": ("yabancı cisim", "yabanci cisim", "foreign body"),
    "calcification": ("kalsifik", "calcific", "calcification"),
    "hydronephrosis": ("hidronefroz", "hydronephrosis"),
}

_NEGATION_MARKERS = (
    " yok",
    " izlenmiyor",
    " gorulmuyor",
    " secilmiyor",
    " saptanmadi",
    " mevcut degil",
    " lehine bulgu yok",
    " no evidence",
    " not seen",
    " absent",
    " without evidence",
    " negative for",
)

_HIGH_ATTENTION_CONCEPTS = {
    "pneumothorax",
    "free_air",
    "fracture",
    "dislocation",
}


def _fold(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "")).lower()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.split())


def _reader_text(review: RadiologyMediaReview) -> str:
    parts: list[str] = [review.summary]
    parts.extend(review.observations)
    return _fold(" ".join(parts))


def _concept_polarities(review: RadiologyMediaReview) -> dict[str, set[str]]:
    """Return positive/uncertain vs negative mentions using a local text window.

    This is deliberately conservative. A concept can appear in both sets when the
    generated prose itself is internally inconsistent; that is surfaced rather than
    silently collapsed.
    """

    text = _reader_text(review)
    polarities: dict[str, set[str]] = {}
    for concept, markers in _CONCEPT_MARKERS.items():
        for raw_marker in markers:
            marker = _fold(raw_marker)
            start = 0
            while True:
                index = text.find(marker, start)
                if index < 0:
                    break
                window_start = max(0, index - 70)
                window_end = min(len(text), index + len(marker) + 70)
                window = " " + text[window_start:window_end] + " "
                polarity = (
                    "negative"
                    if any(negation in window for negation in _NEGATION_MARKERS)
                    else "positive_or_uncertain"
                )
                polarities.setdefault(concept, set()).add(polarity)
                start = index + max(1, len(marker))
    return polarities


def extract_review_concepts(review: RadiologyMediaReview) -> set[str]:
    """Backward-compatible concept mentions regardless of polarity."""
    return set(_concept_polarities(review))


def compare_radiology_readers(
    primary: RadiologyMediaReview,
    second_reader: RadiologyMediaReview,
) -> dict[str, object]:
    primary_mentions = _concept_polarities(primary)
    second_mentions = _concept_polarities(second_reader)

    primary_positive = {
        concept
        for concept, polarities in primary_mentions.items()
        if "positive_or_uncertain" in polarities
    }
    second_positive = {
        concept
        for concept, polarities in second_mentions.items()
        if "positive_or_uncertain" in polarities
    }
    primary_negative = {
        concept for concept, polarities in primary_mentions.items() if "negative" in polarities
    }
    second_negative = {
        concept for concept, polarities in second_mentions.items() if "negative" in polarities
    }

    corroborated = primary_positive & second_positive
    corroborated_negatives = primary_negative & second_negative
    primary_only = primary_positive - second_positive - second_negative
    second_only = second_positive - primary_positive - primary_negative
    polarity_conflicts = (primary_positive & second_negative) | (
        second_positive & primary_negative
    )
    attention_asymmetry = (primary_only | second_only) & _HIGH_ATTENTION_CONCEPTS

    same_modality = (
        primary.detected_modality == second_reader.detected_modality
        or "UNKNOWN" in {primary.detected_modality, second_reader.detected_modality}
    )
    same_region = (
        primary.detected_body_part == second_reader.detected_body_part
        or "OTHER" in {primary.detected_body_part, second_reader.detected_body_part}
    )

    return {
        "mode": "deterministic_concept_polarity_not_ground_truth",
        "corroborated_concepts": sorted(corroborated),
        "corroborated_negative_concepts": sorted(corroborated_negatives),
        "primary_only_concepts": sorted(primary_only),
        "second_reader_only_concepts": sorted(second_only),
        "polarity_conflicts": sorted(polarity_conflicts),
        "high_attention_asymmetry": sorted(attention_asymmetry),
        "modality_compatible": same_modality,
        "body_part_compatible": same_region,
        "requires_physician_attention": bool(attention_asymmetry)
        or bool(polarity_conflicts)
        or not same_modality
        or not same_region,
        "agreement_is_not_validation": True,
    }
