"""Thin Python adapter around MediCore's C++ laboratory core.

The extraction layer provides structured rows from the original report. This module
hands those rows to the native C++ core for deterministic normalization, reference-range
classification, validation, duplicate suppression, confidence gating and selected
non-diagnostic clinical calculations.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any, Mapping, Sequence

LAB_NATIVE_CONTRACT = "medicore-lab-v1"
LAB_VALIDATION_CONTRACT = "medicore-lab-validation-v1"
LAB_METRICS_CONTRACT = "medicore-lab-metrics-v1"


class NativeLabUnavailable(RuntimeError):
    """Raised when the optional native lab extension is not installed."""


@lru_cache(maxsize=1)
def _load_native_module() -> Any | None:
    try:
        return importlib.import_module("medicore_lab")
    except (ImportError, OSError):
        return None


def native_lab_available() -> bool:
    module = _load_native_module()
    return bool(module is not None and getattr(module, "CONTRACT_VERSION", None) == LAB_NATIVE_CONTRACT)


def native_lab_validation_available() -> bool:
    module = _load_native_module()
    return bool(
        module is not None
        and getattr(module, "CONTRACT_VERSION", None) == LAB_NATIVE_CONTRACT
        and getattr(module, "VALIDATION_VERSION", None) == LAB_VALIDATION_CONTRACT
    )


def native_lab_metrics_available() -> bool:
    module = _load_native_module()
    return bool(
        module is not None
        and getattr(module, "CONTRACT_VERSION", None) == LAB_NATIVE_CONTRACT
        and getattr(module, "METRICS_VERSION", None) == LAB_METRICS_CONTRACT
        and callable(getattr(module, "compute_derived_metrics", None))
    )


def _require_module() -> Any:
    module = _load_native_module()
    if module is None:
        raise NativeLabUnavailable("MediCore native C++ lab engine yüklü değil.")
    if getattr(module, "CONTRACT_VERSION", None) != LAB_NATIVE_CONTRACT:
        raise NativeLabUnavailable("MediCore native C++ lab contract sürümü uyumsuz.")
    return module


def process_astra_lab_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize/classify extracted rows with the native C++ core."""
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("Laboratuvar satırları bir liste olmalıdır.")

    payload = [dict(row) for row in rows]
    native_output = _require_module().process_rows(payload)
    if not isinstance(native_output, list):
        raise RuntimeError("Native C++ lab engine geçersiz çıktı döndürdü.")

    processed: list[dict[str, Any]] = []
    for item in native_output:
        if not isinstance(item, dict):
            raise RuntimeError("Native C++ lab engine satır formatı geçersiz.")
        if item.get("contract_version") != LAB_NATIVE_CONTRACT:
            raise RuntimeError("Native C++ lab satır contract sürümü uyumsuz.")

        row = dict(item)
        # Validation metadata is additive so older native binaries remain readable
        # during a rolling deployment. New binaries advertise and emit the contract.
        validation_version = row.get("validation_contract_version")
        if validation_version is not None and validation_version != LAB_VALIDATION_CONTRACT:
            raise RuntimeError("Native C++ lab validation contract sürümü uyumsuz.")
        processed.append(row)
    return processed


def compute_native_lab_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    patient_age: int | None,
    patient_sex: str | None,
) -> list[dict[str, Any]]:
    """Compute deterministic derived metrics from the original extracted rows.

    The native implementation performs unit/quality gates before any formula is
    evaluated. Missing or incompatible inputs simply omit the affected metric.
    """
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("Laboratuvar satırları bir liste olmalıdır.")

    module = _require_module()
    if getattr(module, "METRICS_VERSION", None) != LAB_METRICS_CONTRACT:
        raise NativeLabUnavailable("MediCore native C++ clinical metrics contract sürümü uyumsuz.")
    compute = getattr(module, "compute_derived_metrics", None)
    if not callable(compute):
        raise NativeLabUnavailable("MediCore native C++ clinical metrics modülü yüklü değil.")

    native_output = compute(
        [dict(row) for row in rows],
        patient_age,
        patient_sex or "",
    )
    if not isinstance(native_output, list):
        raise RuntimeError("Native C++ clinical metrics geçersiz çıktı döndürdü.")

    metrics: list[dict[str, Any]] = []
    for item in native_output:
        if not isinstance(item, dict):
            raise RuntimeError("Native C++ clinical metric formatı geçersiz.")
        if item.get("metrics_version") != LAB_METRICS_CONTRACT:
            raise RuntimeError("Native C++ clinical metric contract sürümü uyumsuz.")
        metrics.append(dict(item))
    return metrics
