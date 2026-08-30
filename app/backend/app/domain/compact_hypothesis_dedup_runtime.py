"""Prevent duplicate compact evaluation records for the same analysis run.

The compact evaluation is a current snapshot, not an append-only event. Reuse the
newest existing compact hypothesis for an analysis run so repeated clicks do not
create duplicate cards or spend additional LLM tokens.
"""

from __future__ import annotations

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService
from app.schemas.clinical_copilot import ClinicalHypothesisGenerationResult
from app.schemas.clinical_hypothesis import ClinicalHypothesisResponse

_COMPACT_TYPE = "compact_risk_summary"
_COMPACT_SOURCE = "claude_compact_risk_summary"

_original_generate = ClaudeClinicalHypothesisService.generate_for_analysis_run


async def _generate_without_duplicates(self, analysis_run_id, request):
    existing = list(await self._hypotheses.list_for_analysis_run(analysis_run_id))
    compact = next(
        (
            item
            for item in existing
            if getattr(item, "hypothesis_type", None) == _COMPACT_TYPE
            or getattr(item, "source", None) == _COMPACT_SOURCE
        ),
        None,
    )

    if compact is not None:
        return ClinicalHypothesisGenerationResult(
            analysis_run_id=analysis_run_id,
            lab_report_id=compact.lab_report_id,
            patient_id=compact.patient_id,
            created_hypotheses=[ClinicalHypothesisResponse.model_validate(compact)],
            drafts_count=1,
            created_count=0,
            warnings=["Existing compact evaluation reused; duplicate generation skipped."],
        )

    return await _original_generate(self, analysis_run_id, request)


ClaudeClinicalHypothesisService.generate_for_analysis_run = _generate_without_duplicates
