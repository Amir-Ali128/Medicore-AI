"""SQL-backed API checks for the patient health projection and audit references."""

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.api.routes import patient_timeline
from app.domain.enums import UserRole
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.patient_timeline_event import PatientTimelineEvent
from app.infrastructure.database.models.radiology_report import RadiologyReport
from app.schemas.radiology_report import DEMO_PATIENT_ID
from test_patient_isolation import case_payload, isolated_patients, save, seed_cases


@pytest.fixture
def timeline_client(isolated_patients):
    context = isolated_patients
    PatientTimelineEvent.__table__.create(context.factory.kw["bind"])
    context.client.app.include_router(patient_timeline.router)
    return context


def history(context, patient_id):
    response = context.client.get(f"/timeline/patients/{patient_id}/health-history")
    assert response.status_code == 200, response.text
    return response.json()


def entries(response):
    return [entry for group in response["groups"] for entry in group["entries"]]


def values(response, parameter=None):
    return [
        float(row["value"])
        for entry in entries(response)
        for row in entry["results"]
        if parameter is None or row["test_name"] == parameter
    ]


def test_health_history_keeps_every_kind_bound_to_selected_patient(timeline_client):
    c = timeline_client
    seed_cases(c)
    for patient_id, expected, label, pulse in (
        (c.a, [8.2, 120], "A", 108),
        (c.b, [15.1, 2], "B", 72),
    ):
        response = history(c, patient_id)
        assert response["patient_id"] == str(patient_id)
        assert values(response) == expected
        assert response["total_lab_results"] == 2
        projected = entries(response)
        assert all(entry["patient_id"] == str(patient_id) for entry in projected)
        assert {entry["kind"] for entry in projected} == {
            "laboratory", "report", "clinical", "vital_signs",
        }
        assert all(entry["clinical"]["complaints"] == [f"{label} complaint"]
                   for entry in projected if entry["clinical"] is not None)
        assert all(entry["vital_signs"]["heart_rate"] == pulse
                   for entry in projected if entry["vital_signs"] is not None)
        reports = [entry for entry in projected if entry["kind"] == "report"]
        assert all(f"{label} bulgusu" in entry["report_text"] for entry in reports)
        assert all(entry["inferred_report_type"] == "ULTRASOUND" for entry in reports)


def test_real_test_dates_preserve_august_september_october_results(timeline_client):
    c = timeline_client
    for measured_at, hb in (("2026-08-01", 12.1), ("2026-09-01", 13), ("2026-10-03", 13.8)):
        payload = case_payload(c.a, hb=hb, crp=2, pulse=72, label="A", measured_at=measured_at)
        save(c, c.a, payload)
        save(c, c.a, payload)
    # The records were uploaded together much later than their clinical dates.
    with c.factory() as db:
        for report in db.scalars(select(LabReport).where(LabReport.patient_id == c.a)):
            report.created_at = datetime(2026, 12, 10, tzinfo=timezone.utc)
        db.commit()
    response = history(c, c.a)
    lab_groups = [group for group in response["groups"]
                  if any(entry["results"] for entry in group["entries"])]
    assert [group["date"] for group in lab_groups] == ["2026-10-03", "2026-09-01", "2026-08-01"]
    assert values(response, "Hb") == [13.8, 13, 12.1]
    assert response["total_lab_results"] == 6
    assert all(entry["date_source"] == "measured_at" for entry in entries(response) if entry["results"])


