from __future__ import annotations

import json
import os
import sys

from app.domain.onnx_parity import run_real_model_parity


def main() -> int:
    model_path = os.getenv("XRAY_ONNX_MODEL_PATH", "").strip()
    manifest_path = os.getenv("XRAY_ONNX_MANIFEST_PATH", "").strip()
    if not model_path or not manifest_path:
        print("XRAY_ONNX_MODEL_PATH and XRAY_ONNX_MANIFEST_PATH are required.", file=sys.stderr)
        return 2

    tolerance = float(os.getenv("MEDICORE_NATIVE_ONNX_PARITY_TOLERANCE", "1e-5"))
    batch_size = int(os.getenv("MEDICORE_NATIVE_ONNX_PARITY_BATCH", "2"))
    report = run_real_model_parity(
        model_path,
        manifest_path,
        absolute_tolerance=tolerance,
        batch_size=batch_size,
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
