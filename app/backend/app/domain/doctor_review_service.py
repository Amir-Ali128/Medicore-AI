"""DoctorReviewService.

Applies a physician's review action to a clinical hypothesis and maps the action
onto the hypothesis status. It owns no AI logic, produces no diagnosis and no
treatment advice, and does not commit — the caller (route) owns the transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.domain.enums import ReviewAction
from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
from app.infrastructure.database.models.doctor_review import DoctorReview
from app.infrastructure.database.repositories.clinical_hypothesis_repository import (
    ClinicalHypothesisRepository,
)
from app.infrastructure.database.repositories.doctor_review_repository import (
    DoctorReviewRepository,
)
from app.schemas.doctor_review import DoctorReviewCreate


_STATUS_MAP: dict[ReviewAction, str] = {
    ReviewAction.APPROVE: "approved",
    ReviewAction.REJECT: "rejected",
    ReviewAction.EDIT: "edited",
    ReviewAction.REQUEST_EXTRA_TEST: "extra_test_requested",
    ReviewAction.REFER_SPECIALIST: "specialist_referred",
}


class DoctorReviewService:
    def __init__(
        self,
        hypothesis_repository: ClinicalHypothesisRepository,
        review_repository: DoctorReviewRepository,
    ) -> None:
        self._hypotheses = hypothesis_repository
        self._reviews = review_repository

    async def apply_review(
        self,
        clinical_hypothesis_id: uuid.UUID,
        payload: DoctorReviewCreate,
    ) -> tuple[ClinicalHypothesis, DoctorReview]:
        hypothesis = await self._hypotheses.get_by_id(clinical_hypothesis_id)

        if hypothesis is None:
            raise ValueError("Clinical hypothesis not found.")

        now = datetime.now(timezone.utc)

        review = DoctorReview(
            clinical_hypothesis_id=hypothesis.id,
            doctor_id=payload.doctor_id,
            action=payload.action,
            doctor_note=payload.doctor_note,
            edited_title=(
                payload.edited_title
                if payload.action == ReviewAction.EDIT
                else None
            ),
            edited_summary=(
                payload.edited_summary
                if payload.action == ReviewAction.EDIT
                else None
            ),
            requested_tests_json=list(payload.requested_tests_json or []),
            specialist_referral=payload.specialist_referral,
            reviewed_at=now,
            metadata_json=dict(payload.metadata_json),
        )

        self._reviews.create(review)

        new_status = _STATUS_MAP.get(payload.action, hypothesis.status)
        self._hypotheses.update_status(hypothesis, new_status)

        hypothesis.reviewed_at = now
        hypothesis.reviewed_by_user_id = payload.doctor_id
        hypothesis.needs_doctor_review = False

        await self._hypotheses.flush()

        return hypothesis, review
