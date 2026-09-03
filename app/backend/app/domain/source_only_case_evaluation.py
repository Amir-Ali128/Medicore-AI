"""Patient-scoped compact evaluation when no laboratory analysis run exists.

The existing clinical copilot is analysis-run scoped because its primary evidence is
structured laboratory data. Real cases can still have only clinical intake or only a
radiology/ultrasound report. This module provides a conservative patient-scoped path
for those cases without creating fake laboratory reports or analysis runs.

The source-only path is still physician-review-only. It sends only bounded summaries,
short symptoms and deterministic review flags to the compact model. It never creates
a diagnosis, treatment recommendation, medication order or automatic test order.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain import claude_clinical_hypothesis_service as service_module
from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService
from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
from app.schemas.clinical_copilot import (
    ClinicalHypothesisGenerationRequest,
    ClinicalHypothesisGenerationResult,
)
from app.schemas.clinical_hypothesis import ClinicalHypothesisResponse

_SOURCE_KEYS = ("clinical", "laboratory", "ultrasound")
_SOURCE_SUMMARY_PREFIX = "__MEDICORE_SOURCE_SUMMARY__"
_SOURCE_ONLY_SCOPE = "source_only"
_SOURCE_ONLY_GATE = "SOURCE_CONTEXT_REVIEW"


def source_coverage(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return explicit 0/3..3/3 source coverage without inventing missing data."""

    availability = {key: False for key in _SOURCE_KEYS}
    raw_availability = metadata.get("source_availability")
    explicit_keys: set[str] = set()
    if isinstance(raw_availability, dict):
        for key in _SOURCE_KEYS:
            if key in raw_availability:
                explicit_keys.add(key)
                availability[key] = raw_availability.get(key) is True

    # Backward-compatible fallback for older callers that provide summaries but no
    # availability value for that source. An explicit false is authoritative and
    # cannot be overridden by placeholder/non-empty summary text.
    raw_summaries = metadata.get("source_summaries")
    if isinstance(raw_summaries, dict):
        for key in _SOURCE_KEYS:
            if key in explicit_keys:
                continue
            value = raw_summaries.get(key)
            if isinstance(value, str) and value.strip():
                availability[key] = True

    count = sum(1 for available in availability.values() if available)
    mode = {
        0: "no_source",
        1: "single_source",
        2: "partial_multisource",
        3: "full_multisource",
    }[count]
    return {
        "available": availability,
        "available_count": count,
        "total_sources": len(_SOURCE_KEYS),
        "mode": mode,
        "limited": count < len(_SOURCE_KEYS),
    }


