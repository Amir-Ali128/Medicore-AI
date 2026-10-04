"""Clinician-facing AI report generation for the simplified MediCore case flow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# Import the runtime shim before creating Anthropic clients. This normalizes
# Claude 5 requests (notably thinking/sampling compatibility) and emits sanitized
# provider diagnostics without logging prompts or secrets.
import app.domain.claude_sonnet5_compat_runtime  # noqa: F401
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
- laboratory results with deterministic canonical status and the exact reference text printed in the source report,
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
- ÖNE ÇIKAN LABORATUVAR BULGULARI: inspect the FULL supplied laboratory list, then group the clinically relevant abnormalities and pattern-level findings. Include clinically relevant UNKNOWN results as uncertain source observations without assigning a new high/low/normal status.
- Do not transcribe every normal/unremarkable result. Normal findings may be summarized briefly by system when they provide useful counter-evidence.
- TETKİK / RAPOR BULGULARI: 3-8 short bullet lines containing the important source-reported findings.
- ENTEGRE KLİNİK DEĞERLENDİRME: maximum 2 short paragraphs.
- OLASI KLİNİK DURUMLAR / AYIRICI TANI: preferably 2-5 numbered items. Each item must use this compact pattern:
  "1. <possible condition> — Neden: <reason>. Destekleyen veriler: <specific source findings>. Karşı veri: <if supplied>. Eksik veri: <relevant unanswered question>. Kanıt gücü: <güçlü/orta/zayıf>. Öncelik: <birincil/ikincil>."
- ÖNERİLEN İLERİ TETKİK / İZLEM: preferably 2-6 numbered items. Each item must use this compact pattern:
  "1. <test/follow-up> — Neden: <source finding or differential question>. Amaç: <what uncertainty it helps resolve>. Öncelik: <yakın dönem/rutin/uzman değerlendirmesi>."
- SONUÇ / KANAAT: 2-4 concise sentences only.
- HEKİM NOTU: 1-3 short sentences about missing/conflicting data and physician review.
- Use blank lines between sections, not between every sentence.
- Prefer short bullets over long prose.
- Avoid repetitive wording.

Clinical reasoning rules:
- Integrate clinical context, lab data and report findings.
- Every laboratory row's canonical status (LOW, NORMAL, HIGH or UNKNOWN) is computed by deterministic backend logic. Use that status as supplied; do not recompute, override or relabel it. UNKNOWN remains unclassified even if general clinical knowledge suggests an interval.
- Treat canonical directionality as a clinical reasoning feature. Use combinations of abnormalities to recognize patterns (for example renal, electrolyte, inflammatory, hepatic, hematologic, endocrine or acid-base patterns) when supported by the supplied data.
- A NORMAL result may contribute to a clinical pattern without becoming HIGH or LOW. For example, TIBC 445 µg/dL with source interval 250–450 is NORMAL; "üst sınıra yakın" or "yüksek-normal" describes its position within the interval, not an elevated canonical status. Both interval endpoints are inclusive.
- When multiple abnormalities form a coherent pattern, explicitly connect the pattern to the differential diagnosis and explain which values support it.
- source_flag is copied from the source document only; UI group labels are not supplied. Preserve source flags separately from canonical status and clinical inference. If a source flag conflicts with canonical status, mention the discrepancy without overriding status.
- Rows marked needs_review may contain unresolved transcription or association errors. State that uncertainty; do not treat those rows as established facts.
- In differential diagnosis, clearly distinguish model-generated clinical inference from diagnoses explicitly stated in source documents.
- Use cautious wording such as "ayırıcı tanıda düşünülebilir", "ile uyumlu olabilir", or "olasılığı klinik olarak değerlendirilebilir".
- Do not claim a differential diagnosis is confirmed.
- Do not assign numeric probabilities or certainty scores.
- Prefer a small, clinically useful differential over a long speculative list.
- Rank possible conditions by the strength and specificity of supplied supporting evidence. Keep supporting_evidence, contradicting_evidence and missing_evidence distinct in the prose; missing information is not a negative finding. Use only qualitative confidence (Kanıt gücü) and primary/secondary priority, without implying a confirmed diagnosis.
- Distinguish the main syndrome from its likely cause. For example, only when supplied low hemoglobin, microcytosis/low MCH, increased RDW and depleted ferritin/iron/transferrin saturation accompany menorrhagia and a reported uterine fibroid, prioritize an iron-deficiency anemia pattern with chronic menstrual blood loss as a likely source. A fibroid finding alone does not prove the cause of bleeding.
- von Willebrand disease/coagulopathy and occult gastrointestinal blood loss may remain conditional secondary differentials, but must not have equal weight with a strongly supported primary explanation when their specific evidence is missing. State which bleeding history, family history, examination or other source findings would support them; reprioritize if such evidence is actually supplied. Do not invent reassuring negative findings or exclude these alternatives solely because evidence is missing.
- Preserve event_date, specimen_date, result_date, examination/document dates and uploaded_at as different temporal meanings. A later result release or upload does not move the clinical event to that date; do not invent a date when none is supplied.
- Follow-up tests may use general clinical knowledge when they directly address a source finding or differential question.
- Do not present tests as mandatory. Use wording such as "değerlendirilebilir", "düşünülebilir", or "hekim tarafından uygun görülürse".
- Do not recommend medication or treatment.

Strict source fidelity:
- Source-derived facts must come only from the supplied case.
- Preserve source values, units and printed reference text when clinically relevant.
- Never invent a source finding, value, reference range, reported diagnosis, recommendation, or negative finding.
- You receive the full laboratory list, including NORMAL and UNKNOWN rows. Do not depend on frontend display groups or omit useful counter-evidence.
- Preserve each supplied canonical status alongside its source value, unit and raw_reference/reference_text. Never invent or substitute a reference interval. If status is UNKNOWN, describe the supplied classification_reason or uncertainty without independently classifying the result.
- Comparator values such as "<2" or ">90" remain source observations, not exact numbers; retain the supplied canonical status and its uncertainty.
- Preserve negation and uncertainty.
- Do not add markdown fences or JSON. Return only the finished Turkish medical report.
""".strip()


