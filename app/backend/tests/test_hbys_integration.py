"""Virtual HBYS simulator + Medicore HBYS integration (FHIR R4 / HL7 v2)."""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # app/ -> hbys_sim package

from hbys_sim import main as sim  # noqa: E402
from hbys_sim import records as sim_records  # noqa: E402
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
    monkeypatch.delenv("HBYS_SIM_UI_PASSWORD", raising=False)
    sim_records.store.clear()
    sim_records.reset_runtime_records()
    yield
    sim_records.store.clear()
    sim_records.reset_runtime_records()


def _client() -> HbysClient:
    return HbysClient("http://hbys", "dev-hbys-key", transport=httpx.ASGITransport(app=sim.app))


def _identity_values(patient) -> list[str]:
    return [patient.given_name, patient.family_name, patient.tckn, patient.phone,
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
    assert "R07.4" in clinical.notes and "Acil Servis" not in clinical.notes  # no unit names
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
        self.refreshes = []
        self.concurrent_save = None

    async def get(self, _model, key):
        return self.patients.get(key)

    async def execute(self, _statement):
        return _Result([(p.id, p.protocol_no, p.metadata_json) for p in self.patients.values()])

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj, attribute_names=None, with_for_update=None):
        self.refreshes.append(with_for_update)
        if self.concurrent_save is not None:  # a physician saved the case meanwhile
            obj.metadata_json = {**obj.metadata_json, **self.concurrent_save}


def _user(role=UserRole.DOCTOR):
    return SimpleNamespace(id=uuid.uuid4(), role=role)


def _settings(monkeypatch, *, individual: bool) -> None:
    monkeypatch.setattr(hbys_routes, "get_settings", lambda: SimpleNamespace(hbys_individual_access=individual))
    hbys_routes._confirmed_simulators.clear()


def test_route_allows_clinical_roles_without_any_flag(monkeypatch) -> None:
    _settings(monkeypatch, individual=False)
    for role in (UserRole.DOCTOR, UserRole.ADMIN, UserRole.LAB_STAFF):
        user = _user(role)
        assert asyncio.run(hbys_routes.hbys_user(_client(), user)) is user


def test_route_rejects_individual_and_viewer_roles_by_default(monkeypatch) -> None:
    _settings(monkeypatch, individual=False)
    for role in (UserRole.PATIENT, UserRole.VIEWER):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(hbys_routes.hbys_user(_client(), _user(role)))
        assert caught.value.status_code == 403
    assert "HBYS_INDIVIDUAL_ACCESS" in caught.value.detail


def test_individual_access_works_only_against_the_simulator(monkeypatch) -> None:
    _settings(monkeypatch, individual=True)
    patient_user = _user(UserRole.PATIENT)
    assert asyncio.run(hbys_routes.hbys_user(_client(), patient_user)) is patient_user
    with pytest.raises(HTTPException) as viewer:
        asyncio.run(hbys_routes.hbys_user(_client(), _user(UserRole.VIEWER)))
    assert viewer.value.status_code == 403

    real = FastAPI()

    @real.get("/fhir/metadata")
    def metadata():
        return {"resourceType": "CapabilityStatement", "software": {"name": "Gerçek Hastane HBYS"}}

    hbys_routes._confirmed_simulators.clear()
    real_client = HbysClient("http://real-hbys", "key", transport=httpx.ASGITransport(app=real))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(hbys_routes.hbys_user(real_client, _user(UserRole.PATIENT)))
    assert caught.value.status_code == 403 and "kurumsal" in caught.value.detail


def test_individual_users_only_see_their_own_linked_cases() -> None:
    owner, other = _user(UserRole.PATIENT), _user(UserRole.PATIENT)
    mine = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100201",
                           metadata_json={"owner_user_id": str(owner.id)})
    theirs = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100202",
                             metadata_json={"owner_user_id": str(other.id)})
    rows = asyncio.run(hbys_routes.list_encounters(_client(), _Session([mine, theirs]), owner))
    linked = {row["protocol_no"]: row["medicore_patient_id"] for row in rows}
    assert linked["HBYS-2026-100201"] == str(mine.id)
    assert linked["HBYS-2026-100202"] is None
    doctor_rows = asyncio.run(hbys_routes.list_encounters(_client(), _Session([mine, theirs]), _user()))
    assert {row["medicore_patient_id"] for row in doctor_rows} >= {str(mine.id), str(theirs.id)}