def _dedupe(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        item = str(value or "").strip().upper()
        if item and item not in unique:
            unique.append(item)
    return unique


def _plain_symptoms(symptoms: list[str]) -> list[str]:
    return [
        item
        for item in symptoms
        if isinstance(item, str) and not item.startswith(_SOURCE_SUMMARY_PREFIX)
    ]


def _coverage_limitations(coverage: dict[str, Any]) -> list[str]:
    count = int(coverage.get("available_count") or 0)
    available = coverage.get("available")
    missing: list[str] = []
    if isinstance(available, dict):
        missing = [key for key in _SOURCE_KEYS if available.get(key) is not True]

    limitations = [
        f"Kaynak kapsamı {count}/3; eksik kaynaklar birlikte değerlendirilmedi.",
        "Bu çıktı klinik karar desteğidir ve hekim değerlendirmesi gerektirir.",
    ]
    if missing:
        limitations.append("Eksik kaynaklar: " + ", ".join(missing) + ".")
    return limitations


def _source_only_fallback(flags: list[str], language: str) -> tuple[int, str]:
    if flags == [_SOURCE_ONLY_GATE]:
        if language.lower().startswith("tr"):
            return 1, "Sınırlı kaynak değerlendirildi; risk dışlanamaz, hekim doğrulaması gerekir."
        return 1, "Limited source reviewed; risk cannot be excluded and physician review is required."
    return ClaudeClinicalHypothesisService._fallback_output(flags, language)


async def generate_source_only_case(
    service: ClaudeClinicalHypothesisService,
    patient_id: uuid.UUID,
    request: ClinicalHypothesisGenerationRequest,
) -> ClinicalHypothesisGenerationResult:
    """Generate one compact patient-scoped evaluation without an analysis run."""

    metadata = dict(request.metadata_json or {})
    coverage = source_coverage(metadata)
    source_count = int(coverage["available_count"])
    if source_count == 0:
        return ClinicalHypothesisGenerationResult(
            analysis_run_id=None,
            lab_report_id=None,
            patient_id=patient_id,
            created_hypotheses=[],
            drafts_count=0,
            created_count=0,
            warnings=["AI skipped: no clinical, laboratory or ultrasound source was available."],
        )

    symptoms = list(service._extract_symptoms(metadata))
    vitals = dict(service._extract_vitals(metadata))
    flags = list(service._vital_flags(vitals))

    # Source-only evaluation is user-triggered. If no deterministic abnormal flag is
    # present, a neutral context-review gate lets the compact model summarize the
    # bounded source without pretending that the source itself is abnormal.
    if not flags:
        flags.append(_SOURCE_ONLY_GATE)
    flags = _dedupe(flags)[:20]

    warnings: list[str] = []
    ai_called = True
    try:
        response = await service._client.messages.create(
            model=service._model,
            max_tokens=service_module._MAX_OUTPUT_TOKENS,
            temperature=0,
            system=service_module._SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": service._build_user_prompt(
                                symptoms,
                                flags,
                                request.language,
                            ),
                        }
                    ],
                }
            ],
        )
        payload = service._safe_json(service._collect_text(response))
        if payload is None:
            risk, summary = _source_only_fallback(flags, request.language)
            warnings.append("Invalid compact AI JSON; deterministic fallback used.")
        else:
            risk, summary = service._parse_compact_output(
                payload,
                flags=flags,
                language=request.language,
            )
    except Exception:
        risk, summary = _source_only_fallback(flags, request.language)
        warnings.append("AI call failed; deterministic fallback used.")
        ai_called = False

    domains: list[dict[str, Any]] = []
    domain_router: dict[str, Any] = {}
    try:
        # Imported lazily to avoid a circular import while the runtime patches are
        # installed during application startup.
        from app.domain.clinical_domain_router_runtime import (
            ROUTER_VERSION,
            detect_clinical_domains,
        )

        domains = detect_clinical_domains([], metadata)
        domain_router = {
            "version": ROUTER_VERSION,
            "mode": "evidence_relevance_not_diagnosis",
            "active_domain_ids": sorted(
                str(item.get("id"))
                for item in domains
                if isinstance(item, dict) and item.get("id")
            ),
        }
    except Exception:
        # Routing metadata is additive. Failure to attach it must not turn a bounded
        # source-only evaluation into a server error.
        domains = []
        domain_router = {}

    severity = {1: "low", 2: "medium", 3: "high"}[risk]
    hypothesis = ClinicalHypothesis(
        patient_id=patient_id,
        lab_report_id=None,
        analysis_run_id=None,
        title="Kompakt AI risk özeti",
        summary=summary,
        hypothesis_type="compact_risk_summary",
        confidence=None,
        severity=severity,
        source="claude_compact_risk_summary",
        status="pending_review",
        needs_doctor_review=True,
        evidence_json=[],
        metadata_json={
            "risk": risk,
            "flags": flags,
            "symptoms": _plain_symptoms(symptoms),
            "possible_conditions": [],
            "recommended_laboratory_tests": [],
            "recommended_imaging_tests": [],
            "limitations": _coverage_limitations(coverage),
            "suggested_doctor_actions": ["approve", "edit", "request_extra_test"],
            "model": service._model,
            "generated_by": "claude" if ai_called else "deterministic_fallback",
            "ai_called": ai_called,
            "compact_mode": True,
            "max_output_tokens": service_module._MAX_OUTPUT_TOKENS,
            "evaluation_only": True,
            "requires_physician_review": True,
            "source_evaluation_scope": _SOURCE_ONLY_SCOPE,
            "source_coverage": coverage,
            "source_availability": coverage["available"],
            "source_dates": metadata.get("source_dates", {}),
            "performed_studies": metadata.get("performed_studies", []),
            "clinical_domains": domains,
            "clinical_domain_router": domain_router,
        },
    )
    service._hypotheses.create(hypothesis)
    await service._hypotheses.flush()

    return ClinicalHypothesisGenerationResult(
        analysis_run_id=None,
        lab_report_id=None,
        patient_id=patient_id,
        created_hypotheses=[ClinicalHypothesisResponse.model_validate(hypothesis)],
        drafts_count=1,
        created_count=1,
        warnings=warnings,
    )
