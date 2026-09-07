from __future__ import annotations

import pytest

from app.domain.onnx_inference_engine import ModelContractError
from app.domain.onnx_parity import compare_inference_results


MODEL = {
    "model_id": "fixture-xray",
    "model_version": "1.0.0",
    "model_sha256": "a" * 64,
    "tensor_contract": "xray-core-v2/nchw-f32-0-1",
}


def _result(a: float, b: float):
    return {
        "model": dict(MODEL),
        "batch_size": 1,
        "cases": [
            {
                "scores": [
                    {"label": "finding_a", "score": a},
                    {"label": "finding_b", "score": b},
                ]
            }
        ],
    }


def test_parity_passes_within_tolerance() -> None:
    report = compare_inference_results(
        _result(0.123456, 0.987654),
        _result(0.123457, 0.987653),
        absolute_tolerance=1e-5,
    )
    assert report.passed is True
    assert report.compared_scores == 2
    assert report.max_absolute_error < 1e-5


def test_parity_detects_score_drift() -> None:
    report = compare_inference_results(
        _result(0.1, 0.9),
        _result(0.1, 0.85),
        absolute_tolerance=1e-5,
    )
    assert report.passed is False
    assert report.max_absolute_error == pytest.approx(0.05)


def test_parity_rejects_model_identity_mismatch() -> None:
    native = _result(0.1, 0.9)
    native["model"]["model_sha256"] = "b" * 64
    with pytest.raises(ModelContractError):
        compare_inference_results(_result(0.1, 0.9), native)


def test_parity_rejects_label_mismatch() -> None:
    native = _result(0.1, 0.9)
    native["cases"][0]["scores"][1]["label"] = "different"
    with pytest.raises(ModelContractError):
        compare_inference_results(_result(0.1, 0.9), native)