def test_health_history_keeps_all_50_results_and_combines_same_day_kinds(timeline_client):
    c = timeline_client
    payload = case_payload(c.a, hb=8.2, crp=120, pulse=108, label="A", measured_at="2026-10-01")
    payload["labs"] = [
        {"test_name": f"Parameter {index}", "value": index,
         "measured_at": "2026-10-01", "source_metadata": {"patient_id": str(c.a)}}
        for index in range(50)
    ]
    save(c, c.a, payload)
    with c.factory() as db:
        patient = db.get(Patient, c.a)
        metadata = dict(patient.metadata_json)
        context = dict(metadata["simple_case"]["clinical"])
        # This fixture represents pre-canonical-date JSON. Explicit new nulls
        # instead mean that a clinician cleared the corresponding date.
        context.pop("event_date", None)
        context.pop("vitals_event_date", None)
        context["examination_date"] = "2026-10-01"
        context["vital_signs"] = {**context["vital_signs"], "measurement_date": "2026-10-01"}
        metadata["simple_case"] = {**metadata["simple_case"], "clinical": context}
        patient.metadata_json = metadata
        db.commit()
    response = history(c, c.a)
    same_day = next(group for group in response["groups"] if group["date"] == "2026-10-01")
    assert {entry["kind"] for entry in same_day["entries"]} == {
        "laboratory", "report", "clinical", "vital_signs",
    }
    assert response["total_lab_results"] == 50
    assert values(response) == list(range(50))
    assert len({row["test_name"] for entry in entries(response) for row in entry["results"]}) == 50


def test_malformed_result_patient_and_report_association_is_never_exposed(timeline_client):
    c = timeline_client
    seed_cases(c)
    with c.factory() as db:
        report_a = db.scalar(select(LabReport).where(LabReport.patient_id == c.a))
        db.add(LabResult(patient_id=c.b, lab_report_id=report_a.id,
                         raw_parameter_name="FOREIGN SENTINEL", raw_value="666",
                         measured_at=date(2026, 10, 1), metadata_json={}))
        db.commit()
    assert values(history(c, c.a)) == [8.2, 120]
    assert values(history(c, c.b)) == [15.1, 2]


def test_legacy_clinical_context_with_foreign_patient_marker_is_excluded(timeline_client):
    c = timeline_client
    seed_cases(c)
    with c.factory() as db:
        report_a = db.scalar(select(LabReport).where(LabReport.patient_id == c.a))
        report_a.metadata_json = {
            **report_a.metadata_json,
            "clinical_context": {"patient_id": str(c.b), "notes": "B secret",
                                 "vital_signs": {"heart_rate": 99}},
        }
        db.commit()
    response = history(c, c.a)
    assert "B secret" not in str(response)
    assert all(entry["vital_signs"]["heart_rate"] == 108
               for entry in entries(response) if entry["vital_signs"] is not None)


def test_health_history_and_audit_keep_patient_account_ownership_checks(timeline_client):
    c = timeline_client
    seed_cases(c)
    c.user.id, c.user.role = c.owner_a, UserRole.PATIENT
    assert c.client.get(f"/timeline/patients/{c.a}/health-history").status_code == 200
    for path in (f"/timeline/patients/{c.b}/health-history",
                 f"/timeline/patients/{c.b}",
                 f"/timeline/patients/{c.b}/recent",
                 f"/timeline/patients/{uuid4()}/health-history"):
        assert c.client.get(path).status_code == 404


@pytest.mark.parametrize("reference", ["lab_report_id", "source_entity", "nested_patient"])
def test_audit_rejects_foreign_references_before_writing(timeline_client, reference):
    c = timeline_client
    seed_cases(c)
    with c.factory() as db:
        report_b = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.b))
    payload = {"patient_id": str(c.a), "event_type": "source_added", "title": "New source"}
    if reference == "lab_report_id":
        payload["lab_report_id"] = str(report_b)
    elif reference == "source_entity":
        payload.update(source_entity_type="patient", source_entity_id=str(c.b))
    else:
        payload["metadata_json"] = {"provenance": {"patient_id": str(c.b)}}
    response = c.client.post("/timeline/events", json=payload)
    assert response.status_code == (409 if reference == "nested_patient" else 404), response.text
    with c.factory() as db:
        assert db.scalars(select(PatientTimelineEvent)).all() == []


