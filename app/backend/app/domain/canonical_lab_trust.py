"""Canonical laboratory case -> native C++ trust boundary.

This module is intentionally small. Source-specific parsing is already finished when a
case reaches here. The canonical rows are contract-checked, processed by the native C++
lab core, optionally tightened by the native C++ extensions, and partitioned into rows
that may or may not be used as primary clinical-AI evidence.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.domain import native_lab_engine as native
from app.domain.canonical_lab_model import (
    CANONICAL_LAB_CONTRACT,
    CANONICAL_ROW_CONTRACT,
    CANONICAL_SOURCE_TYPES,
    MAX_CANONICAL_LAB_ROWS,
)

CPP_TRUST_CONTRACT = "medicore-cpp-trust-v1"


def _require_canonical_case(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    if case.get("contract_version") != CANONICAL_LAB_CONTRACT:
        raise ValueError("Canonical laboratuvar case contract sürümü uyumsuz.")
    if case.get("native_ready") is not True:
        raise ValueError("Canonical laboratuvar vakası native işleme için hazır değil.")
    if case.get("source_type") not in CANONICAL_SOURCE_TYPES:
        raise ValueError("Canonical laboratuvar source_type geçersiz.")

    labs = case.get("labs")
    if not isinstance(labs, Sequence) or isinstance(labs, (str, bytes, bytearray)):
        raise ValueError("Canonical laboratuvar vakası labs listesi içermiyor.")
    if not labs:
        raise ValueError("Canonical laboratuvar vakasında en az bir satır olmalıdır.")
    if len(labs) > MAX_CANONICAL_LAB_ROWS:
        raise ValueError(
            f"Tek canonical laboratuvar vakasında en fazla {MAX_CANONICAL_LAB_ROWS} sonuç olabilir."
        )

    rows: list[dict[str, Any]] = []
    for item in labs:
        if not isinstance(item, Mapping):
            raise ValueError("Canonical laboratuvar satırlarından biri object değil.")
        if item.get("canonical_row_contract") != CANONICAL_ROW_CONTRACT:
            raise ValueError("Canonical laboratuvar satır contract sürümü uyumsuz.")
        rows.append(dict(item))
    return rows


def _require_native_trust_module() -> Any:
    module = native._require_module()
    if getattr(module, "CANONICAL_ROW_VERSION", None) != CANONICAL_ROW_CONTRACT:
        raise native.NativeLabUnavailable(
            "MediCore native C++ canonical-row contract sürümü uyumsuz."
        )
    if getattr(module, "TRUST_VERSION", None) != CPP_TRUST_CONTRACT:
        raise native.NativeLabUnavailable("MediCore native C++ trust contract sürümü uyumsuz.")
    if not callable(getattr(module, "process_canonical_rows", None)):
        raise native.NativeLabUnavailable("MediCore native C++ canonical trust bridge yüklü değil.")
    return module


def native_canonical_trust_available() -> bool:
    try:
        _require_native_trust_module()
    except native.NativeLabUnavailable:
        return False
    return True


def process_canonical_lab_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Process one canonical case through the native trust boundary.

    The function never changes a measured numeric value. Reference parsing and
    plausibility checks may only add structure or tighten validation/review status.
    Only rows whose final native validation status is VALID and which do not require
    review are returned in ``trusted_rows``.
    """
    if not isinstance(case, Mapping):
        raise ValueError("Canonical laboratuvar vakası object olmalıdır.")

    rows = _require_canonical_case(case)
    module = _require_native_trust_module()
    extensions = (
        native._load_extensions_module() if native.native_lab_extensions_available() else None
    )

    prepared: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        if extensions is not None:
            row = native._hydrate_reference_with_native(row, extensions)
        prepared.append(row)

    output = module.process_canonical_rows(prepared)
    if not isinstance(output, list):
        raise RuntimeError("Native C++ canonical trust engine geçersiz çıktı döndürdü.")

    processed: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            raise RuntimeError("Native C++ canonical trust satır formatı geçersiz.")
        row = dict(item)
        if row.get("contract_version") != native.LAB_NATIVE_CONTRACT:
            raise RuntimeError("Native C++ lab satır contract sürümü uyumsuz.")
        if row.get("validation_contract_version") != native.LAB_VALIDATION_CONTRACT:
            raise RuntimeError("Native C++ lab validation contract sürümü uyumsuz.")
        if row.get("trust_contract_version") != CPP_TRUST_CONTRACT:
            raise RuntimeError("Native C++ trust contract sürümü uyumsuz.")
        if row.get("canonical_row_contract") != CANONICAL_ROW_CONTRACT:
            raise RuntimeError("Native C++ çıktısı canonical provenance contract'ını kaybetti.")

        if extensions is not None:
            row = native._attach_plausibility(row, extensions)

        # Fail closed after every native extension. A row that became WARNING,
        # NEEDS_REVIEW or INVALID can never remain trusted merely because the core
        # comparison had initially succeeded.
        row["trusted_for_ai"] = (
            str(row.get("validation_status") or "").upper() == "VALID"
            and not bool(row.get("needs_review"))
        )
        row["trust_contract_version"] = CPP_TRUST_CONTRACT
        processed.append(row)

    trusted_rows = [row for row in processed if bool(row.get("trusted_for_ai"))]
    review_rows = [row for row in processed if not bool(row.get("trusted_for_ai"))]
    invalid_rows = [
        row
        for row in review_rows
        if str(row.get("validation_status") or "").upper() == "INVALID"
    ]

    input_count = len(rows)
    output_count = len(processed)
    return {
        "trust_contract_version": CPP_TRUST_CONTRACT,
        "canonical_contract_version": CANONICAL_LAB_CONTRACT,
        "native_contract_version": native.LAB_NATIVE_CONTRACT,
        "validation_contract_version": native.LAB_VALIDATION_CONTRACT,
        "source_type": case.get("source_type"),
        "source": dict(case.get("source") or {}),
        "patient_age": case.get("patient_age"),
        "patient_sex": case.get("patient_sex"),
        "report_date": case.get("report_date"),
        "trusted_rows": trusted_rows,
        "review_rows": review_rows,
        "counts": {
            "input": input_count,
            "processed": output_count,
            "trusted": len(trusted_rows),
            "review": len(review_rows),
            "invalid": len(invalid_rows),
            "deduplicated": max(0, input_count - output_count),
        },
        "needs_review": bool(review_rows),
        "ai_primary_evidence_policy": "native_cpp_VALID_and_no_review_only",
    }
