# MediCore Vision Engine — X-Ray Core v2 + ONNX Contract

This directory contains MediCore's performance-oriented C++ medical-image core.
Python owns ONNX Runtime orchestration, clinical fusion, uncertainty, and the
physician-review workflow.

## Native X-Ray Core v2

The C++ layer provides:

- JPG/PNG/WEBP decoding through OpenCV;
- deterministic 1/3/4-channel -> grayscale conversion;
- robust percentile normalization and technical image-quality metrics;
- aspect-ratio-preserving resize + letterbox transform metadata;
- versioned model-input tensor contract:
  `xray-core-v2/nchw-f32-0-1` = `[1,1,H,W]`, float32, range `[0,1]`;
- native ONNX input/output contract guards used before model execution;
- deterministic CTest coverage.

## ONNX Inference Engine

The backend ONNX layer (`app/domain/onnx_inference_engine.py`) adds:

- JSON model manifests with schema version, model ID and semver;
- mandatory SHA-256 pinning of the exact `.onnx` binary;
- input name/shape/dtype and output class-count validation;
- execution-provider selection with CPU fallback;
- dynamic-batch inference and safe micro-batching for models fixed at batch=1;
- logits -> sigmoid score conversion or bounded probability passthrough;
- per-label thresholds without promoting model scores to autonomous diagnoses;
- preservation of X-Ray Core transform/quality metadata for later heatmaps,
  bounding boxes, and clinical fusion.

Model binaries are deliberately ignored by git (`*.onnx`). A validated model and
matching manifest must be supplied at deployment time.

## Architecture

```text
encoded image
   |
C++ X-Ray Core v2
   |  grayscale / quality / normalize / letterbox
   v
NCHW float32 [0,1] + transform metadata
   |
C++ contract guard + Python ONNX Runtime
   |
raw finding scores + model/version/hash identity
   |
future Vision Post-processing
   |
Python clinical fusion / safety / physician review
```

## Build and native tests

```bash
sudo apt-get install cmake g++ libopencv-dev pybind11-dev
cmake -S native/vision -B native/vision/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/vision/build --parallel 2
ctest --test-dir native/vision/build --output-on-failure
```

## Model configuration

Start from `app/backend/models/xray/manifest.example.json`. Replace every example
field with the selected model's real contract and SHA-256. Then configure the
backend environment:

```text
XRAY_ONNX_ENABLED=true
XRAY_ONNX_MODEL_PATH=/secure/models/chest-xray.onnx
XRAY_ONNX_MANIFEST_PATH=/secure/models/chest-xray.manifest.json
```

The engine remains disabled unless `XRAY_ONNX_ENABLED=true` is explicitly set.
If the model hash, tensor contract, I/O shape, output width, or optional embedded
MediCore metadata does not match, loading/inference fails closed instead of
silently reshaping or guessing.

## Important boundary

This milestone implements model execution infrastructure, not a claim that a
particular model is clinically validated. The selected model, labels, thresholds,
training preprocessing, target population, and intended use still need their own
validation before clinical deployment.

## Next milestone

**DICOM Engine**: pixel pipeline, rescale/modality transform, bit-depth handling,
MONOCHROME1/2 behavior, and modality-specific window preparation before the X-Ray
Core/ONNX path. After that, Vision Post-processing will map model heatmaps/masks/
boxes back through the saved transform metadata.
