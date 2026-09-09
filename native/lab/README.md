# MediCore Native Lab v1

C++20 laboratory normalization, source validation and direct laboratory-to-AI dispatch for the Astra-first lab pipeline.

## Runtime flow

```text
PDF / PNG / JPEG / WEBP (one or many files)
        -> OpenAI multimodal extraction model (OPENAI_LAB_MODEL)
        -> strict structured lab JSON
        -> medicore_lab C++ core
             - normalization
             - source/reference validation
             - native safety classification
             - deduplication / plausibility gates
        -> medicore_lab_ai C++ HTTPS transport
        -> clinical AI receives ALL processed lab rows
             - independently returns NORMAL / LOW / HIGH / UNDETERMINED
             - produces clinical synthesis
        -> C++ / AI disagreement => physician review
        -> PostgreSQL LabReport / LabResult
        -> MediCore UI
```

The first multimodal model reads the original documents. The native C++ lab core then validates and normalizes every extracted row before the second AI hop. When native HTTP support is compiled, the second provider request is sent directly from C++ through `medicore_lab_ai`; the Python OpenAI client is retained only as a resilience fallback.

The native deterministic status is deliberately not included as the AI's answer input. The AI receives the measured value, unit and source-report reference information and classifies each row independently. If the AI and native C++ classification disagree, MediCore marks the row for physician/source review rather than silently trusting either side.

## Build

From `app/backend` after installing `requirements.txt`:

```bash
bash scripts/build_native_lab.sh
```

CMake builds and installs these modules:

- `medicore_lab` — normalization, validation, deterministic rules and metrics
- `medicore_lab_ext` — reference parsing, conversions and plausibility extensions
- `medicore_lab_ai` — direct native C++ laboratory-to-AI request builder and HTTPS transport

Direct native HTTPS uses libcurl. CMake enables it automatically when libcurl development headers are available; otherwise the module still builds with `HTTP_AVAILABLE=false` and MediCore falls back to the established Python clinical AI service.

To require the native HTTP build explicitly:

```bash
cmake -S native/lab -B native/lab/build -DMEDICORE_ENABLE_AI_HTTP=ON
cmake --build native/lab/build --parallel 2
```

## Environment

```text
OPENAI_API_KEY=...
OPENAI_LAB_MODEL=gpt-6-astra
OPENAI_LAB_CLINICAL_MODEL=gpt-5.6-luna
OPENAI_LAB_EXTRACTION_ENABLED=true
NATIVE_LAB_REQUIRED=true
```

The extraction and clinical models remain independently configurable. The C++ direct AI transport uses the configured clinical model for the second hop.

## HTTP endpoints

- `POST /api/v1/lab-analysis/upload` — one PDF/image, backwards compatible field name `file`.
- `POST /api/v1/lab-analysis/upload-direct` — stable frontend single-file route.
- `POST /api/v1/lab-analysis/upload-batch` — multiple PDF/images in one logical case, multipart field name `files`.

The batch request sends all source files in one logical extraction request and preserves source file/page provenance on each stored lab row. All resulting lab rows are then forwarded through the native lab-to-AI path when that transport is available.
