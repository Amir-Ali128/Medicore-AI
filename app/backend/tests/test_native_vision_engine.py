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
    monkeypatch.setattr(native_vision_engine.importlib, "import_module", lambda name: fake_module)

    result = native_vision_engine.inspect_image(b"encoded-image")
    assert result["width"] == 1024
    assert result["channels"] == 1
    _reset_native_cache()


def test_xray_quality_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()
    fake_module = SimpleNamespace(
        inspect_xray_quality=lambda content: {
            "width": 512,
            "height": 512,
            "robust_dynamic_range": 0.62,
            "technical_flags": [],
        }
    )
    monkeypatch.setattr(native_vision_engine.importlib, "import_module", lambda name: fake_module)

    result = native_vision_engine.inspect_xray_quality(b"encoded-image")
    assert result["robust_dynamic_range"] == pytest.approx(0.62)
    assert result["technical_flags"] == []
    _reset_native_cache()


def test_prepare_xray_tensor_enforces_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()
    fake_module = SimpleNamespace(
        prepare_xray_tensor=lambda content, width, height, preserve, pad: {
            "tensor": object(),
            "shape": [1, 1, height, width],
            "layout": "NCHW",
            "dtype": "float32",
            "value_range": (0.0, 1.0),
            "contract_version": native_vision_engine.XRAY_TENSOR_CONTRACT,
            "transform": {"pad_top": 10},
            "quality": {},
        }
    )
    monkeypatch.setattr(native_vision_engine.importlib, "import_module", lambda name: fake_module)

    result = native_vision_engine.prepare_xray_tensor(
        b"encoded-image", target_width=640, target_height=512
    )
    assert result["shape"] == [1, 1, 512, 640]
    assert result["contract_version"] == "xray-core-v2/nchw-f32-0-1"
    _reset_native_cache()


def test_prepare_xray_tensor_rejects_contract_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()
    fake_module = SimpleNamespace(
        prepare_xray_tensor=lambda *args: {
            "shape": [1, 1, 1024, 1024],
            "contract_version": "wrong-version",
        }
    )
    monkeypatch.setattr(native_vision_engine.importlib, "import_module", lambda name: fake_module)

    with pytest.raises(RuntimeError, match="contract"):
        native_vision_engine.prepare_xray_tensor(b"encoded-image")
    _reset_native_cache()


def test_inspect_dicom_requires_technical_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()
    fake_module = SimpleNamespace(
        inspect_dicom=lambda content: {
            "rows": 512,
            "columns": 512,
            "frames": 1,
            "bits_allocated": 16,
            "bits_stored": 12,
            "photometric_interpretation": "MONOCHROME2",
            "modality": "DX",
            "compressed": False,
            "transfer_syntax": "Little Endian Explicit",
        }
    )
    monkeypatch.setattr(native_vision_engine.importlib, "import_module", lambda name: fake_module)

    result = native_vision_engine.inspect_dicom(b"dicom")
    assert result["modality"] == "DX"
    assert result["bits_stored"] == 12
    _reset_native_cache()


def test_prepare_dicom_frame_enforces_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()
    fake_module = SimpleNamespace(
        prepare_dicom_frame=lambda content, frame, center, width: {
            "image": object(),
            "shape": [512, 256],
            "dtype": "uint8",
            "contract_version": native_vision_engine.DICOM_FRAME_CONTRACT,
            "metadata": {"rows": 512, "columns": 256, "modality": "CT"},
            "window": {"source": "dicom", "center": 40.0, "width": 400.0},
        }
    )
    monkeypatch.setattr(native_vision_engine.importlib, "import_module", lambda name: fake_module)

    result = native_vision_engine.prepare_dicom_frame(b"dicom", frame_index=0)
    assert result["shape"] == [512, 256]
    assert result["contract_version"] == "dicom-frame-v1/grayscale-u8"
    _reset_native_cache()


def test_prepare_dicom_frame_requires_complete_window_override() -> None:
    with pytest.raises(ValueError, match="center"):
        native_vision_engine.prepare_dicom_frame(b"dicom", window_center=40.0)


def test_prepare_dicom_xray_tensor_enforces_cr_dx_source(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_native_cache()
    fake_module = SimpleNamespace(
        prepare_dicom_xray_tensor=lambda content, frame, center, width, target_w, target_h, preserve, pad: {
            "tensor": object(),
            "shape": [1, 1, target_h, target_w],
            "contract_version": native_vision_engine.XRAY_TENSOR_CONTRACT,
            "source_contract": native_vision_engine.DICOM_FRAME_CONTRACT,
            "metadata": {"rows": 1024, "columns": 1024, "modality": "DX"},
            "window": {"source": "robust"},
            "transform": {},
            "quality": {},
        }
    )
    monkeypatch.setattr(native_vision_engine.importlib, "import_module", lambda name: fake_module)

    result = native_vision_engine.prepare_dicom_xray_tensor(
        b"dicom", target_width=640, target_height=512
    )
    assert result["shape"] == [1, 1, 512, 640]
    assert result["metadata"]["modality"] == "DX"
    _reset_native_cache()


def test_preprocess_rejects_invalid_max_side() -> None:
    with pytest.raises(ValueError):
        native_vision_engine.preprocess_chest_xray(b"image", max_side=128)


def test_tensor_rejects_invalid_target_size() -> None:
    with pytest.raises(ValueError):
        native_vision_engine.prepare_xray_tensor(b"image", target_width=16)
