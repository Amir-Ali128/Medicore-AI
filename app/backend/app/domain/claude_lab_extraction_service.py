"""ClaudeLabExtractionService.

Uses Claude's vision/PDF capability ONLY to extract structured lab values from an
uploaded image or PDF. It never diagnoses, never interprets medical meaning, and
never recommends treatment. All downstream classification stays deterministic in
the existing AnalysisPipeline.

The anthropic client is imported lazily so the rest of the app can run without
the `anthropic` package installed until extraction is actually used.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import ValidationError

from app.schemas.extraction import LabExtractionResult

SUPPORTED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/webp", "application/pdf"}
)

_MAX_TOKENS = 8192

_SYSTEM_PROMPT = (
    "You extract structured laboratory values from a lab report file. "
    "You are not a doctor. You must not diagnose, must not interpret medical "
    "meaning, and must not recommend treatment. Return only valid JSON."
)

_USER_PROMPT = (
    "Extract the laboratory test values from this document.\n"
    "Rules:\n"
    "- Return ONLY valid JSON, no prose, no markdown code fences.\n"
    "- Do not diagnose. Do not interpret. Do not recommend treatment.\n"
    "- Extract only what is visibly present in the document.\n"
    "- Do not invent missing values.\n"
    "- Preserve original raw strings where possible in raw_value.\n"
    "- Set normalized_value only when the value is clearly numeric.\n"
    "- Use ISO format YYYY-MM-DD for measured_at.\n"
    "- If a field is unclear, use null and set needs_review=true for that item.\n"
    "Return JSON in EXACTLY this schema:\n"
    "{\n"
    '  "values": [\n'
    "    {\n"
    '      "raw_parameter_name": string | null,\n'
    '      "raw_value": string | null,\n'
    '      "normalized_value": number | null,\n'
    '      "unit": string | null,\n'
    '      "extracted_reference_min": number | null,\n'
    '      "extracted_reference_max": number | null,\n'
    '      "extracted_unit": string | null,\n'
    '      "measured_at": string | null,\n'
    '      "needs_review": boolean,\n'
    '      "extraction_note": string | null\n'
    "    }\n"
    "  ],\n"
    '  "overall_needs_review": boolean,\n'
    '  "extraction_confidence": number | null,\n'
    '  "source_file_name": string | null,\n'
    '  "warnings": [string]\n'
    "}"
)


class ClaudeLabExtractionService:
    def __init__(self, *, api_key: str | None, model: str | None) -> None:
        if not model:
            raise ValueError("CLAUDE_EXTRACTION_MODEL is not configured.")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")

        # Lazy import: only require the anthropic package when the service runs.
        from anthropic import AsyncAnthropic

        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)

    async def extract_from_bytes(
        self, file_bytes: bytes, file_name: str | None, content_type: str | None
    ) -> LabExtractionResult:
        if content_type not in SUPPORTED_CONTENT_TYPES:
            raise ValueError(f"Unsupported file type: {content_type}")

        encoded = base64.standard_b64encode(file_bytes).decode("ascii")
        file_block = self._build_file_block(content_type, encoded)

        response = await self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [file_block, {"type": "text", "text": _USER_PROMPT}],
                }
            ],
        )

        text = self._collect_text(response)
        return self._parse_result(text, file_name)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _build_file_block(content_type: str, encoded: str) -> dict[str, Any]:
        if content_type == "application/pdf":
            return {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": encoded,
                },
            }
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": content_type,
                "data": encoded,
            },
        }

    @staticmethod
    def _collect_text(response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts).strip()

    def _parse_result(
        self, text: str, file_name: str | None
    ) -> LabExtractionResult:
        payload = self._safe_json(text)
        if payload is None:
            return self._parse_failure(
                file_name, "Failed to parse extraction output as JSON."
            )
        try:
            result = LabExtractionResult.model_validate(payload)
        except ValidationError:
            return self._parse_failure(
                file_name, "Extraction output did not match the expected schema."
            )

        if result.source_file_name is None and file_name is not None:
            result = result.model_copy(update={"source_file_name": file_name})
        return result

    @staticmethod
    def _safe_json(text: str) -> Any | None:
        if not text:
            return None
        candidate = text.strip()
        # Tolerate accidental markdown fences or surrounding prose.
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None
        try:
            return json.loads(candidate[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None

    @staticmethod
    def _parse_failure(file_name: str | None, warning: str) -> LabExtractionResult:
        return LabExtractionResult(
            values=[],
            overall_needs_review=True,
            extraction_confidence=0.0,
            source_file_name=file_name,
            warnings=[warning],
        )
