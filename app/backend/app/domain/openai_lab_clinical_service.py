"""Physician-assistive laboratory synthesis built on native-validated facts.

The language model never performs deterministic laboratory arithmetic here. It receives
rows already normalized/classified by MediCore's C++ core plus derived metrics calculated
by that same native core. Rows that fail or weaken native validation are separated from
AI-eligible facts and are presented only as review items.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping, Sequence

from openai import AsyncOpenAI

from app.core.config import get_settings


_CLINICAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "headline",
        "overview",
        "priority_findings",
        "systems",
        "reassuring_findings",
        "priority_actions",
        "limitations",
        "narrative_tr",
    ],
    "properties": {
        "headline": {"type": "string"},
        "overview": {"type": "string"},
        "priority_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "severity", "summary", "evidence", "follow_up"],
                "properties": {
                    "title": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "moderate", "info"],
                    },
                    "summary": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "follow_up": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "systems": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "status", "summary", "evidence"],
                "properties": {
                    "title": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["attention", "reassuring", "mixed", "uncertain"],
                    },
                    "summary": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "reassuring_findings": {"type": "array", "items": {"type": "string"}},
        "priority_actions": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "narrative_tr": {"type": "string"},
    },
}


_INSTRUCTIONS = """
You are the clinical laboratory synthesis layer of MediCore-AI, a physician-assistive
clinical decision support system. Write in clear, natural Turkish suitable for a
physician and an informed patient reading together.

The input contains three fact layers:
1) lab_rows: measured values whose deterministic comparison passed MediCore's native
   C++ validation and can be used as primary laboratory facts.
2) review_rows: rows marked WARNING, NEEDS_REVIEW or INVALID by the C++ core. They are
   supplied only so you can state limitations/review needs; NEVER use them as verified
   evidence for a clinical conclusion and NEVER silently repair or reinterpret them.
3) derived_metrics: deterministic calculations produced by the native C++ core.

Hard rules:
- NEVER recalculate a value or derived metric yourself. Use the supplied C++ values.
- NEVER override a C++ result_status or validation_status.
- NEVER promote review_rows into trusted facts, even if a value looks clinically plausible.
- NEVER infer a missing digit, decimal separator, unit, comparator or reference range.
- Clearly distinguish measured laboratory values from calculated metrics.
- Never invent a reference range, diagnosis, symptom, medication, history or test.
- Do not prescribe medication, dose changes, or treatment. Follow-up may recommend
  physician review or clinically relevant confirmatory/monitoring tests.
- Do not call one reduced eGFR value chronic kidney disease. A chronic diagnosis
  requires persistence over time and/or other evidence of kidney damage.
- FIB-4 is a risk index, not a fibrosis diagnosis. In adults over 65, explicitly note
  that age can raise FIB-4 and reduce specificity when that metric is present.
- eAG is calculated from HbA1c and is not an independently measured glucose result.
- Glycemic targets in older adults are individualized. If glucose/HbA1c are clearly
  elevated, explain the pattern and the need for clinician review without choosing a
  treatment target for the patient.
- If existing diabetes history is not provided, use language such as "diyabet ile
  uyumlu olabilir / diyabet olasılığını güçlü destekleyebilir; klinik doğrulama gerekir"
  rather than claiming a definitive diagnosis.
- A missing printed reference range means deterministic normality cannot be claimed.
  Preserve that uncertainty.
- Reserve severity "critical" for findings whose urgency is clearly supported by the
  supplied evidence. Do not invent emergency cutoffs.
- Mention reassuring normal findings compactly; do not narrate every normal row one-by-one.
- Rank the most important clinical pattern first. Group related values by system only
  when evidence for that group exists.
- Every substantive claim must be traceable to supplied evidence strings.
- Do not include patient name, identity number, address, phone, email, protocol number
  or exact date of birth.

