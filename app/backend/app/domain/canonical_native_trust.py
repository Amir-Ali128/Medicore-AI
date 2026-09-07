"""Canonical laboratory case -> native C++ trust boundary.

All seven ingestion families terminate in ``medicore-canonical-lab-v1``. This module
is the only bridge from that source-preserving contract into the deterministic native
lab core. It never invents values, silently corrects measurements, or promotes a row
that native validation marked for review.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.domain.canonical_lab_model import (
    CANONICAL_LAB_CONTRACT,
    CANONICAL_ROW_CONTRACT,
    CANONICAL_SOURCE_TYPES,
)
from app.domain.native_lab_engine import (
    LAB_NATIVE_CONTRACT,
    LAB_VALIDATION_CONTRACT,
    NativeLabUnavailable,
    process_astra_lab_rows,
)

NATIVE_TRUST_CONTRACT = "medicore-native-trust-v1"
NATIVE_PROVENANCE_CONTRACT = "medicore-lab-provenance-v1"
_MAX_CANONICAL_ROWS = 5000
_TRUSTED_RESULT_STATUSES = frozenset({"NORMAL", "LOW", "HIGH"})
_REVIEW_VALIDATION_STATUSES = frozenset({"WARNING", "NEEDS_REVIEW", "INVALID"})


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
        raise ValueError(f"Canonical laboratuvar vakası en fazla {_MAX_CANONICAL_ROWS} satır içerebilir.")

    payload: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping):
            raise ValueError(f"Canonical laboratuvar satırı #{index + 1} object olmalıdır.")
        if item.get("canonical_row_contract") != CANONICAL_ROW_CONTRACT:
            raise ValueError(f"Canonical laboratuvar satırı #{index + 1} contract sürümü uyumsuz.")
        row_source_type = str(item.get("source_type") or "")
        if row_source_type != source_type:
            raise ValueError(f"Canonical laboratuvar satırı #{index + 1} source_type vaka ile uyuşmuyor.")
        payload.append(dict(item))
    return payload


def _trust_row(row: Mapping[str, Any]) -> dict[str, Any]:
    if row.get("contract_version") != LAB_NATIVE_CONTRACT:
        raise RuntimeError("Native C++ lab row contract sürümü uyumsuz.")
    if row.get("validation_contract_version") != LAB_VALIDATION_CONTRACT:
        raise RuntimeError("Native C++ lab validation contract sürümü uyumsuz.")
    if row.get("provenance_contract_version") != NATIVE_PROVENANCE_CONTRACT:
        raise NativeLabUnavailable(
            "Native C++ lab provenance contract yüklü değil; canonical kaynak izi güvenle korunamıyor."
        )
    if row.get("canonical_row_contract") != CANONICAL_ROW_CONTRACT:
        raise RuntimeError("Native C++ çıktı canonical row provenance contract'ını korumadı.")

    enriched = dict(row)
    validation_status = str(enriched.get("validation_status") or "NEEDS_REVIEW").upper()
    result_status = str(enriched.get("result_status") or "NEEDS_REVIEW").upper()
    needs_review = bool(enriched.get("needs_review"))

    trusted = (
        validation_status == "VALID"
        and not needs_review
        and result_status in _TRUSTED_RESULT_STATUSES
    )
    enriched["trusted_for_ai"] = trusted
    enriched["trust_status"] = "TRUSTED" if trusted else "REVIEW"

    if trusted:
        enriched["trust_reason"] = "native_validation_valid"
    elif validation_status in _REVIEW_VALIDATION_STATUSES:
        enriched["trust_reason"] = f"native_validation_{validation_status.lower()}"
    elif needs_review:
        enriched["trust_reason"] = "native_needs_review"
    else:
        enriched["trust_reason"] = "native_result_not_trustable"
    return enriched


def process_canonical_lab_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Run a canonical case through C++ and return an auditable trust envelope.

    Native dedupe is authoritative. Provenance is carried inside the C++ ``LabRow``
    so the winning row after dedupe retains its source SHA/file/page/record metadata.
    Any WARNING/NEEDS_REVIEW/INVALID row is excluded from ``trusted_rows``.
    """
    payload = _validate_canonical_case(case)
    native_rows = process_astra_lab_rows(payload)
    if not native_rows:
        raise ValueError("Native C++ lab engine işlenebilir canonical satır üretmedi.")

    all_rows = [_trust_row(row) for row in native_rows]
    trusted_rows = [dict(row) for row in all_rows if bool(row["trusted_for_ai"])]
    review_rows = [dict(row) for row in all_rows if not bool(row["trusted_for_ai"])]

    source = case.get("source") if isinstance(case.get("source"), Mapping) else {}
    return {
        "contract_version": NATIVE_TRUST_CONTRACT,
        "canonical_contract_version": CANONICAL_LAB_CONTRACT,
        "native_contract_version": LAB_NATIVE_CONTRACT,
        "validation_contract_version": LAB_VALIDATION_CONTRACT,
        "provenance_contract_version": NATIVE_PROVENANCE_CONTRACT,
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
        "native_ready": True,
        "ai_ready": bool(trusted_rows),
    }
