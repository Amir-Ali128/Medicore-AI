"""Metadata-only case rename against real patient/source persistence."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select

from app.domain.enums import UserRole
from app.domain.simple_case import case_fingerprint
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.schemas.radiology_report import DEMO_PATIENT_ID
from test_patient_isolation import isolated_patients, seed_cases
from test_patient_health_timeline_api import timeline_client, history


def rename(c, patient_id, name):
    return c.client.patch(f"/patients/{patient_id}/case-name", json={"case_name": name})


def linked_rows(c, patient_id):
    with c.factory() as db:
        return {
            model.__tablename__: [(str(row.id), deepcopy(row.metadata_json))
                                  for row in db.scalars(select(model).where(model.patient_id == patient_id))]
            for model in (LabReport, RadiologyReport)
        } | {"lab_results": [(str(row.id), str(row.patient_id), row.raw_value)
                             for row in db.scalars(select(LabResult).where(LabResult.patient_id == patient_id))]}


def test_rename_keeps_uuid_protocol_clinical_sources_timeline_and_exact_ai(timeline_client):
    c = timeline_client
    seed_cases(c)
    # Restore an already-generated report, exactly as a returning user would.
    # This test intentionally never asks even the fake AI to generate a report.
    snapshot = c.client.get(f"/simple-case/patients/{c.a}").json()["simple_case"]
    with c.factory() as db:
        patient = db.get(Patient, c.a)
        patient.metadata_json = {**patient.metadata_json, "simple_case_ai_report": {
            "report_text": "Review", "model": "saved-test-model",
            "case_fingerprint": case_fingerprint(snapshot),
        }}
        db.commit()
    ai_calls = c.ai.call_count
    before = c.client.get(f"/patients/{c.a}").json()
    saved = c.client.get(f"/simple-case/patients/{c.a}").json()
    sources = linked_rows(c, c.a)
    timeline = history(c, c.a)["groups"]
    other = c.client.get(f"/patients/{c.b}").json()

    result = rename(c, c.a, " VAKA22 ")
    assert result.status_code == 200, result.text
    after = result.json()
    assert after["id"] == before["id"] == str(c.a)
    assert after["protocol_no"] == before["protocol_no"]
    assert after["created_at"] == before["created_at"]
    assert after["case_name"] == "VAKA22"
    assert after["metadata_json"] == {**before["metadata_json"], "case_name": "VAKA22"}
    assert after["clinical"] == before["clinical"]
    reopened = c.client.get(f"/simple-case/patients/{c.a}").json()
    assert reopened == {**saved, "case_name": "VAKA22"}
    assert reopened["ai_report"]["report_text"] == "Review"
    assert linked_rows(c, c.a) == sources
    assert history(c, c.a)["groups"] == timeline
    assert c.client.get(f"/patients/{c.b}").json() == other
    assert c.ai.call_count == ai_calls  # Rename/reopen never run AI.
    listed = c.client.get("/patients").json()
    assert next(row for row in listed if row["id"] == str(c.a))["case_name"] == "VAKA22"


def test_legacy_names_and_case_insensitive_duplicates_do_not_overwrite(isolated_patients):
    c = isolated_patients
    assert c.client.get(f"/patients/{c.a}").json()["case_name"] == "PATIENT-A"
    assert rename(c, c.a, "VAKA22").status_code == 200
    before = c.client.get(f"/patients/{c.b}").json()
    rejected = rename(c, c.b, " vaka22 ")
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "Bu isimde başka bir vaka zaten mevcut."
    assert c.client.get(f"/patients/{c.b}").json() == before
    assert rename(c, c.a, "patient-b").status_code == 409
    assert rename(c, c.a, "vaka22").status_code == 200  # Own name is allowed.


@pytest.mark.parametrize("name", ["", "  ", "x" * 81, "Name\nline", "x\u202ey"])
def test_invalid_names_leave_case_untouched(isolated_patients, name):
    c = isolated_patients
    before = c.client.get(f"/patients/{c.a}").json()
    assert rename(c, c.a, name).status_code == 422
    assert c.client.get(f"/patients/{c.a}").json() == before


def test_rename_rejects_identifier_fields_and_unowned_or_demo_records(isolated_patients):
    c = isolated_patients
    response = c.client.patch(f"/patients/{c.a}/case-name", json={"case_name": "VAKA22", "id": str(c.b), "protocol_no": "OTHER"})
    assert response.status_code == 422
    assert rename(c, DEMO_PATIENT_ID, "DEMO").status_code == 404
    assert rename(c, uuid4(), "MISSING").status_code == 404
    c.user.role = UserRole.PATIENT
    c.user.id = c.owner_a
    assert rename(c, c.b, "FOREIGN").status_code == 404
    assert rename(c, c.a, "OWN").status_code == 200


def test_creation_and_legacy_updates_keep_custom_name_and_block_duplicates(isolated_patients):
    c = isolated_patients
    assert rename(c, c.a, "VAKA22").status_code == 200
    rejected = c.client.post("/patients", json={"protocol_no": "vaka22"})
    assert rejected.status_code == 409
    created = c.client.post("/patients", json={"protocol_no": "VAKA23", "age": 30})
    assert created.status_code == 201, created.text
    assert created.json()["case_name"] == "VAKA23"
    assert c.client.put(f"/patients/{c.b}", json={"protocol_no": "VAKA22"}).status_code == 409
    updated = c.client.put(f"/patients/{c.a}", json={"protocol_no": "PATIENT-A", "age": 40})
    assert updated.status_code == 200, updated.text
    assert updated.json()["case_name"] == "VAKA22"


def test_names_and_sources_survive_a_file_database_restart(timeline_client, tmp_path):
    import sqlite3
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.api import dependencies
    from test_patient_isolation import AsyncSourceSession

    c = timeline_client
    seed_cases(c)
    assert rename(c, c.a, "VAKA22").status_code == 200
    expected = c.client.get(f"/simple-case/patients/{c.a}").json()
    before_sources = linked_rows(c, c.a)
    database_file = tmp_path / "persisted-cases.db"
    with sqlite3.connect(database_file) as target:
        connection = c.factory.kw["bind"].raw_connection()
        try:
            connection.driver_connection.backup(target)
        finally:
            connection.close()
    restarted_engine = create_engine(f"sqlite:///{database_file}", connect_args={"check_same_thread": False})
    factory = sessionmaker(restarted_engine)
    async def new_sessions():
        with factory() as db:
            yield AsyncSourceSession(db)
    c.client.app.dependency_overrides[dependencies.get_session] = new_sessions
    try:
        with TestClient(c.client.app) as restarted:
            assert restarted.get(f"/simple-case/patients/{c.a}").json() == expected
            listed = restarted.get("/patients").json()
            assert next(row for row in listed if row["id"] == str(c.a))["case_name"] == "VAKA22"
            assert linked_rows(SimpleNamespace(factory=factory), c.a) == before_sources
    finally:
        restarted_engine.dispose()
