"""Runtime integration for universal medical-report reading.

Keeps the existing radiology/DXA deterministic parser as a safe baseline, then
adds a universal source-faithful physician-style summary for text reports. It
also upgrades photographed written reports after multimodal extraction.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.api.routes import radiology_image_review, radiology_reports
from app.domain.medical_report_summary_ai import (
    MedicalReportReview,
    summarize_medical_report_text,
)
from app.domain.report_document_image_ai import RadiologyMediaReview


_original_persist_report = radiology_reports._persist_report
_original_extract_upload_text = radiology_reports._extract_upload_text
_original_anthropic_image_reader = radiology_image_review.review_radiology_media
_original_openai_image_reader = radiology_image_review.review_radiology_media_openai
_original_gemini_image_reader = radiology_image_review.review_radiology_media_gemini

_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _dedupe(values: list[str], *, limit: int = 40) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = " ".join(str(value or "").split()).strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _source_conclusion_finding(conclusion: str) -> str | None:
    text = " ".join(conclusion.split()).strip()
    return f"Kaynak sonuç / kanaat: {text}" if text else None


def _extract_docx_text(content: bytes) -> str:
    """Extract visible paragraph text from a DOCX using only the stdlib."""

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(document_xml)
    except (KeyError, OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("DOCX rapor metni okunamadı.") from exc

    paragraphs: list[str] = []
    for paragraph in root.iter():
        if not paragraph.tag.endswith("}p"):
            continue
        pieces: list[str] = []
        for node in paragraph.iter():
            if node.tag.endswith("}t") and node.text:
                pieces.append(node.text)
            elif node.tag.endswith("}tab"):
                pieces.append("\t")
            elif node.tag.endswith("}br"):
                pieces.append("\n")
        text = "".join(pieces).strip()
        if text:
            paragraphs.append(text)

    extracted = "\n".join(paragraphs).strip()
    if len(extracted) < 10:
        raise ValueError("DOCX dosyasından kullanılabilir klinik rapor metni çıkarılamadı.")
    return extracted


def _extract_upload_text_with_docx(
    filename: str,
    content_type: str | None,
    content: bytes,
) -> tuple[str | None, str]:
    suffix = Path(filename).suffix.lower()
    normalized_content_type = (content_type or "").split(";", 1)[0].lower().strip()
    if suffix == ".docx" or normalized_content_type == _DOCX_CONTENT_TYPE:
        try:
            return _extract_docx_text(content), "docx_upload"
        except ValueError:
            # Preserve the original file rather than losing a report whose text
            # cannot be extracted safely. The UI can keep it in the review queue.
            return None, "binary_file_upload"
    return _original_extract_upload_text(filename, content_type, content)


def _merge_review_metadata(metadata: dict[str, Any], review: MedicalReportReview) -> dict[str, Any]:
    source_conclusion = _source_conclusion_finding(review.conclusion)
    key_findings = _dedupe(
        ([source_conclusion] if source_conclusion else []) + list(review.key_findings)
    )
    metadata.update(
        {
            "analysis_available": True,
            "document_analysis_available": True,
            "analysis_mode": "universal_medical_report_clinical_summary",
            "report_category": review.report_category,
            "report_type": review.report_type,
            "specialty": review.specialty,
            "doctor_summary": review.doctor_summary,
            # Existing frontend uses result_text as the primary clinical-result card.
            # Put the physician-style summary there; preserve the source conclusion
            # separately so no source meaning is lost.
            "result_text": review.doctor_summary,
            "source_conclusion": review.conclusion,
            "key_findings": key_findings,
            "abnormal_findings": list(review.abnormal_findings),
            "reassuring_findings": list(review.reassuring_findings),
            "recommendations": list(review.recommendations),
            "critical_flags": list(review.critical_flags),
            "comparison_text": review.comparison_text,
            "analysis_limitations": list(review.limitations),
            "clinical_summary_confidence": review.confidence,
            "clinical_summary_model": review.model,
            "physician_review_required": True,
            "not_diagnostic": True,
        }
    )
    return metadata


async def _persist_report_with_universal_reader(*args: Any, **kwargs: Any):
    report = await _original_persist_report(*args, **kwargs)
    payload = kwargs.get("payload")
    session = kwargs.get("session")
    if payload is None or session is None:
        return report

    try:
        review = await summarize_medical_report_text(payload.report_text)
    except Exception as exc:
        metadata = dict(report.metadata_json or {})
        metadata["universal_report_summary_status"] = "unavailable"
        metadata["universal_report_summary_error_type"] = exc.__class__.__name__
        report.metadata_json = metadata
        await session.commit()
        await session.refresh(report)
        return report

    if review is None:
        metadata = dict(report.metadata_json or {})
        metadata["universal_report_summary_status"] = "not_configured"
        report.metadata_json = metadata
        await session.commit()
        await session.refresh(report)
        return report

    metadata = _merge_review_metadata(dict(report.metadata_json or {}), review)
    metadata["universal_report_summary_status"] = "completed"
    report.metadata_json = metadata
    report.summary = review.doctor_summary
    if review.conclusion:
        report.impression = review.conclusion

    # Explicit user selections win. Otherwise let the universal reader improve the
    # generic deterministic classification for non-radiology report families too.
    if not getattr(payload, "modality", None) and review.modality not in {"UNKNOWN", "OTHER"}:
        report.modality = review.modality
    if not getattr(payload, "body_part", None) and review.body_part != "OTHER":
        report.body_part = review.body_part

    source_conclusion = _source_conclusion_finding(review.conclusion)
    ai_finding_texts = _dedupe(
        ([source_conclusion] if source_conclusion else []) + list(review.key_findings)
    )
    existing_findings = list(report.findings_json or [])
    existing_texts = {
        " ".join(str(item.get("text") or "").split()).strip()
        for item in existing_findings
        if isinstance(item, dict)
    }
    for finding in ai_finding_texts:
        if finding in existing_texts:
            continue
        existing_findings.append(
            {
                "text": finding,
                "classification": "source_report_finding",
                "is_critical": False,
                "matched_terms": ["universal_report_reader"],
            }
        )
    report.findings_json = existing_findings[:80]

    critical = _dedupe(list(report.critical_findings_json or []) + list(review.critical_flags), limit=20)
    report.critical_findings_json = critical
    report.status = "needs_review" if critical else "analyzed"

    await session.commit()
    await session.refresh(report)
    return report


async def _enhance_report_document(review: RadiologyMediaReview | None) -> RadiologyMediaReview | None:
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
    conclusion_item = _source_conclusion_finding(source_conclusion)
    result_items = _dedupe(
        ([conclusion_item] if conclusion_item else [])
        + list(review.result_items)
        + list(clinical.key_findings),
        limit=32,
    )
    key_findings = _dedupe(list(review.key_findings) + list(clinical.key_findings), limit=32)
    recommendations = _dedupe(
        list(review.recommendations) + list(clinical.recommendations),
        limit=16,
    )
    limitations = _dedupe(list(review.limitations) + list(clinical.limitations), limit=12)

    # The image-review route prefers result_text over summary. Put the clinical
    # synthesis in result_text so the current UI immediately shows the physician-
    # style summary, while the exact source conclusion remains in result_items.
    return replace(
        review,
        summary=clinical.doctor_summary,
        result_text=clinical.doctor_summary,
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


async def _anthropic_reader_with_clinical_summary(*args: Any, **kwargs: Any):
    return await _enhance_report_document(
        await _original_anthropic_image_reader(*args, **kwargs)
    )


async def _openai_reader_with_clinical_summary(*args: Any, **kwargs: Any):
    return await _enhance_report_document(
        await _original_openai_image_reader(*args, **kwargs)
    )


async def _gemini_reader_with_clinical_summary(*args: Any, **kwargs: Any):
    return await _enhance_report_document(
        await _original_gemini_image_reader(*args, **kwargs)
    )


if not getattr(radiology_reports._extract_upload_text, "_medicore_docx_report_reader", False):
    setattr(_extract_upload_text_with_docx, "_medicore_docx_report_reader", True)
    radiology_reports._extract_upload_text = _extract_upload_text_with_docx

if not getattr(radiology_reports._persist_report, "_medicore_universal_report_reader", False):
    setattr(_persist_report_with_universal_reader, "_medicore_universal_report_reader", True)
    radiology_reports._persist_report = _persist_report_with_universal_reader

if not getattr(radiology_image_review.review_radiology_media, "_medicore_universal_report_reader", False):
    setattr(_anthropic_reader_with_clinical_summary, "_medicore_universal_report_reader", True)
    radiology_image_review.review_radiology_media = _anthropic_reader_with_clinical_summary

if not getattr(radiology_image_review.review_radiology_media_openai, "_medicore_universal_report_reader", False):
    setattr(_openai_reader_with_clinical_summary, "_medicore_universal_report_reader", True)
    radiology_image_review.review_radiology_media_openai = _openai_reader_with_clinical_summary

if not getattr(radiology_image_review.review_radiology_media_gemini, "_medicore_universal_report_reader", False):
    setattr(_gemini_reader_with_clinical_summary, "_medicore_universal_report_reader", True)
    radiology_image_review.review_radiology_media_gemini = _gemini_reader_with_clinical_summary
