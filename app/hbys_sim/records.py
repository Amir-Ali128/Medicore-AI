"""Seed records plus everything created at runtime, backed by the store."""

from __future__ import annotations

import itertools
import threading
import uuid
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Any

from .data import (
    ENCOUNTERS, ENCOUNTERS_BY_ID, PATIENTS, PATIENTS_BY_ID, SimEncounter, SimLab, SimPatient,
    SimRadiology, _invalid_tckn,
)
from .store import make_store

_lock = threading.Lock()
_SEED_PATIENTS = {patient.id for patient in PATIENTS}
_SEED_ENCOUNTERS = {encounter.id for encounter in ENCOUNTERS}
store = make_store()
RECEIVED_REPORTS: list[dict[str, Any]] = []


def _patient_from(data: dict[str, Any]) -> SimPatient:
    return SimPatient(**{**data, "birth_date": date.fromisoformat(data["birth_date"])})


def _encounter_from(data: dict[str, Any]) -> SimEncounter:
    return SimEncounter(**{
        **data,
        "admitted_at": datetime.fromisoformat(data["admitted_at"]),
        "specimen_at": datetime.fromisoformat(data["specimen_at"]),
        "diagnoses": [tuple(item) for item in data["diagnoses"]],
        "labs": [SimLab(**item) for item in data["labs"]],
        "radiology": [SimRadiology(**item) for item in data["radiology"]],
    })


def _jsonable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def reset_runtime_records() -> None:
    """Drop runtime additions (tests); seed data is restored."""
    with _lock:
        for encounter in [item for item in ENCOUNTERS if item.id not in _SEED_ENCOUNTERS]:
            ENCOUNTERS.remove(encounter)
            ENCOUNTERS_BY_ID.pop(encounter.id, None)
        for patient in [item for item in PATIENTS if item.id not in _SEED_PATIENTS]:
            PATIENTS.remove(patient)
            PATIENTS_BY_ID.pop(patient.id, None)
        RECEIVED_REPORTS.clear()


def load() -> None:
    """Merge stored records into the in-process registry (startup)."""
    with _lock:
        for data in store.all("patient"):
            if data["id"] not in PATIENTS_BY_ID:
                patient = _patient_from(data)
                PATIENTS.append(patient)
                PATIENTS_BY_ID[patient.id] = patient
        for data in store.all("encounter"):
            if data["id"] not in ENCOUNTERS_BY_ID:
                encounter = _encounter_from(data)
                ENCOUNTERS.append(encounter)
                ENCOUNTERS_BY_ID[encounter.id] = encounter
        for data in store.all("status"):
            encounter = ENCOUNTERS_BY_ID.get(data["id"])
            if encounter is not None:
                encounter.status = data["status"]
        RECEIVED_REPORTS[:] = store.all("report")


def _next_protocol() -> str:
    year = datetime.now().year
    used = {encounter.protocol_no for encounter in ENCOUNTERS}
    for number in itertools.count(100301):
        candidate = f"HBYS-{year}-{number}"
        if candidate not in used:
            return candidate
    raise RuntimeError("unreachable")


def add_patient_with_encounter(
    *, given_name: str, family_name: str, sex: str, birth_date: date, phone: str, address: str,
    department: str, doctor: str, complaints: list[str], history: list[str], medications: list[str],
    diagnoses: list[tuple[str, str]], vitals: dict[str, float], labs: list[SimLab],
    radiology: list[SimRadiology],
) -> SimEncounter:
    now = datetime.now().replace(second=0, microsecond=0)
    with _lock:
        patient_id = f"p-{uuid.uuid4().hex[:8]}"
        # Synthetic, checksum-invalid national ID: never a real citizen's number.
        tckn = _invalid_tckn(str(uuid.uuid4().int)[1:10].replace("0", "1"))
        patient = SimPatient(patient_id, tckn, given_name, family_name, sex, birth_date, phone, address)
        encounter = SimEncounter(
            id=f"e-{uuid.uuid4().hex[:8]}", protocol_no=_next_protocol(), patient_id=patient_id,
            department=department, doctor=doctor, admitted_at=now, status="in-progress",
            complaints=complaints, history=history, medications=medications, diagnoses=diagnoses,
            vitals=vitals, labs=labs, specimen_at=now, radiology=radiology,
        )
        store.put("patient", patient.id, _jsonable(asdict(patient)))
        store.put("encounter", encounter.id, _jsonable(asdict(encounter)))
        PATIENTS.append(patient)
        PATIENTS_BY_ID[patient.id] = patient
        ENCOUNTERS.append(encounter)
        ENCOUNTERS_BY_ID[encounter.id] = encounter
    return encounter


def set_status(encounter: SimEncounter, status: str) -> None:
    with _lock:
        encounter.status = status
        if encounter.id in _SEED_ENCOUNTERS:
            store.put("status", encounter.id, {"id": encounter.id, "status": status})
        else:
            store.put("encounter", encounter.id, _jsonable(asdict(encounter)))


def add_report(report: dict[str, Any]) -> None:
    with _lock:
        stored = {**report, "meta": {"lastUpdated": datetime.now(UTC).isoformat()}}
        store.put("report", stored["id"], stored)
        RECEIVED_REPORTS.append(stored)
