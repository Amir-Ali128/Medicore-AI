"""Enrich compact clinical evidence with deterministic lab reference bounds.

This does not increase what is required to classify a laboratory result. It only
preserves the already-resolved reference limits and backend rule reason so the UI
can explain exactly why a HIGH/LOW result was classified that way.
"""

from __future__ import annotations

from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService

_original_build_evidence = ClaudeClinicalHypothesisService._build_evidence


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_evidence_with_reference_bounds(results: list[Any]) -> list[dict[str, Any]]:
    evidence = list(_original_build_evidence(results))
    by_id = {
        str(getattr(result, "id", "")): result
        for result in results
        if getattr(result, "id", None) is not None
    }

    for item in evidence:
        result = by_id.get(str(item.get("lab_result_id") or ""))
        if result is None:
            continue

        item["reference_min"] = _as_text(getattr(result, "reference_min", None))
        item["reference_max"] = _as_text(getattr(result, "reference_max", None))
        item["reference_source"] = _as_text(getattr(result, "reference_source", None))
        item["classification_reason"] = _as_text(getattr(result, "reason", None))
        item["rule_applied"] = _as_text(getattr(result, "rule_applied", None))

    return evidence


ClaudeClinicalHypothesisService._build_evidence = staticmethod(
    _build_evidence_with_reference_bounds
)
