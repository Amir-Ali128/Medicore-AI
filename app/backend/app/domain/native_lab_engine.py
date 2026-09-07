"""Thin Python adapter around MediCore's C++ laboratory core.

The extraction layer provides structured rows from the original report. This module
hands those rows to the native C++ core for deterministic normalization, reference-range
classification, validation, duplicate suppression, confidence gating, trend/rule
calculations, reference selection and selected non-diagnostic clinical calculations.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any, Mapping, Sequence

LAB_NATIVE_CONTRACT = "medicore-lab-v1"
LAB_VALIDATION_CONTRACT = "medicore-lab-validation-v1"
LAB_METRICS_CONTRACT = "medicore-lab-metrics-v1"
LAB_DETERMINISTIC_CONTRACT = "medicore-lab-deterministic-v1"


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


def native_lab_deterministic_available() -> bool:
    module = _load_native_module()
    return bool(
        module is not None
        and getattr(module, "CONTRACT_VERSION", None) == LAB_NATIVE_CONTRACT
        and getattr(module, "DETERMINISTIC_VERSION", None) == LAB_DETERMINISTIC_CONTRACT
    )


def _require_module() -> Any:
    module = _load_native_module()
    if module is None:
        raise NativeLabUnavailable("MediCore native C++ lab engine yüklü değil.")
    if getattr(module, "CONTRACT_VERSION", None) != LAB_NATIVE_CONTRACT:
        raise NativeLabUnavailable("MediCore native C++ lab contract sürümü uyumsuz.")
    return module


def _require_deterministic_module() -> Any:
    module = _require_module()
    if getattr(module, "DETERMINISTIC_VERSION", None) != LAB_DETERMINISTIC_CONTRACT:
        raise NativeLabUnavailable("MediCore native C++ deterministic contract sürümü uyumsuz.")
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
    """Compute deterministic derived metrics from the original extracted rows."""
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


def native_normalize_alias(value: str | None) -> str:
    module = _require_deterministic_module()
    return str(module.normalize_alias(value or ""))


def native_alias_similarity(left: str | None, right: str | None) -> float:
    module = _require_deterministic_module()
    return float(module.alias_similarity_ratio(left or "", right or ""))


def native_evaluate_rule(
    *,
    parameter_known: bool,
    alias_needs_review: bool,
    reference_needs_review: bool,
    normalized_value: Any,
    reference_min: Any,
    reference_max: Any,
) -> dict[str, Any]:
    module = _require_deterministic_module()
    result = module.evaluate_rule(
        bool(parameter_known),
        bool(alias_needs_review),
        bool(reference_needs_review),
        normalized_value,
        reference_min,
        reference_max,
    )
    if not isinstance(result, dict) or result.get("deterministic_version") != LAB_DETERMINISTIC_CONTRACT:
        raise RuntimeError("Native C++ rule evaluation contract geçersiz.")
    return dict(result)


def native_compare_trend(
    *,
    current_value: Any,
    previous_value: Any,
    time_difference_days: int | None,
    stable_relative_threshold: float = 0.05,
) -> dict[str, Any]:
    module = _require_deterministic_module()
    result = module.compare_trend(
        current_value,
        previous_value,
        time_difference_days,
        float(stable_relative_threshold),
    )
    if not isinstance(result, dict) or result.get("deterministic_version") != LAB_DETERMINISTIC_CONTRACT:
        raise RuntimeError("Native C++ trend contract geçersiz.")
    return dict(result)


def native_select_reference_candidate(
    candidates: Sequence[Mapping[str, Any]],
    *,
    patient_sex: str | None,
    patient_age: int | None,
    pregnancy_status: bool | None,
) -> dict[str, Any]:
    module = _require_deterministic_module()
    result = module.select_reference_candidate(
        [dict(candidate) for candidate in candidates],
        patient_sex or "",
        patient_age,
        pregnancy_status,
    )
    if not isinstance(result, dict) or result.get("deterministic_version") != LAB_DETERMINISTIC_CONTRACT:
        raise RuntimeError("Native C++ reference selection contract geçersiz.")
    return dict(result)
