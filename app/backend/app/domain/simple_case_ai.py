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
- laboratory results with the exact reference text printed in the source report,
- one or more medical report texts/findings.

Write a concise, physician-to-physician Turkish clinical assessment. It must be easy to scan in under one minute.

Use this exact section order and headings:

KLİNİK ÖZET
ÖNE ÇIKAN LABORATUVAR BULGULARI
TETKİK / RAPOR BULGULARI
ENTEGRE KLİNİK DEĞERLENDİRME
OLASI KLİNİK DURUMLAR / AYIRICI TANI
ÖNERİLEN İLERİ TETKİK / İZLEM
SONUÇ / KANAAT
HEKİM NOTU

Formatting rules:
- KLİNİK ÖZET: 3-5 short bullet lines only.
- ÖNE ÇIKAN LABORATUVAR BULGULARI: group only clinically relevant findings. Do NOT transcribe the entire laboratory report.
- Do not list every normal/unremarkable result. If useful, summarize them in one short sentence by system (for example renal function/electrolytes) without enumerating every analyte.
- TETKİK / RAPOR BULGULARI: 3-8 short bullet lines containing the important source-reported findings.
- ENTEGRE KLİNİK DEĞERLENDİRME: maximum 2 short paragraphs.
- OLASI KLİNİK DURUMLAR / AYIRICI TANI: preferably 2-5 numbered items. Each item must use this compact pattern:
  "1. <possible condition> — Neden: <reason>. Destekleyen veriler: <specific source findings>. Eksik/karşı veri: <if relevant>."
- ÖNERİLEN İLERİ TETKİK / İZLEM: preferably 2-6 numbered items. Each item must use this compact pattern:
  "1. <test/follow-up> — Neden: <source finding or differential question>. Amaç: <what uncertainty it helps resolve>. Öncelik: <yakın dönem/rutin/uzman değerlendirmesi>."
- SONUÇ / KANAAT: 2-4 concise sentences only.
- HEKİM NOTU: 1-3 short sentences about missing/conflicting data and physician review.
- Use blank lines between sections, not between every sentence.
- Prefer short bullets over long prose.
- Avoid repetitive wording.

Clinical reasoning rules:
- Integrate clinical context, lab data and report findings.
- In differential diagnosis, clearly distinguish model-generated clinical inference from diagnoses explicitly stated in source documents.
- Use cautious wording such as "ayırıcı tanıda düşünülebilir", "ile uyumlu olabilir", or "olasılığı klinik olarak değerlendirilebilir".
- Do not claim a differential diagnosis is confirmed.
- Do not assign numeric probabilities or certainty scores.
- Prefer a small, clinically useful differential over a long speculative list.
- Follow-up tests may use general clinical knowledge when they directly address a source finding or differential question.
- Do not present tests as mandatory. Use wording such as "değerlendirilebilir", "düşünülebilir", or "hekim tarafından uygun görülürse".
- Do not recommend medication or treatment.

Strict source fidelity:
- Source-derived facts must come only from the supplied case.
- Preserve source values, units and printed reference text when clinically relevant.
- Never invent a source finding, value, reference range, reported diagnosis, recommendation, or negative finding.
- MediCore must not generate NORMAL/ABNORMAL/HIGH/LOW labels.
- Do not say a laboratory result is "high", "low", "normal", "above", "below", or "outside range" unless the source itself explicitly contains that interpretation/flag. When needed, present the value next to the source reference text and let the physician interpret it.
- If a source reference is missing, say only that the source report did not provide a usable reference.
- Preserve negation and uncertainty.
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
            max_tokens=4200,
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
        "KLİNİK ÖZET",
        "ÖNE ÇIKAN LABORATUVAR BULGULARI",
        "TETKİK / RAPOR BULGULARI",
        "ENTEGRE KLİNİK DEĞERLENDİRME",
        "OLASI KLİNİK DURUMLAR / AYIRICI TANI",
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