def test_route_import_returns_deidentified_case_and_linked_patient() -> None:
    patient = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100206", metadata_json={})
    result = asyncio.run(hbys_routes.import_case("e-2006", _client(), _Session([patient]), _user()))
    assert result["protocol_no"] == "HBYS-2026-100206"
    assert result["medicore_patient_id"] == str(patient.id)
    assert "Denemeci" not in json.dumps(result, ensure_ascii=False)


def _current_report(monkeypatch, report):
    async def fake(session, patient, current_user):
        return report
    monkeypatch.setattr(hbys_routes, "_current_ai_report", fake)


def test_route_sends_saved_report_and_records_export(monkeypatch) -> None:
    report = {"report_text": "Diyabetik nefropati olabilir; hekim değerlendirmesi gerekir.",
              "model": "m", "case_fingerprint": "abc"}
    _current_report(monkeypatch, report)
    patient = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100201",
                              metadata_json={"simple_case_ai_report": report})
    session = _Session([patient])
    payload = hbys_routes.HbysReportRequest(patient_id=patient.id)
    result = asyncio.run(hbys_routes.send_report("e-2001", payload, _client(), session, _user()))
    assert result["status"] == "sent" and session.commits == 1
    assert sim.RECEIVED_REPORTS[-1]["conclusion"].startswith("Diyabetik nefropati olabilir")
    assert patient.metadata_json["hbys_export"]["encounter"] == "e-2001"


def test_route_refuses_report_for_other_visit_or_missing_report(monkeypatch) -> None:
    _current_report(monkeypatch, None)
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


def test_route_never_exports_a_stale_report(monkeypatch) -> None:
    """A stored report whose fingerprint no longer matches the saved case is hidden."""
    from app.api.routes import simple_case as simple_case_routes

    stored = {"report_text": "Eski vaka için rapor olabilir; hekim değerlendirmesi gerekir.", "model": "m",
              "case_fingerprint": "eski"}
    patient = SimpleNamespace(id=uuid.uuid4(), protocol_no="HBYS-2026-100201",
                              metadata_json={"simple_case_ai_report": stored})
    calls = []

    async def saved_case_view(patient_id, session, current_user):
        calls.append(patient_id)
        return {"ai_report": None}  # what the case view returns for a stale report

    monkeypatch.setattr(simple_case_routes, "get_saved_simple_case", saved_case_view)
    payload = hbys_routes.HbysReportRequest(patient_id=patient.id)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(hbys_routes.send_report("e-2001", payload, _client(), _Session([patient]), _user()))
    assert caught.value.status_code == 409 and calls == [patient.id]
    assert not sim.RECEIVED_REPORTS


def _bundle_with(encounter, mutate):
    bundle = encounter_bundle(encounter)
    for entry in bundle["entry"]:
        mutate(entry["resource"])
    return bundle


def test_vital_units_are_converted_or_dropped_never_mislabelled() -> None:
    encounter = next(e for e in ENCOUNTERS if e.id == "e-2001")

    def mutate(resource):
        if resource["resourceType"] != "Observation":
            return
        if resource["id"].endswith("-weight_kg"):
            resource["valueQuantity"] = {"value": 154, "unit": "[lb_av]"}
        if resource["id"].endswith("-temperature"):
            resource["valueQuantity"] = {"value": 98.6, "unit": "[degF]"}
        if resource["id"].endswith("-height_cm"):
            resource["valueQuantity"] = {"value": 64, "unit": "furlong"}
        if resource["id"].endswith("-heart_rate"):
            resource["valueQuantity"] = {"value": 84}

    vitals = case_from_bundle(_bundle_with(encounter, mutate)).case.clinical.vital_signs
    assert vitals.weight_kg == pytest.approx(69.85, abs=0.01)
    assert vitals.temperature == pytest.approx(37.0, abs=0.01)
    assert vitals.height_cm is None and vitals.heart_rate is None
    assert vitals.systolic_bp == 148


