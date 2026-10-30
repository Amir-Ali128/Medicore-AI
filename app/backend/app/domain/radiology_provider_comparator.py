"""Deterministic comparison of independent radiology language-model readers.

This comparator does not decide which model is correct. It only surfaces concept
agreement, polarity conflict and clinically important asymmetry so a physician can
see where independent readers converged or where they require reconciliation.
"""

from __future__ import annotations

from app.domain.report_concepts import fold_text as _fold, concept_polarities_text
from app.domain.consistency_config import RADIOLOGY_HIGH_ATTENTION_CONCEPTS as _HIGH_ATTENTION_CONCEPTS

from app.domain.report_document_image_ai import RadiologyMediaReview


def _reader_text(review: RadiologyMediaReview) -> str:
    parts: list[str] = [review.summary]
    parts.extend(review.observations)
    return _fold(" ".join(parts))


def _concept_polarities(review: RadiologyMediaReview) -> dict[str, set[str]]:
    return concept_polarities_text(_reader_text(review))


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


def compare_radiology_reader_set(
    readers: dict[str, RadiologyMediaReview],
) -> dict[str, object]:
    """Summarize 2+ independent readers without converting votes to probability.

    A provider that does not mention a concept is recorded as ``unmentioned`` rather
    than as a negative vote. Two positive/uncertain mentions are called corroborated,
    but never ground truth. Any explicit positive-vs-negative split is surfaced as a
    polarity conflict.
    """

    clean_readers = {
        str(provider).strip(): review
        for provider, review in readers.items()
        if str(provider).strip() and review is not None
    }
    provider_names = sorted(clean_readers)
    mentions = {
        provider: _concept_polarities(review)
        for provider, review in clean_readers.items()
    }
    all_concepts = sorted(
        {concept for provider_mentions in mentions.values() for concept in provider_mentions}
    )

    concept_votes: dict[str, dict[str, list[str]]] = {}
    corroborated: list[str] = []
    corroborated_negative: list[str] = []
    polarity_conflicts: list[str] = []
    high_attention_asymmetry: list[str] = []

    for concept in all_concepts:
        positive = sorted(
            provider
            for provider, provider_mentions in mentions.items()
            if "positive_or_uncertain" in provider_mentions.get(concept, set())
        )
        negative = sorted(
            provider
            for provider, provider_mentions in mentions.items()
            if "negative" in provider_mentions.get(concept, set())
        )
        mentioned = set(positive) | set(negative)
        unmentioned = sorted(set(provider_names) - mentioned)
        concept_votes[concept] = {
            "positive_or_uncertain": positive,
            "negative": negative,
            "unmentioned": unmentioned,
        }

        if len(positive) >= 2:
            corroborated.append(concept)
        if len(negative) >= 2:
            corroborated_negative.append(concept)
        if positive and negative:
            polarity_conflicts.append(concept)
        if (
            concept in _HIGH_ATTENTION_CONCEPTS
            and len(provider_names) >= 2
            and (
                (positive and len(positive) < len(provider_names))
                or (negative and len(negative) < len(provider_names))
            )
        ):
            high_attention_asymmetry.append(concept)

    document_kinds = {
        review.document_kind for review in clean_readers.values() if review.document_kind != "OTHER"
    }
    modalities = {
        review.detected_modality
        for review in clean_readers.values()
        if review.detected_modality != "UNKNOWN"
    }
    body_parts = {
        review.detected_body_part
        for review in clean_readers.values()
        if review.detected_body_part != "OTHER"
    }

    document_kind_compatible = len(document_kinds) <= 1
    modality_compatible = len(modalities) <= 1
    body_part_compatible = len(body_parts) <= 1

    return {
        "mode": "deterministic_multi_provider_concept_polarity_not_ground_truth",
        "reader_count": len(provider_names),
        "providers": provider_names,
        "concept_votes": concept_votes,
        "corroborated_concepts": sorted(corroborated),
        "corroborated_negative_concepts": sorted(corroborated_negative),
        "polarity_conflicts": sorted(polarity_conflicts),
        "high_attention_asymmetry": sorted(set(high_attention_asymmetry)),
        "document_kind_compatible": document_kind_compatible,
        "modality_compatible": modality_compatible,
        "body_part_compatible": body_part_compatible,
        "requires_physician_attention": bool(polarity_conflicts)
        or bool(high_attention_asymmetry)
        or not document_kind_compatible
        or not modality_compatible
        or not body_part_compatible,
        "agreement_is_not_validation": True,
    }
