# MediCore Vision Engine

This directory contains the performance-oriented C++ layer for medical image
processing. The Python backend remains the orchestration and clinical layer.

## Current scope

The first iteration intentionally contains **no disease diagnosis logic**. It
provides:

- encoded JPG/PNG/WEBP decoding through OpenCV;
- technical image metadata inspection;
- conservative chest X-ray grayscale normalization and downscaling;
- Python bindings through pybind11.

The preprocessing path avoids aggressive clinical enhancement by default. Any
future windowing, CLAHE, segmentation, or model-specific normalization should
match a validated model's training pipeline.

## Architecture

```text
React / TypeScript
        |
FastAPI / Python
        |
Python clinical / safety layer
        |
pybind11
        |
MediCore Vision Engine (C++)
        |
OpenCV -> future validated ONNX/TensorRT inference
```

## Build

Ubuntu/Debian example:

```bash
sudo apt-get install cmake g++ libopencv-dev pybind11-dev
cmake -S native/vision -B native/vision/build
cmake --build native/vision/build --config Release
```

Add the produced module directory to `PYTHONPATH` (or package/install the module)
so the backend can import `medicore_vision`.

## Python API

```python
from app.domain.native_vision_engine import (
    inspect_image,
    preprocess_chest_xray,
)

metadata = inspect_image(image_bytes)
normalized = preprocess_chest_xray(image_bytes)
```

## Next milestones

1. Add native build verification to CI.
2. Connect native metadata/preprocessing to the radiology upload pipeline as an
   optional accelerator with Python fallback.
3. Define a versioned model contract for chest X-ray multi-label findings.
4. Add ONNX Runtime only after a validated model and its exact preprocessing
   specification are selected.
5. Keep disease-level interpretation, uncertainty handling, safety messaging,
   and physician-review requirements in Python.
