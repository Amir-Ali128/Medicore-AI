"""Clinical Fusion Brain v2 case adapter.

This module is intentionally deterministic. It converts already-structured signals
from MediCore subsystems into the stable Clinical Fusion v1 evidence contract, then
runs the existing dependency-aware fusion engine. It does not infer disease links
from free text, lab values, or model labels.
"""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable, Mapping

from app.domain.clinical_fusion_brain import evaluate_clinical_fusion
from app.schemas.clinical_fusion import ClinicalFusionEvidence, ClinicalFusionRequest
from app.schemas.clinical_fusion_case import (
    AIReaderCaseSignal,
    ClinicalCaseSignal,
    ClinicalFusionCaseRequest,
    ClinicalFusionCaseResult,
    ClinicalFusionGraphEdge,
    ClinicalFusionGraphNode,
    ImagingCaseSignal,
    LaboratoryCaseSignal,
    OnnxCaseRun,
)


_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slug(value: str) -> str:
    folded = " ".join(str(value or "").split()).casefold()
    slug = _SLUG_RE.sub("-", folded).strip("-")
    return slug[:80] or "finding"


def _metadata(base: Mapping[str, Any] | None, **extra: Any) -> dict[str, Any]:
    output = dict(base or {})
    for key, value in extra.items():
        if value is not None:
            output[key] = value
    return output


def _clinical_dependency(case_id: str, kind: str) -> str:
    if kind == "vital":
        return f"clinical-vitals:{case_id}"
    return f"clinical-case:{case_id}"


def _clinical_source_type(kind: str) -> str:
    if kind == "history":
        return "history"
    if kind == "vital":
        return "vital"
    return "clinical"


def _clinical_evidence(case_id: str, item: ClinicalCaseSignal) -> ClinicalFusionEvidence:
    return ClinicalFusionEvidence(
        id=item.id,
        finding_code=item.finding_code,
        label=item.label,
        source_type=_clinical_source_type(item.kind),
        source_name=item.source_name,
        dependency_group=_clinical_dependency(case_id, item.kind),
        polarity=item.polarity,
        strength=item.strength,
        confidence=item.confidence,
        severity=item.severity,
        hypothesis_codes=item.hypothesis_codes,
        observed_at=item.observed_at,
        location=item.location,
        value=item.value,
        unit=item.unit,
        metadata=_metadata(item.metadata, clinical_kind=item.kind, case_id=case_id),
    )


def _laboratory_evidence(
    case_id: str,
    item: LaboratoryCaseSignal,
) -> ClinicalFusionEvidence:
    group_id = item.report_id or case_id
    return ClinicalFusionEvidence(
        id=item.id,
        finding_code=item.finding_code,
        label=item.label,
        source_type="laboratory",
        source_name=item.source_name,
        dependency_group=f"laboratory:{group_id}",
        polarity=item.polarity,
        strength=item.strength,
        confidence=item.confidence,
        severity=item.severity,
        hypothesis_codes=item.hypothesis_codes,
        observed_at=item.observed_at,
        location=item.location,
        value=item.value,
        unit=item.unit,
        metadata=_metadata(item.metadata, report_id=item.report_id, case_id=case_id),
    )


def _imaging_evidence(item: ImagingCaseSignal) -> ClinicalFusionEvidence:
    source_type = "imaging" if item.kind == "primary" else "ai_detector"
    return ClinicalFusionEvidence(
        id=item.id,
        finding_code=item.finding_code,
        label=item.label,
        source_type=source_type,
        source_name=item.source_name,
        dependency_group=f"imaging-study:{item.study_id}",
        polarity=item.polarity,
        strength=item.strength,
        confidence=item.confidence,
        severity=item.severity,
        hypothesis_codes=item.hypothesis_codes,
        observed_at=item.observed_at,
        location=item.location,
        value=item.value,
        unit=item.unit,
        model_id=item.model_id,
        metadata=_metadata(item.metadata, study_id=item.study_id, imaging_kind=item.kind),
    )


