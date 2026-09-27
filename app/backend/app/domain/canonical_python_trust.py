"""Canonical laboratory case -> pure-Python trust boundary."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.domain.canonical_lab_model import (
    CANONICAL_LAB_CONTRACT,
    CANONICAL_ROW_CONTRACT,
    CANONICAL_SOURCE_TYPES,
)
from app.domain.python_lab_engine import (
    LAB_PYTHON_CONTRACT,
    LAB_VALIDATION_CONTRACT,
    PYTHON_PROVENANCE_CONTRACT,
    process_lab_rows,
)

PYTHON_TRUST_CONTRACT = "medicore-python-trust-v1"
_MAX_CANONICAL_ROWS = 5000
_TRUSTED_RESULT_STATUSES = frozenset({"NORMAL", "LOW", "HIGH"})


def _validate_canonical_case(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(case, Mapping):
        raise ValueError("Canonical laboratuvar vakası bir object olmalıdır.")
    if case.get("contract_version") != CANONICAL_LAB_CONTRACT:
        raise ValueError("Canonical laboratuvar contract sürümü uyumsuz.")

    source_type = str(case.get("source_type") or "")
    if source_type not in CANONICAL_SOURCE_TYPES:
        raise ValueError("Canonical laboratuvar source_type geçersiz.")

    rows = case.get("labs")
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("Canonical laboratuvar vakası labs listesi içermelidir.")
    if not rows:
        raise ValueError("Canonical laboratuvar vakası boş olamaz.")
    if len(rows) > _MAX_CANONICAL_ROWS:
        raise ValueError(
            f"Canonical laboratuvar vakası en fazla {_MAX_CANONICAL_ROWS} satır içerebilir."
        )

    payload: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"Canonical laboratuvar satırı #{index + 1} object olmalıdır."
            )
        if item.get("canonical_row_contract") != CANONICAL_ROW_CONTRACT:
            raise ValueError(
                f"Canonical laboratuvar satırı #{index + 1} contract sürümü uyumsuz."
            )
        row_source_type = str(item.get("source_type") or "")
        if row_source_type != source_type:
            raise ValueError(
                f"Canonical laboratuvar satırı #{index + 1} source_type vaka ile uyuşmuyor."
            )
        payload.append(dict(item))
    return payload


def _trust_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if row.get("contract_version") != LAB_PYTHON_CONTRACT:
        raise RuntimeError("Python lab row contract sürümü uyumsuz.")
    if row.get("validation_contract_version") != LAB_VALIDATION_CONTRACT:
        raise RuntimeError("Python lab validation contract sürümü uyumsuz.")
    if row.get("provenance_contract_version") != PYTHON_PROVENANCE_CONTRACT:
        raise RuntimeError("Python lab provenance contract sürümü uyumsuz.")

    enriched = dict(row)
    validation_status = str(
        enriched.get("validation_status") or "NEEDS_REVIEW"
    ).upper()
    result_status = str(enriched.get("result_status") or "NEEDS_REVIEW").upper()
    needs_review = bool(enriched.get("needs_review"))

    trusted = (
        validation_status == "VALID"
        and not needs_review
        and result_status in _TRUSTED_RESULT_STATUSES
    )
    enriched["trusted_for_ai"] = trusted
    enriched["trust_status"] = "TRUSTED" if trusted else "REVIEW"
    enriched["trust_reason"] = (
        "python_validation_valid"
        if trusted
        else f"python_validation_{validation_status.lower()}"
    )
    return enriched


def process_canonical_lab_case(case: Mapping[str, Any]) -> dict[str, Any]:
    payload = _validate_canonical_case(case)
    python_rows = process_lab_rows(payload)
    if not python_rows:
        raise ValueError("Python lab engine işlenebilir canonical satır üretmedi.")

    all_rows = [_trust_row(row) for row in python_rows]
    trusted_rows = [
        dict(row) for row in all_rows if bool(row.get("trusted_for_ai"))
    ]
    review_rows = [
        dict(row) for row in all_rows if not bool(row.get("trusted_for_ai"))
    ]

    source = case.get("source") if isinstance(case.get("source"), Mapping) else {}
    return {
        "contract_version": PYTHON_TRUST_CONTRACT,
        "canonical_contract_version": CANONICAL_LAB_CONTRACT,
        "python_contract_version": LAB_PYTHON_CONTRACT,
        "validation_contract_version": LAB_VALIDATION_CONTRACT,
        "provenance_contract_version": PYTHON_PROVENANCE_CONTRACT,
        "source_type": case.get("source_type"),
        "source": dict(source),
        "patient_age": case.get("patient_age"),
        "patient_sex": case.get("patient_sex"),
        "report_date": case.get("report_date"),
        "warnings": list(case.get("warnings") or []),
        "input_row_count": len(payload),
        "processed_row_count": len(all_rows),
        "deduplicated_row_count": max(0, len(payload) - len(all_rows)),
        "trusted_count": len(trusted_rows),
        "review_count": len(review_rows),
        "trusted_rows": trusted_rows,
        "review_rows": review_rows,
        "all_rows": all_rows,
        "python_ready": True,
        "ai_ready": bool(trusted_rows),
    }