def test_structured_reference_bounds_are_kept_and_classified() -> None:
    encounter = next(e for e in ENCOUNTERS if e.id == "e-2004")

    def mutate(resource):
        if resource["resourceType"] != "Observation" or "laboratory" not in json.dumps(resource["category"]):
            return
        name = resource["code"]["text"]
        if name == "Potasyum":
            resource["referenceRange"] = [{"low": {"value": 3.5, "unit": "mmol/L"},
                                           "high": {"value": 5.1, "unit": "mmol/L"}}]
        elif name == "Parathormon":
            resource["referenceRange"] = [{"high": {"value": 65, "unit": "pg/mL"}}]
        elif name == "Hemoglobin":
            resource["referenceRange"] = [
                {"low": {"value": 13.5}, "high": {"value": 17.5},
                 "appliesTo": [{"coding": [{"code": "male"}]}]},
                {"low": {"value": 12}, "high": {"value": 15.5},
                 "appliesTo": [{"coding": [{"code": "female"}]}]},
            ]

    imported = case_from_bundle(_bundle_with(encounter, mutate))
    potassium = next(lab for lab in imported.case.labs if lab.test_name == "Potasyum")
    assert potassium.source_reference is None
    assert potassium.source_references[0].minimum == 3.5 and potassium.source_references[0].maximum == 5.1
    statuses = {lab.test_name: str(lab.status).split(".")[-1]
                for lab in normalize_simple_case(imported.case).labs}
    assert statuses["Potasyum"] == "HIGH"       # 6,1 > 5,1
    assert statuses["Parathormon"] == "HIGH"    # 286 > 65
    assert statuses["Hemoglobin"] == "LOW"      # male row selected: 9,9 < 13,5


def _potassium_with(ranges):
    encounter = next(e for e in ENCOUNTERS if e.id == "e-2004")

    def mutate(resource):
        if resource["resourceType"] == "Observation" and resource["code"].get("text") == "Potasyum":
            resource["referenceRange"] = ranges

    imported = case_from_bundle(_bundle_with(encounter, mutate))
    lab = next(item for item in imported.case.labs if item.test_name == "Potasyum")
    status = next(str(item.status).split(".")[-1] for item in normalize_simple_case(imported.case).labs
                  if item.test_name == "Potasyum")
    return lab, status


def test_reference_age_bounds_in_months_or_days_are_never_read_as_years() -> None:
    # Patient is 60: an infant-only range must not be applied, and must not crash the import.
    lab, status = _potassium_with([
        {"low": {"value": 4.1}, "high": {"value": 5.3},
         "age": {"low": {"value": 0, "unit": "mo"}, "high": {"value": 6, "unit": "mo"}}},
        {"low": {"value": 3.5}, "high": {"value": 5.1},
         "age": {"low": {"value": 180, "unit": "d"}}},
    ])
    assert lab.source_references == []  # neither bound is representable in whole years
    assert status == "UNKNOWN"


def test_reference_age_bounds_in_years_are_applied() -> None:
    lab, status = _potassium_with([
        {"low": {"value": 3.5}, "high": {"value": 5.1},
         "age": {"low": {"value": 1, "unit": "a"}, "high": {"value": 24, "unit": "mo"}}},
        {"low": {"value": 3.5}, "high": {"value": 5.1}, "age": {"low": {"value": 18, "unit": "a"}}},
        {"low": {"value": 3.5}, "high": {"value": 5.1},  # contradictory row is skipped, not fatal
         "age": {"low": {"value": 50, "unit": "a"}, "high": {"value": 20, "unit": "a"}}},
    ])
    assert [(r.age_min, r.age_max) for r in lab.source_references] == [(1, 2), (18, None)]
    assert status == "HIGH"


