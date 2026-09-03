"""Deterministic multi-source Clinical Fusion Brain.

The fusion layer combines already-normalized evidence from clinical history/exam,
laboratory data, medical imaging/localization, and AI readers. It deliberately does
not estimate disease probability and does not issue a diagnosis. Its score is only a
rankable evidence-compatibility score for physician review.

A central design rule is dependency-aware aggregation: multiple AI models reading the
same image are correlated evidence and must not be counted as four independent sources.
Callers can set ``dependency_group`` explicitly (recommended). Conservative defaults
are used when they do not.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.schemas.clinical_fusion import (
    ClinicalFusionCandidate,
    ClinicalFusionCandidateResult,
    ClinicalFusionDisagreement,
    ClinicalFusionEvidence,
    ClinicalFusionRequest,
    ClinicalFusionResult,
)

_CONTRACT_VERSION = "clinical-fusion-v1"
_AI_TYPES = {"ai_detector", "ai_reader"}
_CLINICAL_TYPES = {"clinical", "history", "vital"}
_CORE_SOURCE_TYPES = {"clinical", "laboratory", "imaging"}

# These are fusion weights, not claims of clinical accuracy or calibrated likelihood.
# AI-derived evidence is intentionally down-weighted because multiple models may share
# training data, prompts, and the same underlying image.
_SOURCE_WEIGHTS: dict[str, float] = {
    "clinical": 1.00,
    "history": 0.95,
    "vital": 1.00,
    "laboratory": 1.05,
    "imaging": 1.10,
    "ai_detector": 0.75,
    "ai_reader": 0.60,
    "other": 0.70,
}

_LEVEL_RANK = {
    "very_low": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
    "very_high": 4,
}


def _key(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _dependency_group(item: ClinicalFusionEvidence) -> str:
    if item.dependency_group:
        return item.dependency_group

    study_id = item.metadata.get("study_id") if isinstance(item.metadata, dict) else None
    if study_id and item.source_type in {"imaging", "ai_detector", "ai_reader"}:
        return f"imaging-study:{study_id}"
    if item.source_type in {"clinical", "history"}:
        return "clinical-history-exam"
    if item.source_type == "vital":
        return "clinical-vitals"
    if item.source_type == "laboratory":
        return "laboratory"
    if item.source_type == "imaging":
        return "imaging-primary"
    if item.source_type in _AI_TYPES:
        return "imaging-ai-readers"
    return f"other:{_key(item.source_name) or 'source'}"


def _evidence_weight(item: ClinicalFusionEvidence) -> float:
    base = _SOURCE_WEIGHTS[item.source_type]
    return max(0.0, min(1.35, base * item.strength * item.confidence))


def _dedupe_evidence(items: Iterable[ClinicalFusionEvidence]) -> list[ClinicalFusionEvidence]:
    """Keep only the strongest exact duplicate inside one source/dependency group."""

    strongest: dict[tuple[str, str, str, str], ClinicalFusionEvidence] = {}
    for item in items:
        dedupe_key = (
            _key(_dependency_group(item)),
            _key(item.source_name),
            _key(item.finding_code),
            item.polarity,
        )
        existing = strongest.get(dedupe_key)
        if existing is None or _evidence_weight(item) > _evidence_weight(existing):
            strongest[dedupe_key] = item
    return list(strongest.values())


def _group_strength(items: Iterable[ClinicalFusionEvidence]) -> tuple[float, int]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for item in items:
        grouped[_dependency_group(item)].append(_evidence_weight(item))

    total = 0.0
    nonempty = 0
    for weights in grouped.values():
        weights.sort(reverse=True)
        if not weights:
            continue
        nonempty += 1
        # Correlated evidence gets diminishing returns and a hard per-group cap.
        group_value = weights[0] + 0.20 * sum(weights[1:])
        total += min(1.35, group_value)
    return total, nonempty


def _raw_level(score: float) -> str:
    if score >= 80:
        return "very_high"
    if score >= 65:
        return "high"
    if score >= 45:
        return "moderate"
    if score >= 25:
        return "low"
    return "very_low"


def _cap_level(level: str, maximum: str) -> str:
    if _LEVEL_RANK[level] <= _LEVEL_RANK[maximum]:
        return level
    return maximum


def _level_label(level: str, language: str) -> str:
    if language.lower().startswith("tr"):
        return {
            "very_low": "Çok düşük kanıt uyumu",
            "low": "Düşük kanıt uyumu",
            "moderate": "Orta kanıt uyumu",
            "high": "Yüksek kanıt uyumu",
            "very_high": "Çok yüksek kanıt uyumu",
        }[level]
    return {
        "very_low": "Very low evidence compatibility",
        "low": "Low evidence compatibility",
        "moderate": "Moderate evidence compatibility",
        "high": "High evidence compatibility",
        "very_high": "Very high evidence compatibility",
    }[level]


def _core_source_name(source_type: str) -> str | None:
    if source_type in _CLINICAL_TYPES:
        return "clinical"
    if source_type == "laboratory":
        return "laboratory"
    if source_type in {"imaging", "ai_detector", "ai_reader"}:
        return "imaging"
    return None


def _coverage(request: ClinicalFusionRequest) -> tuple[dict[str, bool], bool]:
    observed = {"clinical": False, "laboratory": False, "imaging": False}
    ai_available = False
    for item in request.evidence:
        core = _core_source_name(item.source_type)
        if core:
            observed[core] = True
        if item.source_type in _AI_TYPES:
            ai_available = True

    for key in tuple(observed):
        if key in request.source_availability:
            observed[key] = request.source_availability[key] is True
    if "ai" in request.source_availability:
        ai_available = request.source_availability["ai"] is True
    return observed, ai_available


def _candidate_summary(
    support_groups: int,
    oppose_groups: int,
    uncertain_count: int,
    language: str,
) -> str:
    if language.lower().startswith("tr"):
        parts = [f"{support_groups} bağımsız kanıt grubu destekliyor"]
        if oppose_groups:
            parts.append(f"{oppose_groups} karşıt kanıt grubu var")
        if uncertain_count:
            parts.append(f"{uncertain_count} belirsiz kanıt var")
        return "; ".join(parts) + ". Hekim doğrulaması gerekir."
    parts = [f"{support_groups} independent evidence group(s) support this possibility"]
    if oppose_groups:
        parts.append(f"{oppose_groups} opposing group(s) are present")
    if uncertain_count:
        parts.append(f"{uncertain_count} uncertain item(s) are present")
    return "; ".join(parts) + ". Physician verification is required."


def _limitations(
    *,
    support: list[ClinicalFusionEvidence],
    oppose: list[ClinicalFusionEvidence],
    uncertain: list[ClinicalFusionEvidence],
    support_groups: int,
    core_coverage: dict[str, bool],
    language: str,
) -> list[str]:
    tr = language.lower().startswith("tr")
    limitations: list[str] = []
    if not support:
        limitations.append(
            "Bu olasılığa bağlı destekleyici kanıt yok."
            if tr
            else "No supporting evidence is linked to this possibility."
        )
    if support_groups == 1 and support:
        limitations.append(
            "Destek tek bağımsız kanıt grubundan geliyor; çapraz kaynak doğrulaması yok."
            if tr
            else "Support comes from one independent evidence group; cross-source corroboration is absent."
        )
    if support and all(item.source_type in _AI_TYPES for item in support):
        limitations.append(
            "Destek yalnızca AI okuyuculardan geliyor; temel klinik/lab/görüntüleme kanıtı ile doğrulanmadı."
            if tr
            else "Support comes only from AI readers and is not corroborated by primary clinical/lab/imaging evidence."
        )
    if oppose:
        limitations.append(
            "Karşıt kanıt mevcut; otomatik uzlaştırma yapılmadı."
            if tr
            else "Contradictory evidence is present; it was not automatically reconciled."
        )
    if uncertain:
        limitations.append(
            "Belirsiz/yorumlanamayan kanıtlar puanı destekleyici kanıt olarak artırmadı."
            if tr
            else "Uncertain/unassessable evidence did not increase the support score."
        )
    missing = [key for key, available in core_coverage.items() if not available]
    if missing:
        limitations.append(
            ("Eksik temel kaynaklar: " if tr else "Missing core sources: ")
            + ", ".join(missing)
            + "."
        )
    return limitations[:8]


def _disagreements_for_candidate(
    candidate: ClinicalFusionCandidate,
    linked: list[ClinicalFusionEvidence],
    language: str,
) -> list[ClinicalFusionDisagreement]:
    support = [item for item in linked if item.polarity == "support"]
    oppose = [item for item in linked if item.polarity == "oppose"]
    if not support or not oppose:
        return []

    tr = language.lower().startswith("tr")
    output: list[ClinicalFusionDisagreement] = [
        ClinicalFusionDisagreement(
            kind="cross_source_conflict",
            hypothesis_code=candidate.code,
            evidence_ids=[item.id for item in support + oppose],
            detail=(
                "Aynı olasılık için hem destekleyici hem karşıt kanıt bulundu."
                if tr
                else "Both supporting and opposing evidence were found for the same possibility."
            ),
        )
    ]

    ai_support = [item for item in support if item.source_type in _AI_TYPES]
    ai_oppose = [item for item in oppose if item.source_type in _AI_TYPES]
    if ai_support and ai_oppose:
        output.append(
            ClinicalFusionDisagreement(
                kind="ai_model_disagreement",
                hypothesis_code=candidate.code,
                evidence_ids=[item.id for item in ai_support + ai_oppose],
                detail=(
                    "AI okuyucular aynı olasılıkta birbiriyle çelişiyor."
                    if tr
                    else "AI readers disagree on the same possibility."
                ),
            )
        )

    primary_support = [item for item in support if item.source_type not in _AI_TYPES]
    primary_oppose = [item for item in oppose if item.source_type not in _AI_TYPES]
    if (ai_support and primary_oppose) or (ai_oppose and primary_support):
        involved = ai_support + ai_oppose + primary_support + primary_oppose
        output.append(
            ClinicalFusionDisagreement(
                kind="ai_vs_primary_evidence",
                hypothesis_code=candidate.code,
                evidence_ids=[item.id for item in involved],
                detail=(
                    "AI görüşü ile birincil klinik/lab/görüntüleme kanıtı arasında çelişki var."
                    if tr
                    else "AI opinion conflicts with primary clinical/lab/imaging evidence."
                ),
            )
        )
    return output


def evaluate_clinical_fusion(request: ClinicalFusionRequest) -> ClinicalFusionResult:
    """Fuse normalized evidence into deterministic, physician-reviewable rankings."""

    candidate_by_key = {_key(item.code): item for item in request.candidates}
    evidence = _dedupe_evidence(request.evidence)
    core_coverage, ai_available = _coverage(request)
    core_count = sum(1 for value in core_coverage.values() if value)
    completeness = round(core_count * 100 / 3)

    linked_by_candidate: dict[str, list[ClinicalFusionEvidence]] = defaultdict(list)
    unmapped: list[str] = []
    for item in evidence:
        for code in item.hypothesis_codes:
            normalized = _key(code)
            if normalized in candidate_by_key:
                linked_by_candidate[normalized].append(item)
            elif code not in unmapped:
                unmapped.append(code)

    results: list[ClinicalFusionCandidateResult] = []
    disagreements: list[ClinicalFusionDisagreement] = []
    for normalized_code, candidate in candidate_by_key.items():
        linked = linked_by_candidate.get(normalized_code, [])
        support = [item for item in linked if item.polarity == "support"]
        oppose = [item for item in linked if item.polarity == "oppose"]
        uncertain = [item for item in linked if item.polarity == "uncertain"]

        support_strength, support_groups = _group_strength(support)
        oppose_strength, oppose_groups = _group_strength(oppose)
        diversity_bonus = min(0.60, 0.20 * max(0, support_groups - 1))

        if support_strength <= 0:
            score = 0.0
        else:
            numerator = support_strength + diversity_bonus
            denominator = numerator + 0.90 * oppose_strength + 1.0
            score = 100.0 * numerator / denominator
        score = round(max(0.0, min(100.0, score)), 1)

        level = _raw_level(score)
        # A single dependency group can be useful, but it cannot become high confidence.
        if support_groups <= 1:
            level = _cap_level(level, "moderate")
        if support and all(item.source_type in _AI_TYPES for item in support):
            level = _cap_level(level, "moderate")

        support_core_types = {
            _core_source_name(item.source_type)
            for item in support
            if _core_source_name(item.source_type) in _CORE_SOURCE_TYPES
        }
        contradiction_ratio = (
            oppose_strength / (support_strength + oppose_strength)
            if support_strength + oppose_strength > 0
            else 0.0
        )
        if contradiction_ratio >= 0.35:
            level = _cap_level(level, "moderate")
        if level == "very_high" and (
            support_groups < 3 or len(support_core_types) < 2 or oppose_strength >= 0.30
        ):
            level = "high"

        source_types = sorted({item.source_type for item in support})
        result = ClinicalFusionCandidateResult(
            code=candidate.code,
            display_name=candidate.display_name,
            category=candidate.category,
            compatibility_score=score,
            compatibility_level=level,
            level_label=_level_label(level, request.language),
            support_strength=round(support_strength, 3),
            oppose_strength=round(oppose_strength, 3),
            support_group_count=support_groups,
            oppose_group_count=oppose_groups,
            supporting_evidence_ids=[item.id for item in support],
            contradicting_evidence_ids=[item.id for item in oppose],
            uncertain_evidence_ids=[item.id for item in uncertain],
            supporting_source_types=source_types,
            limitations=_limitations(
                support=support,
                oppose=oppose,
                uncertain=uncertain,
                support_groups=support_groups,
                core_coverage=core_coverage,
                language=request.language,
            ),
            summary=_candidate_summary(
                support_groups,
                oppose_groups,
                len(uncertain),
                request.language,
            ),
        )
        results.append(result)
        disagreements.extend(
            _disagreements_for_candidate(candidate, linked, request.language)
        )

    results.sort(
        key=lambda item: (
            item.compatibility_score,
            item.support_group_count,
            -item.oppose_strength,
            item.display_name.casefold(),
        ),
        reverse=True,
    )

    critical_signal_ids = [
        item.id
        for item in evidence
        if item.severity == "critical" and item.polarity == "support"
    ]
    warnings: list[str] = []
    if unmapped:
        warnings.append(
            "Some evidence referenced hypothesis codes that were not supplied as candidates."
        )
    if not evidence:
        warnings.append("No evidence was supplied; all compatibility scores are zero.")

    disclaimer = (
        "Bu skor olasılık/tanı yüzdesi değildir; yalnızca kaynaklar arası deterministik kanıt uyumudur. Hekim değerlendirmesi zorunludur."
        if request.language.lower().startswith("tr")
        else "This is not a diagnostic probability; it is deterministic cross-source evidence compatibility. Physician review is required."
    )

    return ClinicalFusionResult(
        contract_version=_CONTRACT_VERSION,
        candidates=results,
        critical_signal_ids=critical_signal_ids,
        disagreements=disagreements,
        core_source_coverage=core_coverage,
        core_source_count=core_count,
        data_completeness_percent=completeness,
        ai_reader_available=ai_available,
        unmapped_hypothesis_codes=unmapped,
        warnings=warnings,
        disclaimer=disclaimer,
    )
