"""Real persistence checks for patient isolation and append-only source history."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import dependencies
from app.api.routes import auth, lab_reports, patients, radiology_reports, simple_case
from app.domain.enums import Sex, UserRole
from app.infrastructure.database.models.analysis_run import AnalysisRun
from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.schemas.radiology_report import DEMO_PATIENT_ID


@compiles(JSONB, "sqlite")
def sqlite_jsonb(_type, _compiler, **_kwargs):
    return "JSON"


class AsyncSourceSession:
    def __init__(self, session):
        self.session = session

    def add(self, row):
        self.session.add(row)

    def add_all(self, rows):
        self.session.add_all(rows)

    async def get(self, model, record_id):
        return self.session.get(model, record_id)

    async def execute(self, statement, params=None):
        return self.session.execute(statement, params or {})

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def refresh(self, row):
        self.session.refresh(row)

    async def rollback(self):
        self.session.rollback()

    async def delete(self, row):
        self.session.delete(row)


@pytest.fixture
def isolated_patients(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    for model in (Patient, LabReport, LabResult, RadiologyReport, AnalysisRun, ClinicalHypothesis):
        model.__table__.create(engine)
    factory = sessionmaker(engine)
    user = SimpleNamespace(id=uuid4(), role=UserRole.DOCTOR, is_active=True)
    owner_a, owner_b = uuid4(), uuid4()
    a, b = uuid4(), uuid4()
    with factory() as db:
        db.add_all([
            Patient(id=a, protocol_no="PATIENT-A", sex=Sex.FEMALE,
                    metadata_json={"owner_user_id": str(owner_a)}),
            Patient(id=b, protocol_no="PATIENT-B", sex=Sex.MALE,
                    metadata_json={"owner_user_id": str(owner_b)}),
            Patient(id=DEMO_PATIENT_ID, protocol_no="UPLOAD-HOLD", sex=Sex.UNKNOWN,
                    metadata_json={}),
        ])
        db.commit()
    application = FastAPI()
    for router in (patients.router, simple_case.router, lab_reports.router, radiology_reports.router):
        application.include_router(router)

    async def session_dependency():
        with factory() as db:
            yield AsyncSourceSession(db)

    application.dependency_overrides[dependencies.get_session] = session_dependency
    application.dependency_overrides[auth.get_current_active_user] = lambda: user
    # PostgreSQL archive-file DDL is unrelated to the real source/model commits.
    monkeypatch.setattr(radiology_reports, "_ensure_phase2_table", AsyncMock())
    ai = AsyncMock(return_value=SimpleNamespace(report_text="Review", model="test-only"))
    monkeypatch.setattr(simple_case, "interpret_simple_case", ai)
    with TestClient(application) as client:
        yield SimpleNamespace(client=client, factory=factory, user=user,
                              a=a, b=b, owner_a=owner_a, owner_b=owner_b, ai=ai)
    engine.dispose()


def case_payload(patient_id, *, hb, crp, pulse, label, measured_at="2026-10-01"):
    return {
        "clinical": {
            "complaints": [f"{label} complaint"], "history": [f"{label} history"],
            "medications": [f"{label} medication"], "notes": f"{label} notes",
            "vital_signs": {"heart_rate": pulse, "height_cm": 178 if label == "A" else 165},
        },
        "labs": [
            {"test_name": "Hb", "value": hb, "unit": "g/dL", "measured_at": measured_at,
             "source_metadata": {"patient_id": str(patient_id), "source_file_name": f"{label}-labs.pdf"}},
            {"test_name": "CRP", "value": crp, "unit": "mg/L", "measured_at": measured_at,
             "source_metadata": {"patient_id": str(patient_id), "source_file_name": f"{label}-labs.pdf"}},
        ],
        "reports": [{"report_type": "USG", "report_date": measured_at,
                     "raw_text": f"Abdominal ultrasonografik incelemede {label} bulgusu.",
                     "metadata": {"patient_id": str(patient_id), "source_file_name": f"{label}-report.pdf"}}],
    }


def save(c, patient_id, payload):
    response = c.client.put(f"/simple-case/patients/{patient_id}/save", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def seed_cases(c):
    a = case_payload(c.a, hb=8.2, crp=120, pulse=108, label="A")
    b = case_payload(c.b, hb=15.1, crp=2, pulse=72, label="B")
    save(c, c.a, a)
    save(c, c.b, b)
    return a, b


def test_two_patients_keep_lab_report_clinical_vital_data_separate(isolated_patients):
    c = isolated_patients
    seed_cases(c)
    for patient_id, values, label, pulse in ((c.a, [8.2, 120], "A", 108),
                                             (c.b, [15.1, 2], "B", 72)):
        detail = c.client.get(f"/simple-case/patients/{patient_id}").json()
        assert detail["patient_id"] == str(patient_id)
        assert [row["value"] for row in detail["simple_case"]["labs"]] == values
        assert detail["clinical"]["complaints"] == [f"{label} complaint"]
        assert detail["clinical"]["vital_signs"]["heart_rate"] == pulse
        lab_archive = c.client.get(f"/patients/{patient_id}/lab-reports").json()
        assert len(lab_archive) == 1
        assert lab_archive[0]["patient_id"] == str(patient_id)
        assert [row["value"] for row in lab_archive[0]["metadata_json"]["simple_case_results"]] == values
        reports = c.client.get(f"/radiology-reports/patient/{patient_id}").json()
        assert len(reports) == 1
        assert reports[0]["patient_id"] == str(patient_id)
        assert f"{label} bulgusu" in reports[0]["original_text"]
    with c.factory() as db:
        for patient_id, expected in ((c.a, ["8.2", "120"]), (c.b, ["15.1", "2"])):
            rows = db.scalars(select(LabResult).where(LabResult.patient_id == patient_id)).all()
            assert [row.raw_value for row in rows] == expected
            assert all(db.get(LabReport, row.lab_report_id).patient_id == patient_id for row in rows)


def test_patient_account_cannot_read_other_patients_sources(isolated_patients):
    c = isolated_patients
    seed_cases(c)
    with c.factory() as db:
        report = db.scalar(select(LabReport).where(LabReport.patient_id == c.b))
        report_id = report.id
        radiology_id = db.scalar(select(RadiologyReport.id).where(RadiologyReport.patient_id == c.b))
    c.user.id, c.user.role = c.owner_a, UserRole.PATIENT
    for path in (f"/simple-case/patients/{c.b}", f"/patients/{c.b}/lab-reports",
                 f"/lab-reports/{report_id}", f"/radiology-reports/{radiology_id}"):
        assert c.client.get(path).status_code == 404
    assert c.client.get(f"/simple-case/patients/{c.a}").status_code == 200


@pytest.mark.parametrize("operation", ["save", "ai-interpretation"])
def test_mixed_patient_metadata_is_rejected_before_persistence_or_ai(isolated_patients, operation):
    c = isolated_patients
    a, b = seed_cases(c)
    mixed = deepcopy(a)
    mixed["labs"] = b["labs"]
    response = c.client.request("PUT" if operation == "save" else "POST",
        f"/simple-case/patients/{c.a}/{operation}", json=mixed)
    assert response.status_code == 409, response.text
    c.ai.assert_not_awaited()
    reopened = c.client.get(f"/simple-case/patients/{c.a}").json()
    assert [row["value"] for row in reopened["simple_case"]["labs"]] == [8.2, 120]


@pytest.mark.parametrize("kind", ["lab_report", "lab_result", "radiology_report", "nested"])
def test_foreign_source_reference_is_rejected_even_without_explicit_patient_id(isolated_patients, kind):
    c = isolated_patients
    a, _ = seed_cases(c)
    with c.factory() as db:
        model = {"lab_report": LabReport, "lab_result": LabResult,
                 "radiology_report": RadiologyReport, "nested": LabReport}[kind]
        source_id = db.scalar(select(model.id).where(model.patient_id == c.b))
    reference = {f"{kind if kind != 'nested' else 'lab_report'}_id": str(source_id)}
    a["labs"][0]["source_metadata"] = {"provenance": reference} if kind == "nested" else reference
    response = c.client.post(f"/simple-case/patients/{c.a}/ai-interpretation", json=a)
    assert response.status_code == 404, response.text
    c.ai.assert_not_awaited()


def test_standalone_ai_rejects_sources_from_two_patients(isolated_patients):
    c = isolated_patients
    a, b = seed_cases(c)
    a["reports"] = b["reports"]
    response = c.client.post("/simple-case/ai-interpretation", json=a)
    assert response.status_code == 409
    c.ai.assert_not_awaited()


def test_archived_report_cannot_be_reassigned_to_another_real_patient(isolated_patients):
    c = isolated_patients
    seed_cases(c)
    with c.factory() as db:
        report_id = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.a))
    response = c.client.patch(f"/lab-reports/{report_id}/save", json={"patient_id": str(c.b)})
    assert response.status_code == 409
    with c.factory() as db:
        assert db.get(LabReport, report_id).patient_id == c.a
        assert all(row.patient_id == c.a for row in db.scalars(
            select(LabResult).where(LabResult.lab_report_id == report_id)))


def test_resave_is_idempotent_and_later_results_preserve_all_earlier_sets(isolated_patients):
    c = isolated_patients
    for measured_at, hb in (("2026-08-01", 12.1), ("2026-09-01", 13.0), ("2026-10-03", 13.8)):
        payload = case_payload(c.a, hb=hb, crp=2, pulse=72, label="A", measured_at=measured_at)
        save(c, c.a, payload)
        save(c, c.a, payload)
    # Saving only current clinical information must not delete archived sources.
    save(c, c.a, {"clinical": {"notes": "Updated note"}})
    with c.factory() as db:
        rows = db.scalars(select(LabResult).where(
            LabResult.patient_id == c.a, LabResult.raw_parameter_name == "Hb",
        ).order_by(LabResult.measured_at)).all()
        assert [(row.measured_at.isoformat(), float(row.normalized_value)) for row in rows] == [
            ("2026-08-01", 12.1), ("2026-09-01", 13.0), ("2026-10-03", 13.8),
        ]
        assert len(db.scalars(select(LabReport).where(LabReport.patient_id == c.a)).all()) == 3
        assert len(db.scalars(select(RadiologyReport).where(RadiologyReport.patient_id == c.a)).all()) == 3


def test_one_save_keeps_separate_clinical_dates_and_all_50_parameters(isolated_patients):
    c = isolated_patients
    payload = {"clinical": {}, "labs": [
        {"test_name": f"Parameter {index}", "value": index,
         "measured_at": "2026-10-01" if index < 25 else "2026-10-02",
         "source_metadata": {"source_file_name": "50-results.pdf", "patient_id": str(c.a)}}
        for index in range(50)
    ]}
    save(c, c.a, payload)
    save(c, c.a, payload)
    with c.factory() as db:
        reports = db.scalars(select(LabReport).where(LabReport.patient_id == c.a)).all()
        assert len(reports) == 2
        assert len(db.scalars(select(LabResult).where(LabResult.patient_id == c.a)).all()) == 50
        assert {report.report_date.isoformat() for report in reports} == {"2026-10-01", "2026-10-02"}


def test_shared_temporary_upload_is_visible_only_to_its_uploader(isolated_patients):
    c = isolated_patients
    with c.factory() as db:
        mine = LabReport(patient_id=DEMO_PATIENT_ID, uploaded_by_user_id=c.user.id,
                         source_type="pdf", file_name="mine.pdf", metadata_json={})
        other = LabReport(patient_id=DEMO_PATIENT_ID, uploaded_by_user_id=uuid4(),
                          source_type="pdf", file_name="other.pdf", metadata_json={})
        db.add_all([mine, other])
        db.commit()
        mine_id, other_id = mine.id, other.id
    assert c.client.get(f"/lab-reports/{other_id}").status_code == 404
    assert c.client.get(f"/lab-reports/{mine_id}").status_code == 200
    archive = c.client.get(f"/patients/{DEMO_PATIENT_ID}/lab-reports").json()
    assert [row["id"] for row in archive] == [str(mine_id)]


def test_invalid_internal_source_is_rejected_before_ai(isolated_patients):
    c = isolated_patients
    payload = {"labs": [{"test_name": "Hb", "value": 8.2,
                         "source_metadata": {"source_entity_type": "unsupported",
                                             "source_entity_id": str(uuid4())}}]}
    response = c.client.post(f"/simple-case/patients/{c.a}/ai-interpretation", json=payload)
    assert response.status_code == 422
    c.ai.assert_not_awaited()


def test_simple_case_preserves_exact_original_report_text(isolated_patients):
    c = isolated_patients
    source = "  Abdominal ultrasonografik incelemede doğal görünüm.\n\n "
    save(c, c.a, {"reports": [{"report_type": "USG", "raw_text": source}]})
    with c.factory() as db:
        report = db.scalar(select(RadiologyReport).where(RadiologyReport.patient_id == c.a))
        assert report.original_text == source


@pytest.mark.parametrize("operation", ["read", "save", "ai"])
def test_shared_upload_holding_patient_cannot_be_used_as_case(isolated_patients, operation):
    c = isolated_patients
    path = f"/simple-case/patients/{DEMO_PATIENT_ID}"
    if operation == "read":
        response = c.client.get(path)
    elif operation == "save":
        response = c.client.put(path + "/save", json={"clinical": {"notes": "Private note"}})
    else:
        response = c.client.post(path + "/ai-interpretation", json={})
    assert response.status_code == 404
    c.ai.assert_not_awaited()
    with c.factory() as db:
        assert "simple_case" not in db.get(Patient, DEMO_PATIENT_ID).metadata_json


def test_standalone_ai_rejects_shared_holding_patient_references(isolated_patients):
    c = isolated_patients
    response = c.client.post("/simple-case/ai-interpretation", json={
        "labs": [{"test_name": "Hb", "value": 8.2,
                  "source_metadata": {"patient_id": str(DEMO_PATIENT_ID)}}],
    })
    assert response.status_code == 404
    c.ai.assert_not_awaited()


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("operation", ["save", "scoped-ai", "standalone-ai"])
def test_raw_clinical_patient_markers_cannot_be_dropped_before_scope_check(
    isolated_patients, nested, operation,
):
    c = isolated_patients
    payload = case_payload(c.a, hb=8.2, crp=120, pulse=108, label="A")
    target = payload["clinical"]["vital_signs"] if nested else payload["clinical"]
    target["patient_id"] = str(c.b)
    if operation == "save":
        response = c.client.put(f"/simple-case/patients/{c.a}/save", json=payload)
    elif operation == "scoped-ai":
        response = c.client.post(f"/simple-case/patients/{c.a}/ai-interpretation", json=payload)
    else:
        response = c.client.post("/simple-case/ai-interpretation", json=payload)
    assert response.status_code == 409
    c.ai.assert_not_awaited()
    with c.factory() as db:
        assert "simple_case" not in db.get(Patient, c.a).metadata_json


def test_generic_report_rejects_foreign_metadata_before_persist(isolated_patients):
    c = isolated_patients
    response = c.client.post("/radiology-reports/manual", json={
        "patient_id": str(c.a), "report_text": "Abdominal USG incelemesinde doğal görünüm.",
        "metadata_json": {"clinical_context": {"patient_id": str(c.b)}},
    })
    assert response.status_code == 409
    with c.factory() as db:
        assert not db.scalars(select(RadiologyReport)).all()


@pytest.mark.parametrize("operation", ["read", "list"])
def test_generic_report_does_not_return_legacy_foreign_metadata(isolated_patients, operation):
    c = isolated_patients
    with c.factory() as db:
        report = RadiologyReport(
            patient_id=c.a, uploaded_by_user_id=c.user.id, original_text="Original source text",
            summary="Summary", metadata_json={"clinical_context": {"patient_id": str(c.b)}},
        )
        db.add(report)
        db.commit()
        report_id = report.id
    path = f"/radiology-reports/{report_id}" if operation == "read" else f"/radiology-reports/patient/{c.a}"
    response = c.client.get(path)
    assert response.status_code == 409
    assert "Original source text" not in response.text
