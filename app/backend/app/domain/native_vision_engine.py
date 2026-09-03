"""Optional Python adapter for the MediCore C++ vision engine.

The native module is intentionally limited to technical image inspection and
preprocessing. Clinical interpretation remains in Python and any future model
output must remain assistive and physician-reviewed.
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


def inspect_image(content: bytes) -> dict[str, int | float]:
    """Return technical metadata from the native decoder.

    This does not perform diagnosis or disease classification.
    """
    if not content:
        raise ValueError("Görüntü içeriği boş olamaz.")

    module = _load_native_module()
    if module is None:
        raise NativeVisionUnavailable("MediCore native vision engine yüklü değil.")

    payload = module.inspect_image(content)
    if not isinstance(payload, dict):
        raise RuntimeError("Native vision engine geçersiz metadata döndürdü.")
    return payload


def try_inspect_image(content: bytes) -> dict[str, int | float] | None:
    """Best-effort metadata inspection without breaking the upload pipeline."""
    try:
        return inspect_image(content)
    except (NativeVisionUnavailable, RuntimeError, ValueError):
        return None


def preprocess_chest_xray(content: bytes, *, max_side: int = 2048) -> Any:
    """Run conservative C++ chest-X-ray preprocessing and return a NumPy array.

    The result is an image tensor candidate for a separately validated model;
    this function itself does not classify disease.
    """
    if not 256 <= max_side <= 4096:
        raise ValueError("max_side 256 ile 4096 arasında olmalıdır.")
    if not content:
        raise ValueError("Görüntü içeriği boş olamaz.")

    module = _load_native_module()
    if module is None:
        raise NativeVisionUnavailable("MediCore native vision engine yüklü değil.")
    return module.preprocess_chest_xray(content, max_side)
