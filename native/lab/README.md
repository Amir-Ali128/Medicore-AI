# MediCore Native Lab v1

C++20 laboratory normalization and deterministic reference-range classification for the Astra-first lab pipeline.

## Runtime flow

```text
PDF / PNG / JPEG / WEBP (one or many files)
        -> OpenAI multimodal model (configured by OPENAI_LAB_MODEL)
        -> strict structured lab JSON
        -> medicore_lab C++ core
        -> PostgreSQL LabReport / LabResult
```

The model reads the original documents directly. The C++ layer does not perform OCR and does not make diagnoses; it validates/normalizes extracted rows, classifies numeric values against source-report reference bounds, suppresses exact overlapping duplicates, and marks ambiguous rows for physician review.

## Build

From `app/backend` after installing `requirements.txt`:

```bash
bash scripts/build_native_lab.sh
```

The script configures/builds the CMake target, runs the native tests, and installs the `medicore_lab` extension into `app/backend` so the FastAPI process can import it normally.

## Environment

```text
OPENAI_API_KEY=...
OPENAI_LAB_MODEL=gpt-6-astra
OPENAI_LAB_EXTRACTION_ENABLED=true
NATIVE_LAB_REQUIRED=true
```

`OPENAI_LAB_MODEL` is intentionally configurable so deployments can use any compatible multimodal Responses API model available to the project without code changes.

## HTTP endpoints

- `POST /api/v1/lab-analysis/upload` — one PDF/image, backwards compatible field name `file`.
- `POST /api/v1/lab-analysis/upload-batch` — multiple PDF/images in one logical case, multipart field name `files`.

The batch request sends all source files in a single model request and preserves source file/page provenance on each stored lab row.
