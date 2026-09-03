# MediCore Vision Engine — X-Ray Core v2 + ONNX + DICOM Engine

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

## DICOM Engine v1

The native DICOM path uses DCMTK and provides:

- in-memory `.dcm` parsing without copying patient identifiers into engine output;
- technical metadata for Rows/Columns/Frames, bit depth, pixel representation,
  modality, photometric interpretation, rescale values, window values, and
  transfer syntax;
- native uncompressed 8-bit and 16-bit monochrome Pixel Data decoding;
- correct `BitsStored` / `HighBit` extraction and signed-pixel sign extension;
- `RescaleSlope` + `RescaleIntercept` modality transform before display windowing;
- explicit window override, DICOM WindowCenter/WindowWidth, then robust 0.5/99.5
  percentile fallback in that priority order;
- DICOM-style linear window conversion into a versioned uint8 frame contract:
  `dicom-frame-v1/grayscale-u8`;
- `MONOCHROME1` polarity inversion and `MONOCHROME2` preservation;
- multi-frame selection with bounds checks;
- safe CR/DX-only conversion into the X-Ray Core v2 tensor contract;
- fail-closed handling for compressed/encapsulated Pixel Data in this milestone.

Compressed transfer syntaxes are deliberately reported in metadata but are not
silently decoded. Codec registration/validation can be added as a later extension
without changing the frame/tensor contracts.

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
JPG/PNG/WEBP -----------------> C++ X-Ray Core v2 -----+
                                                       |
DICOM -> DCMTK -> rescale/window/MONOCHROME -> CR/DX -+-> NCHW float32 [0,1]
                                                       |      + transform metadata
                                                       v
                                      C++ contract guard + Python ONNX Runtime
                                                       |
                                      raw finding scores + model identity
                                                       |
                                      future Vision Post-processing
                                                       |
                                      clinical fusion / physician review
```

CT DICOM frames can be decoded/windowed by the DICOM Engine, but the CR/DX X-Ray
classifier path rejects CT rather than feeding it into a model trained for X-rays.
A future CT model should define its own model-input contract.

## Build and native tests

```bash
sudo apt-get install cmake g++ libopencv-dev pybind11-dev libdcmtk-dev
cmake -S native/vision -B native/vision/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/vision/build --parallel 2
ctest --test-dir native/vision/build --output-on-failure
```

## Python DICOM API

```python
from app.domain.native_vision_engine import (
    inspect_dicom,
    prepare_dicom_frame,
    prepare_dicom_xray_tensor,
)

meta = inspect_dicom(dicom_bytes)
frame = prepare_dicom_frame(dicom_bytes, frame_index=0)

# Only CR/DX modalities are permitted into the X-Ray classifier contract.
prepared = prepare_dicom_xray_tensor(
    dicom_bytes,
    target_width=1024,
    target_height=1024,
)
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

These milestones implement technical image processing and model execution
infrastructure, not clinical validation of a particular model. The selected model,
labels, thresholds, training preprocessing, target population, and intended use
still need independent validation before clinical deployment.

## Next milestone

**Vision Post-processing**: segmentation masks, bounding boxes, heatmaps, and
measurements mapped back through saved resize/letterbox transform metadata.
