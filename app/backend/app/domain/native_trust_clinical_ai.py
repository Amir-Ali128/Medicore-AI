"""Native C++ trust envelope -> clinical AI bridge.

This module is the final laboratory trust boundary before generative synthesis.
Only rows explicitly marked ``trusted_for_ai`` by the native trust layer may become
primary laboratory evidence. Review rows are visible to the clinical service only as
non-authoritative limitations and can never be promoted back into trusted evidence.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.domain.canonical_native_trust import (
    NATIVE_PROVENANCE_CONTRACT,
    NATIVE_TRUST_CONTRACT,
)
from app.domain.native_lab_engine import (
    LAB_METRICS_CONTRACT,
    compute_native_lab_metrics,
)
from app.domain.openai_lab_clinical_service import (
    OpenAILabClinicalError,
    build_fallback_clinical_assessment,
    synthesize_lab_clinical_assessment,
)

NATIVE_TRUST_CLINICAL_AI_CONTRACT = "medicore-native-trust-clinical-ai-v1"
TRUSTED_METRICS_POLICY = "native_cpp_trusted_rows_only-v1"
_TRUSTED_RESULTS = frozenset({"NORMAL", "LOW", "HIGH"})


def _as_rows(value: Any, *, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"Native trust envelope {field} listesi içermelidir.")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"Native trust envelope {field}[{index}] object olmalıdır.")
        rows.append(dict(item))
    return rows


def _validate_trusted_row(row: Mapping[str, Any]) -> None:
    if row.get("provenance_contract_version") != NATIVE_PROVENANCE_CONTRACT:
        raise ValueError("Trusted satır native provenance contract taşımıyor.")
    if not bool(row.get("trusted_for_ai")) or str(row.get("trust_status") or "").upper() != "TRUSTED":
        raise ValueError("Trusted satır C++ trust engine tarafından TRUSTED işaretlenmemiş.")
    if str(row.get("validation_status") or "").upper() != "VALID":
        raise ValueError("Trusted satır validation_status=VALID olmalıdır.")
    if bool(row.get("needs_review")):
        raise ValueError("Trusted satır needs_review taşıyamaz.")
    if str(row.get("result_status") or "").upper() not in _TRUSTED_RESULTS:
        raise ValueError("Trusted satır güvenilir NORMAL/LOW/HIGH sonucu taşımıyor.")


def _validate_review_row(row: Mapping[str, Any]) -> None:
    if row.get("provenance_contract_version") != NATIVE_PROVENANCE_CONTRACT:
        raise ValueError("Review satırı native provenance contract taşımıyor.")
    if bool(row.get("trusted_for_ai")) or str(row.get("trust_status") or "").upper() == "TRUSTED":
        raise ValueError("Review satırı trusted evidence olarak işaretlenemez.")


def validate_native_trust_envelope(
    envelope: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(envelope, Mapping):
        raise ValueError("Native trust envelope object olmalıdır.")
    if envelope.get("contract_version") != NATIVE_TRUST_CONTRACT:
        raise ValueError("Native trust contract sürümü uyumsuz.")
    if envelope.get("provenance_contract_version") != NATIVE_PROVENANCE_CONTRACT:
        raise ValueError("Native trust provenance contract sürümü uyumsuz.")

    trusted = _as_rows(envelope.get("trusted_rows"), field="trusted_rows")
    review = _as_rows(envelope.get("review_rows"), field="review_rows")
    all_rows = _as_rows(envelope.get("all_rows"), field="all_rows")

    if int(envelope.get("trusted_count") or 0) != len(trusted):
        raise ValueError("Native trust trusted_count tutarsız.")
    if int(envelope.get("review_count") or 0) != len(review):
        raise ValueError("Native trust review_count tutarsız.")
    if int(envelope.get("processed_row_count") or 0) != len(all_rows):
        raise ValueError("Native trust processed_row_count tutarsız.")
    if len(all_rows) != len(trusted) + len(review):
        raise ValueError("Native trust partition satır sayıları tutarsız.")

    for row in trusted:
        _validate_trusted_row(row)
    for row in review:
        _validate_review_row(row)
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
    """Serialize the native partition for the legacy clinical synthesis API.

    The existing clinical service re-partitions by validation/review state. Native
    trust can be stricter than that legacy rule, so every review-row copy receives a
    policy-only review marker. Native result_status and validation_status are preserved
    byte-for-byte and are never overwritten.
    """
    payload: list[dict[str, Any]] = [dict(row) for row in trusted_rows]
    for source in review_rows:
        row = dict(source)
        row["native_needs_review"] = bool(row.get("needs_review"))
        row["needs_review"] = True
        row["ai_policy_review_only"] = True
        payload.append(row)
    return payload


def _fallback(
    *,
    rows: Sequence[Mapping[str, Any]],
    derived_metrics: Sequence[Mapping[str, Any]],
    reason: str,
) -> dict[str, Any]:
    assessment = build_fallback_clinical_assessment(
        rows=rows,
        derived_metrics=derived_metrics,
    )
    assessment["fallback_reason"] = reason
    return assessment


async def run_native_trust_clinical_pipeline(
    envelope: Mapping[str, Any],
    *,
    use_external_ai: bool = True,
) -> dict[str, Any]:
    """Run a C++ trust envelope through deterministic metrics and clinical synthesis.

    Derived metrics are intentionally calculated from ``trusted_rows`` only in this
    strict AI-facing pipeline. This is more conservative than standalone metric APIs:
    no review-only measurement can influence the generative clinical summary.
    """
    trusted_rows, review_rows, _all_rows = validate_native_trust_envelope(envelope)
    service_rows = _rows_for_clinical_service(trusted_rows, review_rows)

    derived_metrics: list[dict[str, Any]] = []
    if trusted_rows:
        derived_metrics = compute_native_lab_metrics(
            trusted_rows,
            patient_age=_metric_age(envelope.get("patient_age")),
            patient_sex=str(envelope.get("patient_sex") or "") or None,
        )

    ai_attempted = False
    if not trusted_rows:
        assessment = _fallback(
            rows=service_rows,
            derived_metrics=derived_metrics,
            reason="no_trusted_native_evidence",
        )
    elif not use_external_ai:
        assessment = _fallback(
            rows=service_rows,
            derived_metrics=derived_metrics,
            reason="external_ai_disabled",
        )
    else:
        ai_attempted = True
        try:
            assessment = await synthesize_lab_clinical_assessment(
                rows=service_rows,
                derived_metrics=derived_metrics,
                patient_age=_metric_age(envelope.get("patient_age")),
                patient_sex=str(envelope.get("patient_sex") or "") or None,
            )
        except OpenAILabClinicalError:
            # Do not echo provider/runtime error details into API payloads. The caller
            # only needs the stable fallback category; operational details belong in logs.
            assessment = _fallback(
                rows=service_rows,
                derived_metrics=derived_metrics,
                reason="clinical_ai_unavailable",
            )

    return {
        "contract_version": NATIVE_TRUST_CLINICAL_AI_CONTRACT,
        "trust_contract_version": NATIVE_TRUST_CONTRACT,
        "provenance_contract_version": NATIVE_PROVENANCE_CONTRACT,
        "metrics_contract_version": LAB_METRICS_CONTRACT,
        "metrics_policy": TRUSTED_METRICS_POLICY,
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
        "clinical_assessment": assessment,
        "ai_attempted": ai_attempted,
        "ai_used": assessment.get("synthesis_source") == "ai_after_native_cpp",
        "doctor_review_required": bool(review_rows),
    }
