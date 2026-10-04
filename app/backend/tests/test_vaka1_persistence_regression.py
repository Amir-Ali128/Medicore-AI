"""Vaka 1 regressions through the actual save/detail/history and SQL models."""

from copy import deepcopy

import pytest
from sqlalchemy import select

from app.api.routes import patient_timeline
from app.domain.enums import ResultStatus
from app.domain.simple_case import case_fingerprint
from app.infrastructure.database.models.lab_report import LabReport
from app.infrastructure.database.models.lab_result import LabResult
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.radiology_report import RadiologyReport
from test_patient_isolation import isolated_patients, save


@pytest.fixture
def vaka1_client(isolated_patients):
    context = isolated_patients
    context.client.app.include_router(patient_timeline.router)
    return context


def vaka1_payload(patient_id):
    """October 2 observations, October 3 consultation, October 4 iron results."""
    patient_id = str(patient_id)
    early = [
        ("Hb", 10.2, "g/dL", "12–16"),
        ("MCV", 73, "fL", "80–100"),
        ("MCH", 22, "pg", "27–33"),
        ("RDW", 18, "%", "11.5–14.5"),
    ]
    delayed = [
        ("Ferritin", 5, "ng/mL", "15–150"),
        ("Serum demir", 22, "µg/dL", "50–170"),
        ("TIBC", 445, "µg/dL", "250–450"),
        ("TSAT", 5, "%", "15–45"),
    ]
    labs = []
    for late, measurements in ((False, early), (True, delayed)):
        for name, value, unit, reference in measurements:
            labs.append({
                "test_name": name, "value": value, "unit": unit,
                "source_reference": reference,
                # The legacy timestamp is the release date, not the specimen date.
                "measured_at": "2026-10-04" if late else "2026-10-02",
                "specimen_date": "2026-10-02",
                "result_date": "2026-10-04" if late else "2026-10-02",
                "document_date": "2026-10-04",
                "uploaded_at": "2026-10-04T11:00:00+03:00",
                "source_metadata": {
                    "patient_id": patient_id,
                    "source_file_name": "iron-panel.pdf" if late else "hemogram.pdf",
                    "source_flag": "HIGH" if name == "TIBC" else None,
                },
            })
    return {
        "clinical": {
            "age": 38, "sex": "female",
            "complaints": ["Yoğun ve uzun süren adet kanaması", "Halsizlik"],
            "history": ["İntramural myom"], "medications": [],
            "notes": "Mukozalarda solukluk.",
            "event_date": "2026-10-02", "vitals_event_date": "2026-10-02",
            "vital_signs": {"heart_rate": 108, "temperature": 37.2,
                            "height_cm": 178, "weight_kg": 82},
        },
        "labs": labs,
        "reports": [
            {"report_type": "USG", "report_date": "2026-10-04",
             "exam_date": "2026-10-02", "document_date": "2026-10-04",
             "uploaded_at": "2026-10-04T11:00:00+03:00",
             "raw_text": "Pelvik ultrasonografide intramural myom izlenmiştir.",
             "metadata": {"patient_id": patient_id, "source_file_name": "pelvic-usg.pdf"}},
            {"report_type": "Konsültasyon", "report_date": "2026-10-04",
             "document_date": "2026-10-03",
             "uploaded_at": "2026-10-04T11:00:00+03:00",
             "raw_text": "Jinekoloji konsültasyonu: Menoraji ve intramural myom.",
             "metadata": {"patient_id": patient_id, "source_file_name": "gynecology.pdf"}},
        ],
    }


def reopened(context):
    response = context.client.get(f"/simple-case/patients/{context.a}")
    assert response.status_code == 200, response.text
    return response.json()


def timeline(context, patient_id=None):
    response = context.client.get(
        f"/timeline/patients/{patient_id or context.a}/health-history",
    )
    assert response.status_code == 200, response.text
    return response.json()


def lab_by_name(response):
    return {lab["test_name"]: lab for lab in response["labs"]}


