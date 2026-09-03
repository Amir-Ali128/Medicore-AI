"""Python adapter for the optional MediCore C++ vision engine.

X-Ray Core v2 owns technical image preprocessing. DICOM Engine v1 owns native
DICOM metadata, pixel decoding, rescale/windowing, MONOCHROME handling, and safe
CR/DX conversion into the X-Ray tensor contract. Vision Post-processing v1 maps
model-space heatmaps, masks, and boxes back into original-image coordinates.
None of these layers performs autonomous diagnosis by itself.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any, Mapping, Sequence

XRAY_TENSOR_CONTRACT = "xray-core-v2/nchw-f32-0-1"
DICOM_FRAME_CONTRACT = "dicom-frame-v1/grayscale-u8"
VISION_POSTPROCESS_CONTRACT = "vision-post-v1/original-space"


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


def _validated_transform(transform: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "original_width",
        "original_height",
        "output_width",
        "output_height",
        "resized_width",
        "resized_height",
        "pad_left",
        "pad_top",
        "pad_right",
        "pad_bottom",
        "scale_x",
        "scale_y",
    }
    payload = dict(transform)
    if not required.issubset(payload):
        missing = sorted(required.difference(payload))
        raise ValueError(f"Tensor transform alanları eksik: {', '.join(missing)}")
    if int(payload["original_width"]) <= 0 or int(payload["original_height"]) <= 0:
        raise ValueError("Orijinal görüntü boyutları pozitif olmalıdır.")
    return payload


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
    _validated_transform(payload.get("transform") or {})
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
    _validated_transform(payload.get("transform") or {})
    return payload


def map_model_box_to_original(
    box: Sequence[float],
    transform: Mapping[str, Any],
    *,
    clip: bool = True,
) -> tuple[float, float, float, float]:
    """Map one model-space xyxy box through X-Ray Core letterbox geometry."""
    values = tuple(float(value) for value in box)
    if len(values) != 4:
        raise ValueError("Bounding box tam dört xyxy değeri içermelidir.")
    mapped = _require_module().map_model_box_to_original(
        values,
        _validated_transform(transform),
        clip,
    )
    result = tuple(float(value) for value in mapped)
    if len(result) != 4:
        raise RuntimeError("Native post-processing geçersiz bounding box döndürdü.")
    return result


def postprocess_spatial_map(
    spatial_map: Any,
    transform: Mapping[str, Any],
    *,
    threshold: float = 0.5,
    min_component_area: int = 16,
    max_components: int = 32,
    normalize_minmax: bool = True,
    pixel_spacing_row_mm: float | None = None,
    pixel_spacing_col_mm: float | None = None,
) -> dict[str, Any]:
    """Map heatmap/segmentation scores into original pixels and measure regions."""
    if not 0.0 <= float(threshold) <= 1.0:
        raise ValueError("threshold 0 ile 1 arasında olmalıdır.")
    if min_component_area < 1:
        raise ValueError("min_component_area pozitif olmalıdır.")
    if not 1 <= max_components <= 1024:
        raise ValueError("max_components 1 ile 1024 arasında olmalıdır.")
    if (pixel_spacing_row_mm is None) != (pixel_spacing_col_mm is None):
        raise ValueError("Pixel spacing için row ve column birlikte verilmelidir.")
    if pixel_spacing_row_mm is not None:
        if pixel_spacing_row_mm <= 0 or pixel_spacing_col_mm is None or pixel_spacing_col_mm <= 0:
            raise ValueError("Pixel spacing değerleri pozitif olmalıdır.")

    transform_payload = _validated_transform(transform)
    payload = _require_module().postprocess_spatial_map(
        spatial_map,
        transform_payload,
        float(threshold),
        int(min_component_area),
        int(max_components),
        bool(normalize_minmax),
        pixel_spacing_row_mm,
        pixel_spacing_col_mm,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Native vision post-processing geçersiz çıktı döndürdü.")
    if payload.get("contract_version") != VISION_POSTPROCESS_CONTRACT:
        raise RuntimeError("Vision post-processing contract sürümü uyumsuz.")
    expected_shape = [
        int(transform_payload["original_height"]),
        int(transform_payload["original_width"]),
    ]
    if list(payload.get("shape") or []) != expected_shape:
        raise RuntimeError("Post-processing çıktısı orijinal görüntü boyutlarıyla uyuşmuyor.")
    if not isinstance(payload.get("regions"), list):
        raise RuntimeError("Post-processing regions alanı geçersiz.")
    return payload


def postprocess_prepared_spatial_map(
    spatial_map: Any,
    prepared: Mapping[str, Any],
    *,
    threshold: float = 0.5,
    min_component_area: int = 16,
    max_components: int = 32,
    normalize_minmax: bool = True,
) -> dict[str, Any]:
    """Post-process a model map using transform/spacing from a prepared X-Ray item."""
    transform = prepared.get("transform")
    if not isinstance(transform, Mapping):
        raise ValueError("Prepared X-Ray çıktısında transform bulunamadı.")

    row_spacing: float | None = None
    col_spacing: float | None = None
    metadata = prepared.get("metadata")
    if isinstance(metadata, Mapping) and bool(metadata.get("has_pixel_spacing")):
        row_value = metadata.get("pixel_spacing_row_mm")
        col_value = metadata.get("pixel_spacing_col_mm")
        if row_value is not None and col_value is not None:
            row_spacing = float(row_value)
            col_spacing = float(col_value)

    return postprocess_spatial_map(
        spatial_map,
        transform,
        threshold=threshold,
        min_component_area=min_component_area,
        max_components=max_components,
        normalize_minmax=normalize_minmax,
        pixel_spacing_row_mm=row_spacing,
        pixel_spacing_col_mm=col_spacing,
    )


def preprocess_chest_xray(content: bytes, *, max_side: int = 2048) -> Any:
    """Backward-compatible grayscale preprocessing API."""
    _require_content(content)
    if not 256 <= max_side <= 4096:
        raise ValueError("max_side 256 ile 4096 arasında olmalıdır.")
    return _require_module().preprocess_chest_xray(content, max_side)
