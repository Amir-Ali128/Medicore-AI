"""Model registry.

Importing this package imports every ORM model so they are all registered on
`Base.metadata` before `create_all` runs. No models or logic are defined here.
"""

from __future__ import annotations

from app.infrastructure.database.models.analysis_run import AnalysisRun
from app.infrastructure.database.models.clinical_parameter import ClinicalParameter
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.parameter_alias import ParameterAlias
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.reference_range import ReferenceRange
from app.infrastructure.database.models.user import User

__all__ = [
    "User",
    "Patient",
    "ClinicalParameter",
    "ParameterAlias",
    "ReferenceRange",
    "LabReport",
    "LabResult",
    "AnalysisRun",
]