_SEMANTIC_DATE_FIELDS = (
    "event_date",
    "specimen_date",
    "result_date",
    "exam_date",
    "examination_date",
    "consultation_date",
    "document_date",
    "uploaded_at",
)


def _semantic_dates(record: Any) -> dict[str, Any]:
    """Keep date meanings separate, including source metadata in older cases."""
    serialized = record.model_dump(mode="json")
    metadata = serialized.get("source_metadata") or serialized.get("metadata") or {}
    return {
        field: serialized.get(field) or metadata.get(field)
        for field in _SEMANTIC_DATE_FIELDS
    }


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
                "status": item.status,
                "reference_low": item.reference_low,
                "reference_high": item.reference_high,
                "raw_reference": item.raw_reference,
                "classification_reason": item.classification_reason,
                "source_flag": item.source_metadata.get("source_flag"),
                "needs_review": item.source_metadata.get("needs_review", False),
                "ingestion_reasons": item.source_metadata.get("ingestion_reasons", []),
                "measured_at": item.measured_at.isoformat()
                if hasattr(item.measured_at, "isoformat")
                else item.measured_at,
                **_semantic_dates(item),
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
                **_semantic_dates(report),
            }
            for report in normalized.reports
        ],
        "warnings": list(dict.fromkeys([*normalized.warnings, *(str(w) for item in normalized.labs for w in item.source_metadata.get("document_warnings", []))])),
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
    if len(prompt) > 160_000:
        raise RuntimeError("Vaka tek AI çağrısı sınırını aşıyor; sonuçlar sessizce kırpılmadı.")
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    required_headings = (
        "KLİNİK ÖZET",
        "ÖNE ÇIKAN LABORATUVAR BULGULARI",
        "TETKİK / RAPOR BULGULARI",
        "ENTEGRE KLİNİK DEĞERLENDİRME",
        "OLASI KLİNİK DURUMLAR / AYIRICI TANI",
        "ÖNERİLEN İLERİ TETKİK / İZLEM",
        "SONUÇ / KANAAT",
        "HEKİM NOTU",
    )

    async def generate(extra_instruction: str | None = None) -> str:
        user_text = prompt
        if extra_instruction:
            user_text += "\n\n" + extra_instruction

        response = await client.messages.create(
            model=model,
            max_tokens=5200,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}],
                }
            ],
        )

        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        ).strip()

    def missing_headings(report_text: str) -> list[str]:
        upper = report_text.upper()
        return [heading for heading in required_headings if heading not in upper]

    try:
        text = await generate()
    except Exception as exc:
        raise RuntimeError(f"AI klinik rapor üretimi başarısız: {exc}") from exc

    if not text:
        raise RuntimeError("AI klinik rapor modeli boş yanıt döndürdü.")

    missing = missing_headings(text)
    if missing:
        retry_instruction = (
            "Önceki yanıt eksik bölümler içerdi. Vaka verisini yeniden değerlendir ve raporu baştan yaz. "
            "Aşağıdaki başlıkların TAMAMINI, tam bu yazımla ve bu sırayla kullan: "
            + " | ".join(required_headings)
            + ". Hiçbir bölümü atlama. Kısa ve taranabilir yaz."
        )
        try:
            retried = await generate(retry_instruction)
            if retried:
                text = retried
        except Exception:
            pass

    missing = missing_headings(text)
    if missing:
        raise RuntimeError(
            "AI klinik raporu eksik üretildi. Eksik bölümler: " + ", ".join(missing)
        )

    return CaseAIInterpretation(
        report_text=text[:24_000],
        model=model,
    )
