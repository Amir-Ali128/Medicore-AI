"""Expose source fidelity and trend delta fields in lab-analysis API output."""

from __future__ import annotations

from app.domain.analysis_pipeline import AnalysisPipeline


_original_to_output = AnalysisPipeline._to_output


def _to_output_with_source_and_trend(result):
    output = _original_to_output(result)
    return output.model_copy(
        update={
            "raw_value": result.raw_value,
            "measured_at": result.measured_at,
            "previous_value": result.previous_value,
            "absolute_difference": result.absolute_difference,
            "percentage_difference": result.percentage_difference,
            "time_difference_days": result.time_difference_days,
        }
    )


AnalysisPipeline._to_output = staticmethod(_to_output_with_source_and_trend)