def test_audit_accepts_own_source_and_derives_actor_from_authenticated_user(timeline_client):
    c = timeline_client
    seed_cases(c)
    with c.factory() as db:
        report_a = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.a))
    response = c.client.post("/timeline/events", json={
        "patient_id": str(c.a), "event_type": "source_added", "title": "Own source",
        "lab_report_id": str(report_a), "actor_user_id": str(uuid4()),
    })
    assert response.status_code == 201, response.text
    event = response.json()
    assert event["actor_user_id"] == str(c.user.id)
    assert event["lab_report_id"] == str(report_a)
    assert c.client.get(f"/timeline/events/{event['id']}").json()["id"] == event["id"]
    assert c.client.get(f"/timeline/patients/{c.a}").json()["count"] == 1
    assert c.client.get(f"/timeline/patients/{c.b}").json()["count"] == 0


def test_invalid_legacy_audit_references_are_filtered_without_deleting_records(timeline_client):
    c = timeline_client
    seed_cases(c)
    valid_id, invalid_id, other_id = uuid4(), uuid4(), uuid4()
    with c.factory() as db:
        report_a = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.a))
        report_b = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.b))
        for event_id, patient_id, report_id in (
            (valid_id, c.a, report_a), (invalid_id, c.a, report_b), (other_id, c.b, report_b),
        ):
            db.add(PatientTimelineEvent(
                id=event_id, patient_id=patient_id, lab_report_id=report_id,
                event_type="source_added", title="Legacy record",
                occurred_at=datetime(2026, 10, 1, tzinfo=timezone.utc), metadata_json={},
            ))
        db.commit()
    for suffix in ("", "/recent"):
        response = c.client.get(f"/timeline/patients/{c.a}{suffix}")
        assert response.status_code == 200, response.text
        assert [event["id"] for event in response.json()["events"]] == [str(valid_id)]
        assert response.json()["count"] == 1
    assert c.client.get(f"/timeline/events/{invalid_id}").status_code == 404
    with c.factory() as db:
        assert len(db.scalars(select(PatientTimelineEvent)).all()) == 3


@pytest.mark.parametrize("reference", ["patient_id", "nested_source"])
def test_patient_update_rejects_foreign_clinical_context_before_persisting(timeline_client, reference):
    c = timeline_client
    seed_cases(c)
    context = {"notes": "Foreign context must not replace A"}
    if reference == "patient_id":
        context["patient_id"] = str(c.b)
    else:
        with c.factory() as db:
            report_b = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.b))
        context["provenance"] = {"lab_report_id": str(report_b)}
    response = c.client.put(f"/patients/{c.a}", json={
        "protocol_no": "PATIENT-A", "clinical_context": context,
    })
    assert response.status_code == (409 if reference == "patient_id" else 404), response.text
    reopened = c.client.get(f"/simple-case/patients/{c.a}").json()
    assert reopened["clinical"]["notes"] == "A notes"


def test_unknown_generic_report_keeps_original_text_and_fallback_label(timeline_client):
    c = timeline_client
    report_id = uuid4()
    original = "Muayene bulguları: Özgül inceleme türü belirtilmemiştir."
    with c.factory() as db:
        db.add(RadiologyReport(id=report_id, patient_id=c.a, file_name="generic.pdf",
                               original_text=original, summary=original, report_date=date(2026, 9, 2),
                               metadata_json={}))
        db.commit()
    response = history(c, c.a)
    report = next(entry for entry in entries(response) if entry["source_id"] == str(report_id))
    assert report["report_text"] == original
    assert report["inferred_report_type"] == "UNKNOWN"
    assert response["groups"][0]["date"] == "2026-09-02"


@pytest.mark.parametrize("suffix", ["/health-history", "", "/recent"])
def test_shared_upload_identity_cannot_be_opened_as_a_patient_timeline(timeline_client, suffix):
    c = timeline_client
    assert c.client.get(f"/timeline/patients/{DEMO_PATIENT_ID}{suffix}").status_code == 404


def test_foreign_source_reference_inside_legacy_context_is_not_projected(timeline_client):
    c = timeline_client
    seed_cases(c)
    with c.factory() as db:
        source_b = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.b))
        report_a = db.scalar(select(RadiologyReport).where(RadiologyReport.patient_id == c.a))
        report_a.metadata_json = {
            **report_a.metadata_json,
            "clinical_context": {"notes": "B foreign source", "lab_report_id": str(source_b)},
        }
        invalid_id = report_a.id
        db.commit()
    response = history(c, c.a)
    assert "B foreign source" not in str(response)
    assert all(entry["source_id"] != str(invalid_id) for entry in entries(response))
    assert values(response) == [8.2, 120]


