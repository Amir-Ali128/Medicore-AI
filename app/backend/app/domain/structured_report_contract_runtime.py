"""Runtime wiring for the structured physician-report output contract.

Loaded after universal_medical_report_runtime. It keeps backward-compatible
result_text behavior while exposing distinct fields for future UI clients and a
labelled clinical block for the current report screen.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.domain import universal_medical_report_runtime as universal_runtime
from app.domain.medical_report_summary_ai import MedicalReportReview, summarize_medical_report_text
from app.domain.report_document_image_ai import RadiologyMediaReview


_original_merge_review_metadata = universal_runtime._merge_review_metadata


def _structured_result_text(review: MedicalReportReview) -> str:
    sections: list[str] = []
    if review.main_result:
        sections.append(f"ANA SONUÇ: {review.main_result}")
    if review.clinical_interpretation:
        sections.append(f"KLİNİK YORUM: {review.clinical_interpretation}")
    if review.brief_summary:
        sections.append(f"KISACA: {review.brief_summary}")
    return "\n\n".join(sections) or review.doctor_summary


def _visible_findings(review: MedicalReportReview) -> list[str]:
    source_conclusion = universal_runtime._source_conclusion_finding(review.conclusion)
    technical = [f"Teknik bulgu: {item}" for item in review.technical_findings]
    explicit_recommendations = [f"Rapordaki öneri: {item}" for item in review.recommendations]
    return universal_runtime._dedupe(
        technical
        + ([source_conclusion] if source_conclusion else [])
        + list(review.key_findings)
        + explicit_recommendations,
        limit=48,
    )


def _merge_review_metadata_structured(
    metadata: dict[str, Any], review: MedicalReportReview
) -> dict[str, Any]:
    metadata = _original_merge_review_metadata(metadata, review)
    metadata.update(
        {
            "report_contract_version": "physician-report-v2",
            "main_result": review.main_result,
            "technical_findings": list(review.technical_findings),
            "clinical_interpretation": review.clinical_interpretation,
            "brief_summary": review.brief_summary,
            "doctor_summary": review.doctor_summary,
            # The current frontend renders result_text and key_findings. Keep those
            # paths useful while also storing the structured fields separately.
            "result_text": _structured_result_text(review),
            "key_findings": _visible_findings(review),
        }
    )
    return metadata


async def _enhance_report_document_structured(
    review: RadiologyMediaReview | None,
) -> RadiologyMediaReview | None:
    if review is None or review.document_kind != "REPORT_DOCUMENT":
        return review

    visible_text = (review.visible_text or "").strip()
    if len(visible_text) < 10:
        return review

    try:
        clinical = await summarize_medical_report_text(visible_text)
    except Exception:
        return review
    if clinical is None:
        return review

    source_conclusion = review.result_text or clinical.conclusion
    conclusion_item = universal_runtime._source_conclusion_finding(source_conclusion)
    technical_items = [f"Teknik bulgu: {item}" for item in clinical.technical_findings]
    explicit_recommendations = [
        f"Rapordaki öneri: {item}" for item in clinical.recommendations
    ]
    result_items = universal_runtime._dedupe(
        ([conclusion_item] if conclusion_item else [])
        + technical_items
        + list(review.result_items)
        + list(clinical.key_findings)
        + explicit_recommendations,
        limit=48,
    )
    key_findings = universal_runtime._dedupe(
        technical_items
        + list(review.key_findings)
        + list(clinical.key_findings)
        + explicit_recommendations,
        limit=48,
    )
    recommendations = universal_runtime._dedupe(
        list(review.recommendations) + list(clinical.recommendations),
        limit=16,
    )
    limitations = universal_runtime._dedupe(
        list(review.limitations) + list(clinical.limitations),
        limit=12,
    )

    return replace(
        review,
        summary=clinical.doctor_summary,
        # RadiologyMediaReview has no dedicated structured contract fields, so use
        # a labelled source-faithful block for photographed report documents.
        result_text=_structured_result_text(clinical),
        result_items=tuple(result_items),
        key_findings=tuple(key_findings),
        recommendations=tuple(recommendations),
        comparison_text=clinical.comparison_text or review.comparison_text,
        limitations=limitations,
        report_type=clinical.report_type or review.report_type,
        detected_modality=(
            clinical.modality
            if clinical.modality not in {"UNKNOWN", "OTHER"}
            else review.detected_modality
        ),
        detected_body_part=(
            clinical.body_part if clinical.body_part != "OTHER" else review.detected_body_part
        ),
    )


# Existing persistence wrappers resolve these globals at call time, so replacing
# them here upgrades all manual/text/PDF/DOCX paths without duplicating routes.
universal_runtime._merge_review_metadata = _merge_review_metadata_structured
universal_runtime._enhance_report_document = _enhance_report_document_structured
