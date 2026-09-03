# MediCore Vision Engine — X-Ray Core v2

This directory contains MediCore's performance-oriented C++ medical-image core.
Python remains responsible for orchestration, clinical fusion, uncertainty, and
physician-review workflow.

## X-Ray Core v2 scope

The native layer now provides:

- JPG/PNG/WEBP decoding through OpenCV;
- deterministic 1/3/4-channel -> grayscale conversion;
- 8/16-bit-safe conversion into an 8-bit technical working image;
- robust 0.5/99.5 percentile normalization;
- technical quality metrics: normalized mean/stddev, p01/p99, robust dynamic
  range, clipping ratios, entropy, and normalized Laplacian variance;
- explicitly heuristic quality flags such as low contrast, near-uniform image,
  heavy clipping, small input, and low-sharpness heuristic;
- aspect-ratio-preserving resize + letterbox geometry metadata;
- versioned model-input tensor contract:
  `xray-core-v2/nchw-f32-0-1` = `[1,1,H,W]`, float32, value range `[0,1]`;
- pybind11 Python bindings;
- deterministic C++ CTest coverage plus Python adapter contract tests.

None of the quality thresholds are diagnostic or a substitute for radiographic
quality-control validation. Disease inference belongs to the next ONNX stage and
must match the selected model's exact training preprocessing.

## Architecture

```text
encoded image
   |
OpenCV decode
   |
grayscale -> technical quality metrics
   |
robust normalization -> resize/letterbox
   |
NCHW float32 [0,1] tensor + transform metadata
   |
future ONNX inference engine
   |
Python clinical fusion / safety / physician review
```

The transform metadata deliberately preserves resize scale and padding so later
bounding boxes, masks, and heatmaps can be mapped back to original-image
coordinates without guessing.

## Build and tests

Ubuntu/Debian example:

```bash
sudo apt-get install cmake g++ libopencv-dev pybind11-dev
cmake -S native/vision -B native/vision/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/vision/build --parallel 2
ctest --test-dir native/vision/build --output-on-failure
```

## Python API

```python
from app.domain.native_vision_engine import (
    inspect_xray_quality,
    prepare_xray_tensor,
)

quality = inspect_xray_quality(image_bytes)
prepared = prepare_xray_tensor(
    image_bytes,
    target_width=1024,
    target_height=1024,
)

assert prepared["contract_version"] == "xray-core-v2/nchw-f32-0-1"
tensor = prepared["tensor"]       # NumPy float32 [1,1,1024,1024]
transform = prepared["transform"] # scale + letterbox padding
```

## Next milestone

**ONNX Inference Engine**: versioned model loader, input/output contract
validation, batch inference, model metadata/version checks, and isolated failure
handling. The ONNX stage should consume this tensor contract rather than duplicate
image preprocessing.
