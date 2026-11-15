"""FHIR R4 representations of the virtual HBYS records."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .data import PATIENTS_BY_ID, SimEncounter, SimPatient

FHIR_BASE = "urn:hbys-sim"
TCKN_SYSTEM = "urn:oid:2.16.792.1.56.6.3"  # sentetik T.C. kimlik no sistemi
PROTOCOL_SYSTEM = "urn:hbys-sim:protocol-no"

_VITAL_LOINC = {
    "systolic_bp": ("8480-6", "Sistolik kan basıncı", "mm[Hg]"),
    "diastolic_bp": ("8462-4", "Diyastolik kan basıncı", "mm[Hg]"),
    "heart_rate": ("8867-4", "Nabız", "/min"),
    "respiratory_rate": ("9279-1", "Solunum sayısı", "/min"),
    "temperature": ("8310-5", "Vücut sıcaklığı", "Cel"),
    "spo2": ("59408-5", "Oksijen satürasyonu", "%"),
    "height_cm": ("8302-2", "Boy", "cm"),
    "weight_kg": ("29463-7", "Kilo", "kg"),
}

_INTERPRETATION = {"H": "Yüksek", "L": "Düşük", "N": "Normal"}


def _iso(value: date | datetime) -> str:
    return value.isoformat()


def patient_resource(patient: SimPatient) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": patient.id,
        "identifier": [{"system": TCKN_SYSTEM, "value": patient.tckn}],
        "name": [{"family": patient.family_name, "given": [patient.given_name]}],
        "gender": patient.sex,
        "birthDate": _iso(patient.birth_date),
        "telecom": [{"system": "phone", "value": patient.phone}],
        "address": [{"text": patient.address}],
    }


def encounter_resource(encounter: SimEncounter) -> dict[str, Any]:
    return {
        "resourceType": "Encounter",
        "id": encounter.id,
        "status": encounter.status,
        "identifier": [{"system": PROTOCOL_SYSTEM, "value": encounter.protocol_no}],
        "class": {"code": "EMER" if "Acil" in encounter.department else "AMB"},
        "serviceType": {"text": encounter.department},
        "subject": {"reference": f"Patient/{encounter.patient_id}"},
        "participant": [{"individual": {"display": encounter.doctor}}],
        "period": {"start": _iso(encounter.admitted_at)},
        "reasonCode": [{"text": complaint} for complaint in encounter.complaints],
    }


def _observation(encounter: SimEncounter, suffix: str, category: str, code: str, display: str,
                 effective: datetime, **value: Any) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "id": f"{encounter.id}-{suffix}",
        "status": "final",
        "category": [{"coding": [{"code": category}]}],
        "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}], "text": display},
        "subject": {"reference": f"Patient/{encounter.patient_id}"},
        "encounter": {"reference": f"Encounter/{encounter.id}"},
        "effectiveDateTime": _iso(effective),
        **value,
    }


def encounter_bundle(encounter: SimEncounter) -> dict[str, Any]:
    """Patient/$everything-style bundle for one visit, as an HBYS would export it."""
    patient = PATIENTS_BY_ID[encounter.patient_id]
    resources: list[dict[str, Any]] = [patient_resource(patient), encounter_resource(encounter)]

    for index, (code, text) in enumerate(encounter.diagnoses):
        resources.append({
            "resourceType": "Condition", "id": f"{encounter.id}-dx{index}",
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code}], "text": text},
            "subject": {"reference": f"Patient/{encounter.patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter.id}"},
            "category": [{"coding": [{"code": "encounter-diagnosis"}]}],
        })
    for index, text in enumerate(encounter.history):
        resources.append({
            "resourceType": "Condition", "id": f"{encounter.id}-hx{index}", "code": {"text": text},
            "subject": {"reference": f"Patient/{encounter.patient_id}"},
            "category": [{"coding": [{"code": "problem-list-item"}]}],
        })
    for index, text in enumerate(encounter.medications):
        resources.append({
            "resourceType": "MedicationStatement", "id": f"{encounter.id}-med{index}", "status": "active",
            "medicationCodeableConcept": {"text": text},
            "subject": {"reference": f"Patient/{encounter.patient_id}"},
        })
    for key, number in encounter.vitals.items():
        code, display, unit = _VITAL_LOINC[key]
        resources.append(_observation(
            encounter, key, "vital-signs", code, display, encounter.admitted_at,
            valueQuantity={"value": number, "unit": unit},
        ))

    lab_ids = []
    for index, lab in enumerate(encounter.labs):
        observation = _observation(
            encounter, f"lab{index}", "laboratory", lab.loinc, lab.name, encounter.specimen_at,
            valueString=lab.value,
        )
        if lab.unit:
            observation["extension"] = [{"url": f"{FHIR_BASE}:unit", "valueString": lab.unit}]
        if lab.reference:
            observation["referenceRange"] = [{"text": lab.reference}]
        if lab.flag:
            observation["interpretation"] = [{"coding": [{"code": lab.flag}], "text": _INTERPRETATION[lab.flag]}]
        resources.append(observation)
        lab_ids.append(observation["id"])
    if lab_ids:
        resources.append({
            "resourceType": "DiagnosticReport", "id": f"{encounter.id}-lab", "status": "final",
            "category": [{"coding": [{"code": "LAB"}]}], "code": {"text": "Laboratuvar sonuçları"},
            "subject": {"reference": f"Patient/{encounter.patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter.id}"},
            "effectiveDateTime": _iso(encounter.specimen_at),
            "result": [{"reference": f"Observation/{item}"} for item in lab_ids],
        })
    for index, study in enumerate(encounter.radiology):
        resources.append({
            "resourceType": "DiagnosticReport", "id": f"{encounter.id}-rad{index}", "status": "final",
            "category": [{"coding": [{"code": "RAD"}]}],
            "code": {"coding": [{"code": study.modality}], "text": f"{study.modality} {study.body_region}"},
            "subject": {"reference": f"Patient/{encounter.patient_id}"},
            "encounter": {"reference": f"Encounter/{encounter.id}"},
            "effectiveDateTime": _iso(encounter.admitted_at),
            "extension": [{"url": f"{FHIR_BASE}:findings", "valueString": study.findings},
                          {"url": f"{FHIR_BASE}:body-region", "valueString": study.body_region}],
            "conclusion": study.impression,
        })

    return {
        "resourceType": "Bundle", "type": "searchset", "total": len(resources),
        "entry": [{"fullUrl": f"{FHIR_BASE}:{item['resourceType']}/{item['id']}", "resource": item}
                  for item in resources],
    }


def encounter_search_bundle(encounters: list[SimEncounter]) -> dict[str, Any]:
    entries = []
    for encounter in encounters:
        resource = encounter_resource(encounter)
        resource["extension"] = [
            {"url": f"{FHIR_BASE}:lab-count", "valueInteger": len(encounter.labs)},
            {"url": f"{FHIR_BASE}:radiology-count", "valueInteger": len(encounter.radiology)},
        ]
        entries.append({"fullUrl": f"{FHIR_BASE}:Encounter/{encounter.id}", "resource": resource})
    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": entries}


def capability_statement() -> dict[str, Any]:
    return {
        "resourceType": "CapabilityStatement", "status": "active", "kind": "instance",
        "software": {"name": "Sanal HBYS (simülasyon)", "version": "1.0"},
        "fhirVersion": "4.0.1", "format": ["json"],
        "rest": [{"mode": "server", "resource": [
            {"type": "Encounter", "interaction": [{"code": "search-type"}, {"code": "read"}]},
            {"type": "DiagnosticReport", "interaction": [{"code": "create"}]},
        ]}],
    }
