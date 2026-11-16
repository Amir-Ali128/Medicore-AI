"""HBYS (Hastane Bilgi Yönetim Sistemi) integration over FHIR R4.

Medicore imports a visit from the hospital system as a *de-identified* case draft:
only the visit protocol number, age, sex, clinical findings, laboratory results and
radiology text cross the boundary. Names, national ID numbers, phone numbers,
addresses and the exact birth date stay in the HBYS. Free text is additionally
scrubbed with the local privacy gateway using the visit's own identifiers, in case
an HBYS user typed a name into a complaint or report field.

The AI report goes back to the HBYS as a FHIR DiagnosticReport awaiting physician
review (status "preliminary").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app.domain.privacy_gateway import KnownIdentifier, sanitize_text
from app.schemas.simple_case import (
    ClinicalContext,
    LabResultInput,
    MedicalReportInput,
    SimpleCaseRequest,
    VitalSigns,
)

_EXT = "urn:hbys-sim:"
_VITAL_BY_LOINC = {
    "8480-6": "systolic_bp", "8462-4": "diastolic_bp", "8867-4": "heart_rate",
    "9279-1": "respiratory_rate", "8310-5": "temperature", "59408-5": "spo2",
    "8302-2": "height_cm", "29463-7": "weight_kg",
}
_REPORT_TYPE_BY_MODALITY = {
    "DX": "Röntgen", "CR": "Röntgen", "US": "Ultrasonografi", "CT": "BT", "MR": "MR",
    "MG": "Mamografi", "NM": "Nükleer Tıp",
}
_SEX = {"female": "female", "male": "male", "other": "other"}
_MAX_TEXT = 4000


class HbysError(Exception):
    """Safe, user-facing integration error (never carries patient data)."""


class HbysNotConfigured(HbysError):
    pass


@dataclass(frozen=True)
class EncounterSummary:
    encounter_id: str
    protocol_no: str
    department: str | None
    admitted_at: str | None
    status: str | None
    lab_count: int
    radiology_count: int


@dataclass(frozen=True)
class ImportedCase:
    encounter_id: str
    protocol_no: str
    age: int | None
    sex: str
    case: SimpleCaseRequest
    redaction_counts: dict[str, int]


# ----------------------------------------------------------------- FHIR helpers
def _resources(bundle: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        raise HbysError("HBYS geçersiz bir FHIR Bundle döndürdü.")
    return [
        entry["resource"] for entry in bundle.get("entry") or []
        if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)
        and entry["resource"].get("resourceType") == resource_type
    ]


def _extension(resource: dict[str, Any], name: str) -> Any:
    for item in resource.get("extension") or []:
        if isinstance(item, dict) and str(item.get("url", "")).endswith(f":{name}"):
            for key, value in item.items():
                if key.startswith("value"):
                    return value
    return None


def _protocol(encounter: dict[str, Any]) -> str:
    for identifier in encounter.get("identifier") or []:
        if str(identifier.get("system", "")).endswith("protocol-no") and identifier.get("value"):
            return str(identifier["value"]).strip().upper()
    raise HbysError("HBYS muayene kaydında protokol numarası yok.")


def _code(resource: dict[str, Any]) -> str | None:
    for coding in (resource.get("code") or {}).get("coding") or []:
        if coding.get("code"):
            return str(coding["code"])
    return None


def _text(concept: dict[str, Any] | None) -> str | None:
    if not isinstance(concept, dict):
        return None
    value = concept.get("text") or next(
        (coding.get("display") for coding in concept.get("coding") or [] if coding.get("display")), None,
    )
    return str(value).strip() if value else None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _age(birth: str | None, on: datetime | None) -> int | None:
    try:
        born = date.fromisoformat(str(birth))
    except (TypeError, ValueError):
        return None
    today = (on or datetime.now()).date()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return age if 0 <= age <= 130 else None


def _identifiers(patient: dict[str, Any]) -> list[KnownIdentifier]:
    """The visit's own identity values, used only to scrub free text locally."""
    found: list[KnownIdentifier] = []
    for name in patient.get("name") or []:
        parts = [*(name.get("given") or []), name.get("family") or ""]
        full = " ".join(str(part) for part in parts if part).strip()
        if full:
            found.append(KnownIdentifier(full, "HASTA_ADI"))
    for identifier in patient.get("identifier") or []:
        if identifier.get("value"):
            found.append(KnownIdentifier(str(identifier["value"]), "TCKN"))
    for telecom in patient.get("telecom") or []:
        if telecom.get("value"):
            category = "EPOSTA" if telecom.get("system") == "email" else "TELEFON"
            found.append(KnownIdentifier(str(telecom["value"]), category))
    for address in patient.get("address") or []:
        if address.get("text"):
            found.append(KnownIdentifier(str(address["text"]), "ADRES"))
    if patient.get("birthDate"):
        try:
            born = date.fromisoformat(str(patient["birthDate"]))
            found.extend(KnownIdentifier(value, "DOGUM_TARIHI")
                         for value in (born.isoformat(), born.strftime("%d.%m.%Y"), born.strftime("%d/%m/%Y")))
        except ValueError:
            pass
    return found


