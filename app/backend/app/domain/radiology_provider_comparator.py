"""Deterministic comparison of independent radiology language-model readers.

This comparator does not decide which model is correct. It only surfaces concept
agreement/asymmetry so a physician can see where independent readers converged or
where one mentioned a clinically important concept the other did not.
"""

from __future__ import annotations

import unicodedata
from typing import Iterable

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

# Absence from another free-form reader is not a contradiction. These concepts are
# merely highlighted when mentioned by only one reader because missing them can be
# clinically important enough to deserve explicit human attention.
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


def extract_review_concepts(review: RadiologyMediaReview) -> set[str]:
    text = _reader_text(review)
    concepts: set[str] = set()
    for concept, markers in _CONCEPT_MARKERS.items():
        if any(_fold(marker) in text for marker in markers):
            concepts.add(concept)
    return concepts


def compare_radiology_readers(
    primary: RadiologyMediaReview,
    second_reader: RadiologyMediaReview,
) -> dict[str, object]:
    primary_concepts = extract_review_concepts(primary)
    second_concepts = extract_review_concepts(second_reader)
    corroborated = primary_concepts & second_concepts
    primary_only = primary_concepts - second_concepts
    second_only = second_concepts - primary_concepts
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
        "mode": "deterministic_concept_overlap_not_ground_truth",
        "corroborated_concepts": sorted(corroborated),
        "primary_only_concepts": sorted(primary_only),
        "second_reader_only_concepts": sorted(second_only),
        "high_attention_asymmetry": sorted(attention_asymmetry),
        "modality_compatible": same_modality,
        "body_part_compatible": same_region,
        "requires_physician_attention": bool(attention_asymmetry)
        or not same_modality
        or not same_region,
        "agreement_is_not_validation": True,
    }
