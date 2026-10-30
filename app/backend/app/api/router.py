"""MediCore API router.

The active API surface is intentionally small: authentication/patient context,
source medical reports, and the simplified clinical + lab + reports contract.

Legacy native C++/ONNX laboratory and vision pipelines are no longer wired into
the application.
"""

from fastapi import APIRouter

from app.api.routes import (
    analytics,
    auth,
    clinical_voice,
    feedback,
    lab_reports,
    patient_timeline,
    patients,
    radiology_reports,
    simple_case,
)


api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(clinical_voice.router)
api_router.include_router(analytics.router)
api_router.include_router(feedback.router)
api_router.include_router(lab_reports.router)
api_router.include_router(patients.router)
api_router.include_router(patient_timeline.router)
api_router.include_router(radiology_reports.router)
api_router.include_router(simple_case.router)

# The existing admin cost endpoint is exposed only for the opt-in reader telemetry.
from app.core.config import get_settings
if getattr(get_settings(), 'lab_cross_read_enabled', False):
    from app.api.routes import ai_cost_analytics
    api_router.include_router(ai_cost_analytics.router)
