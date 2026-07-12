from fastapi import APIRouter

from app.api.routes import (
    analysis_runs,
    auth,
    clinical_copilot,
    clinical_hypotheses,
    doctor_reviews,
    extraction,
    extraction_review,
    lab_analysis,
    lab_reports,
    lab_results,
    patient_timeline,
    patients,
    radiology_reports,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(patients.router)
api_router.include_router(lab_analysis.router)
api_router.include_router(lab_reports.router)
api_router.include_router(analysis_runs.router)
api_router.include_router(lab_results.router)
api_router.include_router(clinical_hypotheses.router)
api_router.include_router(doctor_reviews.router)
api_router.include_router(extraction.router)
api_router.include_router(clinical_copilot.router)
api_router.include_router(extraction_review.router)
api_router.include_router(patient_timeline.router)
api_router.include_router(radiology_reports.router)
