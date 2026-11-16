"""Virtual HBYS simulator + Medicore HBYS integration (FHIR R4 / HL7 v2)."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # app/ -> hbys_sim package

from hbys_sim import main as sim  # noqa: E402
from hbys_sim.data import ENCOUNTERS, PATIENTS, PATIENTS_BY_ID  # noqa: E402

from app.api.routes import hbys as hbys_routes  # noqa: E402
from app.domain.enums import UserRole  # noqa: E402
from app.domain.hbys_integration import (  # noqa: E402
    HbysError, HbysNotConfigured, case_from_bundle, diagnostic_report,
)
from app.infrastructure.hbys_client import HbysClient  # noqa: E402
from app.domain.privacy_gateway import valid_tckn  # noqa: E402
from app.domain.simple_case import normalize_simple_case  # noqa: E402
from hbys_sim.fhir import encounter_bundle  # noqa: E402

KEY = {"Authorization": "Bearer dev-hbys-key"}


@pytest.fixture(autouse=True)
def _clean_sim(monkeypatch):
    monkeypatch.delenv("HBYS_SIM_API_KEY", raising=False)
    monkeypatch.setenv("HBYS_SIM_ENV", "development")
    sim.RECEIVED_REPORTS.clear()
    yield
    sim.RECEIVED_REPORTS.clear()


def _client() -> HbysClient:
    return HbysClient("http://hbys", "dev-hbys-key", transport=httpx.ASGITransport(app=sim.app))


def _identity_values(patient) -> list[str]:
    return [patient.given_name, patient.family_name, patient.tckn, patient.phone, patient.address,
            patient.birth_date.isoformat(), patient.birth_date.strftime("%d.%m.%Y")]


# ------------------------------------------------------------------ simulator
def test_synthetic_national_ids_can_never_be_real() -> None:
    assert all(len(p.tckn) == 11 and not valid_tckn(p.tckn) for p in PATIENTS)


def test_simulator_requires_api_key() -> None:
    api = TestClient(sim.app)
    assert api.get("/fhir/Encounter").status_code == 401
    assert api.get("/fhir/Encounter", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert api.get("/fhir/Encounter", headers=KEY).json()["total"] == len(ENCOUNTERS)


def test_simulator_without_key_outside_development_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("HBYS_SIM_ENV", "production")
    assert TestClient(sim.app).get("/fhir/Encounter", headers=KEY).status_code == 503


def test_simulator_status_filter_and_everything_bundle() -> None:
    api = TestClient(sim.app)
    open_visits = api.get("/fhir/Encounter?status=in-progress", headers=KEY).json()
    assert {e["resource"]["status"] for e in open_visits["entry"]} == {"in-progress"}
    bundle = api.get("/fhir/Encounter/e-2004/$everything", headers=KEY).json()
    types = {entry["resource"]["resourceType"] for entry in bundle["entry"]}
    assert {"Patient", "Encounter", "Condition", "Observation", "DiagnosticReport", "MedicationStatement"} <= types
    assert api.get("/fhir/Encounter/yok/$everything", headers=KEY).status_code == 404


def test_simulator_hl7_oru_message_structure() -> None:
    message = TestClient(sim.app).get("/hl7/oru/e-2002", headers=KEY).text
    segments = message.strip("\r").split("\r")
    assert segments[0].startswith("MSH|^~\\&|SANAL_HBYS|") and "|ORU^R01^ORU_R01|" in segments[0]
    assert [s[:3] for s in segments[:4]] == ["MSH", "PID", "PV1", "OBR"]
    obx = [s for s in segments if s.startswith("OBX|")]
    assert len(obx) == len(next(e for e in ENCOUNTERS if e.id == "e-2002").labs)
    assert "89579-7^Troponin I" in obx[0] and "|ng/L|< 34|H|" in obx[0]


def test_simulator_validates_and_stores_received_report() -> None:
    api = TestClient(sim.app)
    resource = diagnostic_report(encounter_id="e-2001", report_text="Bulgular olabilir; hekim değerlendirmesi gerekir.",
                                 model="test")
    assert api.post("/fhir/DiagnosticReport", json=resource).status_code == 401
    created = api.post("/fhir/DiagnosticReport", json=resource, headers=KEY)
    assert created.status_code == 201 and created.json()["encounter"] == "Encounter/e-2001"
    assert len(sim.RECEIVED_REPORTS) == 1
    bad = {**resource, "conclusion": "  "}
    assert api.post("/fhir/DiagnosticReport", json=bad, headers=KEY).status_code == 422
    unknown = {**resource, "encounter": {"reference": "Encounter/yok"}}
    assert api.post("/fhir/DiagnosticReport", json=unknown, headers=KEY).status_code == 404
    assert "Medicore AI raporu" in api.get("/ui/encounter/e-2001").text


def test_simulator_ui_pages_render() -> None:
    api = TestClient(sim.app)
    home = api.get("/")
    assert home.status_code == 200 and "HBYS-2026-100201" in home.text
    assert api.get("/ui/encounter/e-2003").status_code == 200


# ------------------------------------------------------------------ mapping
@pytest.mark.parametrize("encounter", ENCOUNTERS, ids=lambda e: e.id)
def test_imported_case_contains_no_patient_identity(encounter) -> None:
    imported = case_from_bundle(encounter_bundle(encounter))
    serialized = json.dumps(imported.case.model_dump(mode="json"), ensure_ascii=False)
    for value in _identity_values(PATIENTS_BY_ID[encounter.patient_id]):
        assert value not in serialized
    assert imported.protocol_no == encounter.protocol_no


@pytest.mark.parametrize("encounter", ENCOUNTERS, ids=lambda e: e.id)
def test_imported_labs_are_classified_from_source_reference_without_unknown(encounter) -> None:
    normalized = normalize_simple_case(case_from_bundle(encounter_bundle(encounter)).case)
    expected = {"H": "HIGH", "L": "LOW", "N": "NORMAL"}
    by_name = {lab.name: expected[lab.flag] for lab in encounter.labs}
    assert len(normalized.labs) == len(encounter.labs)
    for lab in normalized.labs:
        assert str(lab.status).split(".")[-1] == by_name[lab.test_name], lab.test_name


def test_imported_clinical_context_maps_age_sex_vitals_and_reports() -> None:
    encounter = next(e for e in ENCOUNTERS if e.id == "e-2002")
    imported = case_from_bundle(encounter_bundle(encounter))
    clinical = imported.case.clinical
    assert (imported.age, imported.sex) == (47, "male")
    assert clinical.complaints == encounter.complaints
    assert clinical.vital_signs.systolic_bp == 162 and clinical.vital_signs.spo2 == 94
    assert "R07.4" in clinical.notes and "Acil Servis" in clinical.notes
    assert imported.case.reports[0].report_type == "Röntgen"
    assert imported.case.labs[0].source_reference == "< 34"


def test_free_text_containing_patient_identity_is_scrubbed() -> None:
    encounter = next(e for e in ENCOUNTERS if e.id == "e-2003")
    patient = PATIENTS_BY_ID[encounter.patient_id]
    bundle = encounter_bundle(encounter)
    target = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Encounter")
    target["reasonCode"].append({"text": f"{patient.given_name} {patient.family_name} hanım, tel {patient.phone}"})
    imported = case_from_bundle(bundle)
    serialized = json.dumps(imported.case.model_dump(mode="json"), ensure_ascii=False)
    assert patient.family_name not in serialized and patient.phone not in serialized
    assert "[HASTA_ADI]" in serialized and imported.redaction_counts.get("HASTA_ADI")


def test_bundle_with_mismatched_subject_is_rejected() -> None:
    bundle = encounter_bundle(ENCOUNTERS[0])
    target = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Encounter")
    target["subject"] = {"reference": "Patient/baska-hasta"}
    with pytest.raises(HbysError):
        case_from_bundle(bundle)


def test_ai_report_resource_is_preliminary_and_requires_physician_review() -> None:
    resource = diagnostic_report(encounter_id="e-2001", report_text="x", model="m")
    assert resource["status"] == "preliminary"
    assert {"url": "urn:hbys-sim:physician-review-required", "valueBoolean": True} in resource["extension"]


# ------------------------------------------------------------------ client
def test_client_requires_configuration() -> None:
    with pytest.raises(HbysNotConfigured):
        HbysClient(None, "key")
    with pytest.raises(HbysNotConfigured):
        HbysClient("http://hbys", None)


def test_client_maps_errors_without_leaking_detail() -> None:
    wrong_key = HbysClient("http://hbys", "wrong", transport=httpx.ASGITransport(app=sim.app))
    with pytest.raises(HbysError, match="anahtarı reddedildi"):
        asyncio.run(wrong_key.encounters())
    with pytest.raises(HbysError, match="bulunamadı"):
        asyncio.run(_client().encounter_case("e-9999"))
    with pytest.raises(HbysError, match="Geçersiz muayene"):
        asyncio.run(_client().encounter_case("../../etc"))


def test_client_refuses_outbound_report_with_identifiers_or_subject() -> None:
    leaking = diagnostic_report(encounter_id="e-2001", report_text="Hasta tel 0532 123 45 67 aranmalı.", model="m")
    with pytest.raises(HbysError, match="kişisel bilgi"):
        asyncio.run(_client().send_report(leaking))
    with_subject = {**diagnostic_report(encounter_id="e-2001", report_text="x", model="m"),
                    "subject": {"reference": "Patient/p-1001"}}
    with pytest.raises(HbysError):
        asyncio.run(_client().send_report(with_subject))
    assert not sim.RECEIVED_REPORTS


# ------------------------------------------------------------------ routes
class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    def __init__(self, patients=()):
        self.patients = {p.id: p for p in patients}
        self.commits = 0

    async def get(self, _model, key):
        return self.patients.get(key)

    async def execute(self, _statement):
        return _Result([(p.id, p.protocol_no) for p in self.patients.values()])

    async def commit(self):
        self.commits += 1


def _user(role=UserRole.DOCTOR):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def test_route_rejects_non_clinical_roles() -> None:
    for role in (UserRole.PATIENT, UserRole.VIEWER):
        with pytest.raises(HTTPException) as caught:
            hbys_routes.clinical_user(_user(role))
        assert caught.value.status_code == 403


def test_route_import_returns_deidentified_case_and_linked_patient() -> None:
    patient = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100206", metadata_json={})
    result = asyncio.run(hbys_routes.import_case("e-2006", _client(), _Session([patient]), _user()))
    assert result["protocol_no"] == "HBYS-2026-100206"
    assert result["medicore_patient_id"] == str(patient.id)
    assert "Denemeci" not in json.dumps(result, ensure_ascii=False)


def test_route_sends_saved_report_and_records_export() -> None:
    patient = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100201", metadata_json={
        "simple_case_ai_report": {"report_text": "Diyabetik nefropati olabilir; hekim değerlendirmesi gerekir.",
                                  "model": "m", "case_fingerprint": "abc"},
    })
    session = _Session([patient])
    payload = hbys_routes.HbysReportRequest(patient_id=patient.id)
    result = asyncio.run(hbys_routes.send_report("e-2001", payload, _client(), session, _user()))
    assert result["status"] == "sent" and session.commits == 1
    assert sim.RECEIVED_REPORTS[-1]["conclusion"].startswith("Diyabetik nefropati olabilir")
    assert patient.metadata_json["hbys_export"]["encounter"] == "e-2001"


def test_route_refuses_report_for_other_visit_or_missing_report() -> None:
    patient = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100201", metadata_json={})
    session = _Session([patient])
    payload = hbys_routes.HbysReportRequest(patient_id=patient.id)
    with pytest.raises(HTTPException) as other:
        asyncio.run(hbys_routes.send_report("e-2002", payload, _client(), session, _user()))
    assert other.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        asyncio.run(hbys_routes.send_report("e-2001", payload, _client(), session, _user()))
    assert missing.value.status_code == 409 and not sim.RECEIVED_REPORTS


def test_route_reports_unconfigured_integration(monkeypatch) -> None:
    monkeypatch.setattr(hbys_routes, "get_settings", lambda: SimpleNamespace(
        hbys_base_url=None, hbys_api_key=None, hbys_timeout_seconds=1.0))
    with pytest.raises(HTTPException) as caught:
        hbys_routes.get_hbys_client()
    assert caught.value.status_code == 503
