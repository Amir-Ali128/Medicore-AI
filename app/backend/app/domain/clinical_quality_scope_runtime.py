"""Keep recommendation de-duplication scoped to the active multisource case.

The case evaluation screen can load a patient's radiology history so the active
ultrasound can be selected. Historical studies must not suppress a recommendation
for the current case merely because the patient had a similar study months earlier.

This small runtime is imported after ``clinical_quality_runtime`` and narrows the
``performed_studies`` list to studies whose date matches the ultrasound source date
used in the current case. If the active source date is unavailable, imaging history
is not used for de-duplication because case membership cannot be proven.
"""

from __future__ import annotations

from typing import Any

from app.domain import clinical_quality_runtime as quality_runtime


_original_filter_recommendations = quality_runtime._filter_recommendations


def _date_key(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    candidate = text[:10]
    return candidate if candidate[4:5] == "-" and candidate[7:8] == "-" else None


def _active_case_performed_studies(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    performed = metadata.get("performed_studies")
    if not isinstance(performed, list):
        return []

    source_dates = metadata.get("source_dates")
    if not isinstance(source_dates, dict):
        return []

    active_ultrasound_date = _date_key(source_dates.get("ultrasound"))
    if active_ultrasound_date is None:
        return []

    scoped: list[dict[str, Any]] = []
    for item in performed:
        if not isinstance(item, dict):
            continue
        if _date_key(item.get("date")) != active_ultrasound_date:
            continue
        scoped.append(item)
    return scoped


def _filter_recommendations_for_active_case(
    metadata: dict[str, Any],
    results: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    scoped_metadata = dict(metadata)
    scoped_metadata["performed_studies"] = _active_case_performed_studies(metadata)
    return _original_filter_recommendations(scoped_metadata, results)


quality_runtime._filter_recommendations = _filter_recommendations_for_active_case
