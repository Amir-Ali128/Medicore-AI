"""Thin Python adapters around MediCore's C++ laboratory cores.

The extraction layer provides structured rows from original reports. Native C++ owns
deterministic normalization/classification/metrics plus reference parsing, analyte-aware
unit conversion, plausibility checks and fractional-age demographic reference selection.
DB access, I/O and clinical AI orchestration intentionally remain in Python.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any, Mapping, Sequence

LAB_NATIVE_CONTRACT = "medicore-lab-v1"
LAB_VALIDATION_CONTRACT = "medicore-lab-validation-v1"
LAB_METRICS_CONTRACT = "medicore-lab-metrics-v1"
LAB_DETERMINISTIC_CONTRACT = "medicore-lab-deterministic-v1"
LAB_EXTENSIONS_CONTRACT = "medicore-lab-extensions-v1"


class NativeLabUnavailable(RuntimeError):
    """Raised when an expected native lab extension is not installed/compatible."""


@lru_cache(maxsize=1)
def _load_native_module() -> Any | None:
    try:
        return importlib.import_module("medicore_lab")
    except (ImportError, OSError):
        return None


@lru_cache(maxsize=1)
def _load_extensions_module() -> Any | None:
    try:
        return importlib.import_module("medicore_lab_ext")
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


def native_lab_extensions_available() -> bool:
    module = _load_extensions_module()
    return bool(
        module is not None
        and getattr(module, "EXTENSIONS_VERSION", None) == LAB_EXTENSIONS_CONTRACT
        and callable(getattr(module, "parse_reference_text", None))
        and callable(getattr(module, "convert_lab_value", None))
        and callable(getattr(module, "validate_plausibility", None))
        and callable(getattr(module, "select_reference_candidate_v2", None))
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


def _require_extensions_module() -> Any:
    module = _load_extensions_module()
    if module is None:
        raise NativeLabUnavailable("MediCore native C++ lab extensions modülü yüklü değil.")
    if getattr(module, "EXTENSIONS_VERSION", None) != LAB_EXTENSIONS_CONTRACT:
        raise NativeLabUnavailable("MediCore native C++ lab extensions contract sürümü uyumsuz.")
    return module


def process_astra_lab_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        raise ValueError("Laboratuvar satırları bir liste olmalıdır.")
    module = _require_module()
    if getattr(module, "METRICS_VERSION", None) != LAB_METRICS_CONTRACT:
        raise NativeLabUnavailable("MediCore native C++ clinical metrics contract sürümü uyumsuz.")
    compute = getattr(module, "compute_derived_metrics", None)
    if not callable(compute):
        raise NativeLabUnavailable("MediCore native C++ clinical metrics modülü yüklü değil.")
    native_output = compute([dict(row) for row in rows], patient_age, patient_sex or "")
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
    return str(_require_deterministic_module().normalize_alias(value or ""))


def native_alias_similarity(left: str | None, right: str | None) -> float:
    return float(_require_deterministic_module().alias_similarity_ratio(left or "", right or ""))


def native_evaluate_rule(
    *,
    parameter_known: bool,
    alias_needs_review: bool,
    reference_needs_review: bool,
    normalized_value: Any,
    reference_min: Any,
    reference_max: Any,
) -> dict[str, Any]:
    result = _require_deterministic_module().evaluate_rule(
        bool(parameter_known), bool(alias_needs_review), bool(reference_needs_review),
        normalized_value, reference_min, reference_max,
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
    result = _require_deterministic_module().compare_trend(
        current_value, previous_value, time_difference_days, float(stable_relative_threshold)
    )
    if not isinstance(result, dict) or result.get("deterministic_version") != LAB_DETERMINISTIC_CONTRACT:
        raise RuntimeError("Native C++ trend contract geçersiz.")
    return dict(result)


def native_select_reference_candidate(
    candidates: Sequence[Mapping[str, Any]],
    *,
    patient_sex: str | None,
    patient_age: float | None,
    pregnancy_status: bool | None,
) -> dict[str, Any]:
    """Use fractional-age native v2 when available; otherwise legacy integer selector."""
    payload = [dict(candidate) for candidate in candidates]
    if native_lab_extensions_available():
        result = _require_extensions_module().select_reference_candidate_v2(
            payload,
            patient_sex or "",
            patient_age,
            pregnancy_status,
        )
        if not isinstance(result, dict) or result.get("extensions_version") != LAB_EXTENSIONS_CONTRACT:
            raise RuntimeError("Native C++ reference selection v2 contract geçersiz.")
        return dict(result)

    if patient_age is not None and not float(patient_age).is_integer():
        raise NativeLabUnavailable("Legacy native reference selector fractional pediatric age desteklemiyor.")
    result = _require_deterministic_module().select_reference_candidate(
        payload,
        patient_sex or "",
        int(patient_age) if patient_age is not None else None,
        pregnancy_status,
    )
    if not isinstance(result, dict) or result.get("deterministic_version") != LAB_DETERMINISTIC_CONTRACT:
        raise RuntimeError("Native C++ reference selection contract geçersiz.")
    return dict(result)


def native_parse_reference_text(text: str | None) -> dict[str, Any]:
    result = _require_extensions_module().parse_reference_text(text or "")
    if not isinstance(result, dict) or result.get("extensions_version") != LAB_EXTENSIONS_CONTRACT:
        raise RuntimeError("Native C++ reference parser contract geçersiz.")
    return dict(result)


def native_convert_lab_value(
    *, analyte: str, value: float, source_unit: str, target_unit: str
) -> dict[str, Any]:
    result = _require_extensions_module().convert_lab_value(
        analyte, float(value), source_unit, target_unit
    )
    if not isinstance(result, dict) or result.get("extensions_version") != LAB_EXTENSIONS_CONTRACT:
        raise RuntimeError("Native C++ unit conversion contract geçersiz.")
    return dict(result)


def native_validate_plausibility(*, analyte: str, value: float, unit: str) -> dict[str, Any]:
    result = _require_extensions_module().validate_plausibility(analyte, float(value), unit)
    if not isinstance(result, dict) or result.get("extensions_version") != LAB_EXTENSIONS_CONTRACT:
        raise RuntimeError("Native C++ plausibility contract geçersiz.")
    return dict(result)


def native_normalize_unit_semantic(unit: str | None) -> str:
    return str(_require_extensions_module().normalize_unit_semantic(unit or ""))
