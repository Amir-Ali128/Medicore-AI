"""ReferenceResolver.


Resolves which reference range applies to a parameter for a given patient
profile, using a strict priority order:


    1. extracted / PDF reference range (if provided)
    2. database demographic reference range (sex / age / pregnancy)
    3. default database reference range (input-independent fallback)
    4. needs_review (nothing safely resolvable)


Safety rule (deterministic validation): a range is only selected when it is
fully COMPATIBLE with the provided inputs and requires NO missing input. A range
that is sex-specific, age-banded, or pregnancy-specific is never resolved when
the corresponding patient input (sex / age / pregnancy_status) is missing — in
that case the resolver returns a needs_review result instead of guessing.


It selects a range only. It does NOT compare measured values, classify
low/normal/high, diagnose, or produce medical advice.
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
        # --- Priority 1: extracted / PDF range --------------------------
        if (
            request.extracted_reference_min is not None
            or request.extracted_reference_max is not None
        ):
            return await self._from_extracted(request)


        patient_sex = self._request_patient_sex(request)
        patient_age = self._request_patient_age(request)
        pregnancy_status = self._request_pregnancy_status(request)


        # --- Priority 2: database demographic range ---------------------
        # Keep ONLY ranges that are compatible with the provided inputs and
        # require no missing input. Ranges needing an absent age/sex/pregnancy
        # value are dropped here, never resolved.
        candidates = await self._ranges.find_applicable(
            request.canonical_parameter_id,
            sex=patient_sex,
            age=patient_age,
            pregnant=pregnancy_status,
        )
        compatible = [
            rr
            for rr in candidates
            if self._is_compatible(
                rr,
                patient_sex=patient_sex,
                patient_age=patient_age,
                pregnancy_status=pregnancy_status,
            )
        ]
        if compatible:
            return await self._from_demographic(request, compatible)


        # --- Priority 3: default (input-independent) database range ------
        # Only a truly generic range (sex=ANY, no age band, no pregnancy
        # constraint) is safe to use when inputs are missing.
        all_ranges = await self._ranges.list_for_parameter(
            request.canonical_parameter_id
        )
        generic = [rr for rr in all_ranges if self._requires_no_inputs(rr)]
        if generic:
            return await self._from_default(request, generic)


        # --- Priority 3b: identical demographic ranges fallback ----------
        # Some lab markers have the exact same min/max/unit across all stored
        # demographic rows. In that case, using the identical range is safe even
        # when patient age/sex/pregnancy inputs are missing.
        identical = self._identical_effective_ranges(all_ranges)
        if identical:
            return await self._from_identical_demographic_fallback(
                request,
                identical,
            )


        # --- Priority 4: needs review -----------------------------------
        return ReferenceResolutionResult.needs_review_result(
            request,
            reason=(
                "No reference range is safely resolvable: the stored ranges "
                "require patient inputs (age, sex, and/or pregnancy_status) "
                "that were not provided."
            ),
        )


    # -- Priority 1 ------------------------------------------------------
    async def _from_extracted(
        self, request: ReferenceResolutionRequest
    ) -> ReferenceResolutionResult:
        has_min = request.extracted_reference_min is not None
        has_max = request.extracted_reference_max is not None
        has_unit = bool(
            request.extracted_unit
            and request.extracted_unit.strip()
        )

        parameter = await self._parameters.get_by_id(
            request.canonical_parameter_id
        )

        default_unit = (
            (parameter.default_unit or "").strip()
            if parameter is not None
            else ""
        )

        # Empty default unit means the parameter is dimensionless.
        # Example: BUN / Creatinine ratio.
        is_dimensionless = (
            parameter is not None
            and not default_unit
        )

        complete = (
            has_min
            and has_max
            and (has_unit or is_dimensionless)
        )

        reason = "Using the reference range extracted from the report."

        if is_dimensionless and not has_unit:
            reason += (
  " Parameter is dimensionless; "
  "no physical unit is required."
            )
        elif not complete:
            reason += (
  " Extracted range is incomplete "
  "(missing a bound or unit)."
            )

        resolved_unit = (
            request.extracted_unit
            if has_unit
            else default_unit or None
        )

        return ReferenceResolutionResult(
            canonical_parameter_id=request.canonical_parameter_id,
            reference_min=request.extracted_reference_min,
            reference_max=request.extracted_reference_max,
            unit=resolved_unit,
            reference_source=_EXTRACTED_SOURCE,
            confidence=(
  CONF_EXTRACTED_FULL
  if complete
  else CONF_EXTRACTED_PARTIAL
            ),
            reason=reason,
            needs_review=not complete,
            resolved_from=ReferenceStrategy.EXTRACTED,
        )


    # -- Priority 2 ------------------------------------------------------
    async def _from_demographic(
        self,
        request: ReferenceResolutionRequest,
        compatible: list[ReferenceRange],
    ) -> ReferenceResolutionResult:
        ranked = sorted(
            compatible, key=lambda rr: self._specificity(rr), reverse=True
        )
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
            reference_min=best.reference_min,
            reference_max=best.reference_max,
            unit=unit,
            reference_source=best.source,
            confidence=CONF_DEMOGRAPHIC if not ambiguous else CONF_DEMOGRAPHIC_AMBIGUOUS,
            reason=reason,
            needs_review=ambiguous,
            resolved_from=ReferenceStrategy.DATABASE_DEMOGRAPHIC,
        )


    # -- Priority 3 ------------------------------------------------------
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


    # -- request field helpers ------------------------------------------
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
        value = cls._get_first_present(request, "patient_sex", "sex")
        return value


    @classmethod
    def _request_patient_age(cls, request: ReferenceResolutionRequest) -> int | None:
        value = cls._get_first_present(
            request,
            "patient_age",
            "age",
            "age_years",
            "patient_age_years",
        )
        return value


    @classmethod
    def _request_pregnancy_status(
        cls, request: ReferenceResolutionRequest
    ) -> bool | None:
        value = cls._get_first_present(
            request,
            "pregnancy_status",
            "pregnant",
            "is_pregnant",
        )
        return value


    # -- compatibility / specificity helpers -----------------------------
    @staticmethod
    def _is_compatible(
        rr: ReferenceRange,
        *,
        patient_sex: Sex | None,
        patient_age: int | None,
        pregnancy_status: bool | None,
    ) -> bool:
        """True only if `rr` matches provided inputs AND needs no missing input."""
        # Sex-specific range requires a matching, provided sex.
        if rr.sex != Sex.ANY:
            if patient_sex is None or rr.sex != patient_sex:
                return False


        # Pregnancy-specific range (True or False) requires provided pregnancy.
        if rr.pregnancy_status is not None:
            if (
                pregnancy_status is None
                or rr.pregnancy_status != pregnancy_status
            ):
                return False


        # Age-banded range requires a provided age inside the band.
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
        """Return ranges only when every usable row has the same bounds and unit."""
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
        """True for a fully generic range usable regardless of patient inputs."""
        return (
            rr.sex == Sex.ANY
            and rr.age_min is None
            and rr.age_max is None
            and rr.pregnancy_status is None
        )


    @staticmethod
    def _specificity(rr: ReferenceRange) -> float:
        """Higher score = more demographically specific."""
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


    async def _default_unit(self, parameter_id: uuid.UUID) -> str | None:
        parameter = await self._parameters.get_by_id(parameter_id)
        return parameter.default_unit if parameter is not None else None