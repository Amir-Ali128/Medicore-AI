"""Thin Python adapter around MediCore's C++ laboratory core.

The OpenAI model extracts structured rows from the original report. This module
hands those rows to the native C++ core for deterministic normalization,
reference-range classification, duplicate suppression and confidence gating.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any, Mapping, Sequence

LAB_NATIVE_CONTRACT = "medicore-lab-v1"


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


def _require_module() -> Any:
    module = _load_native_module()
    if module is None:
        raise NativeLabUnavailable("MediCore native C++ lab engine yüklü değil.")
    if getattr(module, "CONTRACT_VERSION", None) != LAB_NATIVE_CONTRACT:
        raise NativeLabUnavailable("MediCore native C++ lab contract sürümü uyumsuz.")
    return module


def process_astra_lab_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Normalize/classify Astra-extracted rows with the native C++ core."""
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
        processed.append(dict(item))
    return processed
