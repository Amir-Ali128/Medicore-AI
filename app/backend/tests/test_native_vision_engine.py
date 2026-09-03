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
    assert native_vision_engine.try_assess_chest_xray_quality(b"image") is None

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


def test_quality_metrics_are_normalized_to_float(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()

    fake_module = SimpleNamespace(
        assess_chest_xray_quality=lambda content: {
            "dynamic_range": 255,
            "mean_intensity": 111.4,
            "stddev_intensity": 44.8,
            "clipped_low_fraction": 0.01,
            "clipped_high_fraction": 0.02,
            "laplacian_variance": 312.5,
        }
    )
    monkeypatch.setattr(
        native_vision_engine.importlib,
        "import_module",
        lambda name: fake_module,
    )

    result = native_vision_engine.assess_chest_xray_quality(b"encoded-image")

    assert result["dynamic_range"] == 255.0
    assert result["laplacian_variance"] == 312.5
    assert all(isinstance(value, float) for value in result.values())

    _reset_native_cache()


def test_quality_metrics_reject_incomplete_native_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_native_cache()

    fake_module = SimpleNamespace(
        assess_chest_xray_quality=lambda content: {"dynamic_range": 255.0}
    )
    monkeypatch.setattr(
        native_vision_engine.importlib,
        "import_module",
        lambda name: fake_module,
    )

    with pytest.raises(RuntimeError):
        native_vision_engine.assess_chest_xray_quality(b"encoded-image")

    _reset_native_cache()


def test_tensor_preparation_forwards_target_size(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()
    seen: dict[str, int] = {}

    def prepare(content: bytes, target_size: int):
        seen["target_size"] = target_size
        return [[0.0]]

    fake_module = SimpleNamespace(prepare_chest_xray_tensor=prepare)
    monkeypatch.setattr(
        native_vision_engine.importlib,
        "import_module",
        lambda name: fake_module,
    )

    result = native_vision_engine.prepare_chest_xray_tensor(
        b"encoded-image", target_size=512
    )

    assert result == [[0.0]]
    assert seen["target_size"] == 512

    _reset_native_cache()


def test_preprocess_rejects_invalid_max_side() -> None:
    with pytest.raises(ValueError):
        native_vision_engine.preprocess_chest_xray(b"image", max_side=128)


def test_tensor_preparation_rejects_invalid_target_size() -> None:
    with pytest.raises(ValueError):
        native_vision_engine.prepare_chest_xray_tensor(b"image", target_size=128)