def metadata_values(raw, key):
    """Date location within additive JSON metadata is an implementation detail."""
    found = []
    if isinstance(raw, dict):
        if key in raw:
            found.append(raw[key])
        for value in raw.values():
            found.extend(metadata_values(value, key))
    elif isinstance(raw, list):
        for value in raw:
            found.extend(metadata_values(value, key))
    return found


def test_vaka1_save_and_detail_keep_clinical_dates_and_canonical_status(vaka1_client):
    c = vaka1_client
    payload = vaka1_payload(c.a)
    saved = save(c, c.a, payload)
    assert saved["contract_version"] == "medicore-simple-case-v1"
    expected = {"Hb": "LOW", "MCV": "LOW", "MCH": "LOW", "RDW": "HIGH",
                "Ferritin": "LOW", "Serum demir": "LOW", "TIBC": "NORMAL", "TSAT": "LOW"}
    assert {name: lab["status"] for name, lab in lab_by_name(saved).items()} == expected
    tibc = lab_by_name(saved)["TIBC"]
    assert (tibc["reference_low"], tibc["reference_high"]) == (250, 450)
    assert tibc["raw_reference"] == "250–450"
    assert tibc["source_metadata"]["source_flag"] == "HIGH"
    detail = reopened(c)
    assert detail["clinical"]["complaints"] == payload["clinical"]["complaints"]
    assert detail["clinical"]["notes"] == payload["clinical"]["notes"]
    assert detail["clinical"]["vital_signs"]["heart_rate"] == 108
    assert detail["clinical"]["event_date"] == "2026-10-02"
    assert detail["clinical"]["vitals_event_date"] == "2026-10-02"
    for name, lab in lab_by_name(detail["simple_case"]).items():
        assert lab["status"] == expected[name]
        assert lab["specimen_date"] == "2026-10-02"
        assert lab["uploaded_at"].startswith("2026-10-04T11:00:00")
    assert lab_by_name(detail["simple_case"])["TIBC"]["result_date"] == "2026-10-04"


def test_canonical_status_and_distinct_dates_are_written_to_sql_models(vaka1_client):
    c = vaka1_client
    save(c, c.a, vaka1_payload(c.a))
    with c.factory() as db:
        tibc = db.scalar(select(LabResult).where(
            LabResult.patient_id == c.a, LabResult.raw_parameter_name == "TIBC",
        ))
        assert tibc.result_status == ResultStatus.NORMAL
        assert float(tibc.reference_min) == 250
        assert float(tibc.reference_max) == 450
        assert tibc.measured_at.isoformat() == "2026-10-02"
        assert "2026-10-02" in metadata_values(tibc.metadata_json, "specimen_date")
        assert "2026-10-04" in metadata_values(tibc.metadata_json, "result_date")
        assert any(value.startswith("2026-10-04T11:00:00")
                   for value in metadata_values(tibc.metadata_json, "uploaded_at"))
        assert db.get(LabReport, tibc.lab_report_id).patient_id == c.a
        usg = db.scalar(select(RadiologyReport).where(
            RadiologyReport.patient_id == c.a, RadiologyReport.file_name == "pelvic-usg.pdf",
        ))
        assert "2026-10-02" in metadata_values(usg.metadata_json, "exam_date")
        assert "2026-10-04" in metadata_values(usg.metadata_json, "document_date")


