# Radiology multi-model review

MediCore can run multiple independent multimodal providers over the same uploaded medical image and expose agreement/disagreement as physician-reviewable metadata.

## Safety boundary

This feature produces **visual observations and candidate differentials**, not an autonomous final diagnosis. Model agreement is not clinical validation. The UI keeps physician/radiologist review explicit, and single-frame CT/MR screenshots are not treated as complete studies.

## Providers

1. Anthropic / Claude — existing `ANTHROPIC_API_KEY` plus `CLAUDE_VISION_MODEL` (or existing Claude model fallback).
2. OpenAI Responses API — `OPENAI_API_KEY`, optional `OPENAI_VISION_MODEL` (default `gpt-5.6-terra`).
3. Google Gemini — `GEMINI_API_KEY`, optional `GEMINI_VISION_MODEL` (default `gemini-3.8-flash`).
4. Optional OpenAI-compatible provider — `RADIOLOGY_FOURTH_API_KEY`, `RADIOLOGY_FOURTH_BASE_URL`, `RADIOLOGY_FOURTH_MODEL`.

Multi-provider transmission is disabled by default. Enable it explicitly only after the privacy/data-processing requirements for each configured provider have been reviewed:

```env
RADIOLOGY_MULTI_MODEL_ENABLED=true
RADIOLOGY_MULTI_MODEL_TIMEOUT_SECONDS=45

OPENAI_API_KEY=...
OPENAI_VISION_MODEL=gpt-5.6-terra

GEMINI_API_KEY=...
GEMINI_VISION_MODEL=gemini-3.8-flash

# Optional fourth provider (base URL should include its /v1 prefix when required)
RADIOLOGY_FOURTH_API_KEY=...
RADIOLOGY_FOURTH_BASE_URL=https://provider.example/v1
RADIOLOGY_FOURTH_MODEL=...
```

## Consensus behavior

Each available provider receives the image independently and returns structured observations, up to five candidate differentials, critical-review flags, and limitations. Candidate labels are grouped conservatively. A candidate is promoted to the shared consensus only when at least two independent configured providers produce sufficiently similar labels. One-provider candidates remain visible separately as model disagreement / single-model suggestions.

The saved report metadata includes:

- `providers_succeeded`
- `providers_failed`
- `provider_count`
- `provider_opinions`
- `consensus_differential`
- `single_model_differential`
- `critical_review_flags`
- `model_disagreement_present`
- `consensus_is_not_validation`

The radiology UI shows model count, provider names, shared candidate differentials, supporting observations, priority review flags, and non-consensus candidates.
