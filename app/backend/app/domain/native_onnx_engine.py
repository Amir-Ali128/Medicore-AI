"""Optional native C++ ONNX inference backend.

The model manifest, SHA-256 pinning and public result contract remain identical to
``onnx_inference_engine.py``. Only the execution hot path moves into the optional
``medicore_onnx`` pybind module. If the extension was built without ONNX Runtime C++
libraries this backend reports itself unavailable and callers can safely fall back to
Python onnxruntime.
"""

from __future__ import annotations

import importlib
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.domain.onnx_inference_engine import (
    EXPECTED_XRAY_TENSOR_CONTRACT,
    ModelBusy,
    ModelContractError,
    ModelUnavailable,
    OnnxInferenceError,
    load_model_manifest,
    sha256_file,
)

NATIVE_ONNX_CONTRACT = "medicore-native-onnx-v1"


@lru_cache(maxsize=1)
def _load_native_module() -> Any | None:
    try:
        return importlib.import_module("medicore_onnx")
    except (ImportError, OSError):
        return None


def native_onnx_available() -> bool:
    module = _load_native_module()
    return bool(
        module is not None
        and getattr(module, "CONTRACT_VERSION", None) == NATIVE_ONNX_CONTRACT
        and bool(getattr(module, "AVAILABLE", False))
        and callable(getattr(module, "runtime_available", None))
        and bool(module.runtime_available())
    )


def _require_module() -> Any:
    module = _load_native_module()
    if module is None:
        raise ModelUnavailable("MediCore native ONNX extension yüklü değil.")
    if getattr(module, "CONTRACT_VERSION", None) != NATIVE_ONNX_CONTRACT:
        raise ModelUnavailable("MediCore native ONNX contract sürümü uyumsuz.")
    if not bool(getattr(module, "AVAILABLE", False)):
        raise ModelUnavailable("MediCore native ONNX extension ONNX Runtime olmadan derlenmiş.")
    return module


def _load_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise ModelUnavailable("NumPy yüklü değil.") from exc
    return np