def test_vaka1_health_history_uses_observation_and_availability_dates(vaka1_client):
    c = vaka1_client
    save(c, c.a, vaka1_payload(c.a))
    response = timeline(c)
    assert [group["date"] for group in response["groups"]] == [
        "2026-10-04", "2026-10-03", "2026-10-02",
    ]
    groups = {group["date"]: group["entries"] for group in response["groups"]}
    early = groups["2026-10-02"]
    assert {entry["kind"] for entry in early} == {
        "clinical", "vital_signs", "laboratory", "report",
    }
    lab_entries = [entry for entry in early if entry["results"]]
    assert {row["test_name"] for entry in lab_entries for row in entry["results"]} == {
        "Hb", "MCV", "MCH", "RDW", "Ferritin", "Serum demir", "TIBC", "TSAT",
    }
    for entry in lab_entries:
        assert entry["event_date"] == "2026-10-02"
        assert entry["specimen_date"] == "2026-10-02"
    usg = [entry for entry in early if entry["kind"] == "report"]
    assert len(usg) == 1
    assert usg[0]["inferred_report_type"] == "ULTRASOUND"
    assert usg[0]["exam_date"] == "2026-10-02"
    assert usg[0]["document_date"] == "2026-10-04"
    consultation = groups["2026-10-03"]
    assert len(consultation) == 1
    assert consultation[0]["kind"] == "report"
    assert "Jinekoloji" in consultation[0]["report_text"]
    assert consultation[0]["document_date"] == "2026-10-03"
    delayed = groups["2026-10-04"]
    assert delayed and all(entry["kind"] == "lab_result_available" for entry in delayed)
    result_rows = {row["id"]: row for entry in lab_entries for row in entry["results"]}
    referenced = [result_id for entry in delayed for result_id in entry["result_ids"]]
    assert {result_rows[result_id]["test_name"] for result_id in referenced} == {
        "Ferritin", "Serum demir", "TIBC", "TSAT",
    }
    for entry in delayed:
        assert entry["event_date"] == "2026-10-02"
        assert entry["result_date"] == "2026-10-04"
        assert entry["results"] == []
    assert response["total_lab_results"] == 8
    assert sum(len(entry["results"]) for day in groups.values() for entry in day) == 8
    assert all(entry["patient_id"] == str(c.a) for day in groups.values() for entry in day)


def test_delayed_result_projection_never_duplicates_persisted_sources(vaka1_client):
    c = vaka1_client
    payload = vaka1_payload(c.a)
    save(c, c.a, payload)
    save(c, c.a, payload)
    for _ in range(2):
        assert timeline(c)["total_lab_results"] == 8
    with c.factory() as db:
        assert len(db.scalars(select(LabResult).where(LabResult.patient_id == c.a)).all()) == 8
        assert len(db.scalars(select(LabReport).where(LabReport.patient_id == c.a)).all()) == 2
        assert len(db.scalars(select(RadiologyReport).where(RadiologyReport.patient_id == c.a)).all()) == 2
    other = timeline(c, c.b)
    assert other["total_lab_results"] == 0
    assert other["groups"] == []


def test_client_status_and_canonical_bounds_cannot_override_source_reference(vaka1_client):
    c = vaka1_client
    payload = vaka1_payload(c.a)
    tibc = next(lab for lab in payload["labs"] if lab["test_name"] == "TIBC")
    tibc.update(status="HIGH", reference_low=0, reference_high=5, raw_reference="<5")
    saved = save(c, c.a, payload)
    actual = lab_by_name(saved)["TIBC"]
    assert actual["status"] == "NORMAL"
    assert (actual["reference_low"], actual["reference_high"]) == (250, 450)
    assert actual["raw_reference"] == "250–450"
    with c.factory() as db:
        row = db.scalar(select(LabResult).where(
            LabResult.patient_id == c.a, LabResult.raw_parameter_name == "TIBC",
        ))
        assert row.result_status == ResultStatus.NORMAL