def test_high_precision_bounds_round_trip_without_conflict() -> None:
    lab, status = _potassium_with([{"low": {"value": 3.4999999}, "high": {"value": 5.1234567}}])
    reference = lab.source_references[0]
    assert reference.text == "3.4999999 - 5.1234567"
    assert status == "HIGH"



# ------------------------------------------------------------------ simulator: add patients, status, persistence
_FORM = {
    "given_name": "Form", "family_name": "Hastası", "sex": "male", "birth_date": "1970-05-05",
    "department": "Nefroloji Polikliniği", "diagnosis_code": "n18.3", "diagnosis_text": "KBH evre 3",
    "complaints": "halsizlik, ödem", "systolic_bp": "150", "temperature": "36,8",
    "labs": "Kreatinin | 1,8 | mg/dL | 0,67 - 1,17\nPotasyum | 5,6 | mmol/L | 3,5 - 5,1",
    "modality": "US", "body_region": "Böbrek", "findings": "Parankim ekojenitesi artmış",
}


def _create(api, form=_FORM):
    response = api.post("/ui/new", data=form, follow_redirects=False)
    assert response.status_code == 303, response.text
    return sim.ENCOUNTERS_BY_ID[response.headers["location"].rsplit("/", 1)[1]]


def test_ui_creates_patient_and_visit_that_medicore_can_import() -> None:
    api = TestClient(sim.app)
    encounter = _create(api)
    assert encounter.status == "in-progress" and encounter.protocol_no.startswith("HBYS-")
    assert encounter.diagnoses == [("N18.3", "KBH evre 3")] and encounter.vitals == {"systolic_bp": 150.0, "temperature": 36.8}
    patient = PATIENTS_BY_ID[encounter.patient_id]
    assert not valid_tckn(patient.tckn)  # generated, never a real citizen
    listed = api.get("/fhir/Encounter", headers=KEY).json()
    assert any(entry["resource"]["id"] == encounter.id for entry in listed["entry"])
    imported = case_from_bundle(encounter_bundle(encounter))
    assert "Hastası" not in json.dumps(imported.case.model_dump(mode="json"), ensure_ascii=False)
    statuses = [str(lab.status).split(".")[-1] for lab in normalize_simple_case(imported.case).labs]
    assert statuses == ["HIGH", "HIGH"]
    assert imported.case.reports[0].report_type == "Ultrasonografi"


@pytest.mark.parametrize("change, message", [
    ({"given_name": ""}, "Ad ve soyad"),
    ({"birth_date": "2999-01-01"}, "Doğum tarihi"),
    ({"diagnosis_code": "kalp"}, "ICD-10"),
    ({"systolic_bp": "abc"}, "sayı olmalı"),
    ({"spo2": "130"}, "aralığında"),
    ({"labs": "sadece isim"}, "1. satır"),
    ({"department": "Uydurma"}, "birim"),
    ({"modality": "US", "findings": "", "impression": ""}, "Radyoloji"),
])
def test_ui_form_validation_keeps_input_and_explains(change, message) -> None:
    response = TestClient(sim.app).post("/ui/new", data={**_FORM, **change})
    assert response.status_code == 200 and message in response.text
    assert "Nefroloji Polikliniği" in response.text  # values are kept


def test_ui_status_toggle_and_labels() -> None:
    api = TestClient(sim.app)
    assert api.post("/ui/encounter/e-2001/status", data={"status": "finished"}, follow_redirects=False).status_code == 303
    assert sim.ENCOUNTERS_BY_ID["e-2001"].status == "finished"
    assert api.get("/fhir/Encounter?status=finished", headers=KEY).json()["total"] >= 1
    assert api.post("/ui/encounter/e-2001/status", data={"status": "uydurma"}).status_code == 422
    home = api.get("/").text
    assert "Devam ediyor" in home and "Tamamlandı" in home and "taburcu" in home
    api.post("/ui/encounter/e-2001/status", data={"status": "in-progress"})


def test_ui_rejects_cross_site_posts() -> None:
    api = TestClient(sim.app)
    response = api.post("/ui/new", data=_FORM, headers={"origin": "https://kotu.example"})
    assert response.status_code == 403
    assert api.post("/ui/encounter/e-2001/status", data={"status": "finished"},
                    headers={"referer": "https://kotu.example/x"}).status_code == 403


