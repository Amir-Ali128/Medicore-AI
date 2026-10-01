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

from app.infrastructure.runtime_resilience import (
    AsyncDependencyGuard,
    get_anthropic_guard,
)
from app.schemas.extraction import ExtractedLabValue, LabExtractionResult

SUPPORTED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "image/webp", "application/pdf"}
)

_MAX_TOKENS = 8192

_SYSTEM_PROMPT = (
    "You extract structured laboratory values from a lab report file. "
    "You are not a doctor. You must not diagnose, must not interpret medical "
    "meaning, and must not recommend treatment. Return only valid JSON."
)

_IMAGE_AUDIT_PROMPT = (
    "\nIMAGE COMPLETENESS AUDIT:\n"
    "- This may be a photographed teaching/synthetic case sheet rather than a conventional laboratory report.\n"
    "- Re-scan the entire visible table row by row from the first parameter to the last parameter.\n"
    "- Return ALL visible parameter rows even when reference_min/reference_max and measured_at are absent.\n"
    "- If a column explicitly says Yüksek, Düşük or Normal, copy it to source_flag.\n"
    "- Do not stop after the first few rows. Do not summarize the table.\n"
)

_USER_PROMPT = (
    "Extract the laboratory test values from this document.\n"
    "Rules:\n"
    "- Return ONLY valid JSON, no prose, no markdown code fences.\n"
    "- Do not diagnose. Do not interpret. Do not recommend treatment.\n"
    "- Extract only what is visibly present in the document.\n"
    "- Do not invent missing values.\n"
    "- Count visible laboratory rows independently before transcription; return visible_row_count, or null if the count is unclear.\n"
    "- Copy the printed reference cell exactly into reference_text, including inequalities and textual references.\n"
    "- IMPORTANT: scan the laboratory table from top to bottom and extract EVERY visible parameter row, not only abnormal rows and not only rows with a reference range.\n"
    "- Rows that have only Parametre + Değer, or Parametre + Değer + explicit status (for example Beklenen durum: Yüksek/Düşük/Normal), are valid laboratory rows and MUST be returned.\n"
    "- Preserve derived rows exactly when printed, including ratios and calculated values such as BUN/Kreatinin, Anyon Açığı, Kalsiyum/Fosfor Oranı and GFR.\n"
    "- Headings, explanatory paragraphs, hypotheses and recommendations are NOT lab rows.\n"
    "- Preserve original raw strings where possible in raw_value.\n"
    "- Set normalized_value only when the value is clearly numeric.\n"
    "- Use ISO format YYYY-MM-DD for measured_at.\n"
    "- If the document explicitly labels a row as high/low/normal (for example Yüksek, Düşük, Normal, H, L, N), copy that label exactly into source_flag. Do not infer source_flag when it is not explicitly printed.\n"
    "- If a field is unclear, use null and set needs_review=true for that item.\n"
    "Return JSON in EXACTLY this schema:\n"
    "{\n"
    '  "visible_row_count": number | null,\n'
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
    '      "extraction_note": string | null,\n'
    '      "source_flag": string | null,\n'
    '      "reference_text": string | null\n'
    "    }\n"
    "  ],\n"
    '  "overall_needs_review": boolean,\n'
    '  "extraction_confidence": number | null,\n'
    '  "source_file_name": string | null,\n'
    '  "warnings": [string]\n'
    "}"
)