class _Scrubber:
    def __init__(self, identifiers: list[KnownIdentifier]) -> None:
        self._identifiers = identifiers
        self.counts: dict[str, int] = {}

    def __call__(self, value: Any) -> str | None:
        if value is None:
            return None
        text = " ".join(str(value).split())[:_MAX_TEXT]
        if not text:
            return None
        result = sanitize_text(text, known_identifiers=self._identifiers)
        for key, count in result.redaction_counts.items():
            self.counts[key] = self.counts.get(key, 0) + count
        return result.text


# ----------------------------------------------------------------- mapping
def encounter_summaries(bundle: dict[str, Any]) -> list[EncounterSummary]:
    summaries = []
    for encounter in _resources(bundle, "Encounter"):
        summaries.append(EncounterSummary(
            encounter_id=str(encounter.get("id")),
            protocol_no=_protocol(encounter),
            department=_text(encounter.get("serviceType")),
            admitted_at=(encounter.get("period") or {}).get("start"),
            status=encounter.get("status"),
            lab_count=int(_extension(encounter, "lab-count") or 0),
            radiology_count=int(_extension(encounter, "radiology-count") or 0),
        ))
    return summaries


def case_from_bundle(bundle: dict[str, Any]) -> ImportedCase:
    encounters = _resources(bundle, "Encounter")
    patients = _resources(bundle, "Patient")
    if len(encounters) != 1 or len(patients) != 1:
        raise HbysError("HBYS yanıtı tek bir hasta ve muayene içermeli.")
    encounter, patient = encounters[0], patients[0]
    if (encounter.get("subject") or {}).get("reference") != f"Patient/{patient.get('id')}":
        raise HbysError("HBYS muayenesi farklı bir hastaya ait görünüyor.")

    scrub = _Scrubber(_identifiers(patient))
    started = _parse_datetime((encounter.get("period") or {}).get("start"))
    age = _age(patient.get("birthDate"), started)
    sex = _SEX.get(str(patient.get("gender")), "unknown")

    conditions = _resources(bundle, "Condition")
    history, diagnoses = [], []
    for condition in conditions:
        category = {c.get("code") for cat in condition.get("category") or [] for c in cat.get("coding") or []}
        text = scrub(_text(condition.get("code")))
        if not text:
            continue
        if "encounter-diagnosis" in category:
            code = _code(condition)
            diagnoses.append(f"{code} {text}" if code and not text.startswith(code) else text)
        else:
            history.append(text)

    vitals: dict[str, float] = {}
    labs: list[LabResultInput] = []
    for observation in _resources(bundle, "Observation"):
        category = {c.get("code") for cat in observation.get("category") or [] for c in cat.get("coding") or []}
        code = _code(observation)
        if "vital-signs" in category and code in _VITAL_BY_LOINC:
            quantity = observation.get("valueQuantity") or {}
            if isinstance(quantity.get("value"), (int, float)) and not isinstance(quantity.get("value"), bool):
                vitals[_VITAL_BY_LOINC[code]] = float(quantity["value"])
            continue
        if "laboratory" not in category:
            continue
        name = scrub(_text(observation.get("code")))
        if not name:
            continue
        quantity = observation.get("valueQuantity") or {}
        value = observation.get("valueString", quantity.get("value"))
        unit = _extension(observation, "unit") or quantity.get("unit")
        reference = next((r.get("text") for r in observation.get("referenceRange") or [] if r.get("text")), None)
        flag = next((c.get("code") for i in observation.get("interpretation") or [] for c in i.get("coding") or []), None)
        effective = _parse_datetime(observation.get("effectiveDateTime"))
        labs.append(LabResultInput(
            test_name=name[:256],
            value=scrub(value) if isinstance(value, str) else value,
            unit=scrub(unit),
            source_reference=scrub(reference),
            specimen_date=effective,
            measured_at=effective,
            # HBYS flags are informative only; Medicore re-classifies from the
            # value and the reference the source supplied.
            source_metadata={"source_system": "hbys", "loinc": code, "hbys_flag": flag},
        ))

    reports: list[MedicalReportInput] = []
    for report in _resources(bundle, "DiagnosticReport"):
        category = {c.get("code") for cat in report.get("category") or [] for c in cat.get("coding") or []}
        if "RAD" not in category:
            continue
        modality = (_code(report) or "").upper()
        effective = _parse_datetime(report.get("effectiveDateTime"))
        reports.append(MedicalReportInput(
            report_type=_REPORT_TYPE_BY_MODALITY.get(modality, "Radyoloji Raporu"),
            report_date=effective, exam_date=effective,
            body_region=scrub(_extension(report, "body-region")),
            findings=scrub(_extension(report, "findings")),
            impression=scrub(report.get("conclusion")),
            metadata={"source_system": "hbys", "modality": modality or None},
        ))

    medications = [
        text for text in (scrub(_text(item.get("medicationCodeableConcept")))
                          for item in _resources(bundle, "MedicationStatement")) if text
    ]
    complaints = [text for text in (scrub(_text(reason)) for reason in encounter.get("reasonCode") or []) if text]
    department = scrub(_text(encounter.get("serviceType")))
    notes = "; ".join(filter(None, [
        f"HBYS birimi: {department}" if department else None,
        f"HBYS ön tanı (ICD-10): {', '.join(diagnoses)}" if diagnoses else None,
    ])) or None

    clinical = ClinicalContext(
        age=age, sex=sex, complaints=complaints, history=history, medications=medications,
        notes=notes, vital_signs=VitalSigns(**vitals) if vitals else None,
        event_date=started, vitals_event_date=started if vitals else None,
    )
    return ImportedCase(
        encounter_id=str(encounter.get("id")),
        protocol_no=_protocol(encounter),
        age=age, sex=sex,
        case=SimpleCaseRequest(clinical=clinical, labs=labs, reports=reports),
        redaction_counts=dict(scrub.counts),
    )


def diagnostic_report(*, encounter_id: str, report_text: str, model: str | None) -> dict[str, Any]:
    return {
        "resourceType": "DiagnosticReport",
        "status": "preliminary",  # AI suggestion awaiting physician review
        "category": [{"coding": [{"code": "AI"}], "text": "Medicore AI ön değerlendirme"}],
        "code": {"text": "Medicore AI klinik ön değerlendirme raporu"},
        "encounter": {"reference": f"Encounter/{encounter_id}"},
        "issued": datetime.now().astimezone().isoformat(),
        "conclusion": report_text,
        "extension": [
            {"url": f"{_EXT}generated-by", "valueString": "medicore-ai"},
            {"url": f"{_EXT}model", "valueString": model or "unknown"},
            {"url": f"{_EXT}physician-review-required", "valueBoolean": True},
        ],
    }
