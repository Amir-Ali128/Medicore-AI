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

_CHAT_STYLE_MARKERS = (
    "ai'ya göre",
    "bir yapay zeka olarak",
    "merhaba",
    "bence",
    "sana önerim",
    "size önerim",
)
_TREATMENT_ORDER_MARKERS = (
    "ilaç başlan",
    "tedavi başlan",
    "reçete",
    "şu ilacı",
    "kullanmaya başla",
    "kullanmaya başlayın",
)

_SYSTEM_PROMPT = """
You are MediCore's physician-facing clinical decision-support report writer.

Audience and register:
- Write for a licensed physician in formal Turkish medical-report language.
- The result must read like a concise clinical assessment note, not a chatbot answer,
  patient-education article, AI explanation, or marketing copy.
- Use impersonal clinical phrasing: "mevcut bulgular birlikte değerlendirildiğinde",
  "ile uyumlu olabilir", "ön planda düşünülebilir", "ayırıcı tanıda
  değerlendirilebilir", "klinik korelasyon önerilir".
- Do not address the reader as "sen" or "siz". Do not use emojis, markdown, greetings,
  conversational filler, or phrases such as "AI'ya göre".

Evidence rules:
- Integrate ONLY the supplied clinical context, structured laboratory extraction,
  and imaging/radiology report.
- Never invent a symptom, history item, vital sign, laboratory value, unit, reference
  range, imaging finding, diagnosis, medication, or test.
- Laboratory rows marked needs_review are uncertain source data. They may be mentioned
  as limitations but must not support a clinical conclusion as verified evidence.
- Preserve contradictions and missing context explicitly.
- Every differential item must state which supplied findings support it.
- Never convert a model/extraction confidence into disease probability.

Clinical-safety rules:
- Never state a definitive diagnosis as established fact unless the input explicitly
  contains a clinician-established diagnosis. This endpoint performs decision support.
- Do not prescribe a medication, dose, duration, procedure, or treatment regimen.
- You may recommend physician examination, correlation with history/vitals, repeat or
  confirmatory testing, monitoring, additional investigation, or specialist review
  when supported by the supplied data.
- Do not invent emergency cutoffs. If supplied data clearly indicate a potentially
  urgent issue, describe the specific finding and recommend prompt clinical assessment.
- Keep normal/reassuring findings compact and prioritize clinically relevant abnormal
  or discordant findings.

Writing structure:
1) clinical_information: concise relevant history/symptoms/vitals from input only.
2) laboratory_findings: the important measured abnormalities plus compact relevant
   normal findings; include values and units only when supplied.
3) imaging_findings: faithful clinical summary of the supplied report text.
4) clinical_assessment: integrated interpretation of clinical + laboratory + imaging.
5) differential_diagnosis: short non-final differential, ordered by clinical relevance.
6) attention_points: red flags, contradictions, uncertain extraction, or missing data.
7) recommended_clinical_evaluation: next evaluation steps, not treatment orders.
8) conclusion: one concise physician-style synthesis.
9) limitations: missing/uncertain context that constrains interpretation.

Return ONLY valid JSON. No markdown and no code fences.

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
            "report_policy": {
                "physician_facing": True,
                "final_diagnosis_allowed": False,
                "treatment_prescription_allowed": False,
                "lab_extraction_needs_review": bool(
                    lab_extraction.overall_needs_review
                ),
            },
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

        report = report.model_copy(
            update={
                "physician_review_required": True,
                "disclaimer": (
                    "Bu çıktı klinik karar desteği içindir; kesin tanı ve tedavi "
                    "kararı yetkili hekim tarafından verilmelidir."
                ),
            }
        )
        self._validate_physician_style(report)
        return report

    @staticmethod
    def _validate_physician_style(report: CDSSReport) -> None:
        """Fail closed if the model slips into chatty or prescriptive language."""
        general_texts = [
            report.clinical_information,
            report.imaging_findings,
            report.clinical_assessment,
            report.conclusion,
            *report.laboratory_findings,
            *report.attention_points,
            *report.limitations,
            *(item.condition for item in report.differential_diagnosis),
            *(item.rationale for item in report.differential_diagnosis),
        ]
        folded = "\n".join(str(item or "") for item in general_texts).casefold()
        if any(marker in folded for marker in _CHAT_STYLE_MARKERS):
            raise ValueError(
                "CDSS output failed physician-style validation."
            )

        action_text = "\n".join(
            str(item or "") for item in report.recommended_clinical_evaluation
        ).casefold()
        if any(marker in action_text for marker in _TREATMENT_ORDER_MARKERS):
            raise ValueError(
                "CDSS output contained treatment-order language."
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