class ClaudeLabExtractionService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        guard: AsyncDependencyGuard | None = None,
    ) -> None:
        if not model:
            raise ValueError("CLAUDE_EXTRACTION_MODEL is not configured.")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")

        # Lazy import: only require the anthropic package when the service runs.
        from anthropic import AsyncAnthropic

        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)
        self._guard = guard or get_anthropic_guard("lab-extraction")

    async def extract_from_bytes(
        self, file_bytes: bytes, file_name: str | None, content_type: str | None
    ) -> LabExtractionResult:
        if content_type not in SUPPORTED_CONTENT_TYPES:
            raise ValueError(f"Unsupported file type: {content_type}")

        encoded = base64.standard_b64encode(file_bytes).decode("ascii")
        file_block = self._build_file_block(content_type, encoded)

        async def run(prompt: str) -> LabExtractionResult:
            response = await self._guard.call(
                lambda: self._client.messages.create(
                    model=self._model,
                    max_tokens=_MAX_TOKENS,
                    system=_SYSTEM_PROMPT,
                    messages=[
                        {
                            "role": "user",
                            "content": [file_block, {"type": "text", "text": prompt}],
                        }
                    ],
                )
            )
            text = self._collect_text(response)
            return self._parse_result(text, file_name)

        first = await run(
            _USER_PROMPT + (_IMAGE_AUDIT_PROMPT if content_type and content_type.startswith("image/") else "")
        )

        # Photographed tables are the most common place for models to stop early.
        # If only a small subset was returned, run one explicit completeness audit
        # and merge unique rows rather than silently accepting a truncated table.
        if content_type and content_type.startswith("image/") and (
            len(first.values) <= 8 or (first.visible_row_count is not None and first.visible_row_count > len(first.values))
        ):
            try:
                second = await run(_USER_PROMPT + _IMAGE_AUDIT_PROMPT + (
                "\nThe previous extraction may have been incomplete. Perform a fresh full-table pass. "
                "Return every visible row exactly once."
                ))
            except Exception:
                return first.model_copy(update={"overall_needs_review": True, "warnings": [*first.warnings, "image_completeness_audit_failed"]})

            merged = []
            seen = set()
            for item in [*first.values, *second.values]:
                key = (
                    (item.raw_parameter_name or "").strip().casefold(),
                    (item.raw_value or "").strip().casefold(),
                    (item.unit or item.extracted_unit or "").strip().casefold(),
                    str(item.measured_at or ""),
                    str(item.reference_text or ""),
                    str(item.extracted_reference_min),
                    str(item.extracted_reference_max),
                    str(item.source_flag or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)

            first = first.model_copy(
                update={
                    "values": merged,
                    "visible_row_count": max((n for n in (first.visible_row_count, second.visible_row_count) if n is not None), default=None),
                    "overall_needs_review": first.overall_needs_review or second.overall_needs_review,
                    "extraction_confidence": max(
                        first.extraction_confidence or 0.0,
                        second.extraction_confidence or 0.0,
                    ),
                    "warnings": list(dict.fromkeys([
                        *first.warnings,
                        *second.warnings,
                        "image_full_table_audit_retry",
                    ])),
                }
            )

        return first

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
            # A malformed optional date/number must not discard the entire table.
            # Keep source strings, remove only invalid cells, and require review.
            if not isinstance(payload, dict) or not isinstance(payload.get('values'), list):
                return self._parse_failure(file_name, 'Extraction output did not match the expected schema.')
            values = []
            repaired = False
            for row in payload['values']:
                if not isinstance(row, dict):
                    repaired = True
                    continue
                try:
                    values.append(ExtractedLabValue.model_validate(row))
                except ValidationError as exc:
                    safe = dict(row)
                    for error in exc.errors(include_input=False):
                        safe.pop(error['loc'][0], None)
                    safe.update(needs_review=True, extraction_note='Invalid extracted cells removed; verify against source.')
                    values.append(ExtractedLabValue.model_validate(safe))
                    repaired = True
            # Validate metadata separately; discard malformed metadata, not rows.
            metadata = {**payload, 'values': values}
            try:
                result = LabExtractionResult.model_validate(metadata)
            except ValidationError as exc:
                for error in exc.errors(include_input=False):
                    metadata.pop(error['loc'][0], None)
                result = LabExtractionResult.model_validate(metadata)
                repaired = True
            if repaired:
                result = result.model_copy(update={
                    'overall_needs_review': True,
                    'warnings': [*result.warnings, 'extraction_invalid_cells_review'],
                })

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