def test_foreign_vital_provenance_is_not_discarded_before_patient_validation(timeline_client):
    c = timeline_client
    seed_cases(c)
    response = c.client.put(f"/patients/{c.a}", json={
        "protocol_no": "PATIENT-A",
        "clinical_context": {"vital_signs": {"heart_rate": 99, "patient_id": str(c.b)}},
    })
    assert response.status_code == 409, response.text
    assert c.client.get(f"/patients/{c.a}").json()["clinical"]["vital_signs"]["heart_rate"] == 108


def test_shared_upload_cannot_reference_another_uploaders_source(timeline_client):
    c = timeline_client
    own_id, foreign_id = uuid4(), uuid4()
    with c.factory() as db:
        db.add_all([
            LabReport(id=foreign_id, patient_id=DEMO_PATIENT_ID,
                      uploaded_by_user_id=uuid4(), metadata_json={}),
            LabReport(id=own_id, patient_id=DEMO_PATIENT_ID,
                      uploaded_by_user_id=c.user.id,
                      metadata_json={"provenance": {"lab_report_id": str(foreign_id)}}),
        ])
        db.commit()
    assert c.client.get(f"/lab-reports/{own_id}").status_code == 404
    response = c.client.patch(f"/lab-reports/{own_id}/save", json={"patient_id": str(c.a)})
    assert response.status_code == 404, response.text
    with c.factory() as db:
        assert db.get(LabReport, own_id).patient_id == DEMO_PATIENT_ID


def test_uploader_can_archive_own_staged_reference_without_losing_its_context(timeline_client):
    c = timeline_client
    own_id = uuid4()
    with c.factory() as db:
        db.add(LabReport(id=own_id, patient_id=DEMO_PATIENT_ID, uploaded_by_user_id=c.user.id,
                         metadata_json={"patient_id": str(DEMO_PATIENT_ID), "clinical_context": {
                             "notes": "My upload", "patient_id": str(DEMO_PATIENT_ID),
                             "lab_report_id": str(own_id),
                         }}))
        db.commit()
    response = c.client.patch(f"/lab-reports/{own_id}/save", json={"patient_id": str(c.a)})
    assert response.status_code == 200, response.text
    metadata = response.json()["metadata_json"]
    assert metadata["patient_id"] == metadata["clinical_context"]["patient_id"] == str(c.a)
    assert metadata["clinical_context"]["notes"] == "My upload"
    assert c.client.get(f"/lab-reports/{own_id}").status_code == 200


def test_lab_clinical_attachment_checks_raw_patient_marker_before_extra_is_ignored(timeline_client):
    c = timeline_client
    seed_cases(c)
    with c.factory() as db:
        report_id = db.scalar(select(LabReport.id).where(LabReport.patient_id == c.a))
    response = c.client.patch(f"/lab-reports/{report_id}/clinical-context", json={
        "patient_information": {"age": 99, "patient_id": str(c.b)},
    })
    assert response.status_code == 409, response.text
    with c.factory() as db:
        assert "clinical_context" not in db.get(LabReport, report_id).metadata_json


def test_shared_upload_identity_is_not_a_patient_archive_record(timeline_client):
    c = timeline_client
    listed = c.client.get("/patients")
    assert listed.status_code == 200, listed.text
    assert {record["id"] for record in listed.json()} == {str(c.a), str(c.b)}
    for method, body in (("GET", None), ("PUT", {"protocol_no": "HOLD-EDIT"}), ("DELETE", None)):
        response = c.client.request(method, f"/patients/{DEMO_PATIENT_ID}", json=body)
        assert response.status_code == 404, response.text
    with c.factory() as db:
        assert db.get(Patient, DEMO_PATIENT_ID).protocol_no == "UPLOAD-HOLD"
