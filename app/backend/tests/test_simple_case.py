"""Simple case normalization, access control and report freshness regressions."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dependencies
from app.api.routes import auth, lab_reports, patient_timeline, patients, simple_case
from app.domain.enums import UserRole
from app.domain.simple_case import case_fingerprint, normalize_simple_case
from app.schemas.simple_case import SimpleCaseRequest



def test_age_specific_reference_is_selected_without_classification():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 12, "sex": "male"},
            "labs": [
                {
                    "test_name": "ALP",
                    "value": 210,
                    "unit": "U/L",
                    "source_references": [
                        {
                            "text": "Adult: 40-130 U/L",
                            "minimum": 40,
                            "maximum": 130,
                            "unit": "U/L",
                            "age_min": 18,
                        },
                        {
                            "text": "Age 10-17: 80-350 U/L",
                            "minimum": 80,
                            "maximum": 350,
                            "unit": "U/L",
                            "age_min": 10,
                            "age_max": 17,
                        },
                    ],
                }
            ],
            "reports": [
                {
                    "report_type": "ECG",
                    "findings": "Sinus rhythm.",
                }
            ],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text == "Age 10-17: 80-350 U/L"
    assert result.labs[0].reference_source == "report_age_sex_match"
    dumped = result.model_dump()
    assert "classification" not in dumped["labs"][0]
    assert "status" not in dumped["labs"][0]


def test_source_reference_is_preserved_as_is():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 45, "sex": "female"},
            "labs": [
                {
                    "test_name": "TSH",
                    "value": 2.1,
                    "unit": "mIU/L",
                    "source_reference": "0.27 - 4.20",
                }
            ],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text == "0.27 - 4.20"
    assert result.labs[0].reference_source == "report"


def test_missing_reference_creates_warning_but_does_not_invent_one():
    payload = SimpleCaseRequest.model_validate(
        {
            "clinical": {"age": 30, "sex": "unknown"},
            "labs": [{"test_name": "Example", "value": 10}],
        }
    )

    result = normalize_simple_case(payload)

    assert result.labs[0].reference_text is None
    assert result.labs[0].reference_source == "missing"
    assert result.warnings



@pytest.fixture
def context():
    user = SimpleNamespace(id=uuid4(), role=UserRole.PATIENT, is_active=True)
    patient = SimpleNamespace(
        id=uuid4(), protocol_no="TEST-001", sex="unknown",
        metadata_json={"owner_user_id": str(user.id)},
    )
    other = SimpleNamespace(
        id=uuid4(), metadata_json={"owner_user_id": str(uuid4())},
    )
    now = datetime.now(UTC)
    report = SimpleNamespace(
        id=uuid4(), patient_id=patient.id, uploaded_by_user_id=user.id,
        source_type="simple_case_pdf", file_name="lab.pdf", report_date=None,
        status="saved", metadata_json={}, created_at=now, updated_at=now,
    )
    event = SimpleNamespace(id=uuid4(), patient_id=patient.id)
    records = {patient.id: patient, other.id: other}
    session = SimpleNamespace(
        get=AsyncMock(side_effect=lambda model, id: records.get(id)),
        execute=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock(),
        rollback=AsyncMock(),
    )
    repository = SimpleNamespace(get_by_id=AsyncMock(return_value=report))
    timeline_repository = SimpleNamespace(
        get_by_id=AsyncMock(return_value=event),
        delete_by_id=AsyncMock(return_value=True),
    )
    timeline_service = SimpleNamespace(
        list_for_patient=AsyncMock(return_value=[]), create_event=AsyncMock(),
    )
    app = FastAPI()
    for module in (lab_reports, patient_timeline, patients, simple_case):
        app.include_router(module.router)

    async def get_session():
        yield session

    app.dependency_overrides[dependencies.get_session] = get_session
    app.dependency_overrides[dependencies.get_lab_report_repository] = lambda: repository
    app.dependency_overrides[dependencies.get_patient_timeline_repository] = lambda: timeline_repository
    app.dependency_overrides[dependencies.get_patient_timeline_service] = lambda: timeline_service
    with TestClient(app) as client:
        yield SimpleNamespace(
            app=app, client=client, user=user, patient=patient, other=other,
            report=report, event=event, session=session, repository=repository,
            timeline_repository=timeline_repository, timeline_service=timeline_service,
        )


def authenticate(context):
    context.app.dependency_overrides[auth.get_current_active_user] = lambda: context.user


def test_anonymous_requests_cannot_read_write_or_call_paid_ai(context, monkeypatch):
    ai = AsyncMock()
    monkeypatch.setattr(simple_case, "interpret_simple_case", ai)
    c = context
    requests = [
        ("GET", f"/lab-reports/{c.report.id}", None),
        ("PATCH", f"/lab-reports/{c.report.id}/patient-metadata", {}),
        ("PATCH", f"/lab-reports/{c.report.id}/clinical-context", {}),
        ("PATCH", f"/lab-reports/{c.report.id}/save", {"patient_id": str(c.patient.id)}),
        ("POST", "/timeline/events", {"patient_id": str(c.patient.id), "event_type": "note", "title": "test"}),
        ("GET", f"/timeline/events/{c.event.id}", None),
        ("GET", f"/timeline/patients/{c.patient.id}", None),
        ("GET", f"/timeline/patients/{c.patient.id}/recent", None),
        ("DELETE", f"/timeline/events/{c.event.id}", None),
        ("POST", "/simple-case/ai-interpretation", {}),
        ("POST", "/simple-case/labs/pdf", None),
        ("POST", "/simple-case/reports/pdf", None),
    ]
    for method, path, body in requests:
        response = c.client.request(method, path, json=body)
        assert response.status_code == 401, (path, response.text)
    ai.assert_not_awaited()
    c.session.commit.assert_not_awaited()
    c.timeline_repository.delete_by_id.assert_not_awaited()


@pytest.mark.parametrize("operation", ["read", "demographics", "clinical", "move"])
def test_patient_cannot_access_or_move_another_patients_report(context, operation):
    c = context
    authenticate(c)
    c.report.patient_id = c.other.id
    old_owner = c.report.uploaded_by_user_id
    base = f"/lab-reports/{c.report.id}"
    requests = {
        "read": ("GET", base, None),
        "demographics": ("PATCH", base + "/patient-metadata", {"age": 45}),
        "clinical": ("PATCH", base + "/clinical-context", {}),
        "move": ("PATCH", base + "/save", {"patient_id": str(c.patient.id)}),
    }
    method, path, body = requests[operation]
    response = c.client.request(method, path, json=body)
    assert response.status_code == 404
    assert c.report.patient_id == c.other.id
    assert c.report.uploaded_by_user_id == old_owner
    c.session.commit.assert_not_awaited()


def test_patient_can_read_and_move_own_report(context):
    c = context
    authenticate(c)
    assert c.client.get(f"/lab-reports/{c.report.id}").status_code == 200
    c.other.metadata_json["owner_user_id"] = str(c.user.id)
    response = c.client.patch(
        f"/lab-reports/{c.report.id}/save", json={"patient_id": str(c.other.id)},
    )
    assert response.status_code == 200
    assert c.report.patient_id == c.other.id
    c.session.commit.assert_awaited_once()


@pytest.mark.parametrize("operation", ["create", "read", "list", "recent", "delete"])
def test_timeline_checks_patient_ownership_before_read_or_mutation(context, operation):
    c = context
    authenticate(c)
    c.event.patient_id = c.other.id
    requests = {
        "create": ("POST", "/timeline/events", {"patient_id": str(c.other.id), "event_type": "note", "title": "test"}),
        "read": ("GET", f"/timeline/events/{c.event.id}", None),
        "list": ("GET", f"/timeline/patients/{c.other.id}", None),
        "recent": ("GET", f"/timeline/patients/{c.other.id}/recent", None),
        "delete": ("DELETE", f"/timeline/events/{c.event.id}", None),
    }
    method, path, body = requests[operation]
    assert c.client.request(method, path, json=body).status_code == 404
    c.timeline_service.create_event.assert_not_awaited()
    c.timeline_service.list_for_patient.assert_not_awaited()
    c.timeline_repository.delete_by_id.assert_not_awaited()
    c.session.commit.assert_not_awaited()


def test_patient_can_list_and_delete_own_timeline(context):
    c = context
    authenticate(c)
    assert c.client.get(f"/timeline/patients/{c.patient.id}").status_code == 200
    assert c.client.delete(f"/timeline/events/{c.event.id}").json() == {"deleted": True}
    c.timeline_repository.delete_by_id.assert_awaited_once_with(c.event.id)


def test_doctor_update_preserves_patient_owner(context, monkeypatch):
    c = context
    authenticate(c)
    c.user.role = UserRole.DOCTOR
    owner = str(uuid4())
    c.patient.metadata_json["owner_user_id"] = owner
    monkeypatch.setattr(patients, "_ensure_protocol_available", AsyncMock())
    # This endpoint uses an ORM response schema; test the transaction directly.
    import asyncio
    from app.schemas.patient_record import PatientRecordUpsert
    payload = PatientRecordUpsert(protocol_no="TEST-001", sex="unknown", age=40)
    asyncio.run(patients.update_patient_record(c.patient.id, payload, c.session, c.user))
    assert c.patient.metadata_json["owner_user_id"] == owner
    assert c.patient.metadata_json["age"] == 40


@pytest.mark.parametrize("matches", [True, False, None])
def test_case_save_keeps_only_ai_report_for_the_same_case(context, monkeypatch, matches):
    c = context
    authenticate(c)
    payload = {"clinical": {"age": 40}, "labs": [{"test_name": "TSH", "value": 2.1}]}
    normalized = normalize_simple_case(SimpleCaseRequest.model_validate(payload)).model_dump(mode="json")
    report = {"report_text": "existing", "model": "mock"}
    if matches is not None:
        report["case_fingerprint"] = case_fingerprint(normalized) if matches else "old-case"
    c.patient.metadata_json["simple_case_ai_report"] = report
    monkeypatch.setattr(simple_case, "_persist_simple_case_sources", AsyncMock())
    response = c.client.put(f"/simple-case/patients/{c.patient.id}/save", json=payload)
    assert response.status_code == 200
    assert ("simple_case_ai_report" in c.patient.metadata_json) is (matches is True)
    saved = c.client.get(f"/simple-case/patients/{c.patient.id}").json()
    assert (saved["ai_report"] is not None) is (matches is True)


def test_saved_case_hides_a_report_for_different_inputs(context):
    c = context
    authenticate(c)
    c.patient.metadata_json.update({
        "simple_case": {"clinical": {"age": 40}},
        "simple_case_ai_report": {"report_text": "stale", "case_fingerprint": "old-case"},
    })
    assert c.client.get(f"/simple-case/patients/{c.patient.id}").json()["ai_report"] is None


def test_authenticated_ai_report_is_bound_to_its_inputs(context, monkeypatch):
    c = context
    authenticate(c)
    monkeypatch.setattr(simple_case, "interpret_simple_case", AsyncMock(return_value=SimpleNamespace(report_text="mock report", model="mock")))
    payload = {"clinical": {"age": 45}, "labs": []}
    response = c.client.post(f"/simple-case/patients/{c.patient.id}/ai-interpretation", json=payload)
    assert response.status_code == 200
    expected = normalize_simple_case(SimpleCaseRequest.model_validate(payload)).model_dump(mode="json")
    assert c.patient.metadata_json["simple_case_ai_report"]["case_fingerprint"] == case_fingerprint(expected)
