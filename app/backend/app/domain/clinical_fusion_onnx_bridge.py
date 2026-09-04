"""Bridge MediCore ONNX inference output into Clinical Fusion case input.

The bridge copies model identity, scores, thresholds, and non-sensitive technical
context. It does not reinterpret a classifier score as disease probability and does
not infer candidate-hypothesis mappings from label text.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.schemas.clinical_fusion import FusionSeverity
from app.schemas.clinical_fusion_case import OnnxCaseRun


class ClinicalFusionOnnxBridgeError(ValueError):
    """Raised when an ONNX result does not satisfy the expected MediCore contract."""


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ClinicalFusionOnnxBridgeError(f"{name} must be a mapping.")
    return value


def _copy_map(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def onnx_case_run_from_inference_result(
    result: Mapping[str, Any],
    *,
    run_id: str,
    study_id: str,
    case_index: int = 0,
    hypothesis_map: Mapping[str, Sequence[str]] | None = None,
    location_by_label: Mapping[str, Mapping[str, Any]] | None = None,
    severity_by_label: Mapping[str, FusionSeverity] | None = None,
) -> OnnxCaseRun:
    """Convert one case from ``OnnxInferenceEngine.infer_*`` output.

    ``hypothesis_map`` remains mandatory in meaning, even though an empty mapping is
    accepted: without an explicit mapping, above-threshold model findings are kept as
    unmapped evidence and cannot raise a candidate's fusion score.
    """

    payload = _require_mapping(result, "ONNX result")
    model = _require_mapping(payload.get("model"), "ONNX result.model")
    model_id = str(model.get("model_id") or "").strip()
    if not model_id:
        raise ClinicalFusionOnnxBridgeError("ONNX result.model.model_id is required.")

    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ClinicalFusionOnnxBridgeError("ONNX result.cases must be a non-empty list.")
    if case_index < 0 or case_index >= len(cases):
        raise ClinicalFusionOnnxBridgeError("case_index is outside ONNX result.cases.")
    case = _require_mapping(cases[case_index], "ONNX result case")
    scores = case.get("scores")
    if not isinstance(scores, list):
        raise ClinicalFusionOnnxBridgeError("ONNX result case.scores must be a list.")

    findings: list[dict[str, Any]] = []
    for index, raw in enumerate(scores):
        item = _require_mapping(raw, f"ONNX score[{index}]")
        try:
            label = str(item["label"]).strip()
            score = float(item["score"])
            threshold = float(item["threshold"])
            above_threshold = bool(item["above_threshold"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ClinicalFusionOnnxBridgeError(
                f"ONNX score[{index}] is missing a valid label/score/threshold/status."
            ) from exc
        if not label:
            raise ClinicalFusionOnnxBridgeError(f"ONNX score[{index}].label is empty.")
        findings.append(
            {
                "label": label,
                "score": score,
                "threshold": threshold,
                "above_threshold": above_threshold,
            }
        )

    technical_metadata: dict[str, Any] = {
        "source_contract": "onnx-inference-engine",
        "case_index": case_index,
    }
    for key in (
        "model_sha256",
        "tensor_contract",
        "input_name",
        "input_shape",
        "output_name",
        "output_kind",
        "providers",
    ):
        if key in model:
            technical_metadata[key] = model[key]
    if "quality" in case:
        technical_metadata["quality"] = case["quality"]
    if "transform" in case:
        technical_metadata["transform"] = case["transform"]

    return OnnxCaseRun.model_validate(
        {
            "run_id": run_id,
            "study_id": study_id,
            "model_id": model_id,
            "model_version": model.get("model_version"),
            "findings": findings,
            "hypothesis_map": {
                str(key): [str(item) for item in values]
                for key, values in (hypothesis_map or {}).items()
            },
            "location_by_label": {
                str(key): dict(value)
                for key, value in (location_by_label or {}).items()
            },
            "severity_by_label": dict(severity_by_label or {}),
            "metadata": technical_metadata,
        }
    )
