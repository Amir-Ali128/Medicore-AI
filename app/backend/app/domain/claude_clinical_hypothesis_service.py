"""ClaudeClinicalHypothesisService.

Uses Claude ONLY to generate doctor-reviewable clinical hypotheses from lab
results that were already structured and classified deterministically. It never
produces a final diagnosis, never recommends treatment or medication, never
produces patient-facing interpretation, never alters lab results or statuses,
and never approves anything. Every generated hypothesis is persisted as
pending_review / needs_doctor_review=True and awaits a physician action
(Module H). The service does not commit — the caller (route) owns the
transaction.

Safety guards before persistence:
  * evidence must link to a real LabResult id from THIS analysis run,
  * drafts failing the confidence policy are skipped,
  * drafts containing final-diagnosis / treatment / medication language are
    skipped,
  * persisted summaries are normalized into cautious physician-review wording.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.domain.enums import ResultStatus
from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
from app.infrastructure.database.repositories.analysis_run_repository import (
    AnalysisRunRepository,
)
from app.infrastructure.database.repositories.clinical_hypothesis_repository import (
    ClinicalHypothesisRepository,
)
from app.infrastructure.database.repositories.lab_result_repository import (
    LabResultRepository,
)
from app.schemas.clinical_copilot import (
    ClinicalHypothesisDraft,
    ClinicalHypothesisEvidenceDraft,
    ClinicalHypothesisGenerationRequest,
    ClinicalHypothesisGenerationResult,
)
from app.schemas.clinical_hypothesis import ClinicalHypothesisResponse

_MAX_TOKENS = 8192
_HYPOTHESIS_SOURCE = "claude_clinical_hypothesis"
_PENDING_REVIEW_STATUS = "pending_review"
_DOCTOR_REVIEW_QUEUE = "doctor_review"

# Doctor actions the copilot may suggest (mapped to Module H ReviewAction).
_ALLOWED_DOCTOR_ACTIONS: frozenset[str] = frozenset(
    {"approve", "reject", "edit", "request_extra_test", "refer_specialist"}
)

# Final-diagnosis / treatment / medication language that must never be persisted.
_BLOCKED_PHRASES: tuple[str, ...] = (
    "diagnosed with",
    "the patient has",
    "treat with",
    "start medication",
    "prescribe",
    "you should",
    "take medication",
    "final diagnosis",
    "kesin tanı",
    "tanısı konmuştur",
    "tedavi başlanmalı",
    "ilaç başlanmalı",
    "reçete edilmeli",
)

_SYSTEM_PROMPT = (
    "You are assisting a licensed physician. You generate clinical hypotheses "
    "for physician review only. You must not produce final diagnoses. You must "
    "not recommend treatment or medication. You must not invent facts or lab "
    "values. You must use only the provided structured lab results. Every "
    "hypothesis must include evidence linked to the provided lab results. If "
    "evidence is insufficient, return no hypothesis or include clear "
    "limitations. Use cautious wording such as 'may be considered', 'pattern "
    "may be compatible with', 'requires physician review', and 'evidence is "
    "limited'. Never use wording such as 'the patient has', 'diagnosed with', "
    "'treat with', 'start medication', or 'you should'. Return only valid JSON."
)


class ClaudeClinicalHypothesisService:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        lab_result_repository: LabResultRepository,
        clinical_hypothesis_repository: ClinicalHypothesisRepository,
        analysis_run_repository: AnalysisRunRepository,
    ) -> None:
        if not model:
            raise ValueError("CLAUDE_HYPOTHESIS_MODEL is not configured.")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")

        from anthropic import AsyncAnthropic  # lazy import

        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)
        self._lab_results = lab_result_repository
        self._hypotheses = clinical_hypothesis_repository
        self._runs = analysis_run_repository

    async def generate_for_analysis_run(
        self,
        analysis_run_id: uuid.UUID,
        request: ClinicalHypothesisGenerationRequest,
    ) -> ClinicalHypothesisGenerationResult:
        run = await self._runs.get_by_id(analysis_run_id)
        if run is None:
            raise ValueError("Analysis run not found.")

        results = list(await self._lab_results.list_for_analysis_run(analysis_run_id))
        if not results:
            return self._empty_result(
                analysis_run_id, run, ["No lab results found for this analysis run."]
            )

        # Whitelist of real LabResult ids for THIS analysis run.
        allowed_ids: set[str] = {str(r.id) for r in results}

        prompt_results = [
            r
            for r in results
            if request.include_normal_results or r.result_status != ResultStatus.NORMAL
        ]

        user_prompt = self._build_user_prompt(run, prompt_results, request)
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": [{"type": "text", "text": user_prompt}]}
            ],
        )

        payload = self._safe_json(self._collect_text(response))
        if payload is None:
            return self._empty_result(
                analysis_run_id,
                run,
                ["Failed to parse Claude hypothesis output as JSON."],
            )

        raw_hypotheses = payload.get("hypotheses")
        if not isinstance(raw_hypotheses, list):
            raw_hypotheses = []
        warnings: list[str] = [
            str(w) for w in payload.get("warnings", []) if w is not None
        ]

        created: list[ClinicalHypothesis] = []
        for raw in raw_hypotheses:
            if len(created) >= request.max_hypotheses:
                break

            try:
                draft = ClinicalHypothesisDraft.model_validate(raw)
            except ValidationError:
                warnings.append("Skipped an invalid hypothesis draft.")
                continue

            # --- Issue 2: confidence policy ------------------------------
            if request.min_confidence is not None:
                if draft.confidence is None:
                    warnings.append(
                        "Skipped a hypothesis without confidence below the "
                        "requested confidence policy."
                    )
                    continue
                if draft.confidence < request.min_confidence:
                    warnings.append(
                        "Skipped a hypothesis below the requested minimum confidence."
                    )
                    continue

            # --- Issue 1: evidence must link to real LabResult ids -------
            valid_evidence: list[ClinicalHypothesisEvidenceDraft] = []
            for item in draft.evidence:
                if (
                    item.lab_result_id is not None
                    and str(item.lab_result_id) in allowed_ids
                ):
                    valid_evidence.append(item)
                else:
                    warnings.append(
                        "Discarded evidence not linked to a lab result from this "
                        "analysis run."
                    )
            if not valid_evidence:
                warnings.append(
                    "Skipped a hypothesis without valid linked lab-result evidence."
                )
                continue

            # --- Issue 3: output safety guard ----------------------------
            if self._contains_blocked_language(draft, valid_evidence):
                warnings.append(
                    "Skipped a hypothesis containing final-diagnosis or "
                    "treatment/medication language."
                )
                continue

            hypothesis = self._build_hypothesis(
                run,
                draft,
                valid_evidence,
                language=request.language,
            )
            self._hypotheses.create(hypothesis)
            created.append(hypothesis)

        await self._hypotheses.flush()

        return ClinicalHypothesisGenerationResult(
            analysis_run_id=analysis_run_id,
            lab_report_id=run.lab_report_id,
            patient_id=run.patient_id,
            created_hypotheses=[
                ClinicalHypothesisResponse.model_validate(h) for h in created
            ],
            drafts_count=len(raw_hypotheses),
            created_count=len(created),
            warnings=warnings,
        )

    # -- persistence -----------------------------------------------------
    def _build_hypothesis(
        self,
        run: Any,
        draft: ClinicalHypothesisDraft,
        evidence: list[ClinicalHypothesisEvidenceDraft],
        *,
        language: str,
    ) -> ClinicalHypothesis:
        allowed_actions = [
            action
            for action in draft.suggested_doctor_actions
            if action in _ALLOWED_DOCTOR_ACTIONS
        ]
        if "approve" not in allowed_actions:
            allowed_actions.insert(0, "approve")

        return ClinicalHypothesis(
            patient_id=run.patient_id,
            lab_report_id=run.lab_report_id,
            analysis_run_id=run.id,
            title=draft.title,
            summary=self._build_review_summary(draft, language),
            hypothesis_type=draft.hypothesis_type,
            confidence=draft.confidence,
            severity=draft.severity,
            source=_HYPOTHESIS_SOURCE,
            status=_PENDING_REVIEW_STATUS,
            needs_doctor_review=True,
            evidence_json=[item.model_dump(mode="json") for item in evidence],
            metadata_json={
                "limitations": list(draft.limitations),
                "suggested_doctor_actions": allowed_actions,
                "model": self._model,
                "generated_by": "claude",
                "approval_queue": _DOCTOR_REVIEW_QUEUE,
                "approval_status": _PENDING_REVIEW_STATUS,
                "requires_physician_approval": True,
                "display_language": language,
            },
        )

    @staticmethod
    def _build_review_summary(
        draft: ClinicalHypothesisDraft,
        language: str,
    ) -> str:
        title = draft.title.strip().rstrip(".") or "klinik bir olasılık"
        original_summary = draft.summary.strip()
        normalized_language = (language or "tr").strip().lower()

        if normalized_language.startswith("tr"):
            opening = f"Bu hastada {title} düşünülebilir."
            closing = (
                "Bu değerlendirme kesin tanı değildir; doktor değerlendirmesi "
                "ve onayı gerekir."
            )
        else:
            opening = f"In this patient, {title} may be considered."
            closing = (
                "This is not a final diagnosis and requires physician review "
                "and approval."
            )

        parts = [opening]
        if original_summary and original_summary.casefold() != opening.casefold():
            parts.append(original_summary)
        parts.append(closing)
        return " ".join(parts)

    # -- guards ----------------------------------------------------------
    @staticmethod
    def _contains_blocked_language(
        draft: ClinicalHypothesisDraft,
        evidence: list[ClinicalHypothesisEvidenceDraft],
    ) -> bool:
        fragments: list[str] = [draft.title, draft.summary]
        fragments.extend(draft.limitations)
        fragments.extend(draft.suggested_doctor_actions)
        fragments.extend(item.note for item in evidence if item.note)
        haystack = " \n ".join(f for f in fragments if f).lower()
        return any(phrase in haystack for phrase in _BLOCKED_PHRASES)

    # -- prompt / parsing helpers ---------------------------------------
    def _build_user_prompt(
        self,
        run: Any,
        results: list[Any],
        request: ClinicalHypothesisGenerationRequest,
    ) -> str:
        lab_results = [
            {
                "lab_result_id": str(r.id),
                "raw_parameter_name": r.raw_parameter_name,
                "parameter_code": r.parameter_code,
                "canonical_name": r.canonical_name,
                "normalized_value": self._num(r.normalized_value),
                "unit": r.unit,
                "reference_min": self._num(r.reference_min),
                "reference_max": self._num(r.reference_max),
                "result_status": r.result_status.value if r.result_status else None,
                "trend_status": r.trend_status.value if r.trend_status else None,
                "needs_review": r.needs_review,
                "reason": r.reason,
            }
            for r in results
        ]
        context = {
            "analysis_run_id": str(run.id),
            "patient_id": str(run.patient_id),
            "lab_report_id": str(run.lab_report_id) if run.lab_report_id else None,
            "max_hypotheses": request.max_hypotheses,
            "language": request.language,
            "lab_results": lab_results,
        }

        language_instruction = (
            "When language is Turkish, use a concise possible condition/pattern "
            "as the title and write the summary in Turkish. Phrase it cautiously "
            "as a possibility for this patient, for example: 'Bu hastada <başlık> "
            "düşünülebilir.' End by stating that physician review and approval are "
            "required. Never state that the patient definitely has a condition. "
        )

        instructions = (
            "Generate clinical hypotheses for physician review only, using ONLY "
            "the lab_results below. Do not diagnose, do not recommend treatment "
            "or medication, do not write patient-facing text. Each hypothesis "
            "must cite evidence referencing lab_result_id values from the input. "
            + language_instruction
            + "suggested_doctor_actions may only contain: approve, reject, edit, "
            "request_extra_test, refer_specialist.\n"
            "Return ONLY valid JSON (no markdown) in EXACTLY this shape:\n"
            "{\n"
            '  "hypotheses": [\n'
            "    {\n"
            '      "title": string, "summary": string,\n'
            '      "hypothesis_type": string | null, "confidence": number | null,\n'
            '      "severity": string | null,\n'
            '      "evidence": [ {"lab_result_id": string | null, '
            '"parameter_code": string | null, "parameter_name": string | null, '
            '"value": string | null, "unit": string | null, '
            '"result_status": string | null, "trend_status": string | null, '
            '"note": string | null} ],\n'
            '      "limitations": [string],\n'
            '      "suggested_doctor_actions": [string]\n'
            "    }\n"
            "  ],\n"
            '  "warnings": [string]\n'
            "}\n\n"
            "INPUT:\n"
        )
        return instructions + json.dumps(context, ensure_ascii=False)

    # -- small helpers ---------------------------------------------------
    def _empty_result(
        self, analysis_run_id: uuid.UUID, run: Any, warnings: list[str]
    ) -> ClinicalHypothesisGenerationResult:
        return ClinicalHypothesisGenerationResult(
            analysis_run_id=analysis_run_id,
            lab_report_id=run.lab_report_id,
            patient_id=run.patient_id,
            created_hypotheses=[],
            drafts_count=0,
            created_count=0,
            warnings=warnings,
        )

    @staticmethod
    def _num(value: Decimal | None) -> str | None:
        return str(value) if value is not None else None

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
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
