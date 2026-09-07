"""Python-vs-native ONNX parity verification for release/production gates.

This module does not interpret model output clinically. It verifies that the same pinned
model and tensor produce materially equivalent score contracts through Python ONNX
Runtime and the native C++ ONNX Runtime path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.domain.onnx_inference_engine import (
    EXPECTED_XRAY_TENSOR_CONTRACT,
    ModelContractError,
    OnnxInferenceEngine,
    load_model_manifest,
)
from app.domain.native_onnx_engine import NativeOnnxInferenceEngine, native_onnx_available


@dataclass(frozen=True)
class OnnxParityReport:
    passed: bool
    max_absolute_error: float
    compared_scores: int
    model_id: str
    model_version: str
    model_sha256: str
    tolerance: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "max_absolute_error": self.max_absolute_error,
            "compared_scores": self.compared_scores,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
            "tolerance": self.tolerance,
        }


def _model_identity(result: Mapping[str, Any]) -> tuple[str, str, str, str]:
    model = result.get("model")
    if not isinstance(model, Mapping):
        raise ModelContractError("Parity result model metadata eksik.")
    return (
        str(model.get("model_id") or ""),
        str(model.get("model_version") or ""),
        str(model.get("model_sha256") or ""),
        str(model.get("tensor_contract") or ""),
    )


def _scores_by_label(case: Mapping[str, Any]) -> dict[str, float]:
    raw = case.get("scores")
    if not isinstance(raw, list):
        raise ModelContractError("Parity result scores listesi eksik.")
    scores: dict[str, float] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise ModelContractError("Parity score öğesi geçersiz.")
        label = str(item.get("label") or "")
        if not label or label in scores:
            raise ModelContractError("Parity score label boş veya tekrarlı.")
        scores[label] = float(item["score"])
    return scores


def compare_inference_results(
    python_result: Mapping[str, Any],
    native_result: Mapping[str, Any],
    *,
    absolute_tolerance: float = 1e-5,
) -> OnnxParityReport:
    if absolute_tolerance <= 0:
        raise ValueError("absolute_tolerance pozitif olmalıdır.")

    py_identity = _model_identity(python_result)
    native_identity = _model_identity(native_result)
    if py_identity != native_identity:
        raise ModelContractError("Python/native parity aynı model kimliğini taşımıyor.")
    if py_identity[3] != EXPECTED_XRAY_TENSOR_CONTRACT:
        raise ModelContractError("Parity tensor contract X-Ray Core v2 ile uyumsuz.")

    py_cases = python_result.get("cases")
    native_cases = native_result.get("cases")
    if not isinstance(py_cases, list) or not isinstance(native_cases, list):
        raise ModelContractError("Parity cases listesi eksik.")
    if len(py_cases) != len(native_cases):
        raise ModelContractError("Python/native parity batch boyutları farklı.")

    max_error = 0.0
    compared = 0
    for py_case, native_case in zip(py_cases, native_cases, strict=True):
        if not isinstance(py_case, Mapping) or not isinstance(native_case, Mapping):
            raise ModelContractError("Parity case formatı geçersiz.")
        py_scores = _scores_by_label(py_case)
        native_scores = _scores_by_label(native_case)
        if py_scores.keys() != native_scores.keys():
            raise ModelContractError("Python/native parity label kümeleri farklı.")
        for label, py_score in py_scores.items():
            error = abs(py_score - native_scores[label])
            max_error = max(max_error, error)
            compared += 1

    if compared == 0:
        raise ModelContractError("Parity karşılaştırılacak skor üretmedi.")

    return OnnxParityReport(
        passed=max_error <= absolute_tolerance,
        max_absolute_error=max_error,
        compared_scores=compared,
        model_id=py_identity[0],
        model_version=py_identity[1],
        model_sha256=py_identity[2],
        tolerance=absolute_tolerance,
    )


def run_engine_parity(
    python_engine: Any,
    native_engine: Any,
    batch: Any,
    *,
    absolute_tolerance: float = 1e-5,
) -> OnnxParityReport:
    python_result = python_engine.infer_batch(
        batch, tensor_contract=EXPECTED_XRAY_TENSOR_CONTRACT
    )
    native_result = native_engine.infer_batch(
        batch, tensor_contract=EXPECTED_XRAY_TENSOR_CONTRACT
    )
    return compare_inference_results(
        python_result,
        native_result,
        absolute_tolerance=absolute_tolerance,
    )


def run_real_model_parity(
    model_path: str | Path,
    manifest_path: str | Path,
    *,
    absolute_tolerance: float = 1e-5,
    batch_size: int = 2,
    seed: int = 20260907,
) -> OnnxParityReport:
    """Run a deterministic real-model parity check; intended for release gates."""
    if not native_onnx_available():
        raise ModelContractError("Native C++ ONNX Runtime parity için kullanılabilir değil.")
    manifest = load_model_manifest(manifest_path)
    if batch_size < 1 or batch_size > manifest.max_batch_size:
        raise ValueError("batch_size manifest limitinin dışında.")

    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise ModelContractError("NumPy parity testi için gerekli.") from exc

    rng = np.random.default_rng(seed)
    batch = rng.random(
        (
            batch_size,
            manifest.input_shape[1],
            manifest.input_shape[2],
            manifest.input_shape[3],
        ),
        dtype=np.float32,
    )

    python_engine = OnnxInferenceEngine(
        model_path,
        manifest_path,
        providers=("CPUExecutionProvider",),
        max_concurrency=1,
    )
    native_engine = NativeOnnxInferenceEngine(
        model_path,
        manifest_path,
        max_concurrency=1,
    )
    report = run_engine_parity(
        python_engine,
        native_engine,
        batch,
        absolute_tolerance=absolute_tolerance,
    )
    if not report.passed:
        raise ModelContractError(
            f"Native ONNX parity başarısız: max abs error={report.max_absolute_error:.8g}, "
            f"tolerance={report.tolerance:.8g}."
        )
    return report