narrative_tr should read like a concise high-quality clinical explanation: start with
"Bu sonuçlarda en önemli konu ..." when there is a clear leading issue, then use short
section headings and paragraphs, and finish with an explicit priority order. It is a
clinical decision-support summary, not a diagnosis or treatment order.
""".strip()


class OpenAILabClinicalError(RuntimeError):
    pass


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return value


def _validation_state(row: Mapping[str, Any]) -> str:
    """Normalize native validation state while remaining compatible with v1 rows."""
    explicit = str(row.get("validation_status") or "").strip().upper()
    if explicit in {"VALID", "WARNING", "NEEDS_REVIEW", "INVALID"}:
        return explicit
    if bool(row.get("needs_review")) or str(row.get("result_status") or "").upper() == "NEEDS_REVIEW":
        return "NEEDS_REVIEW"
    return "VALID"


def _row_requires_review(row: Mapping[str, Any]) -> bool:
    return _validation_state(row) != "VALID" or bool(row.get("needs_review"))


def _clinical_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "test": row.get("display_name") or row.get("canonical_name") or row.get("raw_parameter_name"),
        "loinc_code": row.get("loinc_code"),
        "value": _json_safe(row.get("normalized_value")),
        "unit": row.get("unit"),
        "reference_min": _json_safe(row.get("reference_min")),
        "reference_max": _json_safe(row.get("reference_max")),
        "reference_text": row.get("reference_text"),
        "reference_type": row.get("reference_type"),
        "result_status": row.get("result_status"),
        "validation_status": _validation_state(row),
        "needs_review": _row_requires_review(row),
        "reason": row.get("reason"),
        "classification_confidence": _json_safe(row.get("classification_confidence")),
    }


def _metric_input(metric: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "code": metric.get("code"),
        "name": metric.get("name"),
        "value": _json_safe(metric.get("value")),
        "unit": metric.get("unit"),
        "formula": metric.get("formula"),
        "input_labels": list(metric.get("input_labels") or []),
        "note": metric.get("note"),
    }


def partition_rows_for_ai(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate C++-validated facts from rows that must remain review-only.

    This is the trust boundary between deterministic native processing and generative
    clinical synthesis. The AI gets review rows for transparency, but they cannot enter
    the trusted evidence list.
    """
    trusted: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for row in rows:
        serialized = _clinical_row(row)
        if _row_requires_review(row):
            review.append(serialized)
        else:
            trusted.append(serialized)
    return trusted, review