def _ai_reader_evidence(item: AIReaderCaseSignal) -> ClinicalFusionEvidence:
    return ClinicalFusionEvidence(
        id=item.id,
        finding_code=item.finding_code,
        label=item.label,
        source_type="ai_reader",
        source_name=item.provider,
        dependency_group=f"imaging-study:{item.study_id}",
        polarity=item.polarity,
        strength=item.strength,
        confidence=item.confidence,
        severity=item.severity,
        hypothesis_codes=item.hypothesis_codes,
        observed_at=item.observed_at,
        location=item.location,
        value=item.value,
        unit=item.unit,
        model_id=item.model_id,
        metadata=_metadata(
            item.metadata,
            study_id=item.study_id,
            provider=item.provider,
        ),
    )


def _lookup_casefold(mapping: Mapping[str, Any], label: str, default: Any) -> Any:
    target = label.casefold()
    for key, value in mapping.items():
        if str(key).casefold() == target:
            return value
    return default


def evidence_from_onnx_run(run: OnnxCaseRun) -> tuple[list[ClinicalFusionEvidence], list[str]]:
    """Adapt one real ONNX classifier run into dependency-aware evidence.

    Important: a below-threshold score is *not* interpreted as evidence that a
    condition is absent. It is emitted as uncertain evidence. This avoids turning a
    classifier threshold into an unvalidated negative diagnostic rule.
    """

    output: list[ClinicalFusionEvidence] = []
    warnings: list[str] = []
    for index, finding in enumerate(run.findings):
        hypotheses = list(
            _lookup_casefold(run.hypothesis_map, finding.label, []) or []
        )
        location = _lookup_casefold(run.location_by_label, finding.label, None)
        severity = _lookup_casefold(
            run.severity_by_label,
            finding.label,
            "moderate",
        )
        polarity = "support" if finding.above_threshold else "uncertain"
        if finding.above_threshold and not hypotheses:
            warnings.append(
                f"ONNX finding '{finding.label}' is above threshold but has no explicit hypothesis mapping."
            )

        output.append(
            ClinicalFusionEvidence(
                id=f"onnx:{run.run_id}:{index}:{_slug(finding.label)}",
                finding_code=finding.label,
                label=finding.label,
                source_type="ai_detector",
                source_name=f"onnx:{run.model_id}",
                dependency_group=f"imaging-study:{run.study_id}",
                polarity=polarity,
                strength=1.0,
                # The model score affects deterministic evidence weight but remains
                # explicitly labeled as a model score, not a disease probability.
                confidence=finding.score,
                severity=severity,
                hypothesis_codes=hypotheses,
                location=location,
                value=finding.score,
                model_id=run.model_id,
                metadata=_metadata(
                    run.metadata,
                    study_id=run.study_id,
                    run_id=run.run_id,
                    model_version=run.model_version,
                    model_score=finding.score,
                    threshold=finding.threshold,
                    above_threshold=finding.above_threshold,
                    score_semantics="model_score_not_disease_probability",
                ),
            )
        )
    return output, warnings


def normalize_case_evidence(
    request: ClinicalFusionCaseRequest,
) -> tuple[list[ClinicalFusionEvidence], list[str]]:
    evidence: list[ClinicalFusionEvidence] = []
    warnings: list[str] = []

    evidence.extend(_clinical_evidence(request.case_id, item) for item in request.clinical_signals)
    evidence.extend(
        _laboratory_evidence(request.case_id, item)
        for item in request.laboratory_signals
    )
    evidence.extend(_imaging_evidence(item) for item in request.imaging_signals)
    evidence.extend(_ai_reader_evidence(item) for item in request.ai_reader_signals)

    for run in request.onnx_runs:
        adapted, run_warnings = evidence_from_onnx_run(run)
        evidence.extend(adapted)
        warnings.extend(run_warnings)

    # IDs from direct signals are validated by the case schema. Generated ONNX IDs
    # are checked here as a final fail-closed contract guard.
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in evidence:
        key = item.id.casefold()
        if key in seen and item.id not in duplicates:
            duplicates.append(item.id)
        seen.add(key)
    if duplicates:
        raise ValueError(f"Normalized evidence IDs are not unique: {duplicates[:5]}")

    return evidence, warnings


