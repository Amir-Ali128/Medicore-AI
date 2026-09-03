from fastapi import APIRouter

from app.api.routes import (
    ai_cost_analytics,
    analysis_runs,
    analytics,
    auth,
    clinical_copilot,
    clinical_fusion,
    clinical_hypotheses,
    combined_case_import,
    doctor_reviews,
    extraction,
    extraction_review,
    feedback,
    lab_analysis,
    lab_manual_entry,
    lab_pdf_direct_alias,
    lab_pdf_direct_upload,
    lab_pdf_system_extract,
    lab_pdf_system_extract_runtime,
    lab_reports,
    lab_results,
    patient_timeline,
    patients,
    radiology_image_review,
    radiology_reports,
)
from app.domain.radiology_report_safety import analyze_radiology_report_safely
from app.schemas.lab_analysis import PatientMetadataOutput

# Keep the existing radiology routes intact while enforcing the conservative
# findings-only evidence filter for every manual-text and PDF analysis request.
radiology_reports.analyze_radiology_report = analyze_radiology_report_safely


def _privacy_safe_lab_patient_metadata(text: str) -> PatientMetadataOutput:
    """Keep useful coarse demographics while dropping direct PDF identifiers.

    Laboratory PDFs can contain names, surnames, national identity numbers and
    exact dates of birth. Those direct identifiers are not needed for the lab
    value analysis and must not be copied into structured analysis metadata.
    """
    folded_text = lab_analysis._fold_patient_text(text)
    _birth_date, age, sex = lab_analysis._extract_patient_demographics(folded_text)
    return PatientMetadataOutput(
        display_name=None,
        age=age,
        sex=sex,
        birth_date=None,
    )


# The existing parser still uses labels such as "TC Kimlik" to understand where
# table/header sections end, but it no longer returns the person's name, surname,
# T.C. identity number or exact birth date as structured patient metadata.
lab_analysis._parse_patient_metadata_from_text = _privacy_safe_lab_patient_metadata

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(analytics.router)
api_router.include_router(ai_cost_analytics.router)
api_router.include_router(feedback.router)
api_router.include_router(patients.router)
# Stable, unique endpoint used by the frontend for PDF-first parsing.
api_router.include_router(lab_pdf_direct_alias.router)
# Keep /lab-analysis/upload direct-first for backwards compatibility.
api_router.include_router(lab_pdf_direct_upload.router)
api_router.include_router(lab_pdf_system_extract.router)
api_router.include_router(lab_analysis.router)
api_router.include_router(lab_manual_entry.router)
api_router.include_router(combined_case_import.router)
api_router.include_router(lab_reports.router)
api_router.include_router(analysis_runs.router)
api_router.include_router(lab_results.router)
api_router.include_router(clinical_hypotheses.router)
api_router.include_router(doctor_reviews.router)
api_router.include_router(extraction.router)
api_router.include_router(clinical_copilot.router)
api_router.include_router(clinical_fusion.router)
api_router.include_router(extraction_review.router)
api_router.include_router(patient_timeline.router)
api_router.include_router(radiology_reports.router)
api_router.include_router(radiology_image_review.router)
