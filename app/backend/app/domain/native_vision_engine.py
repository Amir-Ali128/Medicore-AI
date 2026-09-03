"""Python adapter for the optional MediCore C++ vision engine.

X-Ray Core v2 owns technical decoding, grayscale conversion, quality metrics,
normalization, resize/letterbox geometry, and tensor preparation. It does not
perform disease classification or diagnosis.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

XRAY_TENSOR_CONTRACT = "xray-core-v2/nchw-f32-0-1"


class NativeVisionUnavailable(RuntimeError):
    """Raised when the optional native extension is not installed."""


@lru_cache(maxsize=1)
def _load_native_module() -> Any | None:
    try:
        return importlib.import_module("medicore_vision")
    except (ImportError, OSError):
        return None


def native_vision_available() -> bool:
    return _load_native_module() is not None


def _require_content(content: bytes) -> None:
    if not content:
        raise ValueError("Görüntü içeriği boş olamaz.")


def _require_module() -> Any:
    module = _load_native_module()
    if module is None:
        raise NativeVisionUnavailable("MediCore native vision engine yüklü değil.")
    return module


def inspect_image(content: bytes) -> dict[str, int | float]:
    _require_content(content)
    payload = _require_module().inspect_image(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Native vision engine geçersiz metadata döndürdü.")
    return payload


def try_inspect_image(content: bytes) -> dict[str, int | float] | None:
    try:
        return inspect_image(content)
    except (NativeVisionUnavailable, RuntimeError, ValueError):
        return None


def inspect_xray_quality(content: bytes) -> dict[str, Any]:
    """Return technical image-quality metrics; flags are non-diagnostic heuristics."""
    _require_content(content)
    payload = _require_module().inspect_xray_quality(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Native X-Ray Core geçersiz kalite metrikleri döndürdü.")
    return payload


def prepare_xray_tensor(
    content: bytes,
    *,
    target_width: int = 1024,
    target_height: int = 1024,
    preserve_aspect_ratio: bool = True,
    pad_value: int = 0,
) -> dict[str, Any]:
    """Prepare versioned NCHW float32 [0,1] model input plus geometry metadata."""
    _require_content(content)
    if not 32 <= target_width <= 4096 or not 32 <= target_height <= 4096:
        raise ValueError("Tensor boyutları 32 ile 4096 arasında olmalıdır.")
    if not 0 <= pad_value <= 255:
        raise ValueError("pad_value 0 ile 255 arasında olmalıdır.")

    payload = _require_module().prepare_xray_tensor(
        content,
        target_width,
        target_height,
        preserve_aspect_ratio,
        pad_value,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Native X-Ray Core geçersiz tensor çıktısı döndürdü.")
    if payload.get("contract_version") != XRAY_TENSOR_CONTRACT:
        raise RuntimeError("Native X-Ray Core tensor contract sürümü uyumsuz.")
    shape = payload.get("shape")
    if list(shape or []) != [1, 1, target_height, target_width]:
        raise RuntimeError("Native X-Ray Core beklenmeyen tensor shape döndürdü.")
    return payload


def preprocess_chest_xray(content: bytes, *, max_side: int = 2048) -> Any:
    """Backward-compatible grayscale preprocessing API."""
    _require_content(content)
    if not 256 <= max_side <= 4096:
        raise ValueError("max_side 256 ile 4096 arasında olmalıdır.")
    return _require_module().preprocess_chest_xray(content, max_side)