def test_ui_requires_password_when_a_key_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("HBYS_SIM_API_KEY", "gizli-anahtar")
    api = TestClient(sim.app)
    assert api.get("/").status_code == 401 and api.get("/ui/new").status_code == 401
    assert api.get("/", auth=("hbys", "yanlis")).status_code == 401
    assert api.get("/", auth=("hbys", "gizli-anahtar")).status_code == 200
    monkeypatch.setenv("HBYS_SIM_UI_PASSWORD", "ekran-sifresi")
    assert api.get("/", auth=("hbys", "ekran-sifresi")).status_code == 200


def test_ui_without_any_secret_outside_development_is_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("HBYS_SIM_ENV", "production")
    assert TestClient(sim.app).get("/").status_code == 503


def test_runtime_records_survive_a_restart() -> None:
    api = TestClient(sim.app)
    encounter = _create(api)
    api.post(f"/ui/encounter/{encounter.id}/status", data={"status": "finished"})
    api.post("/ui/encounter/e-2003/status", data={"status": "in-progress"})
    api.post("/fhir/DiagnosticReport", headers=KEY, json=diagnostic_report(
        encounter_id=encounter.id, report_text="Olabilir; hekim değerlendirmesi gerekir.", model="m"))
    sim_records.reset_runtime_records()  # process memory gone (spin-down)
    sim.ENCOUNTERS_BY_ID["e-2003"].status = "finished"
    assert encounter.id not in sim.ENCOUNTERS_BY_ID
    with TestClient(sim.app):  # startup reloads from the store
        restored = sim.ENCOUNTERS_BY_ID[encounter.id]
        assert restored.status == "finished" and len(restored.labs) == 2
        assert sim.ENCOUNTERS_BY_ID["e-2003"].status == "in-progress"
        assert len(sim.RECEIVED_REPORTS) == 1
    sim.ENCOUNTERS_BY_ID["e-2003"].status = "finished"


# ------------------------------------------------------------------ automatic export after an AI report
class _SessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _hbys_patient(protocol="HBYS-2026-100201", report=True):
    metadata = {"simple_case": {"labs": [{"test_name": "K", "source_metadata": {"source_system": "hbys"}}]}}
    if report:
        metadata["simple_case_ai_report"] = {"report_text": "Diyabetik nefropati olabilir; hekim değerlendirmesi gerekir.",
                                             "model": "m", "case_fingerprint": "fp"}
    return SimpleNamespace(id=uuid.uuid4(), protocol_no=protocol, metadata_json=metadata)


def _auto(monkeypatch, patient, user, *, report="saved", individual=False):
    from app.infrastructure.database import session as db_session

    session = _Session([patient])
    monkeypatch.setattr(db_session, "AsyncSessionFactory", lambda: _SessionCtx(session))
    monkeypatch.setattr(hbys_routes, "get_hbys_client", _client)
    _settings(monkeypatch, individual=individual)

    async def current(session_, patient_, user_):
        if report == "saved":
            return patient_.metadata_json.get("simple_case_ai_report")
        return None

    monkeypatch.setattr(hbys_routes, "_current_ai_report", current)
    asyncio.run(hbys_routes.auto_export_ai_report(patient.id, user))
    return patient.metadata_json.get("hbys_export"), session


def test_auto_export_sends_new_report_to_the_visit(monkeypatch) -> None:
    patient = _hbys_patient()
    export, session = _auto(monkeypatch, patient, _user())
    assert export["status"] == "sent" and export["trigger"] == "auto" and export["encounter"] == "e-2001"
    assert sim.RECEIVED_REPORTS[-1]["conclusion"].startswith("Diyabetik nefropati olabilir")
    assert sim.RECEIVED_REPORTS[-1]["status"] == "preliminary" and session.commits == 1


