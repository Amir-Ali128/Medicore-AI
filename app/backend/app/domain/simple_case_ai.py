"""Clinician-facing AI report generation for the simplified MediCore case flow."""

from __future__ import annotations

from app.domain.privacy_gateway import PrivacyViolation

from app.infrastructure.ai_privacy_client import privacy_call

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Import the runtime shim before creating Anthropic clients. This normalizes
# Claude 5 requests (notably thinking/sampling compatibility) and emits sanitized
# provider diagnostics without logging prompts or secrets.
import app.domain.claude_sonnet5_compat_runtime  # noqa: F401
from anthropic import AsyncAnthropic

from app.core.config import get_settings
from app.domain.simple_case import normalize_simple_case
from app.domain.consistency_flags import collect_consistency_flags, render_consistency_section
from app.schemas.simple_case import SimpleCaseRequest


logger = logging.getLogger(__name__)


def _heading_key(text: str) -> str:
    """Compare formatting/Turkish casing only; never rewrite clinical output."""
    folded = unicodedata.normalize("NFKD", text.replace("ı", "i")).casefold()
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = re.sub(r"[#*_]", "", folded)
    return re.sub(r"\s*/\s*", "/", " ".join(folded.split()))


@dataclass(frozen=True)
class CaseAIInterpretation:
    report_text: str
    model: str
    consistency_flags: list[dict] | None = None


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
                "raw_value": item.value,
                "normalized_value": item.normalized_value,
                "value_comparator": item.value_comparator,
                "value_limit": item.value_limit,
                "parsed_unit": item.parsed_unit,
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
                "source_metadata": {key: item.source_metadata[key] for key in (
                    "source_page", "source_row", "extraction_confidence",
                    "needs_review", "ingestion_reasons", "reader_values", "reader_normalized_value",
                ) if key in item.source_metadata},
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

    if getattr(settings, 'report_consistency_enabled', False):
        from app.domain.report_consistency import apply_report_consistency
        payload = apply_report_consistency(payload)
    case_payload = _build_case_payload(payload)
    if getattr(settings, 'lab_consistency_rules_enabled', False):
        from app.domain.lab_consistency_rules import annotate_request
        payload = annotate_request(payload)
        case_payload = _build_case_payload(payload)
    flags = collect_consistency_flags(payload) if getattr(settings, "consistency_section_enabled", False) else None
    if flags is not None:
        case_payload["consistency_flags"] = flags
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

    async def generate(extra_instruction: str | None = None, *, token_budget: int = 5200) -> tuple[str, str | None]:
        user_text = prompt
        if extra_instruction:
            user_text += "\n\n" + extra_instruction

        response = await privacy_call(client.messages.create, provider='Anthropic', call_site=__name__,
            model=model,
            max_tokens=token_budget,
            system=_SYSTEM_PROMPT + ("\nconsistency_flags bayraklarını yorumunda dikkate al; işaretli değerleri kesin kabul etme. VERİ TUTARLILIK UYARILARI bölümünü yazma; bu bölüm sunucu tarafından eklenecek." if flags is not None else ""),
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_text}],
                }
            ],
        )

        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        ).strip()
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "max_tokens":
            logger.warning("clinical_report_truncated code=output_limit budget=%s", token_budget)
        return text, stop_reason

    def missing_headings(report_text: str) -> list[str]:
        normalized = _heading_key(report_text)
        return [heading for heading in required_headings if _heading_key(heading) not in normalized]

    try:
        text, stop_reason = await generate()
    except PrivacyViolation:
        raise
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        logger.warning("clinical_report_provider_failed type=%s status=%s", type(exc).__name__, status)
        if status in (401, 403):
            message = "AI rapor hizmetine erişim reddedildi. Sunucudaki sağlayıcı erişimi kontrol edilmeli."
        elif status == 429:
            message = "AI rapor hizmetinin istek veya kullanım sınırına ulaşıldı. Kısa süre sonra tekrar deneyin."
        elif "timeout" in type(exc).__name__.lower():
            message = "AI rapor hizmeti süre sınırını aştı. Kısa süre sonra tekrar deneyin."
        else:
            message = "AI rapor hizmeti yanıt veremedi. Kısa süre sonra tekrar deneyin."
        raise RuntimeError(message) from None

    if not text:
        logger.warning("clinical_report_validation_failed code=empty_response")
        raise RuntimeError("AI klinik rapor modeli boş yanıt döndürdü.")

    def append_application_review_note(report_text: str, absent: list[str], reason: str | None) -> str:
        # This is explicitly application-owned review guidance, not an invented
        # clinical conclusion or a claim that the model produced a physician note.
        if absent == ["HEKİM NOTU"] and reason == "end_turn":
            lines = report_text.splitlines()
            keys = [_heading_key(line.strip().strip("# *:")) for line in lines]
            clinical_keys = [_heading_key(heading) for heading in required_headings[:-1]]
            positions = []
            for key in clinical_keys:
                if key not in keys:
                    return report_text
                positions.append(keys.index(key))
            if positions != sorted(positions):
                return report_text
            for index, start in enumerate(positions):
                end = positions[index+1] if index+1 < len(positions) else len(lines)
                if not any(line.strip().strip("# *-:") for line in lines[start+1:end]):
                    return report_text
            logger.warning("clinical_report_review_note code=application_notice")
            return report_text + "\n\nHEKİM NOTU\nUygulama notu: Yapay zekâ hekim notu üretmedi. Raporun klinik içeriği hekim tarafından gözden geçirilmelidir."
        return report_text

    text = append_application_review_note(text, missing_headings(text), stop_reason)
    missing = missing_headings(text)
    if missing or stop_reason == "max_tokens":
        logger.warning("clinical_report_validation_retry code=missing_sections count=%s", len(missing))
        retry_instruction = (
            "Önceki yanıt eksik bölümler içerdi. Vaka verisini yeniden değerlendir ve raporu baştan yaz. "
            "Aşağıdaki başlıkların TAMAMINI, tam bu yazımla ve bu sırayla kullan: "
            + " | ".join(required_headings)
            + ". Hiçbir bölümü atlama. Tekrarlama yapmadan kısa ve taranabilir yaz; son iki bölümü de bütçe dolmadan tamamla."
        )
        try:
            retried, retried_stop = await generate(
                retry_instruction, token_budget=8000 if stop_reason == "max_tokens" else 5200,
            )
            if retried:
                text, stop_reason = retried, retried_stop
                text = append_application_review_note(text, missing_headings(text), stop_reason)
        except PrivacyViolation:
            raise
        except Exception as exc:
            logger.warning("clinical_report_retry_failed type=%s status=%s", type(exc).__name__, getattr(exc,"status_code",None))

    if stop_reason == "max_tokens":
        raise RuntimeError("AI raporu çıktı sınırında kesildi; tamamlanmamış klinik rapor kaydedilmedi. Lütfen yeniden deneyin.")
    missing = missing_headings(text)
    if missing:
        logger.warning("clinical_report_validation_failed code=missing_sections count=%s", len(missing))
        raise RuntimeError(
            "AI klinik raporu eksik üretildi. Eksik bölümler: " + ", ".join(missing)
        )

    if flags is not None:
        # Only the backend owns this section, even if a model ignores its prompt.
        from app.domain.consistency_config import CONSISTENCY_HEADING
        lines, kept, suppress = text.splitlines(), [], False
        for line in lines:
            heading = _heading_key(line.strip().strip('# *:'))
            if heading == _heading_key(CONSISTENCY_HEADING):
                suppress = True
                continue
            if heading in {_heading_key(value) for value in required_headings}:
                suppress = False
            if not suppress:
                kept.append(line)
        text = '\n'.join(kept)
    return CaseAIInterpretation(
        report_text=(render_consistency_section(flags) if flags is not None else "") + text,
        model=model,
        consistency_flags=flags,
    )
