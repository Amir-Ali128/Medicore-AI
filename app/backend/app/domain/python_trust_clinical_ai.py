"""Pure-Python trust envelope -> clinical AI bridge."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.domain.canonical_python_trust import (
    PYTHON_PROVENANCE_CONTRACT,
    PYTHON_TRUST_CONTRACT,
)
from app.domain.openai_lab_clinical_service import (
    OpenAILabClinicalError,
    build_fallback_clinical_assessment,
    synthesize_lab_clinical_assessment,
)
from app.domain.python_lab_engine import (
    LAB_METRICS_CONTRACT,
    compute_python_lab_metrics,
)

PYTHON_TRUST_CLINICAL_AI_CONTRACT = "medicore-python-trust-clinical-ai-v1"
TRUSTED_METRICS_POLICY = "python_validated_rows_only-v1"
LONGITUDINAL_AI_POLICY = "python_trends_only-v1"
_TRUSTED_RESULTS = frozenset({"NORMAL", "LOW", "HIGH"})


def _as_rows(value: Any, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise ValueError(f"Python trust envelope {field} listesi içermelidir.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"Python trust envelope {field}[{index}] object olmalıdır."
            )
        rows.append(dict(item))
    return rows


def validate_python_trust_envelope(
    envelope: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(envelope, Mapping):
        raise ValueError("Python trust envelope object olmalıdır.")
    if envelope.get("contract_version") != PYTHON_TRUST_CONTRACT:
        raise ValueError("Python trust contract sürümü uyumsuz.")
    if envelope.get("provenance_contract_version") != PYTHON_PROVENANCE_CONTRACT:
        raise ValueError("Python trust provenance contract sürümü uyumsuz.")

    trusted = _as_rows(envelope.get("trusted_rows"), field="trusted_rows")
    review = _as_rows(envelope.get("review_rows"), field="review_rows")
    all_rows = _as_rows(envelope.get("all_rows"), field="all_rows")

    if int(envelope.get("trusted_count") or 0) != len(trusted):
        raise ValueError("Python trust trusted_count tutarsız.")
    if int(envelope.get("review_count") or 0) != len(review):
        raise ValueError("Python trust review_count tutarsız.")
    if int(envelope.get("processed_row_count") or 0) != len(all_rows):
        raise ValueError("Python trust processed_row_count tutarsız.")

    for row in trusted:
        if (
            not bool(row.get("trusted_for_ai"))
            or str(row.get("validation_status") or "").upper() != "VALID"
            or bool(row.get("needs_review"))
            or str(row.get("result_status") or "").upper()
            not in _TRUSTED_RESULTS
        ):
            raise ValueError("Trusted satır Python doğrulama politikasını karşılamıyor.")

    return trusted, review, all_rows


def _metric_age(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or numeric > 130 or not numeric.is_integer():
        return None
    return int(numeric)


def _rows_for_clinical_service(
    trusted_rows: Sequence[Mapping[str, Any]],
    review_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    payload = [dict(row) for row in trusted_rows]
    for source in review_rows:
        row = dict(source)
        row["needs_review"] = True
        row["ai_policy_review_only"] = True
        payload.append(row)
    return payload


def _python_trend_metrics(
    trends: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for trend in trends:
        if str(trend.get("backend") or "") != "python":
            continue
        status = str(trend.get("trend_status") or "").upper()
        if status not in {"UP", "DOWN", "STABLE"}:
            continue
        name = str(
            trend.get("test")
            or trend.get("parameter_code")
            or "Laboratory trend"
        )
        value = trend.get("percentage_difference")
        metrics.append(
            {
                "code": f"trend:{trend.get('parameter_code') or name}"[:128],
                "name": f"{name} longitudinal trend",
                "value": value if value is not None else 0.0,
                "unit": "% change" if value is not None else "",
                "formula": "Python Decimal current-vs-previous comparison",
                "input_labels": [name],
                "note": (
                    f"status={status}; previous={trend.get('previous_value')}; "
                    f"current={trend.get('current_value')}; "
                    f"days={trend.get('time_difference_days')}. "
                    "Use only as longitudinal context; do not recalculate."
                ),
            }
        )
    return metrics


async def run_python_trust_clinical_pipeline(
    envelope: Mapping[str, Any],
    *,
    use_external_ai: bool = True,
    longitudinal_trends: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    trusted_rows, review_rows, _ = validate_python_trust_envelope(envelope)
    service_rows = _rows_for_clinical_service(trusted_rows, review_rows)

    derived_metrics = compute_python_lab_metrics(
        trusted_rows,
        patient_age=_metric_age(envelope.get("patient_age")),
        patient_sex=str(envelope.get("patient_sex") or "") or None,
    )
    trend_metrics = _python_trend_metrics(longitudinal_trends)
    ai_metrics = [*derived_metrics, *trend_metrics]

    ai_attempted = False
    if not trusted_rows or not use_external_ai:
        assessment = build_fallback_clinical_assessment(
            rows=service_rows,
            derived_metrics=ai_metrics,
        )
    else:
        ai_attempted = True
        try:
            assessment = await synthesize_lab_clinical_assessment(
                rows=service_rows,
                derived_metrics=ai_metrics,
                patient_age=_metric_age(envelope.get("patient_age")),
                patient_sex=str(envelope.get("patient_sex") or "") or None,
            )
        except OpenAILabClinicalError:
            assessment = build_fallback_clinical_assessment(
                rows=service_rows,
                derived_metrics=ai_metrics,
            )

    return {
        "contract_version": PYTHON_TRUST_CLINICAL_AI_CONTRACT,
        "trust_contract_version": PYTHON_TRUST_CONTRACT,
        "provenance_contract_version": PYTHON_PROVENANCE_CONTRACT,
        "metrics_contract_version": LAB_METRICS_CONTRACT,
        "metrics_policy": TRUSTED_METRICS_POLICY,
        "longitudinal_ai_policy": LONGITUDINAL_AI_POLICY,
        "source_type": envelope.get("source_type"),
        "source": dict(envelope.get("source") or {}),
        "patient_age": envelope.get("patient_age"),
        "patient_sex": envelope.get("patient_sex"),
        "report_date": envelope.get("report_date"),
        "trusted_count": len(trusted_rows),
        "review_count": len(review_rows),
        "trusted_rows": trusted_rows,
        "review_rows": review_rows,
        "derived_metrics": derived_metrics,
        "longitudinal_trends": [dict(item) for item in longitudinal_trends],
        "python_trends_used_by_ai": len(trend_metrics),
        "clinical_assessment": assessment,
        "ai_attempted": ai_attempted,
        "ai_used": assessment.get("synthesis_source")
        == "ai_after_python_validation",
        "doctor_review_required": bool(review_rows),
    }
