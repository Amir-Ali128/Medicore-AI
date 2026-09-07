"""ReferenceResolver.

Database I/O remains in Python. Candidate compatibility, specificity and ambiguity
selection prefer the native C++ deterministic core when its contract is available.
The original Python selector remains as a safe fallback for rolling deploys and for
fractional-age bands that the current native v1 integer-age contract does not yet
represent exactly.

Priority:
    1. extracted / report range
    2. demographic database range
    3. generic database range
    4. identical demographic fallback
    5. needs review

This service selects a range only. It does not diagnose or add clinical meaning.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.domain.enums import Sex
from app.infrastructure.database.models.reference_range import ReferenceRange
from app.infrastructure.database.repositories.clinical_parameter_repository import (
    ClinicalParameterRepository,
)
from app.infrastructure.database.repositories.reference_range_repository import (
    ReferenceRangeRepository,
)
from app.schemas.analysis import (
    ReferenceResolutionRequest,
    ReferenceResolutionResult,
    ReferenceStrategy,
)

CONF_EXTRACTED_FULL = 0.98
CONF_EXTRACTED_PARTIAL = 0.70
CONF_DEMOGRAPHIC = 0.90
CONF_DEMOGRAPHIC_AMBIGUOUS = 0.70
CONF_DEFAULT = 0.60
CONF_IDENTICAL_DEMOGRAPHIC_FALLBACK = 0.85

_EXTRACTED_SOURCE = "extracted_report"


class ReferenceResolver:
    def __init__(
        self,
        reference_range_repository: ReferenceRangeRepository,
        parameter_repository: ClinicalParameterRepository,
    ) -> None:
        self._ranges = reference_range_repository
        self._parameters = parameter_repository

    async def resolve(
        self, request: ReferenceResolutionRequest
    ) -> ReferenceResolutionResult:
        if (
            request.extracted_reference_min is not None
            or request.extracted_reference_max is not None
        ):
            return await self._from_extracted(request)

        patient_sex = self._request_patient_sex(request)
        patient_age = self._request_patient_age(request)
        pregnancy_status = self._request_pregnancy_status(request)

        all_ranges = list(
            await self._ranges.list_for_parameter(request.canonical_parameter_id)
        )

        native = await self._resolve_database_native(
            request,
            all_ranges,
            patient_sex=patient_sex,
            patient_age=patient_age,
            pregnancy_status=pregnancy_status,
        )
        if native is not None:
            return native

        return await self._resolve_database_python(
            request,
            all_ranges,
            patient_sex=patient_sex,
            patient_age=patient_age,
            pregnancy_status=pregnancy_status,
        )

    async def _resolve_database_native(
        self,
        request: ReferenceResolutionRequest,
        all_ranges: list[ReferenceRange],
        *,
        patient_sex: Sex | None,
        patient_age: float | None,
        pregnancy_status: bool | None,
    ) -> ReferenceResolutionResult | None:
        """Use native selector only when v1 can represent all age bounds exactly."""
        try:
            from app.domain.native_lab_engine import (
                native_lab_deterministic_available,
                native_select_reference_candidate,
            )

            if not native_lab_deterministic_available():
                return None

            if patient_age is not None and not float(patient_age).is_integer():
                return None
            for rr in all_ranges:
                if rr.age_min is not None and not float(rr.age_min).is_integer():
                    return None
                if rr.age_max is not None and not float(rr.age_max).is_integer():
                    return None

            payload = [
                {
                    "reference_min": float(rr.reference_min) if rr.reference_min is not None else None,
                    "reference_max": float(rr.reference_max) if rr.reference_max is not None else None,
                    "unit": rr.unit,
                    "source": rr.source,
                    "sex": rr.sex.value,
                    "age_min": int(rr.age_min) if rr.age_min is not None else None,
                    "age_max": int(rr.age_max) if rr.age_max is not None else None,
                    "pregnancy_status": rr.pregnancy_status,
                }
                for rr in all_ranges
            ]
            selected = native_select_reference_candidate(
                payload,
                patient_sex=patient_sex.value if patient_sex is not None else None,
                patient_age=int(patient_age) if patient_age is not None else None,
                pregnancy_status=pregnancy_status,
            )
        except (ImportError, RuntimeError, OSError, ValueError, TypeError, KeyError):
            return None

        index = selected.get("index")
        if index is None:
            return ReferenceResolutionResult.needs_review_result(
                request,
                reason=str(
                    selected.get("reason")
                    or "No reference range is safely resolvable from the provided patient inputs."
                ),
            )

        try:
            chosen = all_ranges[int(index)]
        except (IndexError, TypeError, ValueError):
            return None

        strategy_raw = str(selected.get("strategy") or "needs_review")
        try:
            strategy = ReferenceStrategy(strategy_raw)
        except ValueError:
            return None

        unit = chosen.unit or await self._default_unit(request.canonical_parameter_id)
        return ReferenceResolutionResult(
            canonical_parameter_id=request.canonical_parameter_id,
            parameter_code=request.parameter_code,
            reference_range_id=chosen.id,
            reference_min=chosen.reference_min,
            reference_max=chosen.reference_max,
            unit=unit,
            reference_source=chosen.source,
            confidence=float(selected.get("confidence") or 0.0),
            reason=str(selected.get("reason") or ""),
            needs_review=bool(selected.get("needs_review")),
            resolved_from=strategy,
        )

    async def _resolve_database_python(
        self,
        request: ReferenceResolutionRequest,
        all_ranges: list[ReferenceRange],
        *,
        patient_sex: Sex | None,
        patient_age: float | None,
        pregnancy_status: bool | None,
    ) -> ReferenceResolutionResult:
        compatible = [
            rr
            for rr in all_ranges
            if self._is_compatible(
                rr,
                patient_sex=patient_sex,
                patient_age=patient_age,
                pregnancy_status=pregnancy_status,
            )
        ]
        if compatible:
            return await self._from_demographic(request, compatible)

        generic = [rr for rr in all_ranges if self._requires_no_inputs(rr)]
        if generic:
            return await self._from_default(request, generic)

        identical = self._identical_effective_ranges(all_ranges)
        if identical:
            return await self._from_identical_demographic_fallback(request, identical)

        return ReferenceResolutionResult.needs_review_result(
            request,
            reason=(
                "No reference range is safely resolvable: the stored ranges "
                "require patient inputs (age, sex, and/or pregnancy_status) "
                "that were not provided."
            ),
        )

    async def _from_extracted(
        self, request: ReferenceResolutionRequest
    ) -> ReferenceResolutionResult:
        has_min = request.extracted_reference_min is not None
        has_max = request.extracted_reference_max is not None
        has_unit = bool(request.extracted_unit and request.extracted_unit.strip())

        parameter = await self._parameters.get_by_id(request.canonical_parameter_id)
        default_unit = (
            (parameter.default_unit or "").strip()
            if parameter is not None
            else ""
        )
        is_dimensionless = parameter is not None and not default_unit
        complete = has_min and has_max and (has_unit or is_dimensionless)

        reason = "Using the reference range extracted from the report."
        if is_dimensionless and not has_unit:
            reason += " Parameter is dimensionless; no physical unit is required."
        elif not complete:
            reason += " Extracted range is incomplete (missing a bound or unit)."

        resolved_unit = request.extracted_unit if has_unit else default_unit or None
        return ReferenceResolutionResult(
            canonical_parameter_id=request.canonical_parameter_id,
            parameter_code=request.parameter_code,
            reference_min=request.extracted_reference_min,
            reference_max=request.extracted_reference_max,
            unit=resolved_unit,
            reference_source=_EXTRACTED_SOURCE,
            confidence=CONF_EXTRACTED_FULL if complete else CONF_EXTRACTED_PARTIAL,
            reason=reason,
            needs_review=not complete,
            resolved_from=ReferenceStrategy.EXTRACTED,
        )

    async def _from_demographic(
        self,
        request: ReferenceResolutionRequest,
        compatible: list[ReferenceRange],
    ) -> ReferenceResolutionResult:
        ranked = sorted(compatible, key=lambda rr: self._specificity(rr), reverse=True)
        best = ranked[0]
        top_score = self._specificity(best)
        tied = [rr for rr in ranked if self._specificity(rr) == top_score]
        ambiguous = len(tied) > 1

        reason = (
            "Matched a demographic reference range fully compatible with the "
            "provided patient inputs."
        )
        if ambiguous:
            reason += " Multiple equally-specific ranges matched; review needed."

        unit = best.unit or await self._default_unit(request.canonical_parameter_id)
        return ReferenceResolutionResult(
            canonical_parameter_id=request.canonical_parameter_id,
            parameter_code=request.parameter_code,
            reference_range_id=best.id,
            reference_min=best.reference_min,
            reference_max=best.reference_max,
            unit=unit,
            reference_source=best.source,
            confidence=CONF_DEMOGRAPHIC if not ambiguous else CONF_DEMOGRAPHIC_AMBIGUOUS,
            reason=reason,
            needs_review=ambiguous,
            resolved_from=ReferenceStrategy.DATABASE_DEMOGRAPHIC,
        )

    async def _from_default(
        self,
        request: ReferenceResolutionRequest,
        generic: list[ReferenceRange],
    ) -> ReferenceResolutionResult:
        ambiguous = len(generic) > 1
        chosen = generic[0]
        unit = chosen.unit or await self._default_unit(request.canonical_parameter_id)
        reason = "Using a general, input-independent reference range."
        if ambiguous:
            reason += " Multiple general ranges exist; review needed."

        return ReferenceResolutionResult(
            canonical_parameter_id=request.canonical_parameter_id,
            parameter_code=request.parameter_code,
            reference_range_id=chosen.id,
            reference_min=chosen.reference_min,
            reference_max=chosen.reference_max,
            unit=unit,
            reference_source=chosen.source,
            confidence=CONF_DEFAULT,
            reason=reason,
            needs_review=ambiguous,
            resolved_from=ReferenceStrategy.DATABASE_DEFAULT,
        )

    async def _from_identical_demographic_fallback(
        self,
        request: ReferenceResolutionRequest,
        identical: list[ReferenceRange],
    ) -> ReferenceResolutionResult:
        chosen = identical[0]
        unit = chosen.unit or await self._default_unit(request.canonical_parameter_id)
        return ReferenceResolutionResult(
            canonical_parameter_id=request.canonical_parameter_id,
            parameter_code=request.parameter_code,
            reference_range_id=chosen.id,
            reference_min=chosen.reference_min,
            reference_max=chosen.reference_max,
            unit=unit,
            reference_source=chosen.source,
            confidence=CONF_IDENTICAL_DEMOGRAPHIC_FALLBACK,
            reason=(
                "Using a stored reference range because all demographic ranges "
                "for this parameter have identical bounds and unit."
            ),
            needs_review=False,
            resolved_from=ReferenceStrategy.DATABASE_DEFAULT,
        )

    @staticmethod
    def _get_first_present(request: ReferenceResolutionRequest, *names: str) -> Any:
        for name in names:
            if hasattr(request, name):
                value = getattr(request, name)
                if value is not None:
                    return value
        return None

    @classmethod
    def _request_patient_sex(cls, request: ReferenceResolutionRequest) -> Sex | None:
        return cls._get_first_present(request, "patient_sex", "sex")

    @classmethod
    def _request_patient_age(cls, request: ReferenceResolutionRequest) -> float | None:
        return cls._get_first_present(
            request,
            "patient_age",
            "age",
            "age_years",
            "patient_age_years",
        )

    @classmethod
    def _request_pregnancy_status(
        cls, request: ReferenceResolutionRequest
    ) -> bool | None:
        return cls._get_first_present(
            request,
            "pregnancy_status",
            "pregnant",
            "is_pregnant",
        )

    @staticmethod
    def _is_compatible(
        rr: ReferenceRange,
        *,
        patient_sex: Sex | None,
        patient_age: float | None,
        pregnancy_status: bool | None,
    ) -> bool:
        if rr.sex != Sex.ANY:
            if patient_sex is None or rr.sex != patient_sex:
                return False

        if rr.pregnancy_status is not None:
            if pregnancy_status is None or rr.pregnancy_status != pregnancy_status:
                return False

        if rr.age_min is not None or rr.age_max is not None:
            if patient_age is None:
                return False
            if rr.age_min is not None and patient_age < rr.age_min:
                return False
            if rr.age_max is not None and patient_age > rr.age_max:
                return False

        return True

    @staticmethod
    def _identical_effective_ranges(ranges: list[ReferenceRange]) -> list[ReferenceRange]:
        usable = [
            rr
            for rr in ranges
            if rr.reference_min is not None
            and rr.reference_max is not None
            and bool(rr.unit)
        ]
        if not usable:
            return []

        first = usable[0]
        first_key = (
            first.reference_min,
            first.reference_max,
            (first.unit or "").strip().lower(),
        )
        for rr in usable[1:]:
            key = (
                rr.reference_min,
                rr.reference_max,
                (rr.unit or "").strip().lower(),
            )
            if key != first_key:
                return []
        return usable

    @staticmethod
    def _requires_no_inputs(rr: ReferenceRange) -> bool:
        return (
            rr.sex == Sex.ANY
            and rr.age_min is None
            and rr.age_max is None
            and rr.pregnancy_status is None
        )

    @staticmethod
    def _specificity(rr: ReferenceRange) -> float:
        score = 0.0
        if rr.sex != Sex.ANY:
            score += 2.0
        if rr.pregnancy_status is not None:
            score += 2.0
        if rr.age_min is not None:
            score += 0.5
        if rr.age_max is not None:
            score += 0.5
        return score

    async def _default_unit(self, parameter_id: uuid.UUID | None) -> str | None:
        if parameter_id is None:
            return None
        parameter = await self._parameters.get_by_id(parameter_id)
        return parameter.default_unit if parameter is not None else None