class NativeOnnxInferenceEngine:
    """Manifest-pinned classifier whose model execution runs in C++."""

    def __init__(
        self,
        model_path: str | Path,
        manifest_path: str | Path,
        *,
        max_concurrency: int = 2,
        concurrency_wait_seconds: float = 2.0,
        intra_op_num_threads: int | None = None,
        inter_op_num_threads: int | None = None,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("ONNX max_concurrency must be at least 1.")
        if concurrency_wait_seconds <= 0:
            raise ValueError("ONNX concurrency_wait_seconds must be positive.")
        if intra_op_num_threads is not None and intra_op_num_threads < 1:
            raise ValueError("ONNX intra_op_num_threads must be at least 1.")
        if inter_op_num_threads is not None and inter_op_num_threads < 1:
            raise ValueError("ONNX inter_op_num_threads must be at least 1.")

        self.model_path = Path(model_path)
        self.manifest_path = Path(manifest_path)
        self.manifest = load_model_manifest(self.manifest_path)
        self._max_concurrency = int(max_concurrency)
        self._concurrency_wait_seconds = float(concurrency_wait_seconds)
        self._intra_op_num_threads = intra_op_num_threads
        self._inter_op_num_threads = inter_op_num_threads
        self._execution_gate = threading.BoundedSemaphore(self._max_concurrency)

        actual_hash = sha256_file(self.model_path)
        if actual_hash.lower() != self.manifest.model_sha256.lower():
            raise ModelContractError(
                "ONNX model SHA-256 manifest ile eşleşmiyor; model sürümü doğrulanamadı."
            )
        self.model_sha256 = actual_hash.lower()

        module = _require_module()
        try:
            self._runner = module.NativeOnnxSession(
                str(self.model_path),
                self.manifest.input_name,
                self.manifest.output_name,
                self.manifest.input_shape[1],
                self.manifest.input_shape[2],
                self.manifest.input_shape[3],
                len(self.manifest.labels),
                self.manifest.input_shape[0],
                int(intra_op_num_threads or 0),
                int(inter_op_num_threads or 0),
            )
        except Exception as exc:
            raise ModelUnavailable("Native C++ ONNX session oluşturulamadı.") from exc

        self._static_input_batch = int(getattr(self._runner, "static_input_batch", -1))
        self.providers = ("CPUExecutionProvider(native-cpp)",)

    def describe(self) -> dict[str, Any]:
        return {
            "model_id": self.manifest.model_id,
            "model_version": self.manifest.model_version,
            "model_sha256": self.model_sha256,
            "tensor_contract": self.manifest.tensor_contract,
            "input_name": self.manifest.input_name,
            "input_shape": list(self.manifest.input_shape),
            "output_name": self.manifest.output_name,
            "output_kind": self.manifest.output_kind,
            "labels": list(self.manifest.labels),
            "max_batch_size": self.manifest.max_batch_size,
            "providers": list(self.providers),
            "runtime_backend": "native_cpp",
            "native_contract": NATIVE_ONNX_CONTRACT,
            "runtime_limits": {
                "max_concurrency": self._max_concurrency,
                "concurrency_wait_seconds": self._concurrency_wait_seconds,
                "intra_op_num_threads": self._intra_op_num_threads,
                "inter_op_num_threads": self._inter_op_num_threads,
            },
        }

    def _validate_batch(self, batch: Any, *, tensor_contract: str) -> Any:
        if tensor_contract != self.manifest.tensor_contract:
            raise ModelContractError("Inference tensor contract model manifest ile uyuşmuyor.")
        np = _load_numpy()
        array = np.asarray(batch)
        if array.dtype != np.float32:
            raise ModelContractError("Inference input dtype float32 olmalıdır.")
        if array.ndim != 4:
            raise ModelContractError("Inference input rank 4 [N,1,H,W] olmalıdır.")
        expected = self.manifest.input_shape
        if array.shape[0] < 1 or array.shape[0] > self.manifest.max_batch_size:
            raise ModelContractError("Inference batch boyutu manifest limitinin dışında.")
        if array.shape[1:] != (expected[1], expected[2], expected[3]):
            raise ModelContractError("Inference input shape model manifest ile uyuşmuyor.")
        if not bool(np.isfinite(array).all()):
            raise ModelContractError("Inference tensor NaN/Inf içeremez.")
        minimum = float(array.min())
        maximum = float(array.max())
        if minimum < -1e-6 or maximum > 1.0 + 1e-6:
            raise ModelContractError("Inference tensor değerleri [0,1] aralığında olmalıdır.")
        return np.ascontiguousarray(array)

    def _run_raw(self, batch: Any) -> Any:
        acquired = self._execution_gate.acquire(timeout=self._concurrency_wait_seconds)
        if not acquired:
            raise ModelBusy(
                "ONNX inference kapasitesi dolu; istek yerel concurrency sınırında bekletilmedi."
            )
        try:
            np = _load_numpy()
            try:
                raw = self._runner.run(batch)
            except Exception as exc:
                raise OnnxInferenceError("Native C++ ONNX inference çalıştırılamadı.") from exc
            return np.asarray(raw, dtype=np.float32)
        finally:
            self._execution_gate.release()

    def infer_batch(
        self,
        batch: Any,
        *,
        tensor_contract: str = EXPECTED_XRAY_TENSOR_CONTRACT,
    ) -> dict[str, Any]:
        np = _load_numpy()
        array = self._validate_batch(batch, tensor_contract=tensor_contract)
        raw = self._run_raw(array)
        expected_shape = (array.shape[0], len(self.manifest.labels))
        if raw.shape != expected_shape:
            raise ModelContractError(
                f"ONNX output shape {tuple(raw.shape)} beklenen {expected_shape} ile uyuşmuyor."
            )
        if not bool(np.isfinite(raw).all()):
            raise ModelContractError("ONNX model output NaN/Inf içeriyor.")

        if self.manifest.output_kind == "logits":
            clipped = np.clip(raw, -80.0, 80.0)
            scores = 1.0 / (1.0 + np.exp(-clipped))
        else:
            scores = np.clip(raw, 0.0, 1.0)

        cases: list[dict[str, Any]] = []
        for row in scores:
            findings = []
            for label, score_value in zip(self.manifest.labels, row, strict=True):
                score = float(score_value)
                threshold = self.manifest.threshold_for(label)
                findings.append(
                    {
                        "label": label,
                        "score": score,
                        "threshold": threshold,
                        "above_threshold": bool(score >= threshold),
                    }
                )
            findings.sort(key=lambda item: item["score"], reverse=True)
            cases.append({"scores": findings})

        return {
            "model": self.describe(),
            "batch_size": int(array.shape[0]),
            "cases": cases,
        }

    def infer_prepared_xrays(
        self,
        prepared_items: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        if not prepared_items:
            raise ModelContractError("En az bir hazırlanmış X-Ray tensor gerekir.")
        np = _load_numpy()
        tensors = []
        metadata: list[dict[str, Any]] = []
        expected_single_shape = [
            1,
            self.manifest.input_shape[1],
            self.manifest.input_shape[2],
            self.manifest.input_shape[3],
        ]
        for item in prepared_items:
            if item.get("contract_version") != self.manifest.tensor_contract:
                raise ModelContractError("Hazırlanmış X-Ray tensor contract uyumsuz.")
            if list(item.get("shape") or []) != expected_single_shape:
                raise ModelContractError("Hazırlanmış X-Ray tensor shape modelle uyumsuz.")
            tensor = np.asarray(item.get("tensor"))
            if tensor.dtype != np.float32:
                raise ModelContractError("Hazırlanmış X-Ray tensor dtype float32 olmalıdır.")
            tensors.append(tensor)
            metadata.append(
                {
                    "transform": item.get("transform"),
                    "quality": item.get("quality"),
                }
            )

        batch = np.concatenate(tensors, axis=0)
        result = self.infer_batch(batch, tensor_contract=self.manifest.tensor_contract)
        for case, context in zip(result["cases"], metadata, strict=True):
            case.update(context)
        return result
