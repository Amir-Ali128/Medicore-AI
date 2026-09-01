"""Keep compact AI evaluation focused strictly on HIGH/LOW laboratory rows.

Normal laboratory values are useful for the source record, but the combined case
summary and compact AI review should not spend attention or tokens on them. Rows
that are merely marked needs_review without a HIGH/LOW classification are also
excluded from the compact abnormal-lab evidence path.
"""

from __future__ import annotations

from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


def _review_results_high_low_only(
    results: list[Any],
    request: Any,
) -> list[Any]:
    del request
    selected: list[Any] = []
    for result in results:
        status = ClaudeClinicalHypothesisService._status_value(result)
        if status in {"high", "low"}:
            selected.append(result)
    return selected


ClaudeClinicalHypothesisService._review_results = staticmethod(
    _review_results_high_low_only
)
