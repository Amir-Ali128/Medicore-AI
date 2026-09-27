"""Claude-backed clinical fusion report service for MediCore.

This service combines structured laboratory extraction, clinician-entered context,
and a radiology/imaging report into a concise physician-facing CDSS report.
It never persists a final diagnosis and never prescribes treatment.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.infrastructure.runtime_resilience import (
    AsyncDependencyGuard,
    get_anthropic_guard,
)
from app.schemas.cdss_report import CDSSReport, ClinicalContext
from app.schemas.extraction import LabExtractionResult

_MAX_TOKENS = 6000

_SYSTEM_PROMPT = """
You are the clinical decision-support report writer inside MediCore AI.

Your audience is a licensed physician. Produce a concise, professional,
doctor-style clinical decision-support report by integrating ONLY:
1) the supplied clinical context,
2) the supplied structured laboratory extraction,
3) the supplied imaging/radiology report.

Mandatory rules:
- Never invent symptoms, history, vital signs, laboratory values, or imaging findings.
- Never state a definitive diagnosis as established fact.
- Prefer cautious clinical wording such as:
  "bulgular ... ile uyumlu olabilir",
  "... ön planda düşünülebilir",
  "ayırıcı tanıda değerlendirilebilir",
  "klinik korelasyon önerilir".
- Do not prescribe medications, doses, durations, or treatment regimens.
- You may recommend physician evaluation, monitoring, confirmatory/repeat tests,
  additional investigation, or specialist review when supported by the input.
- Explicitly state when evidence is incomplete, uncertain, or contradictory.
- Do not output numeric disease probabilities.
- Keep the style suitable for a physician-facing medical record/CDSS workflow.
- Return ONLY valid JSON. No markdown and no code fences.

Return exactly this structure:
{
  "report_title": "KLİNİK KARAR DESTEK RAPORU",
  "clinical_information": "string",
  "laboratory_findings": ["string"],
  "imaging_findings": "string",
  "clinical_assessment": "string",
  "differential_diagnosis": [
    {
      "condition": "string",
      "rationale": "string",
      "likelihood_label": "low|moderate|high|uncertain"
    }
  ],
  "attention_points": ["string"],
  "recommended_clinical_evaluation": ["string"],
  "conclusion": "string",
  "limitations": ["string"],
  "physician_review_required": true,
  "disclaimer": "Bu çıktı klinik karar desteği içindir; kesin tanı ve tedavi kararı yetkili hekim tarafından verilmelidir."
}
""".strip()


class ClaudeCDSSReportService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        guard: AsyncDependencyGuard | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")
        if not model:
            raise ValueError("CLAUDE_CDSS_MODEL is not configured.")

        from anthropic import AsyncAnthropic

        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)
        self._guard = guard or get_anthropic_guard("cdss-report")

    async def generate_report(
        self,
        *,
        clinical_context: ClinicalContext,
        lab_extraction: LabExtractionResult,
        imaging_report_text: str,
    ) -> CDSSReport:
        source_payload = {
            "clinical_context": clinical_context.model_dump(mode="json"),
            "laboratory_extraction": lab_extraction.model_dump(mode="json"),
            "imaging_report": imaging_report_text,
        }

        response = await self._guard.call(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Aşağıdaki kaynakları birlikte değerlendir ve "
                                    "hekim incelemesine uygun CDSS raporu oluştur.\n\n"
                                    + json.dumps(
                                        source_payload,
                                        ensure_ascii=False,
                                        separators=(",", ":"),
                                    )
                                ),
                            }
                        ],
                    }
                ],
            )
        )

        payload = self._safe_json(self._collect_text(response))
        if payload is None:
            raise ValueError("CDSS model output could not be parsed as JSON.")

        try:
            report = CDSSReport.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(
                "CDSS model output did not match the expected report schema."
            ) from exc

        return report.model_copy(
            update={
                "physician_review_required": True,
                "disclaimer": (
                    "Bu çıktı klinik karar desteği içindir; kesin tanı ve tedavi "
                    "kararı yetkili hekim tarafından verilmelidir."
                ),
            }
        )

    @staticmethod
    def _collect_text(response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts).strip()

    @staticmethod
    def _safe_json(text: str) -> dict[str, Any] | None:
        if not text:
            return None

        candidate = text.strip()
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return None

        try:
            value = json.loads(candidate[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None

        return value if isinstance(value, dict) else None
