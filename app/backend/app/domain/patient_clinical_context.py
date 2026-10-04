"""Read current and legacy clinical records through one source-preserving view."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.domain.document_dates import calendar_day
from app.schemas.simple_case import ClinicalContext, VitalSigns


def _mapping(value: Any) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _lines(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [line.strip() for item in values if isinstance(item, str)
            for line in item.splitlines() if line.strip()]


def normalize_patient_clinical(source: Any, metadata: Mapping | None = None) -> ClinicalContext:
    source, metadata = _mapping(source), _mapping(metadata)
    patient = _mapping(source.get('patient_information'))
    complaint = _mapping(source.get('presenting_complaint'))
    history = _mapping(source.get('clinical_history_details'))
    exam = _mapping(source.get('physical_exam'))
    modern = any(key in source for key in ('complaints', 'history', 'medications', 'notes'))
    data = {
        'age': source.get('age', patient.get('age', metadata.get('age'))),
        'sex': source.get('sex', patient.get('sex')) or metadata.get('sex') or 'unknown',
        'complaints': _lines(source.get('complaints')) if modern else [
            *_lines(complaint.get('chief_complaint')), *_lines(complaint.get('associated_symptoms')),
            *_lines(complaint.get('reason_for_visit')), *_lines(complaint.get('complaint_duration')),
        ],
        'history': _lines(source.get('history')) if modern else [
            line for key in ('history_of_present_illness', 'current_medical_conditions', 'past_medical_history',
                             'family_history', 'allergies', 'tobacco_alcohol', 'past_surgeries')
            for line in _lines(history.get(key))
        ],
        'medications': _lines(source.get('medications') if modern else history.get('medications')),
        'notes': source.get('notes') if modern else exam.get('examination_findings'),
        'event_date': calendar_day(source.get('event_date') if 'event_date' in source else source.get('examination_date') or exam.get('examination_date')),
        'vitals_event_date': calendar_day(source.get('vitals_event_date') if 'vitals_event_date' in source else _mapping(source.get('vital_signs')).get('measurement_date') or exam.get('measurement_date')),
    }
    if not isinstance(data['notes'], str):
        data['notes'] = None
    else:
        data['notes'] = data['notes'].strip() or None
    legacy_vitals = {
        'systolic_bp': exam.get('blood_pressure_systolic'), 'diastolic_bp': exam.get('blood_pressure_diastolic'),
        'heart_rate': exam.get('pulse_bpm'), 'respiratory_rate': exam.get('respiratory_rate'),
        'temperature': exam.get('temperature_c'), 'spo2': exam.get('oxygen_saturation_percent'),
        'height_cm': patient.get('height_cm', metadata.get('height_cm')),
        'weight_kg': patient.get('weight_kg', metadata.get('weight_kg')),
    }
    # Explicit nulls are cleared measurements, never replaced by stale legacy values.
    raw_vitals = _mapping(source.get('vital_signs')) if 'vital_signs' in source else legacy_vitals
    safe_vitals = {}
    for name, value in raw_vitals.items():
        if name not in VitalSigns.model_fields:
            continue
        try:
            safe_vitals[name] = getattr(VitalSigns.model_validate({name: value}), name)
        except ValidationError:
            # Read old malformed metadata without crashing the archive or inventing a value.
            safe_vitals[name] = None
    data['vital_signs'] = (
        VitalSigns.model_validate(safe_vitals)
        if safe_vitals and ('vital_signs' in source or any(value is not None for value in safe_vitals.values()))
        else None
    )
    try:
        return ClinicalContext.model_validate(data)
    except ValidationError:
        # Old demographic values must not hide otherwise readable clinical history.
        data.update(age=None, sex='unknown')
        return ClinicalContext.model_validate(data)


def patient_clinical_context(metadata: Mapping | None) -> ClinicalContext:
    metadata = _mapping(metadata)
    snapshot = _mapping(metadata.get('simple_case'))
    source = snapshot.get('clinical') if isinstance(snapshot.get('clinical'), Mapping) else metadata.get('clinical_context')
    return normalize_patient_clinical(source, metadata)
