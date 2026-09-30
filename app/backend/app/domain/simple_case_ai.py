"""Clinician-facing AI synthesis for the simplified MediCore case flow."""

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
    clinical_summary: str
    integrated_findings: tuple[str, ...]
    correlations: tuple[str, ...]
    attention_points: tuple[str, ...]
    missing_or_conflicting_data: tuple[str, ...]
    clinician_conclusion: str
    limitations: tuple[str, ...]
    model: str


_SYSTEM_PROMPT = """
You are MediCore's clinician-facing case synthesis layer.

You receive one structured case containing:
- clinical context,
- laboratory results with source-provided reference text,
- medical report text/findings.

Your job is to synthesize the sources together for physician review.

Strict rules:
- Use only information present in the supplied case.
- Never invent a diagnosis, finding, value, reference range, recommendation, or negative finding.
- Do not classify lab values as high/low/normal unless the source report itself explicitly says so.
- Preserve uncertainty and negation.
- Do not prescribe treatment or medication changes.
- Do not claim to replace physician judgment.
- If data are missing or conflicting, say so.
- Clinical relationships may be described cautiously: "birlikte değerlendirildiğinde", "uyumlu olabilir",
  "ilişkili olabilir", "klinik korelasyon gerekir".
- Keep output concise, clinically useful, and in Turkish.
- Return JSON only.

Required JSON:
{
  "clinical_summary": "2-5 sentence integrated case summary",
  "integrated_findings": ["source-grounded important findings"],
  "correlations": ["cross-source relationships between clinical/lab/report data"],
  "attention_points": ["items that merit physician attention"],
  "missing_or_conflicting_data": ["missing, ambiguous, or conflicting source data"],
  "clinician_conclusion": "short final physician-facing synthesis",
  "limitations": ["limitations of the synthesis"]
}
""".strip()


def _clean(value: object, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _list(value: object, *, limit: int = 12, item_limit: int = 900) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = _clean(item, item_limit)
        if cleaned and cleaned not in out:
            out.append(cleaned)
        if len(out) >= limit:
            break
    return tuple(out)


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
        raise RuntimeError("Anthropic klinik yorum modeli yapılandırılmamış.")

    case_payload = _build_case_payload(payload)
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    response = await client.messages.create(
        model=model,
        max_tokens=2200,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            case_payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )[:180_000],
                    }
                ],
            }
        ],
    )

    text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ).strip()

    if not text:
        raise RuntimeError("AI klinik yorum modeli boş yanıt döndürdü.")

    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AI klinik yorum çıktısı geçerli JSON değil.") from exc

    if not isinstance(data, dict):
        raise RuntimeError("AI klinik yorum çıktısı beklenen formatta değil.")

    summary = _clean(data.get("clinical_summary"), 5000)
    conclusion = _clean(data.get("clinician_conclusion"), 3500)
    if not summary and not conclusion:
        raise RuntimeError("AI klinik yorumunda kullanılabilir özet bulunamadı.")

    return CaseAIInterpretation(
        clinical_summary=summary,
        integrated_findings=_list(data.get("integrated_findings"), limit=16),
        correlations=_list(data.get("correlations"), limit=16),
        attention_points=_list(data.get("attention_points"), limit=16),
        missing_or_conflicting_data=_list(
            data.get("missing_or_conflicting_data"),
            limit=12,
        ),
        clinician_conclusion=conclusion,
        limitations=_list(data.get("limitations"), limit=10),
        model=model,
    )