def test_pre_status_saved_snapshot_is_reclassified_on_detail_without_source_rewrite(vaka1_client):
    c = vaka1_client
    save(c, c.a, vaka1_payload(c.a))
    with c.factory() as db:
        patient = db.get(Patient, c.a)
        metadata = deepcopy(patient.metadata_json)
        for lab in metadata["simple_case"]["labs"]:
            for field in ("status", "reference_low", "reference_high", "raw_reference",
                          "classification_reason"):
                lab.pop(field, None)
        patient.metadata_json = metadata
        tibc = db.scalar(select(LabResult).where(
            LabResult.patient_id == c.a, LabResult.raw_parameter_name == "TIBC",
        ))
        tibc.result_status = ResultStatus.UNKNOWN
        tibc.reference_min = tibc.reference_max = None
        db.commit()
    detail = reopened(c)
    actual = lab_by_name(detail["simple_case"])["TIBC"]
    assert actual["status"] == "NORMAL"
    assert (actual["reference_low"], actual["reference_high"]) == (250, 450)
    assert actual["source_metadata"]["source_flag"] == "HIGH"
    history = timeline(c)
    historical_tibc = [row for group in history["groups"] for entry in group["entries"]
                       for row in entry["results"] if row["test_name"] == "TIBC"]
    assert len(historical_tibc) == 1
    assert historical_tibc[0]["status"] == "NORMAL"
    with c.factory() as db:
        assert len(db.scalars(select(LabResult).where(LabResult.patient_id == c.a)).all()) == 8
        # A read-time compatibility projection must not silently rewrite legacy storage.
        row = db.scalar(select(LabResult).where(
            LabResult.patient_id == c.a, LabResult.raw_parameter_name == "TIBC",
        ))
        assert row.result_status == ResultStatus.UNKNOWN


def test_fresh_ai_report_keeps_exact_canonical_text_and_timestamp_fingerprint(vaka1_client):
    c = vaka1_client
    payload = vaka1_payload(c.a)
    payload["clinical"].update(event_date="2026-10-02T09:30:00+03:00",
                               notes="  Solukluk.\nKlinik izlem.  ")
    saved = save(c, c.a, payload)
    report = {"report_text": "Güncel rapor", "model": "mock",
              "case_fingerprint": case_fingerprint(saved)}
    with c.factory() as db:
        patient = db.get(Patient, c.a)
        patient.metadata_json = {**patient.metadata_json, "simple_case_ai_report": report}
        db.commit()
    detail = reopened(c)
    assert detail["ai_report"]["report_text"] == "Güncel rapor"
    assert detail["simple_case"]["clinical"] == saved["clinical"]


def test_recomputed_status_invalidates_report_bound_to_a_wrong_old_status(vaka1_client):
    c = vaka1_client
    save(c, c.a, vaka1_payload(c.a))
    with c.factory() as db:
        patient = db.get(Patient, c.a)
        metadata = deepcopy(patient.metadata_json)
        tibc = next(lab for lab in metadata["simple_case"]["labs"] if lab["test_name"] == "TIBC")
        tibc["status"] = "HIGH"
        metadata["simple_case_ai_report"] = {
            "report_text": "Eski hatalı sınıflandırma", "model": "mock",
            "case_fingerprint": case_fingerprint(metadata["simple_case"]),
        }
        patient.metadata_json = metadata
        db.commit()
    detail = reopened(c)
    assert lab_by_name(detail["simple_case"])["TIBC"]["status"] == "NORMAL"
    assert detail["ai_report"] is None


def test_resaving_a_pre_upgrade_source_does_not_duplicate_its_rows(vaka1_client):
    c = vaka1_client
    payload = {"labs": [{"test_name": "TIBC", "value": 445, "unit": "µg/dL",
                "source_reference": "250–450", "measured_at": "2026-10-02",
                "source_metadata": {"source_file_name": "legacy.pdf"}}]}
    save(c, c.a, payload)
    new_fields = ("status", "reference_low", "reference_high", "raw_reference",
                  "classification_reason", "source_reference", "source_references",
                  "event_date", "specimen_date", "result_date", "document_date", "uploaded_at")
    with c.factory() as db:
        source = db.scalar(select(LabReport).where(LabReport.patient_id == c.a))
        raw = deepcopy(source.raw_payload)
        for field in new_fields:
            raw["labs"][0].pop(field, None)
        source.raw_payload = raw
        db.commit()
    save(c, c.a, payload)
    with c.factory() as db:
        assert len(db.scalars(select(LabReport).where(LabReport.patient_id == c.a)).all()) == 1
        assert len(db.scalars(select(LabResult).where(LabResult.patient_id == c.a)).all()) == 1
