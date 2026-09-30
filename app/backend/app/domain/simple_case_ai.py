"""Clinician-facing AI report generation for the simplified MediCore case flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.domain.simple_case import normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest


@dataclass(frozen=True)
class CaseAIInterpretation:
    report_text: str
    model: str


_SYSTEM_PROMPT = """
You are MediCore's clinician-facing medical report writer.

You receive one structured case containing:
- clinical context,
- laboratory results with the reference text printed in the source report,
- one or more medical report texts/findings.

Write a professional Turkish clinical assessment report for physician review.

Use this exact section order and headings:

KLİNİK BİLGİ
LABORATUVAR DEĞERLENDİRMESİ
TETKİK / RAPOR BULGULARI
ENTEGRE KLİNİK DEĞERLENDİRME
SONUÇ / KANAAT
ÖNERİLEN İLERİ TETKİK / İZLEM
HEKİM NOTU

Style:
- Write like a concise physician-to-physician report, not like a chatbot.
- Use complete clinical sentences and short paragraphs.
- Integrate the clinical context, laboratory data and report findings together.
- In the laboratory section, include source values, units and printed reference text when useful.
- If a reference is missing, explicitly say the source report did not provide one.
- In the integrated assessment, explain cross-source relationships cautiously.
- In SONUÇ / KANAAT, summarize only source-supported conclusions and clinically relevant synthesis.
- In ÖNERİLEN İLERİ TETKİK / İZLEM, suggest reasonable next diagnostic tests or follow-up measurements that a physician may consider, based only on abnormalities or uncertainties present in the case.
- Every suggested test must include a short rationale tied to a specific source finding.
- Do not present tests as mandatory. Use wording such as "değerlendirilebilir", "düşünülebilir", or "hekim tarafından uygun görülürse".
- Do not recommend treatment, medication, procedures, or invasive testing unless the source report explicitly recommends it; if an invasive test is relevant, frame it only as a specialist-consideration item.
- Prioritize the list: urgent/near-term items first, routine follow-up later.
- HEKİM NOTU should state missing/conflicting data and that final interpretation requires physician review when applicable.

Strict safety/fidelity rules:
- Use only information present in the supplied case.
- Never invent a diagnosis, finding, value, reference range, recommendation, or negative finding.
- Do not classify a lab value as high/low/normal unless that wording is explicitly present in the source.
- Preserve negation and uncertainty.
- Do not prescribe medication or treatment.
- Do not provide invented probabilities.
- Avoid conversational phrases such as "istersen", "size yardımcı olabilirim", or "doktorunuza danışın".
- Do not add markdown fences or JSON. Return only the finished Turkish medical report.
""".strip()


def _build_case_payload(payload: SimpleCaseRequest) -> dict[str, Any]:
    normalized = normalize_simple_case(payload)
    return {
        "clinical": normalized.clinical.model_dump(mode="json"),
        "labs": [
            {
                "test_name": item.test_name,
                "value": item.value,
                "unit": item.unit,
                "reference_text": item.reference_text,
                "reference_source": item.reference_source,
                "measured_at": item.measured_at.isoformat()
                if hasattr(item.measured_at, "isoformat")
                else item.measured_at,
            }
            for item in normalized.labs
        ],
        "reports": [
            {
                "report_type": report.report_type,
                "report_date": report.report_date.isoformat()
                if hasattr(report.report_date, "isoformat")
                else report.report_date,
                "body_region": report.body_region,
                "findings": report.findings,
                "impression": report.impression,
                "raw_text": report.raw_text,
            }
            for report in normalized.reports
        ],
        "warnings": list(normalized.warnings),
    }


async def interpret_simple_case(payload: SimpleCaseRequest) -> CaseAIInterpretation:
    settings = get_settings()
    model = (
        settings.claude_hypothesis_model
        or settings.claude_extraction_model
        or settings.claude_vision_model
    )
    if not settings.anthropic_api_key or not model:
        raise RuntimeError("Anthropic klinik rapor modeli yapılandırılmamış.")

    case_payload = _build_case_payload(payload)
    prompt = json.dumps(case_payload, ensure_ascii=False, separators=(",", ":"))
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=3200,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt[:160_000],
                        }
                    ],
                }
            ],
        )
    except Exception as exc:
        raise RuntimeError(f"AI klinik rapor üretimi başarısız: {exc}") from exc

    text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ).strip()

    if not text:
        raise RuntimeError("AI klinik rapor modeli boş yanıt döndürdü.")

    required_headings = (
        "KLİNİK BİLGİ",
        "LABORATUVAR DEĞERLENDİRMESİ",
        "TETKİK / RAPOR BULGULARI",
        "ENTEGRE KLİNİK DEĞERLENDİRME",
        "SONUÇ / KANAAT",
        "ÖNERİLEN İLERİ TETKİK / İZLEM",
        "HEKİM NOTU",
    )
    if not any(heading in text.upper() for heading in required_headings):
        text = "KLİNİK DEĞERLENDİRME RAPORU\n\n" + text

    return CaseAIInterpretation(
        report_text=text[:24_000],
        model=model,
    )