def test_auto_export_for_individual_user_needs_the_flag(monkeypatch) -> None:
    export, _ = _auto(monkeypatch, _hbys_patient(), _user(UserRole.PATIENT), individual=False)
    assert export["status"] == "failed" and "HBYS_INDIVIDUAL_ACCESS" in export["detail"]
    export, _ = _auto(monkeypatch, _hbys_patient(), _user(UserRole.PATIENT), individual=True)
    assert export["status"] == "sent"


def test_auto_export_skips_stale_report_and_unknown_protocol(monkeypatch) -> None:
    export, _ = _auto(monkeypatch, _hbys_patient(), _user(), report="stale")
    assert export["status"] == "skipped" and "Güncel AI raporu yok" in export["detail"]
    export, _ = _auto(monkeypatch, _hbys_patient(protocol="BASKA-1"), _user())
    assert export["status"] == "skipped" and "bulunamadı" in export["detail"]
    assert not sim.RECEIVED_REPORTS


def test_auto_export_ignores_cases_not_imported_from_hbys(monkeypatch) -> None:
    patient = _hbys_patient()
    patient.metadata_json["simple_case"] = {"labs": [{"test_name": "K", "source_metadata": {}}]}
    export, session = _auto(monkeypatch, patient, _user())
    assert export is None and session.commits == 0 and not sim.RECEIVED_REPORTS


def test_auto_export_records_hbys_failures(monkeypatch) -> None:
    patient = _hbys_patient()
    monkeypatch.setattr(hbys_routes, "get_hbys_client",
                        lambda: HbysClient("http://hbys", "yanlis", transport=httpx.ASGITransport(app=sim.app)))
    from app.infrastructure.database import session as db_session
    monkeypatch.setattr(db_session, "AsyncSessionFactory", lambda: _SessionCtx(_Session([patient])))
    _settings(monkeypatch, individual=False)
    asyncio.run(hbys_routes.auto_export_ai_report(patient.id, _user()))
    assert patient.metadata_json["hbys_export"]["status"] == "failed"
    assert "anahtarı reddedildi" in patient.metadata_json["hbys_export"]["detail"]


def test_encounter_list_shows_export_state(monkeypatch) -> None:
    patient = _hbys_patient()
    patient.metadata_json["hbys_export"] = {"status": "sent", "sent_at": "2026-11-16T12:00:00+00:00"}
    rows = asyncio.run(hbys_routes.list_encounters(_client(), _Session([patient]), _user()))
    row = next(item for item in rows if item["protocol_no"] == patient.protocol_no)
    assert row["hbys_export"]["status"] == "sent" and row["medicore_patient_id"] == str(patient.id)


def test_hbys_case_detection() -> None:
    assert hbys_routes.is_hbys_case(_hbys_patient().metadata_json)
    assert hbys_routes.is_hbys_case({"simple_case": {"reports": [{"metadata": {"source_system": "hbys"}}]}})
    assert not hbys_routes.is_hbys_case({"simple_case": {"labs": [{"source_metadata": {"source_system": "pdf"}}]}})
    assert not hbys_routes.is_hbys_case({})


def test_ai_report_schedules_hbys_auto_export_only_for_hbys_cases(monkeypatch) -> None:
    from fastapi import BackgroundTasks
    from app.api.routes import simple_case as simple_case_routes
    from app.schemas.simple_case import SimpleCaseRequest

    async def no_validation(*args, **kwargs):
        return None

    async def fake_interpret(payload):
        return SimpleNamespace(report_text="Bulgular olabilir; hekim değerlendirmesi gerekir.", model="m",
                               consistency_flags=None)

    class _Request:
        async def json(self):
            return {}

    monkeypatch.setattr(simple_case_routes, "_validate_case_patient_sources", no_validation)
    monkeypatch.setattr(simple_case_routes, "interpret_simple_case", fake_interpret)
    monkeypatch.setattr(hbys_routes, "get_settings", lambda: SimpleNamespace(
        hbys_base_url="http://hbys", hbys_api_key="k", hbys_individual_access=False))
    user = SimpleNamespace(id=uuid.uuid4(), role=UserRole.DOCTOR)

    def run(patient):
        session = _Session([patient])
        session.refresh = lambda obj: asyncio.sleep(0)
        tasks = BackgroundTasks()
        asyncio.run(simple_case_routes.ai_interpret_patient_case(
            patient.id, SimpleCaseRequest(), _Request(), session, user, tasks))
        return tasks.tasks

    scheduled = run(_hbys_patient())
    assert len(scheduled) == 1 and scheduled[0].func is hbys_routes.auto_export_ai_report
    plain = _hbys_patient()
    plain.metadata_json["simple_case"] = {"labs": [{"source_metadata": {"source_system": "pdf"}}]}
    assert run(plain) == []



