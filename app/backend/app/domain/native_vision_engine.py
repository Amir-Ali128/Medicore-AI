"""Python adapter for the optional MediCore C++ vision engine.

X-Ray Core v2 owns technical image preprocessing. DICOM Engine v1 owns native
DICOM metadata, pixel decoding, rescale/windowing, MONOCHROME handling, and safe
CR/DX conversion into the X-Ray tensor contract. Neither layer performs disease
diagnosis by itself.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

XRAY_TENSOR_CONTRACT = "xray-core-v2/nchw-f32-0-1"
DICOM_FRAME_CONTRACT = "dicom-frame-v1/grayscale-u8"


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


def inspect_dicom(content: bytes) -> dict[str, Any]:
    """Inspect technical DICOM metadata without exposing patient identifiers."""
    _require_content(content)
    payload = _require_module().inspect_dicom(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Native DICOM Engine geçersiz metadata döndürdü.")
    required = {
        "rows",
        "columns",
        "frames",
        "bits_allocated",
        "bits_stored",
        "photometric_interpretation",
        "modality",
        "compressed",
    }
    if not required.issubset(payload):
        raise RuntimeError("Native DICOM Engine metadata contract eksik.")
    return payload


def prepare_dicom_frame(
    content: bytes,
    *,
    frame_index: int = 0,
    window_center: float | None = None,
    window_width: float | None = None,
) -> dict[str, Any]:
    """Decode one DICOM frame into a versioned uint8 grayscale technical frame."""
    _require_content(content)
    if frame_index < 0:
        raise ValueError("frame_index negatif olamaz.")
    if (window_center is None) != (window_width is None):
        raise ValueError("Window override için center ve width birlikte verilmelidir.")
    if window_width is not None and window_width < 1:
        raise ValueError("window_width en az 1 olmalıdır.")

    payload = _require_module().prepare_dicom_frame(
        content,
        frame_index,
        window_center,
        window_width,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Native DICOM Engine geçersiz frame çıktısı döndürdü.")
    if payload.get("contract_version") != DICOM_FRAME_CONTRACT:
        raise RuntimeError("Native DICOM frame contract sürümü uyumsuz.")
    shape = list(payload.get("shape") or [])
    metadata = payload.get("metadata") or {}
    if shape != [metadata.get("rows"), metadata.get("columns")]:
        raise RuntimeError("Native DICOM frame shape metadata ile uyuşmuyor.")
    return payload


def prepare_dicom_xray_tensor(
    content: bytes,
    *,
    frame_index: int = 0,
    window_center: float | None = None,
    window_width: float | None = None,
    target_width: int = 1024,
    target_height: int = 1024,
    preserve_aspect_ratio: bool = True,
    pad_value: int = 0,
) -> dict[str, Any]:
    """Decode CR/DX DICOM and prepare the X-Ray Core v2 tensor contract."""
    _require_content(content)
    if frame_index < 0:
        raise ValueError("frame_index negatif olamaz.")
    if (window_center is None) != (window_width is None):
        raise ValueError("Window override için center ve width birlikte verilmelidir.")
    if window_width is not None and window_width < 1:
        raise ValueError("window_width en az 1 olmalıdır.")
    if not 32 <= target_width <= 4096 or not 32 <= target_height <= 4096:
        raise ValueError("Tensor boyutları 32 ile 4096 arasında olmalıdır.")
    if not 0 <= pad_value <= 255:
        raise ValueError("pad_value 0 ile 255 arasında olmalıdır.")

    payload = _require_module().prepare_dicom_xray_tensor(
        content,
        frame_index,
        window_center,
        window_width,
        target_width,
        target_height,
        preserve_aspect_ratio,
        pad_value,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Native DICOM X-Ray tensor çıktısı geçersiz.")
    if payload.get("contract_version") != XRAY_TENSOR_CONTRACT:
        raise RuntimeError("DICOM X-Ray tensor contract sürümü uyumsuz.")
    if payload.get("source_contract") != DICOM_FRAME_CONTRACT:
        raise RuntimeError("DICOM source frame contract sürümü uyumsuz.")
    if list(payload.get("shape") or []) != [1, 1, target_height, target_width]:
        raise RuntimeError("DICOM X-Ray tensor shape beklenenden farklı.")
    metadata = payload.get("metadata") or {}
    if str(metadata.get("modality") or "").upper() not in {"CR", "DX"}:
        raise RuntimeError("CR/DX dışı DICOM X-Ray tensor contract'a giremez.")
    return payload


def preprocess_chest_xray(content: bytes, *, max_side: int = 2048) -> Any:
    """Backward-compatible grayscale preprocessing API."""
    _require_content(content)
    if not 256 <= max_side <= 4096:
        raise ValueError("max_side 256 ile 4096 arasında olmalıdır.")
    return _require_module().preprocess_chest_xray(content, max_side)
