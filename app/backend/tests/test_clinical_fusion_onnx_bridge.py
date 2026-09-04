from __future__ import annotations

import pytest

from app.domain.clinical_fusion_onnx_bridge import (
    ClinicalFusionOnnxBridgeError,
    onnx_case_run_from_inference_result,
)


def _result():
    return {
        "model": {
            "model_id": "chest-xray-net",
            "model_version": "1.2.3",
            "model_sha256": "a" * 64,
            "tensor_contract": "xray-core-v2/nchw-f32-0-1",
            "input_name": "image",
            "input_shape": [-1, 1, 1024, 1024],
            "output_name": "scores",
            "output_kind": "probabilities",
            "providers": ["CPUExecutionProvider"],
        },
        "batch_size": 2,
        "cases": [
            {
                "scores": [
                    {
                        "label": "pneumothorax",
                        "score": 0.91,
                        "threshold": 0.65,
                        "above_threshold": True,
                    },
                    {
                        "label": "pleural_effusion",
                        "score": 0.10,
                        "threshold": 0.50,
                        "above_threshold": False,
                    },
                ],
                "quality": {"technical_flags": []},
                "transform": {"pad_top": 20, "pad_left": 0},
            },
            {
                "scores": [
                    {
                        "label": "pneumothorax",
                        "score": 0.20,
                        "threshold": 0.65,
                        "above_threshold": False,
                    }
                ]
            },
        ],
    }


def test_bridge_preserves_real_onnx_score_contract_and_model_identity() -> None:
    run = onnx_case_run_from_inference_result(
        _result(),
        run_id="run-1",
        study_id="cxr-1",
        case_index=0,
        hypothesis_map={"pneumothorax": ["pneumothorax"]},
        location_by_label={"pneumothorax": {"bbox_xyxy": [10, 20, 30, 40]}},
    )

    assert run.model_id == "chest-xray-net"
    assert run.model_version == "1.2.3"
    assert len(run.findings) == 2
    assert run.findings[0].score == pytest.approx(0.91)
    assert run.hypothesis_map["pneumothorax"] == ["pneumothorax"]
    assert run.location_by_label["pneumothorax"]["bbox_xyxy"] == [10, 20, 30, 40]
    assert run.metadata["model_sha256"] == "a" * 64
    assert run.metadata["tensor_contract"] == "xray-core-v2/nchw-f32-0-1"
    assert run.metadata["transform"]["pad_top"] == 20


def test_bridge_selects_requested_batch_case() -> None:
    run = onnx_case_run_from_inference_result(
        _result(),
        run_id="run-2",
        study_id="cxr-2",
        case_index=1,
        hypothesis_map={"pneumothorax": ["pneumothorax"]},
    )
    assert len(run.findings) == 1
    assert run.findings[0].above_threshold is False
    assert run.metadata["case_index"] == 1


def test_bridge_does_not_infer_hypothesis_map_from_model_label() -> None:
    run = onnx_case_run_from_inference_result(
        _result(),
        run_id="run-3",
        study_id="cxr-3",
    )
    assert run.hypothesis_map == {}


def test_bridge_rejects_missing_model_identity() -> None:
    result = _result()
    result["model"]["model_id"] = ""
    with pytest.raises(ClinicalFusionOnnxBridgeError, match="model_id"):
        onnx_case_run_from_inference_result(
            result,
            run_id="run-bad",
            study_id="cxr-bad",
        )


def test_bridge_rejects_out_of_range_case_index() -> None:
    with pytest.raises(ClinicalFusionOnnxBridgeError, match="case_index"):
        onnx_case_run_from_inference_result(
            _result(),
            run_id="run-bad",
            study_id="cxr-bad",
            case_index=99,
        )