def test_export_result_never_overwrites_a_concurrent_case_save(monkeypatch) -> None:
    patient = _hbys_patient()
    from app.infrastructure.database import session as db_session

    session = _Session([patient])
    session.concurrent_save = {"clinical_context": {"complaints": ["hekimin yeni kaydı"]}, "simple_case_ai_report": None}
    monkeypatch.setattr(db_session, "AsyncSessionFactory", lambda: _SessionCtx(session))
    monkeypatch.setattr(hbys_routes, "get_hbys_client", _client)
    _settings(monkeypatch, individual=False)
    original_report = dict(patient.metadata_json["simple_case_ai_report"])

    async def current(session_, patient_, user_):
        return original_report

    monkeypatch.setattr(hbys_routes, "_current_ai_report", current)
    asyncio.run(hbys_routes.auto_export_ai_report(patient.id, _user()))
    # the row was re-read under a lock and only hbys_export was added on top
    assert session.refreshes == [True]
    assert patient.metadata_json["clinical_context"] == {"complaints": ["hekimin yeni kaydı"]}
    assert patient.metadata_json["simple_case_ai_report"] is None
    assert patient.metadata_json["hbys_export"]["status"] == "sent"


def test_ui_password_may_contain_turkish_characters(monkeypatch) -> None:
    monkeypatch.setenv("HBYS_SIM_UI_PASSWORD", "şifreĞüç")
    api = TestClient(sim.app)
    token = base64.b64encode("hbys:şifreĞüç".encode("utf-8")).decode("ascii")
    assert api.get("/", headers={"Authorization": f"Basic {token}"}).status_code == 200
    wrong = base64.b64encode("hbys:sifre".encode("utf-8")).decode("ascii")
    assert api.get("/", headers={"Authorization": f"Basic {wrong}"}).status_code == 401
    assert sim._same_secret("anahtarçğ", "anahtarçğ") and not sim._same_secret("anahtarcg", "anahtarçğ")



# ------------------------------------------------------------------ policy: no hospital / clinician / unit / address / family
_FORBIDDEN = ["Ankara Şehir Hastanesi", "Gazi Üniversitesi", "Ahmet Hekimoğlu", "Ayşe Kardiyolog",
              "Nefroloji Polikliniği", "Kızılay Mah", "Fatma Annesi", "Mehmet Babası"]


def _bundle_with_care_identities():
    encounter = next(e for e in ENCOUNTERS if e.id == "e-2004")
    bundle = encounter_bundle(encounter)
    for entry in bundle["entry"]:
        resource = entry["resource"]
        if resource["resourceType"] == "Encounter":
            resource["participant"] = [{"individual": {"display": "Uzm. Dr. Ahmet Hekimoğlu"}}]
            resource["serviceProvider"] = {"display": "Ankara Şehir Hastanesi"}
            resource["reasonCode"] += [
                {"text": "Dr. Ayşe Kardiyolog yönlendirdi"},
                {"text": "Gazi Üniversitesi Tıp Fakültesi'nden sevkli"},
                {"text": "Bölüm: Nefroloji Polikliniği"},
                {"text": "annesi Fatma Annesi refakatçi, ev adresi Kızılay Mah. 5"},
            ]
        if resource["resourceType"] == "Patient":
            resource["contact"] = [
                {"relationship": [{"text": "anne"}], "name": {"given": ["Fatma"], "family": "Annesi"},
                 "address": {"text": "Kızılay Mah. Atatürk Bulv. No:5"}},
                {"relationship": [{"text": "baba"}], "name": {"given": ["Mehmet"], "family": "Babası"}},
            ]
            resource["address"] = [{"text": "Kızılay Mah. Atatürk Bulv. No:5 Çankaya/Ankara"}]
    bundle["entry"].append({"resource": {"resourceType": "Organization", "id": "o1", "name": "Gazi Üniversitesi"}})
    bundle["entry"].append({"resource": {"resourceType": "Practitioner", "id": "pr1",
                                         "name": [{"prefix": ["Dr."], "given": ["Ayşe"], "family": "Kardiyolog"}]}})
    return bundle