def _auto_source_availability(
    request: ClinicalFusionCaseRequest,
) -> dict[str, bool]:
    availability = {
        "clinical": bool(request.clinical_signals),
        "laboratory": bool(request.laboratory_signals),
        "imaging": bool(
            request.imaging_signals or request.ai_reader_signals or request.onnx_runs
        ),
        "ai": bool(
            request.ai_reader_signals
            or request.onnx_runs
            or any(item.kind == "detector" for item in request.imaging_signals)
        ),
    }
    # Explicit caller values are authoritative, including False.
    availability.update(request.source_availability)
    return availability


def _graph(
    request: ClinicalFusionCaseRequest,
    evidence: Iterable[ClinicalFusionEvidence],
) -> tuple[list[ClinicalFusionGraphNode], list[ClinicalFusionGraphEdge]]:
    nodes: list[ClinicalFusionGraphNode] = []
    edges: list[ClinicalFusionGraphEdge] = []
    seen_nodes: set[str] = set()

    def add_node(node: ClinicalFusionGraphNode) -> None:
        if node.id not in seen_nodes:
            nodes.append(node)
            seen_nodes.add(node.id)

    for candidate in request.candidates:
        add_node(
            ClinicalFusionGraphNode(
                id=f"candidate:{candidate.code}",
                kind="candidate",
                label=candidate.display_name,
            )
        )

    for item in evidence:
        evidence_node = f"evidence:{item.id}"
        dependency = item.dependency_group or "ungrouped"
        dependency_node = f"dependency:{dependency}"
        add_node(
            ClinicalFusionGraphNode(
                id=evidence_node,
                kind="evidence",
                label=item.label,
                source_type=item.source_type,
                polarity=item.polarity,
            )
        )
        add_node(
            ClinicalFusionGraphNode(
                id=dependency_node,
                kind="dependency_group",
                label=dependency,
            )
        )
        edges.append(
            ClinicalFusionGraphEdge(
                source=evidence_node,
                target=dependency_node,
                relation="member_of",
            )
        )
        relation = {
            "support": "supports",
            "oppose": "opposes",
            "uncertain": "uncertain_for",
        }[item.polarity]
        for code in item.hypothesis_codes:
            edges.append(
                ClinicalFusionGraphEdge(
                    source=evidence_node,
                    target=f"candidate:{code}",
                    relation=relation,
                )
            )
    return nodes, edges


def evaluate_clinical_case_fusion(
    request: ClinicalFusionCaseRequest,
) -> ClinicalFusionCaseResult:
    evidence, adapter_warnings = normalize_case_evidence(request)
    source_availability = _auto_source_availability(request)

    fusion_request = ClinicalFusionRequest(
        candidates=request.candidates,
        evidence=evidence,
        source_availability=source_availability,
        language=request.language,
    )
    fusion = evaluate_clinical_fusion(fusion_request)
    graph_nodes, graph_edges = _graph(request, evidence)

    counts = dict(Counter(item.source_type for item in evidence))
    supported = [item for item in evidence if item.polarity == "support"]
    if fusion.critical_signal_ids:
        review_priority = "critical"
    elif any(item.severity == "high" for item in supported):
        review_priority = "priority"
    else:
        review_priority = "routine"

    return ClinicalFusionCaseResult(
        fusion=fusion,
        normalized_evidence=evidence,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        source_evidence_counts=counts,
        review_priority=review_priority,
        needs_conflict_review=bool(fusion.disagreements),
        adapter_warnings=adapter_warnings,
    )
