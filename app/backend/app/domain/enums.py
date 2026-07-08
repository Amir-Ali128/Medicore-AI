"""Domain enumerations.


Pure, framework-agnostic value objects that belong to the domain layer. They
carry no persistence concerns; the infrastructure layer maps them onto native
PostgreSQL enum types. String-valued members keep the stored representation
stable and human-readable regardless of member renaming.
"""


from __future__ import annotations


from enum import StrEnum




class UserRole(StrEnum):
    """Access role of an authenticated user."""


    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"
    LAB_STAFF = "lab_staff"
    VIEWER = "viewer"
    SYSTEM = "system"




class AnalysisLevel(StrEnum):
    """Depth at which a parameter participates in analysis.


    L0 is a passive dictionary record (recognized but not analysed). L4 is the
    Phase 1 active tier eligible for rule-based numeric range validation.
    """


    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"




class ResultStatus(StrEnum):
    """Outcome of evaluating a single measured value against its range."""


    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"
    NEEDS_REVIEW = "needs_review"
    UNKNOWN = "unknown"




class TrendStatus(StrEnum):
    """Direction of a parameter across successive measurements."""


    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    NO_PREVIOUS_RESULT = "no_previous_result"




class ReviewAction(StrEnum):
    """Human review decision within the review workflow."""


    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    REQUEST_EXTRA_TEST = "request_extra_test"
    REFER_SPECIALIST = "refer_specialist"




class Sex(StrEnum):
    """Biological sex.


    `ANY` is used by reference ranges that apply irrespective of sex (e.g.
    most pediatric ranges); it is not intended as a patient attribute.
    """


    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    UNKNOWN = "unknown"
    ANY = "any"




def enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Return member *values* for SQLAlchemy `Enum(values_callable=...)`.


    Ensures the database persists the stable string value rather than the
    Python member name.
    """
    return [member.value for member in enum_cls]