def test_import_never_carries_hospital_clinician_unit_address_or_family_names() -> None:
    imported = case_from_bundle(_bundle_with_care_identities())
    serialized = json.dumps(imported.case.model_dump(mode="json"), ensure_ascii=False)
    for value in _FORBIDDEN:
        assert value not in serialized, value
    for placeholder in ("[HEKIM]", "[KURUM]", "[BIRIM]", "[ADRES]", "[HASTA_ADI]"):
        assert placeholder in serialized, placeholder
    # clinical content of the same visit is untouched
    assert "bacaklarda şişlik" in imported.case.clinical.complaints
    assert any(lab.test_name == "Kreatinin" for lab in imported.case.labs)


def test_encounter_list_has_no_unit_names() -> None:
    rows = asyncio.run(hbys_routes.list_encounters(_client(), _Session([]), _user()))
    assert rows and all("department" not in row for row in rows)
    assert "Polikliniği" not in json.dumps(rows, ensure_ascii=False)


def test_simulator_does_not_keep_address_doctor_or_family() -> None:
    api = TestClient(sim.app)
    form_page = api.get("/ui/new").text
    assert "name='address'" not in form_page and "name='doctor'" not in form_page
    assert "aile (anne/baba) bilgisi" in form_page
    bundle = api.get("/fhir/Encounter/e-2004/$everything", headers=KEY).json()
    patient = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Patient")
    encounter = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Encounter")
    assert "address" not in patient and "contact" not in patient and "participant" not in encounter
    assert "Hekim:" not in api.get("/ui/encounter/e-2004").text
    assert "SANAL_HASTANE" not in api.get("/hl7/oru/e-2004", headers=KEY).text


def test_older_stored_records_with_address_or_doctor_still_load() -> None:
    sim_records.store.put("patient", "p-old", {"id": "p-old", "tckn": "10000000999", "given_name": "Eski", "family_name": "Kayıt",
                                               "sex": "female", "birth_date": "1970-01-01", "phone": "", "address": "Eski adres"})
    sim_records.store.put("encounter", "e-old", {
        "id": "e-old", "protocol_no": "HBYS-2026-109999", "patient_id": "p-old", "department": "Acil Servis",
        "doctor": "Dr. Eski", "admitted_at": "2026-11-10T10:00:00", "status": "finished", "complaints": [], "history": [],
        "medications": [], "diagnoses": [], "vitals": {}, "labs": [], "specimen_at": "2026-11-10T10:00:00", "radiology": []})
    with TestClient(sim.app):
        assert "e-old" in sim.ENCOUNTERS_BY_ID and not hasattr(sim.ENCOUNTERS_BY_ID["e-old"], "doctor")


def test_ai_payload_masks_clinician_hospital_unit_and_family_keys() -> None:
    from collections import Counter
    from app.infrastructure.ai_privacy_client import _sanitize_payload

    counts = Counter()
    result = _sanitize_payload({"doctor_name": "Dr. Ali", "hospital": "Gazi Hastanesi", "department": "Nefroloji",
                                "mother_name": "Fatma", "father_name": "Mehmet", "home_address": "Kızılay"}, counts, ())
    assert result == {"doctor_name": "[HEKIM]", "hospital": "[KURUM]", "department": "[BIRIM]",
                      "mother_name": "[HASTA_ADI]", "father_name": "[HASTA_ADI]", "home_address": "[ADRES]"}
