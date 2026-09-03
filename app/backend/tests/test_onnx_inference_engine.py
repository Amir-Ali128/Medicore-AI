from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from app.domain import onnx_inference_engine as engine_module


class FakeSession:
    def __init__(
        self,
        *,
        input_shape=None,
        output_shape=None,
        metadata=None,
    ) -> None:
        self.input_shape = input_shape or [None, 1, 4, 4]
        self.output_shape = output_shape or [None, 2]
        self.metadata = metadata or {
            "medicore.model_id": "test-xray",
            "medicore.model_version": "1.2.3",
            "medicore.tensor_contract": engine_module.EXPECTED_XRAY_TENSOR_CONTRACT,
        }
        self.run_calls = 0
        self._providers = ["CPUExecutionProvider"]

    def get_inputs(self):
        return [SimpleNamespace(name="image", shape=self.input_shape, type="tensor(float)")]

    def get_outputs(self):
        return [SimpleNamespace(name="findings", shape=self.output_shape, type="tensor(float)")]

    def get_modelmeta(self):
        return SimpleNamespace(custom_metadata_map=self.metadata)

    def get_providers(self):
        return list(self._providers)

    def run(self, output_names, feed):
        assert output_names == ["findings"]
        batch = feed["image"]
        self.run_calls += 1
        rows = np.tile(np.array([[0.0, 2.0]], dtype=np.float32), (batch.shape[0], 1))
        return [rows]


class FakeOrt:
    class SessionOptions:
        pass

    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def get_available_providers(self):
        return ["CPUExecutionProvider"]

    def InferenceSession(self, path, *, sess_options, providers):
        assert path
        assert sess_options is not None
        assert providers == ["CPUExecutionProvider"]
        self.session._providers = providers
        return self.session


def _write_model_and_manifest(tmp_path, *, model_bytes=b"fake-onnx-model", **overrides):
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(model_bytes)
    payload = {
        "schema_version": 1,
        "model_id": "test-xray",
        "model_version": "1.2.3",
        "model_sha256": hashlib.sha256(model_bytes).hexdigest(),
        "tensor_contract": engine_module.EXPECTED_XRAY_TENSOR_CONTRACT,
        "input_name": "image",
        "input_shape": [-1, 1, 4, 4],
        "output_name": "findings",
        "output_kind": "logits",
        "labels": ["opacity", "effusion"],
        "max_batch_size": 4,
        "provider_order": ["CPUExecutionProvider"],
        "default_threshold": 0.5,
    }
    payload.update(overrides)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return model_path, manifest_path


def _install_fake_runtime(monkeypatch, session: FakeSession) -> None:
    monkeypatch.setattr(engine_module, "_load_onnxruntime", lambda: FakeOrt(session))


def test_engine_validates_hash_and_runs_dynamic_batch(tmp_path, monkeypatch):
    model_path, manifest_path = _write_model_and_manifest(tmp_path)
    session = FakeSession()
    _install_fake_runtime(monkeypatch, session)

    engine = engine_module.OnnxInferenceEngine(model_path, manifest_path)
    batch = np.ones((2, 1, 4, 4), dtype=np.float32)
    result = engine.infer_batch(batch)

    assert result["batch_size"] == 2
    assert result["model"]["model_version"] == "1.2.3"
    assert result["model"]["tensor_contract"] == engine_module.EXPECTED_XRAY_TENSOR_CONTRACT
    assert len(result["cases"]) == 2
    assert result["cases"][0]["scores"][0]["label"] == "effusion"
    assert result["cases"][0]["scores"][0]["score"] > 0.8
    assert session.run_calls == 1


def test_fixed_batch_one_is_microbatched_without_padding(tmp_path, monkeypatch):
    model_path, manifest_path = _write_model_and_manifest(tmp_path)
    session = FakeSession(input_shape=[1, 1, 4, 4])
    _install_fake_runtime(monkeypatch, session)

    engine = engine_module.OnnxInferenceEngine(model_path, manifest_path)
    result = engine.infer_batch(np.zeros((3, 1, 4, 4), dtype=np.float32))

    assert result["batch_size"] == 3
    assert session.run_calls == 3


def test_model_hash_mismatch_is_rejected_before_session(tmp_path, monkeypatch):
    model_path, manifest_path = _write_model_and_manifest(
        tmp_path,
        model_sha256="0" * 64,
    )
    _install_fake_runtime(monkeypatch, FakeSession())

    with pytest.raises(engine_module.ModelContractError, match="SHA-256"):
        engine_module.OnnxInferenceEngine(model_path, manifest_path)


def test_session_output_class_count_must_match_labels(tmp_path, monkeypatch):
    model_path, manifest_path = _write_model_and_manifest(tmp_path)
    _install_fake_runtime(monkeypatch, FakeSession(output_shape=[None, 3]))

    with pytest.raises(engine_module.ModelContractError, match="sınıf sayısı"):
        engine_module.OnnxInferenceEngine(model_path, manifest_path)


def test_batch_contract_dtype_and_range_are_strict(tmp_path, monkeypatch):
    model_path, manifest_path = _write_model_and_manifest(tmp_path)
    _install_fake_runtime(monkeypatch, FakeSession())
    engine = engine_module.OnnxInferenceEngine(model_path, manifest_path)

    with pytest.raises(engine_module.ModelContractError, match="dtype"):
        engine.infer_batch(np.zeros((1, 1, 4, 4), dtype=np.float64))
    with pytest.raises(engine_module.ModelContractError, match=r"\[0,1\]"):
        engine.infer_batch(np.full((1, 1, 4, 4), 2.0, dtype=np.float32))
    with pytest.raises(engine_module.ModelContractError, match="contract"):
        engine.infer_batch(
            np.zeros((1, 1, 4, 4), dtype=np.float32),
            tensor_contract="wrong-contract",
        )


def test_prepared_xray_batch_preserves_transform_and_quality(tmp_path, monkeypatch):
    model_path, manifest_path = _write_model_and_manifest(tmp_path)
    _install_fake_runtime(monkeypatch, FakeSession())
    engine = engine_module.OnnxInferenceEngine(model_path, manifest_path)

    prepared = {
        "contract_version": engine_module.EXPECTED_XRAY_TENSOR_CONTRACT,
        "shape": [1, 1, 4, 4],
        "tensor": np.zeros((1, 1, 4, 4), dtype=np.float32),
        "transform": {"scale_x": 0.5},
        "quality": {"technical_flags": []},
    }
    result = engine.infer_prepared_xrays([prepared, prepared])

    assert result["batch_size"] == 2
    assert result["cases"][0]["transform"] == {"scale_x": 0.5}
    assert result["cases"][0]["quality"] == {"technical_flags": []}


def test_manifest_rejects_wrong_xray_tensor_contract(tmp_path):
    _, manifest_path = _write_model_and_manifest(
        tmp_path,
        tensor_contract="legacy-xray-contract",
    )
    with pytest.raises(engine_module.ModelManifestError, match="tensor contract"):
        engine_module.load_model_manifest(manifest_path)


def test_configured_engine_is_opt_in(monkeypatch):
    engine_module.get_configured_xray_onnx_engine.cache_clear()
    monkeypatch.delenv("XRAY_ONNX_ENABLED", raising=False)
    assert engine_module.get_configured_xray_onnx_engine() is None
    engine_module.get_configured_xray_onnx_engine.cache_clear()
