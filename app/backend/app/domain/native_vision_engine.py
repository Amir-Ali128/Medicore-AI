"""Optional Python adapter for the MediCore C++ vision engine.

C++ owns technical image primitives and tensor preparation. Python owns
orchestration, model contracts, safety policy and all clinical interpretation.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any


class NativeVisionUnavailable(RuntimeError):
    """Raised when the optional native extension is not installed."""


@lru_cache(maxsize=1)
def _load_native_module() -> Any | None:
    try:
        return importlib.import_module("medicore_vision")
    except (ImportError, OSError):
        return None


def native_vision_available() -> bool:
    """Return whether the C++ extension can be imported in this process."""
    return _load_native_module() is not None


def _require_content(content: bytes) -> None:
    if not content:
        raise ValueError("Görüntü içeriği boş olamaz.")


def _require_native_module() -> Any:
    module = _load_native_module()
    if module is None:
        raise NativeVisionUnavailable("MediCore native vision engine yüklü değil.")
    return module


def inspect_image(content: bytes) -> dict[str, int | float]:
    """Return technical metadata from the native decoder."""
    _require_content(content)
    payload = _require_native_module().inspect_image(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Native vision engine geçersiz metadata döndürdü.")
    return payload


def try_inspect_image(content: bytes) -> dict[str, int | float] | None:
    """Best-effort metadata inspection without breaking the upload pipeline."""
    try:
        return inspect_image(content)
    except (NativeVisionUnavailable, RuntimeError, ValueError):
        return None


def assess_chest_xray_quality(content: bytes) -> dict[str, float]:
    """Return technical quality metrics computed by C++.

    The metrics are descriptive only. They do not determine whether a study is
    clinically diagnostic and are not a disease classifier.
    """
    _require_content(content)
    payload = _require_native_module().assess_chest_xray_quality(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Native vision engine geçersiz kalite metriği döndürdü.")

    required = {
        "dynamic_range",
        "mean_intensity",
        "stddev_intensity",
        "clipped_low_fraction",
        "clipped_high_fraction",
        "laplacian_variance",
    }
    if not required.issubset(payload):
        raise RuntimeError("Native vision engine eksik kalite metriği döndürdü.")
    return {key: float(payload[key]) for key in required}


def try_assess_chest_xray_quality(content: bytes) -> dict[str, float] | None:
    """Best-effort technical quality assessment with a non-fatal fallback."""
    try:
        return assess_chest_xray_quality(content)
    except (NativeVisionUnavailable, RuntimeError, ValueError, TypeError):
        return None


def preprocess_chest_xray(content: bytes, *, max_side: int = 2048) -> Any:
    """Run conservative C++ chest-X-ray preprocessing and return a NumPy array."""
    if not 256 <= max_side <= 4096:
        raise ValueError("max_side 256 ile 4096 arasında olmalıdır.")
    _require_content(content)
    return _require_native_module().preprocess_chest_xray(content, max_side)


def prepare_chest_xray_tensor(content: bytes, *, target_size: int = 1024) -> Any:
    """Return a C++-prepared square float32 tensor candidate in the [0,1] range.

    A concrete disease model must still define and validate its exact input
    contract before this tensor is used for inference.
    """
    if not 224 <= target_size <= 2048:
        raise ValueError("target_size 224 ile 2048 arasında olmalıdır.")
    _require_content(content)
    return _require_native_module().prepare_chest_xray_tensor(content, target_size)
