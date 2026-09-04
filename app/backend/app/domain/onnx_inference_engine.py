"""Versioned ONNX inference runtime for MediCore X-Ray models.

The engine consumes tensors prepared by X-Ray Core v2. It deliberately keeps
model execution separate from clinical interpretation: outputs are model scores,
not autonomous diagnoses. A model manifest and SHA-256 pin the exact binary and
its input/output contract before any inference is allowed.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.core.config import get_settings

EXPECTED_XRAY_TENSOR_CONTRACT = "xray-core-v2/nchw-f32-0-1"
MANIFEST_SCHEMA_VERSION = 1
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class OnnxInferenceError(RuntimeError):
    """Base class for X-Ray ONNX runtime failures."""


class ModelManifestError(OnnxInferenceError):
    """Raised when a model manifest is malformed or unsupported."""


class ModelContractError(OnnxInferenceError):
    """Raised when model I/O does not match the pinned MediCore contract."""


class ModelUnavailable(OnnxInferenceError):
    """Raised when a configured model/runtime cannot be loaded."""


class ModelBusy(OnnxInferenceError):
    """Raised when local ONNX execution slots are saturated."""


@dataclass(frozen=True)
class OnnxModelManifest:
    schema_version: int
    model_id: str
    model_version: str
    model_sha256: str
    tensor_contract: str
    input_name: str
    input_shape: tuple[int, int, int, int]
    output_name: str
    output_kind: str
    labels: tuple[str, ...]
    max_batch_size: int = 8
    provider_order: tuple[str, ...] = ("CPUExecutionProvider",)
    default_threshold: float = 0.5
    thresholds: Mapping[str, float] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OnnxModelManifest":
        try:
            schema_version = int(value["schema_version"])
            model_id = str(value["model_id"]).strip()
            model_version = str(value["model_version"]).strip()
            model_sha256 = str(value["model_sha256"]).strip().lower()
            tensor_contract = str(value["tensor_contract"]).strip()
            input_name = str(value["input_name"]).strip()
            input_shape = tuple(int(item) for item in value["input_shape"])
            output_name = str(value["output_name"]).strip()
            output_kind = str(value["output_kind"]).strip().lower()
            labels = tuple(str(item).strip() for item in value["labels"])
            max_batch_size = int(value.get("max_batch_size", 8))
            provider_order = tuple(
                str(item).strip()
                for item in value.get("provider_order", ["CPUExecutionProvider"])
            )
            default_threshold = float(value.get("default_threshold", 0.5))
            thresholds_raw = value.get("thresholds", {})
            thresholds = {
                str(key).strip(): float(threshold)
                for key, threshold in dict(thresholds_raw).items()
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ModelManifestError("ONNX model manifest alanları geçersiz.") from exc

        if schema_version != MANIFEST_SCHEMA_VERSION:
            raise ModelManifestError(
                f"Desteklenmeyen manifest schema_version: {schema_version}."
            )
        if not model_id or not re.fullmatch(r"[A-Za-z0-9._-]+", model_id):
            raise ModelManifestError("model_id boş veya geçersiz karakter içeriyor.")
        if not _SEMVER_RE.fullmatch(model_version):
            raise ModelManifestError("model_version semver biçiminde olmalıdır (örn. 1.0.0).")
        if not _SHA256_RE.fullmatch(model_sha256):
            raise ModelManifestError("model_sha256 tam 64 karakterlik SHA-256 olmalıdır.")
        if tensor_contract != EXPECTED_XRAY_TENSOR_CONTRACT:
            raise ModelManifestError(
                "Model manifest X-Ray Core v2 tensor contract ile uyumlu değil."
            )
        if not input_name or not output_name:
            raise ModelManifestError("input_name ve output_name zorunludur.")
        if len(input_shape) != 4:
            raise ModelManifestError("input_shape NCHW olarak dört boyutlu olmalıdır.")
        batch, channels, height, width = input_shape
        if batch == 0 or batch < -1:
            raise ModelManifestError("input_shape batch boyutu -1 veya pozitif olmalıdır.")
        if channels != 1:
            raise ModelManifestError("X-Ray Core v2 model input kanalı 1 olmalıdır.")
        if height <= 0 or width <= 0:
            raise ModelManifestError("Model giriş yüksekliği/genişliği pozitif olmalıdır.")
        if output_kind not in {"logits", "probabilities"}:
            raise ModelManifestError("output_kind logits veya probabilities olmalıdır.")
        if not labels or any(not label for label in labels):
            raise ModelManifestError("Model en az bir dolu label içermelidir.")
        if len(set(labels)) != len(labels):
            raise ModelManifestError("Model label listesinde tekrar olamaz.")
        if max_batch_size < 1 or max_batch_size > 128:
            raise ModelManifestError("max_batch_size 1 ile 128 arasında olmalıdır.")
        if not provider_order or any(not item for item in provider_order):
            raise ModelManifestError("provider_order en az bir provider içermelidir.")
        if not 0.0 <= default_threshold <= 1.0:
            raise ModelManifestError("default_threshold 0 ile 1 arasında olmalıdır.")
        for label, threshold in thresholds.items():
            if label not in labels:
                raise ModelManifestError(f"Bilinmeyen threshold label: {label}.")
            if not 0.0 <= threshold <= 1.0:
                raise ModelManifestError(f"{label} threshold değeri 0 ile 1 arasında olmalıdır.")

        return cls(
            schema_version=schema_version,
            model_id=model_id,
            model_version=model_version,
            model_sha256=model_sha256,
            tensor_contract=tensor_contract,
            input_name=input_name,
            input_shape=(batch, channels, height, width),
            output_name=output_name,
            output_kind=output_kind,
            labels=labels,
            max_batch_size=max_batch_size,
            provider_order=provider_order,
            default_threshold=default_threshold,
            thresholds=thresholds,
        )

    def threshold_for(self, label: str) -> float:
        return float(self.thresholds.get(label, self.default_threshold))


def load_model_manifest(path: str | Path) -> OnnxModelManifest:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelUnavailable(f"ONNX manifest bulunamadı: {manifest_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelManifestError("ONNX manifest okunamadı veya geçerli JSON değil.") from exc
    if not isinstance(payload, dict):
        raise ModelManifestError("ONNX manifest JSON nesnesi olmalıdır.")
    return OnnxModelManifest.from_mapping(payload)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise ModelUnavailable(f"ONNX model bulunamadı: {path}") from exc
    except OSError as exc:
        raise ModelUnavailable(f"ONNX model okunamadı: {path}") from exc
    return digest.hexdigest()


def _load_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - dependency is installed in production/CI
        raise ModelUnavailable("NumPy yüklü değil.") from exc
    return np


def _load_onnxruntime() -> Any:
    try:
        import onnxruntime as ort
    except ImportError as exc:  # pragma: no cover - dependency is installed in production/CI
        raise ModelUnavailable("ONNX Runtime yüklü değil.") from exc
    return ort


def _static_dim(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


class OnnxInferenceEngine:
    """Loads one pinned ONNX classifier and executes validated batched inference."""

    def __init__(
        self,
        model_path: str | Path,
        manifest_path: str | Path,
        *,
        providers: Sequence[str] | None = None,
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

        ort = _load_onnxruntime()
        try:
            available = set(ort.get_available_providers())
        except Exception as exc:
            raise ModelUnavailable("ONNX Runtime provider listesi alınamadı.") from exc

        requested = tuple(providers or self.manifest.provider_order)
        selected = [provider for provider in requested if provider in available]
        if not selected and "CPUExecutionProvider" in available:
            selected = ["CPUExecutionProvider"]
        if not selected:
            raise ModelUnavailable("Uygun ONNX Runtime execution provider bulunamadı.")

        try:
            options = ort.SessionOptions()
            if intra_op_num_threads is not None:
                options.intra_op_num_threads = int(intra_op_num_threads)
            if inter_op_num_threads is not None:
                options.inter_op_num_threads = int(inter_op_num_threads)
            self._session = ort.InferenceSession(
                str(self.model_path),
                sess_options=options,
                providers=selected,
            )
        except Exception as exc:
            raise ModelUnavailable("ONNX model session oluşturulamadı.") from exc

        self.providers = tuple(self._session.get_providers())
        self._static_input_batch: int | None = None
        self._validate_session_contract()

    def _validate_session_contract(self) -> None:
        inputs = list(self._session.get_inputs())
        outputs = list(self._session.get_outputs())
        input_node = next((item for item in inputs if item.name == self.manifest.input_name), None)
        output_node = next((item for item in outputs if item.name == self.manifest.output_name), None)
        if input_node is None:
            raise ModelContractError(
                f"Model input bulunamadı: {self.manifest.input_name}."
            )
        if output_node is None:
            raise ModelContractError(
                f"Model output bulunamadı: {self.manifest.output_name}."
            )
        if getattr(input_node, "type", None) not in {None, "tensor(float)"}:
            raise ModelContractError("Model input dtype float32 olmalıdır.")

        input_shape = list(getattr(input_node, "shape", []) or [])
        if len(input_shape) != 4:
            raise ModelContractError("ONNX model input rank 4 NCHW olmalıdır.")
        expected = self.manifest.input_shape
        static_batch = _static_dim(input_shape[0])
        static_channels = _static_dim(input_shape[1])
        static_height = _static_dim(input_shape[2])
        static_width = _static_dim(input_shape[3])
        if static_channels is not None and static_channels != expected[1]:
            raise ModelContractError("ONNX model kanal sayısı manifest ile uyuşmuyor.")
        if static_height is not None and static_height != expected[2]:
            raise ModelContractError("ONNX model input yüksekliği manifest ile uyuşmuyor.")
        if static_width is not None and static_width != expected[3]:
            raise ModelContractError("ONNX model input genişliği manifest ile uyuşmuyor.")
        if expected[0] > 0 and static_batch is not None and static_batch != expected[0]:
            raise ModelContractError("ONNX model batch boyutu manifest ile uyuşmuyor.")
        self._static_input_batch = static_batch

        output_shape = list(getattr(output_node, "shape", []) or [])
        if len(output_shape) != 2:
            raise ModelContractError("ONNX classifier output rank 2 [N,C] olmalıdır.")
        static_classes = _static_dim(output_shape[1])
        if static_classes is not None and static_classes != len(self.manifest.labels):
            raise ModelContractError("ONNX output sınıf sayısı label listesiyle uyuşmuyor.")

        try:
            metadata = dict(
                getattr(self._session.get_modelmeta(), "custom_metadata_map", {}) or {}
            )
        except Exception:
            metadata = {}
        expected_metadata = {
            "medicore.model_id": self.manifest.model_id,
            "medicore.model_version": self.manifest.model_version,
            "medicore.tensor_contract": self.manifest.tensor_contract,
        }
        for key, expected_value in expected_metadata.items():
            actual_value = metadata.get(key)
            if actual_value is not None and actual_value != expected_value:
                raise ModelContractError(f"ONNX custom metadata uyumsuz: {key}.")

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
        return array

    def _run_raw(self, batch: Any) -> Any:
        acquired = self._execution_gate.acquire(timeout=self._concurrency_wait_seconds)
        if not acquired:
            raise ModelBusy(
                "ONNX inference kapasitesi dolu; istek yerel concurrency sınırında bekletilmedi."
            )

        try:
            np = _load_numpy()
            size = int(batch.shape[0])
            try:
                if self._static_input_batch in {None, size}:
                    raw = self._session.run(
                        [self.manifest.output_name],
                        {self.manifest.input_name: batch},
                    )[0]
                    return np.asarray(raw, dtype=np.float32)
                if self._static_input_batch == 1:
                    rows = []
                    for index in range(size):
                        output = self._session.run(
                            [self.manifest.output_name],
                            {self.manifest.input_name: batch[index : index + 1]},
                        )[0]
                        rows.append(np.asarray(output, dtype=np.float32))
                    return np.concatenate(rows, axis=0)
            except Exception as exc:
                if isinstance(exc, OnnxInferenceError):
                    raise
                raise OnnxInferenceError("ONNX inference çalıştırılamadı.") from exc
            raise ModelContractError(
                "Model sabit batch boyutu gelen batch ile uyumsuz; otomatik padding uygulanmadı."
            )
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

    def infer_prepared_xrays(self, prepared_items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
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


def _env_enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_configured_xray_onnx_engine() -> OnnxInferenceEngine | None:
    """Load the configured model only when explicitly enabled.

    The model binary itself is intentionally not committed to the repository.
    """
    if not _env_enabled(os.getenv("XRAY_ONNX_ENABLED")):
        return None
    model_path = os.getenv("XRAY_ONNX_MODEL_PATH", "").strip()
    manifest_path = os.getenv("XRAY_ONNX_MANIFEST_PATH", "").strip()
    if not model_path or not manifest_path:
        raise ModelUnavailable(
            "XRAY_ONNX_ENABLED açık ancak model/manifest yolu yapılandırılmamış."
        )
    settings = get_settings()
    return OnnxInferenceEngine(
        model_path,
        manifest_path,
        max_concurrency=settings.onnx_max_concurrency,
        concurrency_wait_seconds=settings.onnx_concurrency_wait_seconds,
        intra_op_num_threads=settings.onnx_intra_op_threads,
        inter_op_num_threads=settings.onnx_inter_op_threads,
    )


def try_get_configured_xray_onnx_engine() -> OnnxInferenceEngine | None:
    """Best-effort loader suitable for optional integration/fallback paths."""
    try:
        return get_configured_xray_onnx_engine()
    except (OnnxInferenceError, OSError, ValueError):
        return None
