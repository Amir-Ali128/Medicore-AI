from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain import native_vision_engine


def _reset_native_cache() -> None:
    native_vision_engine._load_native_module.cache_clear()


def test_native_vision_unavailable_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()

    def fake_import_module(name: str):
        assert name == "medicore_vision"
        raise ImportError("not installed")

    monkeypatch.setattr(native_vision_engine.importlib, "import_module", fake_import_module)

    assert native_vision_engine.native_vision_available() is False
    assert native_vision_engine.try_inspect_image(b"image") is None

    _reset_native_cache()


def test_native_vision_metadata_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()

    fake_module = SimpleNamespace(
        inspect_image=lambda content: {
            "width": 1024,
            "height": 1024,
            "channels": 1,
            "mean_intensity": 120.5,
            "stddev_intensity": 31.2,
            "min_intensity": 0,
            "max_intensity": 255,
        }
    )
    monkeypatch.setattr(
        native_vision_engine.importlib,
        "import_module",
        lambda name: fake_module,
    )

    result = native_vision_engine.inspect_image(b"encoded-image")

    assert result["width"] == 1024
    assert result["channels"] == 1

    _reset_native_cache()


def test_preprocess_rejects_invalid_max_side() -> None:
    with pytest.raises(ValueError):
        native_vision_engine.preprocess_chest_xray(b"image", max_side=128)