def build_fallback_clinical_assessment(
    *,
    rows: Sequence[Mapping[str, Any]],
    derived_metrics: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Safe deterministic fallback when the narrative model is unavailable."""
    trusted_rows, review_rows = partition_rows_for_ai(rows)
    abnormal = [
        row
        for row in trusted_rows
        if str(row.get("result_status") or "").upper() in {"HIGH", "LOW"}
    ]
    normal = [
        row
        for row in trusted_rows
        if str(row.get("result_status") or "").upper() == "NORMAL"
    ]

    def evidence(row: Mapping[str, Any]) -> str:
        name = row.get("test") or row.get("display_name") or row.get("canonical_name") or row.get("raw_parameter_name") or "Test"
        value = row.get("value") if "value" in row else row.get("normalized_value")
        unit = row.get("unit") or ""
        return f"{name}: {value} {unit}".strip()

    priority_findings: list[dict[str, Any]] = []
    for row in abnormal[:8]:
        status = str(row.get("result_status") or "").upper()
        priority_findings.append(
            {
                "title": f"{evidence(row)} — {'yüksek' if status == 'HIGH' else 'düşük'}",
                "severity": "moderate",
                "summary": str(row.get("reason") or "Kaynak laboratuvar referansına göre sapma saptandı."),
                "evidence": [evidence(row)],
                "follow_up": ["Sonucu klinik bağlam, önceki ölçümler ve hekim değerlendirmesiyle birlikte gözden geçirin."],
            }
        )

    headline = (
        "Kaynak laboratuvar referanslarına göre doğrulanmış öncelikli sapmalar saptandı."
        if abnormal
        else "Doğrulanmış belirgin kaynak-referans sapması saptanmadı; doğrulama gereken sonuçlar ayrıca gösterildi."
    )
    normal_evidence = [evidence(row) for row in normal[:8]]
    metric_lines = [
        f"{metric.get('name')}: {metric.get('value')} {metric.get('unit') or ''}".strip()
        for metric in derived_metrics
    ]
    narrative_parts = [headline]
    if abnormal:
        narrative_parts.append("Öne çıkanlar:\n" + "\n".join(f"• {evidence(row)}" for row in abnormal[:8]))
    if metric_lines:
        narrative_parts.append("C++ ile hesaplanan ek metrikler:\n" + "\n".join(f"• {line}" for line in metric_lines))
    if normal_evidence:
        narrative_parts.append("Kaynak aralığı içinde doğrulanmış bazı sonuçlar:\n" + "\n".join(f"• {line}" for line in normal_evidence))
    if review_rows:
        narrative_parts.append(
            f"{len(review_rows)} sonuç C++ doğrulama katmanı tarafından kaynak/hekim kontrolüne ayrıldı ve klinik kanıt olarak kullanılmadı."
        )
    narrative_parts.append("Bu çıktı klinik karar desteğidir; tanı veya tedavi kararı değildir.")

    limitations = [
        "AI klinik sentezi kullanılamadığı için bu metin yalnızca deterministik yedek özettir.",
        "Kaynak raporda referansı bulunmayan sonuçların normal/düşük/yüksek sınıflaması yapılmaz.",
    ]
    if review_rows:
        limitations.append(
            f"{len(review_rows)} satır WARNING/NEEDS_REVIEW/INVALID durumunda olduğu için doğrulanmış klinik kanıta dahil edilmedi."
        )

    return {
        "headline": headline,
        "overview": "Laboratuvar sonuçları native C++ sınıflandırması, doğrulama durumu ve kaynak referansları temel alınarak özetlendi.",
        "priority_findings": priority_findings,
        "systems": [],
        "reassuring_findings": normal_evidence,
        "priority_actions": [
            "Öncelikli sapmaları hastanın öyküsü, muayenesi, önceki sonuçları ve mevcut tedavileriyle birlikte değerlendirin."
        ] if abnormal else [],
        "limitations": limitations,
        "narrative_tr": "\n\n".join(narrative_parts),
        "model": None,
        "synthesis_source": "deterministic_fallback",
    }


async def synthesize_lab_clinical_assessment(
    *,
    rows: Sequence[Mapping[str, Any]],
    derived_metrics: Sequence[Mapping[str, Any]],
    patient_age: int | None,
    patient_sex: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise OpenAILabClinicalError("OPENAI_API_KEY yapılandırılmamış.")

    model = (settings.openai_lab_model or "").strip()
    if not model:
        raise OpenAILabClinicalError("OPENAI_LAB_MODEL yapılandırılmamış.")

    trusted_rows, review_rows = partition_rows_for_ai(rows)
    payload = {
        "patient_context": {
            "age": patient_age,
            "sex": patient_sex,
        },
        "lab_rows": trusted_rows,
        "review_rows": review_rows,
        "derived_metrics": [_metric_input(metric) for metric in derived_metrics],
        "trust_policy": {
            "primary_lab_facts": "native_cpp_validation_status_VALID_only",
            "review_rows_are_non_authoritative": True,
            "silent_correction_allowed": False,
        },
    }

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.responses.create(
            model=model,
            store=False,
            max_output_tokens=8000,
            instructions=_INSTRUCTIONS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "medicore_lab_clinical_synthesis_v1",
                    "strict": True,
                    "schema": _CLINICAL_SCHEMA,
                }
            },
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        }
                    ],
                }
            ],
        )
    except Exception as exc:
        raise OpenAILabClinicalError(f"OpenAI klinik laboratuvar sentezi başarısız: {exc}") from exc

    output_text = str(getattr(response, "output_text", "") or "").strip()
    if not output_text:
        raise OpenAILabClinicalError("OpenAI klinik laboratuvar sentezi boş yanıt döndürdü.")

    try:
        assessment = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise OpenAILabClinicalError("OpenAI klinik laboratuvar sentezi geçerli JSON değil.") from exc

    if not isinstance(assessment, dict):
        raise OpenAILabClinicalError("OpenAI klinik laboratuvar sentezi beklenen şemada değil.")
    assessment["model"] = model
    assessment["synthesis_source"] = "ai_after_native_cpp"
    return assessment
