"""Core logic for the simplified MediCore clinical case flow."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from app.domain.lab_result_classification import canonical_lab_unit, classify_lab_result, has_sex_specific_segments, parse_source_reference
from app.domain.document_dates import calendar_day, date_values
from app.schemas.simple_case import (
    ClinicalContext,
    LabReferenceRange,
    LabResultInput,
    LabResultOutput,
    SimpleCaseRequest,
    SimpleCaseResponse,
)


def case_fingerprint(case: dict[str, Any]) -> str:
    """Bind an AI report to the exact normalized case used to generate it."""
    # Additive parsing diagnostics must not invalidate an unchanged legacy report.
    # Raw observations, reference evidence, status and reasons stay in the hash.
    parsing_fields = {'normalized_value', 'value_comparator', 'value_limit', 'parsed_unit'}
    stable = {**case, 'labs': [
        {key: value for key, value in row.items() if key not in parsing_fields}
        for row in case.get('labs', [])
    ]} if 'labs' in case else case
    encoded = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _reference_matches_patient(
    reference: LabReferenceRange,
    clinical: ClinicalContext,
) -> bool:
    """Return whether a source-provided reference applies to the patient.

    This function only selects among reference ranges already present in the
    source report. It never invents a medical reference range.
    """

    # One printed reference with rows for both sexes ("Erkek: 13-17 Kadın:
    # 12-15") is selected here and resolved by the classifier with the
    # patient's sex; dropping it would wrongly report "no reference".
    combined_sex_text = reference.sex in (None, "unknown") and has_sex_specific_segments(reference.text)
    label = '' if combined_sex_text else (reference.text.rsplit(':', 1)[0] if ':' in reference.text else '')
    label = ''.join(char for char in unicodedata.normalize('NFKD', label.casefold().replace('ı','i')) if not unicodedata.combining(char))
    if re.search(r'\b(female|male|women|men|kadin|erkek)\b', label) and reference.sex in (None, 'unknown'):
        return False
    if re.search(r'\b(age|yas|adult|adults|child|children|pediatric|eriskin|cocuk)\b', label) and reference.age_min is None and reference.age_max is None:
        return False

    female_label = bool(re.search(r'\b(female|women|kadin)\b', label))
    male_label = bool(re.search(r'\b(male|men|erkek)\b', label))
    if female_label and (male_label or reference.sex != 'female'):
        return False
    if male_label and reference.sex != 'male':
        return False
    labelled_age = re.search(r'\b(?:age|yas)\s*(\d+)\s*[-–—]\s*(\d+)\b', label)
    if labelled_age and (reference.age_min != int(labelled_age[1]) or reference.age_max != int(labelled_age[2])):
        return False

    if clinical.age is not None:
        if reference.age_min is not None and clinical.age < reference.age_min:
            return False
        if reference.age_max is not None and clinical.age > reference.age_max:
            return False
    elif reference.age_min is not None or reference.age_max is not None:
        return False

    if reference.sex and reference.sex != "unknown":
        if clinical.sex == "unknown" or reference.sex != clinical.sex:
            return False

    return True


def select_source_reference(
    lab: LabResultInput,
    clinical: ClinicalContext,
) -> tuple[str | None, str, LabReferenceRange | None]:
    """Choose the best source-report reference without classifying the result."""

    if lab.source_references:
        matching = [
            reference
            for reference in lab.source_references
            if _reference_matches_patient(reference, clinical)
        ]
        if matching:
            # Prefer the most specific source row: sex + two age bounds, then
            # one age bound, then generic.
            def specificity(item: LabReferenceRange) -> tuple[int, int, int]:
                return (
                    1 if item.sex and item.sex != "unknown" else 0,
                    1 if item.age_min is not None else 0,
                    1 if item.age_max is not None else 0,
                )

            matching.sort(key=specificity, reverse=True)
            selected = matching[0]
            # Equally applicable but conflicting source rows are not resolved by
            # list order. Missing clinical context must not create a false label.
            tied = [item for item in matching if specificity(item) == specificity(selected)]
            def signature(item):
                parsed = parse_source_reference(item.text, item.minimum, item.maximum)
                if parsed.error:
                    return ('unparsed', item.text, item.minimum, item.maximum, item.unit)
                # Unit spelling/boundary semantics are part of the evidence.
                units = {canonical_lab_unit(value) for value in (item.unit, parsed.unit) if canonical_lab_unit(value)}
                if not units and canonical_lab_unit(lab.unit):
                    units.add(canonical_lab_unit(lab.unit))
                units = tuple(sorted(units))
                return (parsed.low, parsed.high, parsed.low_inclusive, parsed.high_inclusive, units)
            signatures = {signature(item) for item in tied}
            if len(signatures) > 1:
                return None, "missing", None
            return selected.text, "report_age_sex_match", selected

    if not lab.source_references and (lab.source_reference or lab.raw_reference):
        return lab.source_reference or lab.raw_reference, "report", None

    return None, "missing", None


def normalize_simple_case(payload: SimpleCaseRequest) -> SimpleCaseResponse:
    labs: list[LabResultOutput] = []
    warnings: list[str] = []

    for lab in payload.labs:
        reference_text, reference_source, reference_details = select_source_reference(
            lab,
            payload.clinical,
        )
        if reference_source == "missing":
            warnings.append(
                f"{lab.test_name}: kaynak raporda kullanılabilir referans aralığı bulunamadı."
            )

        classification = classify_lab_result(
            value=lab.value,
            unit=lab.unit,
            reference_text=reference_text,
            reference_low=reference_details.minimum if reference_details else None,
            reference_high=reference_details.maximum if reference_details else None,
            reference_unit=reference_details.unit if reference_details else None,
            ingestion_reasons=lab.source_metadata.get("ingestion_reasons", ()),
            patient_sex=payload.clinical.sex,
        )

        labs.append(
            LabResultOutput(
                test_name=lab.test_name,
                value=lab.value,
                unit=lab.unit,
                measured_at=lab.measured_at,
                **{key: (getattr(lab, key) if key in lab.model_fields_set else
                         calendar_day(date_values(lab.model_dump()).get(key)))
                   for key in ("event_date", "specimen_date", "result_date", "document_date", "uploaded_at")},
                reference_text=reference_text,
                reference_source=reference_source,
                reference_details=reference_details,
                source_reference=lab.source_reference,
                source_references=list(lab.source_references),
                source_metadata=dict(lab.source_metadata),
                status=classification.status,
                reference_low=classification.reference_low,
                reference_high=classification.reference_high,
                raw_reference=classification.raw_reference,
                classification_reason=classification.classification_reason,
                normalized_value=classification.normalized_value,
                value_comparator=classification.value_comparator,
                value_limit=classification.value_limit,
                parsed_unit=classification.parsed_unit,
                status_explanation=classification.status_explanation,
            )
        )

    return SimpleCaseResponse(
        clinical=payload.clinical,
        labs=labs,
        reports=payload.reports,
        warnings=warnings,
    )
