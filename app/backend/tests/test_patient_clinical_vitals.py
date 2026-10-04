"""Clinical history/vitals round trips through the real patient persistence model.

SQLite exercises JSON commits and fresh sessions without a production database.
Only unrelated lab/report source persistence is stubbed; no paid AI calls run.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.api.routes import auth, patients, simple_case
from app.domain.enums import Sex, UserRole
from app.domain.patient_clinical_context import patient_clinical_context
from app.domain.simple_case import case_fingerprint
from app.domain.simple_case_ai import _build_case_payload
from app.infrastructure.database.models.patient import Patient
from app.schemas.simple_case import SimpleCaseRequest, VitalSigns


@compiles(JSONB, "sqlite")
def sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


class AsyncPatientSession:
    """Async interface over a real, request-scoped SQLAlchemy test session."""
    def __init__(self, session):
        self.session = session

    def add(self, record):
        self.session.add(record)

    async def get(self, model, record_id):
        return self.session.get(model, record_id)

    async def execute(self, statement):
        return self.session.execute(statement)

    async def commit(self):
        self.session.commit()

    async def refresh(self, record):
        self.session.refresh(record)

    async def rollback(self):
        self.session.rollback()


@pytest.fixture
def persisted_case(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Patient.__table__.create(engine)
    factory = sessionmaker(engine)
    user = SimpleNamespace(id=uuid4(), role=UserRole.PATIENT, is_active=True)
    app = FastAPI()
    app.include_router(patients.router)
    app.include_router(simple_case.router)

    async def session_dependency():
        with factory() as session:
            yield AsyncPatientSession(session)

    app.dependency_overrides[dependencies.get_session] = session_dependency
    app.dependency_overrides[auth.get_current_active_user] = lambda: user
    monkeypatch.setattr(simple_case, "_persist_simple_case_sources", AsyncMock())
    with TestClient(app) as client:
        created = client.post("/patients", json={"protocol_no": "VAKA01", "age": 38, "sex": "male"})
        assert created.status_code == 201, created.text
        yield SimpleNamespace(client=client, factory=factory, user=user, id=created.json()["id"])
    engine.dispose()


def clinical_data():
    return {
        "age": 38, "sex": "male",
        "complaints": ["2 gündür kusma", "ağız kuruluğu", "halsizlik", "idrar miktarında azalma"],
        "history": ["Hipertansiyon", "5 yıl önce böbrek taşı", "baba kolon kanseri", "penisilin alerjisi"],
        "medications": ["amlodipin 5 mg/gün"],
        "notes": "Ağız mukozası kuru, cilt turgoru azalmış, hafif taşikardik…",
        "vital_signs": {"systolic_bp": 145, "diastolic_bp": 90, "heart_rate": 108,
                        "respiratory_rate": 18, "temperature": 37.2, "spo2": 97,
                        "height_cm": 178, "weight_kg": 82, "glucose_mg_dl": 108},
    }


def save(c, clinical=None):
    response = c.client.put(f"/simple-case/patients/{c.id}/save",
                            json={"clinical": clinical or clinical_data()})
    assert response.status_code == 200, response.text
    return response.json()


def test_clinical_and_all_vitals_persist_and_reload_in_detail_and_archive(persisted_case):
    c = persisted_case
    expected = {**clinical_data(), "event_date": None, "vitals_event_date": None}
    saved = save(c)
    with c.factory() as db:
        patient = db.get(Patient, UUID(c.id))
        assert patient.metadata_json["clinical_context"] == expected
        assert patient.metadata_json["simple_case"]["clinical"] == expected
        assert "height_cm" not in patient.metadata_json
        assert "weight_kg" not in patient.metadata_json
        assert patient.sex == Sex.MALE
    detail = c.client.get(f"/patients/{c.id}").json()
    reopened = c.client.get(f"/simple-case/patients/{c.id}").json()
    assert detail["clinical"] == saved["clinical"] == reopened["clinical"] == expected
    # SQLite lacks PostgreSQL's JSON containment operator; the doctor archive
    # route exercises the same serialization without account filtering.
    c.user.role = UserRole.DOCTOR
    archive = c.client.get("/patients").json()
    assert archive[0]["clinical"] == expected


@pytest.mark.parametrize("legacy", [False, True])
def test_old_clinical_context_without_snapshot_remains_readable(persisted_case, legacy):
    c = persisted_case
    raw = clinical_data()
    raw.pop("vital_signs")
    if legacy:
        raw = {
            "patient_information": {"age": 38, "sex": "male"},
            "presenting_complaint": {"chief_complaint": "2 gündür kusma\nağız kuruluğu"},
            "clinical_history_details": {"past_medical_history": "Hipertansiyon",
                                         "family_history": "baba kolon kanseri", "allergies": "penisilin",
                                         "medications": "amlodipin 5 mg/gün"},
            "physical_exam": {"pulse_bpm": 108, "examination_findings": "Ağız mukozası kuru"},
        }
    with c.factory() as db:
        patient = db.get(Patient, UUID(c.id))
        patient.metadata_json = {**patient.metadata_json, "clinical_context": raw,
                                 "height_cm": 178, "weight_kg": 82}
        db.commit()
    detail = c.client.get(f"/patients/{c.id}")
    assert detail.status_code == 200, detail.text
    clinical = detail.json()["clinical"]
    assert "2 gündür kusma" in clinical["complaints"]
    assert "Hipertansiyon" in clinical["history"]
    assert clinical["medications"] == ["amlodipin 5 mg/gün"]
    assert clinical["notes"].startswith("Ağız mukozası kuru")
    assert clinical["vital_signs"]["height_cm"] == 178
    assert clinical["vital_signs"]["weight_kg"] == 82
    reopened = c.client.get(f"/simple-case/patients/{c.id}").json()
    assert reopened["simple_case"] is None
    assert reopened["clinical"] == clinical


def test_older_case_client_without_vitals_does_not_erase_measurements(persisted_case):
    c = persisted_case
    save(c)
    clinical = clinical_data()
    clinical.pop("vital_signs")
    clinical["notes"] = "Güncellenmiş not"
    updated = save(c, clinical)
    assert updated["clinical"]["vital_signs"] == clinical_data()["vital_signs"]
    assert c.client.get(f"/patients/{c.id}").json()["clinical"]["notes"] == "Güncellenmiş not"


def test_demographics_only_update_preserves_history_and_uses_shared_height_weight(persisted_case):
    c = persisted_case
    save(c)
    response = c.client.put(f"/patients/{c.id}", json={"protocol_no": "VAKA01", "height_cm": 180, "weight_kg": 81})
    assert response.status_code == 200, response.text
    clinical = response.json()["clinical"]
    assert clinical["complaints"] == clinical_data()["complaints"]
    assert clinical["vital_signs"]["heart_rate"] == 108
    assert clinical["vital_signs"]["height_cm"] == 180
    assert clinical["vital_signs"]["weight_kg"] == 81
    reopened = c.client.get(f"/simple-case/patients/{c.id}").json()
    assert reopened["clinical"] == reopened["simple_case"]["clinical"] == clinical
    assert "height_cm" not in response.json()["metadata_json"]


def test_legacy_history_edit_preserves_unspecified_vitals_but_updates_explicit_pulse(persisted_case):
    c = persisted_case
    save(c)
    response = c.client.put(f"/patients/{c.id}", json={"protocol_no": "VAKA01", "clinical_context": {
        "presenting_complaint": {"chief_complaint": "kontrol"},
        "physical_exam": {"pulse_bpm": 92, "examination_findings": "Kontrol notu"},
    }})
    assert response.status_code == 200, response.text
    vitals = response.json()["clinical"]["vital_signs"]
    assert vitals["heart_rate"] == 92
    assert vitals["height_cm"] == 178
    assert vitals["glucose_mg_dl"] == 108
    assert response.json()["clinical"]["complaints"] == ["kontrol"]


def test_explicitly_cleared_vitals_do_not_resurrect_old_height_weight(persisted_case):
    c = persisted_case
    save(c)
    with c.factory() as db:
        patient = db.get(Patient, UUID(c.id))
        patient.metadata_json = {**patient.metadata_json, "height_cm": 199, "weight_kg": 99}
        db.commit()
    clinical = clinical_data()
    clinical["vital_signs"] = None
    save(c, clinical)
    detail = c.client.get(f"/patients/{c.id}").json()
    assert detail["clinical"]["vital_signs"] is None
    assert "height_cm" not in detail["metadata_json"]
    assert patient_clinical_context({"height_cm": 199, "clinical_context": {"vital_signs": None}}).vital_signs is None


@pytest.mark.parametrize("measurement", [{"spo2": 101}, {"heart_rate": True}, {"temperature": float('nan')}, {"weight_kg": -1}])
def test_invalid_measurements_are_rejected(measurement):
    with pytest.raises(ValidationError):
        VitalSigns.model_validate(measurement)


def test_invalid_vital_api_request_does_not_modify_patient(persisted_case):
    c = persisted_case
    save(c)
    clinical = clinical_data()
    clinical["vital_signs"]["spo2"] = 101
    response = c.client.put(f"/simple-case/patients/{c.id}/save", json={"clinical": clinical})
    assert response.status_code == 422
    assert c.client.get(f"/patients/{c.id}").json()["clinical"] == {
        **clinical_data(), "event_date": None, "vitals_event_date": None,
    }
    response = c.client.put(f"/patients/{c.id}", json={"protocol_no": "VAKA01", "clinical_context": clinical})
    assert response.status_code == 422


def test_case_patient_id_and_ownership_are_preserved(persisted_case):
    c = persisted_case
    with c.factory() as db:
        other = Patient(protocol_no="OTHER-01", metadata_json={"owner_user_id": str(uuid4())})
        db.add(other)
        db.commit()
        other_id = other.id
    response = c.client.put(f"/simple-case/patients/{other_id}/save", json={"clinical": clinical_data()})
    assert response.status_code == 404
    with c.factory() as db:
        assert db.get(Patient, other_id).metadata_json.get("clinical_context") is None
        assert db.get(Patient, UUID(c.id)).metadata_json["owner_user_id"] == str(c.user.id)


def test_ai_receives_structured_vitals_separately_from_notes():
    clinical = clinical_data()
    payload = _build_case_payload(SimpleCaseRequest.model_validate({"clinical": clinical}))
    assert payload["clinical"]["vital_signs"]["heart_rate"] == 108
    assert payload["clinical"]["notes"] == clinical["notes"]
    zero = VitalSigns(heart_rate=0, spo2=0)
    assert zero.heart_rate == zero.spo2 == 0


def test_old_patient_without_context_keeps_demographics_on_height_update(persisted_case):
    c = persisted_case
    response = c.client.put(f"/patients/{c.id}", json={"protocol_no": "VAKA01", "height_cm": 180})
    assert response.status_code == 200, response.text
    clinical = response.json()["clinical"]
    assert clinical["age"] == 38
    assert clinical["sex"] == "male"
    assert clinical["vital_signs"]["height_cm"] == 180


def test_case_partial_update_preserves_unspecified_history_and_demographics(persisted_case):
    c = persisted_case
    save(c)
    updated = save(c, {"notes": "Güncel muayene notu"})["clinical"]
    assert updated["age"] == 38
    assert updated["sex"] == "male"
    assert updated["complaints"] == clinical_data()["complaints"]
    assert updated["vital_signs"] == clinical_data()["vital_signs"]


def test_vital_change_invalidates_saved_ai_report(persisted_case):
    c = persisted_case
    save(c)
    with c.factory() as db:
        patient = db.get(Patient, UUID(c.id))
        report = {"report_text": "Önceki rapor", "model": "test",
                  "case_fingerprint": case_fingerprint(patient.metadata_json["simple_case"])}
        patient.metadata_json = {**patient.metadata_json, "simple_case_ai_report": report}
        db.commit()
    assert c.client.get(f"/simple-case/patients/{c.id}").json()["ai_report"] is not None
    clinical = clinical_data()
    clinical["vital_signs"]["heart_rate"] = 92
    save(c, clinical)
    assert c.client.get(f"/simple-case/patients/{c.id}").json()["ai_report"] is None
