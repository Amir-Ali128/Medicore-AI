"""Build physician-facing abnormal-lab evidence with exact source fidelity.

The compact model still receives only symptoms/source summaries and bounded backend
flags. This evidence is created after the model call and is stored only as structured
metadata for the UI, so every HIGH/LOW laboratory row can be explained without
increasing LLM prompt size.
"""

from __future__ import annotations

from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _status_value(result: Any) -> str:
    status = getattr(result, "result_status", None)
    return str(getattr(status, "value", status) or "unknown").lower()


def _build_evidence_with_reference_bounds(results: list[Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []

    # review_results already excludes normal values in compact mode. Keep all of
    # them (bounded defensively) so a report with 18 abnormal parameters displays
    # all 18 rather than silently stopping at the legacy first 10.
    for result in results[:100]:
        value = getattr(result, "normalized_value", None)
        trend = getattr(result, "trend_status", None)
        source_name = (
            _as_text(getattr(result, "raw_parameter_name", None))
            or _as_text(getattr(result, "canonical_name", None))
            or "Laboratuvar parametresi"
        )
        evidence.append(
            {
                "lab_result_id": str(getattr(result, "id", "")) or None,
                "parameter_code": _as_text(getattr(result, "parameter_code", None)),
                "parameter_name": source_name,
                "raw_value": _as_text(getattr(result, "raw_value", None)),
                "value": str(value) if value is not None else None,
                "unit": _as_text(getattr(result, "unit", None)),
                "result_status": _status_value(result),
                "trend_status": getattr(trend, "value", trend),
                "measured_at": _as_text(getattr(result, "measured_at", None)),
                "previous_value": _as_text(getattr(result, "previous_value", None)),
                "absolute_difference": _as_text(getattr(result, "absolute_difference", None)),
                "percentage_difference": getattr(result, "percentage_difference", None),
                "time_difference_days": getattr(result, "time_difference_days", None),
                "reference_min": _as_text(getattr(result, "reference_min", None)),
                "reference_max": _as_text(getattr(result, "reference_max", None)),
                "reference_source": _as_text(getattr(result, "reference_source", None)),
                "classification_reason": _as_text(getattr(result, "reason", None)),
                "rule_applied": _as_text(getattr(result, "rule_applied", None)),
            }
        )

    return evidence


ClaudeClinicalHypothesisService._build_evidence = staticmethod(
    _build_evidence_with_reference_bounds
)
