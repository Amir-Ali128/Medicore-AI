"""Sanal HBYS: a small hospital information system simulator for Medicore.

It mimics the parts of a Turkish HBYS that Medicore integrates with: hasta kabul
(patients + visit protocol numbers), poliklinik/acil visits (complaints, vitals,
ICD-10 diagnoses, medications), laboratory results and radiology reports. Data is
exposed through standard interfaces (FHIR R4 JSON and HL7 v2.5 ORU^R01) and
Medicore posts its physician-review AI report back as a FHIR DiagnosticReport.

Run from the ``app`` directory:  uvicorn hbys_sim.main:app --port 8100
All records are synthetic; see data.py. Records added through the UI and received
reports persist in PostgreSQL when HBYS_SIM_DATABASE_URL is set (store.py).
"""

from __future__ import annotations

import base64
import hmac
import html
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Any
from urllib.parse import parse_qs, urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from . import records
from .data import ENCOUNTERS, ENCOUNTERS_BY_ID, PATIENTS_BY_ID, SimLab, SimRadiology
from .fhir import capability_statement, encounter_bundle, encounter_search_bundle
from .hl7 import oru_r01

_MAX_REPORT_CHARS = 20_000
_DEV_KEY = "dev-hbys-key"
_STATUS_LABELS = {"in-progress": "Devam ediyor", "finished": "Tamamlandı"}
_DEPARTMENTS = [
    "Acil Servis", "Dahiliye Polikliniği", "Kardiyoloji Polikliniği", "Nefroloji Polikliniği",
    "Endokrinoloji Polikliniği", "Göğüs Hastalıkları Polikliniği", "Gastroenteroloji Polikliniği",
    "Nöroloji Polikliniği", "Kadın Hastalıkları ve Doğum Polikliniği", "Çocuk Sağlığı ve Hastalıkları Polikliniği",
    "Genel Cerrahi Polikliniği", "Yoğun Bakım",
]
_MODALITIES = {"": "Yok", "DX": "Röntgen", "US": "Ultrasonografi", "CT": "BT", "MR": "MR"}
_VITAL_FIELDS = {
    "systolic_bp": ("Sistolik KB (mmHg)", 40, 300), "diastolic_bp": ("Diyastolik KB (mmHg)", 20, 200),
    "heart_rate": ("Nabız (/dk)", 20, 250), "respiratory_rate": ("Solunum (/dk)", 4, 80),
    "temperature": ("Ateş (°C)", 30, 45), "spo2": ("SpO₂ (%)", 40, 100),
    "height_cm": ("Boy (cm)", 30, 250), "weight_kg": ("Kilo (kg)", 1, 400),
}
_ICD10 = re.compile(r"^[A-Z][0-9]{2}(\.[0-9A-Z]{1,4})?$")


@asynccontextmanager
async def lifespan(_: FastAPI):
    records.load()
    yield


app = FastAPI(title="Sanal HBYS", version="1.1", docs_url="/docs", redoc_url=None, lifespan=lifespan)

# Reports received from Medicore (same list object the records module keeps in sync).
RECEIVED_REPORTS = records.RECEIVED_REPORTS


def _development() -> bool:
    return os.environ.get("HBYS_SIM_ENV", "development") == "development"


def _api_key() -> str:
    key = os.environ.get("HBYS_SIM_API_KEY", "").strip()
    if key:
        return key
    if not _development():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "HBYS_SIM_API_KEY tanımlı değil.")
    return _DEV_KEY


def require_api_key(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = _api_key()
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz HBYS API anahtarı.",
                            headers={"WWW-Authenticate": "Bearer"})


Authorized = Annotated[None, Depends(require_api_key)]


def _ui_password() -> str | None:
    """UI password: HBYS_SIM_UI_PASSWORD, else the API key. None = open (development only)."""
    password = os.environ.get("HBYS_SIM_UI_PASSWORD", "").strip() or os.environ.get("HBYS_SIM_API_KEY", "").strip()
    if password:
        return password
    if _development():
        return None
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "HBYS_SIM_UI_PASSWORD veya HBYS_SIM_API_KEY tanımlı değil.")


def require_ui_login(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = _ui_password()
    if expected is None:
        return
    scheme, _, encoded = (authorization or "").partition(" ")
    try:
        _, _, supplied = base64.b64decode(encoded.strip()).decode("utf-8").partition(":")
    except Exception:
        supplied = ""
    if scheme.lower() != "basic" or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sanal HBYS girişi gerekli.",
                            headers={"WWW-Authenticate": 'Basic realm="Sanal HBYS", charset="UTF-8"'})


UiLogin = Annotated[None, Depends(require_ui_login)]


def _same_origin(request: Request) -> None:
    """Basic-auth credentials are sent automatically; refuse cross-site form posts."""
    host = request.headers.get("host", "")
    for header in ("origin", "referer"):
        value = request.headers.get(header)
        if value and urlparse(value).netloc != host:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Farklı bir siteden gelen istek reddedildi.")


def _encounter_or_404(encounter_id: str):
    encounter = ENCOUNTERS_BY_ID.get(encounter_id)
    if encounter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Muayene kaydı bulunamadı.")
    return encounter


# ---------------------------------------------------------------- integration API
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "system": "sanal-hbys"}


@app.get("/fhir/metadata")
def metadata(_: Authorized) -> dict[str, Any]:
    return capability_statement()


@app.get("/fhir/Encounter")
def search_encounters(
    _: Authorized,
    encounter_status: Annotated[str | None, Query(alias="status", pattern="^(in-progress|finished)$")] = None,
) -> dict[str, Any]:
    encounters = [item for item in ENCOUNTERS if encounter_status in (None, item.status)]
    encounters.sort(key=lambda item: item.admitted_at, reverse=True)
    return encounter_search_bundle(encounters)


@app.get("/fhir/Encounter/{encounter_id}/$everything")
def encounter_everything(encounter_id: str, _: Authorized) -> dict[str, Any]:
    return encounter_bundle(_encounter_or_404(encounter_id))


@app.get("/hl7/oru/{encounter_id}", response_class=PlainTextResponse)
def hl7_oru(encounter_id: str, _: Authorized) -> str:
    return oru_r01(_encounter_or_404(encounter_id))


@app.post("/fhir/DiagnosticReport", status_code=status.HTTP_201_CREATED)
def receive_report(resource: dict[str, Any], _: Authorized) -> dict[str, Any]:
    if resource.get("resourceType") != "DiagnosticReport":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "resourceType DiagnosticReport olmalı.")
    reference = str((resource.get("encounter") or {}).get("reference") or "")
    encounter = _encounter_or_404(reference.removeprefix("Encounter/"))
    conclusion = resource.get("conclusion")
    if not isinstance(conclusion, str) or not conclusion.strip() or len(conclusion) > _MAX_REPORT_CHARS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "conclusion boş olamaz ve 20000 karakteri aşamaz.")
    if resource.get("status") not in {"preliminary", "final"}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status preliminary veya final olmalı.")
    stored = {
        **resource,
        "id": f"medicore-{uuid.uuid4()}",
        "subject": {"reference": f"Patient/{encounter.patient_id}"},
    }
    records.add_report(stored)
    return {"id": stored["id"], "encounter": f"Encounter/{encounter.id}", "status": "accepted"}


# ---------------------------------------------------------------- HBYS UI
_STYLE = """
:root{--bg:#f4f6f8;--card:#fff;--ink:#14202b;--muted:#5b6b7a;--line:#dde3e9;--brand:#0f5c8c;--hi:#b42318;--lo:#175cd3;--ok:#067647}
@media (prefers-color-scheme:dark){:root{--bg:#0f1720;--card:#16212c;--ink:#e6edf3;--muted:#9aa9b6;--line:#26333f;--brand:#5fb0e6;--hi:#ff8a80;--lo:#8ab4ff;--ok:#75e0a7}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
header{background:var(--brand);color:#fff;padding:14px 16px}header h1{margin:0;font-size:18px}header p{margin:2px 0 0;opacity:.85;font-size:13px}
main{max-width:1100px;margin:0 auto;padding:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:14px;overflow-x:auto}
h2{font-size:16px;margin:0 0 10px}table{border-collapse:collapse;width:100%;min-width:560px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;border:1px solid var(--line)}
.tag.open{color:var(--ok);border-color:currentColor}.H{color:var(--hi);font-weight:600}.L{color:var(--lo);font-weight:600}
a{color:var(--brand)}.muted{color:var(--muted)}pre{white-space:pre-wrap;margin:0;font:inherit}
.warn{border-left:4px solid #f79009;padding:8px 12px;background:var(--card);margin-bottom:14px;border-radius:6px}
.err{border-left:4px solid var(--hi);padding:8px 12px;background:var(--card);margin-bottom:14px;border-radius:6px}
.btn{display:inline-block;background:var(--brand);color:#fff;border:0;border-radius:8px;padding:8px 14px;font:inherit;cursor:pointer;text-decoration:none}
.btn.ghost{background:transparent;color:var(--brand);border:1px solid var(--brand)}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}
label{display:block;font-size:13px;color:var(--muted)}input,select,textarea{width:100%;margin-top:3px;padding:7px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);font:inherit}
textarea{min-height:70px}fieldset{border:1px solid var(--line);border-radius:8px;margin:0 0 12px;padding:10px 12px}legend{font-weight:600;padding:0 4px}
"""


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
        f"<style>{_STYLE}</style></head><body><header><h1>Sanal HBYS</h1>"
        f"<p>Hastane Bilgi Yönetim Sistemi simülasyonu · tüm kayıtlar sentetiktir</p></header>"
        f"<main><div class='warn'>Bu sistem yalnızca test içindir. <b>Gerçek hasta bilgisi girmeyin.</b> "
        f"T.C. numaraları sistem tarafından üretilir ve geçersizdir (checksum'dan geçmez).</div>{body}</main></body></html>"
    )


def _status_tag(value: str) -> str:
    css = "tag open" if value == "in-progress" else "tag"
    return f"<span class='{css}'>{_STATUS_LABELS.get(value, html.escape(value))}</span>"


@app.get("/", response_class=HTMLResponse)
def ui_home(_: UiLogin) -> HTMLResponse:
    rows = []
    for encounter in sorted(ENCOUNTERS, key=lambda item: item.admitted_at, reverse=True):
        patient = PATIENTS_BY_ID[encounter.patient_id]
        reports = sum(1 for item in RECEIVED_REPORTS if item["encounter"]["reference"] == f"Encounter/{encounter.id}")
        rows.append(
            f"<tr><td><a href='/ui/encounter/{encounter.id}'>{html.escape(encounter.protocol_no)}</a></td>"
            f"<td>{html.escape(patient.given_name)} {html.escape(patient.family_name)}</td>"
            f"<td>{html.escape(encounter.department)}</td><td>{encounter.admitted_at:%d.%m.%Y %H:%M}</td>"
            f"<td>{_status_tag(encounter.status)}</td><td>{len(encounter.labs)} tetkik</td>"
            f"<td>{'✓ ' + str(reports) if reports else '<span class=muted>-</span>'}</td></tr>"
        )
    received = "".join(
        f"<tr><td><a href='/ui/encounter/{html.escape(item['encounter']['reference'].removeprefix('Encounter/'))}'>"
        f"{html.escape(ENCOUNTERS_BY_ID[item['encounter']['reference'].removeprefix('Encounter/')].protocol_no if item['encounter']['reference'].removeprefix('Encounter/') in ENCOUNTERS_BY_ID else item['encounter']['reference'])}</a></td>"
        f"<td>{'Ön değerlendirme (hekim onayı bekliyor)' if item.get('status') == 'preliminary' else html.escape(str(item.get('status', '')))}</td>"
        f"<td>{html.escape(item['meta']['lastUpdated'][:16].replace('T', ' '))}</td></tr>"
        for item in reversed(RECEIVED_REPORTS)
    ) or "<tr><td colspan='3' class='muted'>Henüz Medicore'dan rapor gelmedi.</td></tr>"
    return _page("Sanal HBYS", (
        "<div class='card'><div class='row'><h2>Hasta Kabul · Muayene Listesi</h2>"
        "<a class='btn' href='/ui/new'>+ Yeni hasta / muayene</a></div>"
        "<p class='muted'>Durum: <b>Devam ediyor</b> = hasta hastanede, muayene/tetkikler sürüyor; "
        "<b>Tamamlandı</b> = muayene kapandı, hasta taburcu oldu veya poliklinikten çıktı.</p>"
        "<table><tr><th>Protokol No</th><th>Hasta</th><th>Birim</th><th>Kabul</th><th>Durum</th>"
        "<th>Laboratuvar</th><th>AI raporu</th></tr>" + "".join(rows) + "</table></div>"
        "<div class='card'><h2>Medicore'dan Gelen AI Raporları</h2><table><tr><th>Muayene</th><th>Durum</th>"
        "<th>Alındı</th></tr>" + received + "</table></div>"
    ))


@app.get("/ui/encounter/{encounter_id}", response_class=HTMLResponse)
def ui_encounter(encounter_id: str, _: UiLogin) -> HTMLResponse:
    encounter = _encounter_or_404(encounter_id)
    patient = PATIENTS_BY_ID[encounter.patient_id]
    esc = html.escape
    labs = "".join(
        f"<tr><td>{esc(lab.name)}</td><td class='{lab.flag or ''}'>{esc(lab.value)}</td>"
        f"<td>{esc(lab.unit or '')}</td><td>{esc(lab.reference or '')}</td><td>{esc(lab.flag or '')}</td></tr>"
        for lab in encounter.labs
    ) or "<tr><td colspan='5' class='muted'>Laboratuvar istemi yok.</td></tr>"
    vitals = ", ".join(
        f"{_VITAL_FIELDS[key][0] if key in _VITAL_FIELDS else esc(key)}: {value:g}"
        for key, value in encounter.vitals.items()
    ) or "-"
    radiology = "".join(
        f"<p><b>{esc(_MODALITIES.get(study.modality, study.modality))} · {esc(study.body_region)}</b><br>"
        f"{esc(study.findings)}<br><i>Sonuç:</i> {esc(study.impression)}</p>" for study in encounter.radiology
    ) or "<p class='muted'>Radyoloji istemi yok.</p>"
    reports = "".join(
        f"<div class='card'><h2>Medicore AI raporu · {esc(item['meta']['lastUpdated'][:16].replace('T', ' '))}"
        f" <span class='tag'>hekim onayı bekliyor</span></h2><pre>{esc(item['conclusion'])}</pre></div>"
        for item in reversed(RECEIVED_REPORTS) if item["encounter"]["reference"] == f"Encounter/{encounter.id}"
    ) or "<div class='card muted'>Bu muayene için henüz Medicore AI raporu gelmedi.</div>"
    target = "finished" if encounter.status == "in-progress" else "in-progress"
    toggle = "Muayeneyi tamamla (kapat)" if target == "finished" else "Muayeneyi yeniden aç"
    return _page(encounter.protocol_no, (
        "<p><a href='/'>← Muayene listesi</a></p>"
        f"<div class='card'><div class='row'><h2>{esc(encounter.protocol_no)} · {_status_tag(encounter.status)}</h2>"
        f"<form method='post' action='/ui/encounter/{encounter.id}/status'>"
        f"<input type='hidden' name='status' value='{target}'><button class='btn ghost'>{toggle}</button></form></div></div>"
        f"<div class='card'><h2>Hasta Kimlik (HBYS'de kalır, Medicore'a gönderilmez)</h2>"
        f"<p>{esc(patient.given_name)} {esc(patient.family_name)} · T.C. {esc(patient.tckn)} · "
        f"{patient.birth_date:%d.%m.%Y} · {esc(patient.phone or '-')}<br><span class='muted'>{esc(patient.address or '-')}</span></p></div>"
        f"<div class='card'><h2>Poliklinik · {esc(encounter.department)}</h2>"
        f"<p><b>Hekim:</b> {esc(encounter.doctor)}<br><b>Şikâyet:</b> {esc(', '.join(encounter.complaints) or '-')}<br>"
        f"<b>Özgeçmiş:</b> {esc(', '.join(encounter.history) or '-')}<br>"
        f"<b>İlaçlar:</b> {esc(', '.join(encounter.medications) or '-')}<br>"
        f"<b>Tanı (ICD-10):</b> {esc('; '.join(f'{c} {t}'.strip() for c, t in encounter.diagnoses) or '-')}<br>"
        f"<b>Vital bulgular:</b> {vitals}</p></div>"
        f"<div class='card'><h2>Laboratuvar · numune {encounter.specimen_at:%d.%m.%Y %H:%M}</h2>"
        f"<table><tr><th>Tetkik</th><th>Sonuç</th><th>Birim</th><th>Referans</th><th>Bayrak</th></tr>{labs}</table></div>"
        f"<div class='card'><h2>Radyoloji</h2>{radiology}</div>{reports}"
    ))


@app.post("/ui/encounter/{encounter_id}/status")
async def ui_set_status(encounter_id: str, request: Request, _: UiLogin) -> RedirectResponse:
    _same_origin(request)
    encounter = _encounter_or_404(encounter_id)
    value = parse_qs((await request.body()).decode("utf-8")).get("status", [""])[0]
    if value not in _STATUS_LABELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Geçersiz durum.")
    records.set_status(encounter, value)
    return RedirectResponse(f"/ui/encounter/{encounter.id}", status_code=status.HTTP_303_SEE_OTHER)


def _form_page(values: dict[str, str], error: str | None = None) -> HTMLResponse:
    esc = html.escape

    def field(name: str, label: str, kind: str = "text", extra: str = "") -> str:
        return (f"<label>{label}<input type='{kind}' name='{name}' value='{esc(values.get(name, ''))}' {extra}></label>")

    def options(name: str, choices: dict[str, str]) -> str:
        return "".join(
            f"<option value='{esc(key)}'{' selected' if values.get(name, '') == key else ''}>{esc(label)}</option>"
            for key, label in choices.items()
        )

    vitals = "".join(field(key, label, "text", "inputmode='decimal'") for key, (label, _, _) in _VITAL_FIELDS.items())
    departments = options("department", {item: item for item in _DEPARTMENTS})
    return _page("Yeni hasta / muayene", (
        "<p><a href='/'>← Muayene listesi</a></p>"
        + (f"<div class='err'>{esc(error)}</div>" if error else "")
        + "<form method='post' action='/ui/new' class='card'><h2>Yeni hasta kabulü ve muayene</h2>"
        "<fieldset><legend>Hasta (HBYS'de kalır)</legend><div class='grid'>"
        + field("given_name", "Ad *", extra="required maxlength='60'")
        + field("family_name", "Soyad *", extra="required maxlength='60'")
        + f"<label>Cinsiyet *<select name='sex'>{options('sex', {'female': 'Kadın', 'male': 'Erkek'})}</select></label>"
        + field("birth_date", "Doğum tarihi *", "date", "required")
        + field("phone", "Telefon", extra="maxlength='20'")
        + field("address", "Adres", extra="maxlength='200'")
        + "</div><p class='muted'>T.C. kimlik no sistem tarafından sentetik olarak üretilir.</p></fieldset>"
        "<fieldset><legend>Muayene</legend><div class='grid'>"
        f"<label>Birim<select name='department'>{departments}</select></label>"
        + field("doctor", "Hekim", extra="maxlength='80' placeholder='Dr. Sentetik Hekim'")
        + field("diagnosis_code", "Ön tanı ICD-10 kodu", extra="maxlength='8' placeholder='N18.4'")
        + field("diagnosis_text", "Ön tanı", extra="maxlength='120'")
        + "</div>"
        f"<label>Şikâyetler (virgülle ayırın)<textarea name='complaints' maxlength='800'>{esc(values.get('complaints', ''))}</textarea></label>"
        f"<label>Özgeçmiş / hastalıklar<textarea name='history' maxlength='800'>{esc(values.get('history', ''))}</textarea></label>"
        f"<label>Kullandığı ilaçlar<textarea name='medications' maxlength='800'>{esc(values.get('medications', ''))}</textarea></label>"
        "</fieldset>"
        f"<fieldset><legend>Vital bulgular (boş bırakılabilir)</legend><div class='grid'>{vitals}</div></fieldset>"
        "<fieldset><legend>Laboratuvar sonuçları</legend>"
        "<p class='muted'>Her satıra bir tetkik: <code>Tetkik | Sonuç | Birim | Referans</code> — örn. "
        "<code>Kreatinin | 1,8 | mg/dL | 0,67 - 1,17</code>. Referansı yazmazsanız Medicore sonucu "
        "normal/anormal olarak sınıflandıramaz (referans uydurulmaz).</p>"
        f"<textarea name='labs' rows='8' maxlength='6000'>{esc(values.get('labs', ''))}</textarea></fieldset>"
        "<fieldset><legend>Radyoloji (isteğe bağlı)</legend><div class='grid'>"
        f"<label>Tetkik türü<select name='modality'>{options('modality', _MODALITIES)}</select></label>"
        + field("body_region", "Bölge", extra="maxlength='60' placeholder='Akciğer'")
        + "</div>"
        f"<label>Bulgular<textarea name='findings' maxlength='3000'>{esc(values.get('findings', ''))}</textarea></label>"
        f"<label>Sonuç<textarea name='impression' maxlength='1000'>{esc(values.get('impression', ''))}</textarea></label>"
        "</fieldset><button class='btn'>Hastayı kaydet ve muayeneyi aç</button></form>"
    ))


@app.get("/ui/new", response_class=HTMLResponse)
def ui_new(_: UiLogin) -> HTMLResponse:
    return _form_page({"department": "Dahiliye Polikliniği", "sex": "female", "modality": ""})


def _split(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,\n;]", value) if item.strip()][:30]


def _parse_form(values: dict[str, str]) -> dict[str, Any]:
    given, family = values.get("given_name", "").strip(), values.get("family_name", "").strip()
    if not given or not family:
        raise ValueError("Ad ve soyad zorunludur.")
    if len(given) > 60 or len(family) > 60 or any(char.isdigit() for char in given + family):
        raise ValueError("Ad ve soyad en fazla 60 karakter olmalı ve rakam içermemeli.")
    sex = values.get("sex", "")
    if sex not in {"female", "male"}:
        raise ValueError("Cinsiyet seçin.")
    try:
        born = date.fromisoformat(values.get("birth_date", ""))
    except ValueError:
        raise ValueError("Geçerli bir doğum tarihi girin.") from None
    today = date.today()
    if born > today or today.year - born.year > 120:
        raise ValueError("Doğum tarihi gelecekte olamaz ve yaş 120'yi aşamaz.")
    department = values.get("department", "")
    if department not in _DEPARTMENTS:
        raise ValueError("Geçerli bir birim seçin.")
    code = values.get("diagnosis_code", "").strip().upper()
    if code and not _ICD10.fullmatch(code):
        raise ValueError("ICD-10 kodu örn. N18.4 biçiminde olmalı.")
    diagnosis_text = values.get("diagnosis_text", "").strip()[:120]
    vitals: dict[str, float] = {}
    for key, (label, low, high) in _VITAL_FIELDS.items():
        raw = values.get(key, "").strip().replace(",", ".")
        if not raw:
            continue
        try:
            number = float(raw)
        except ValueError:
            raise ValueError(f"{label} sayı olmalı.") from None
        if not low <= number <= high:
            raise ValueError(f"{label} {low:g}–{high:g} aralığında olmalı.")
        vitals[key] = number
    labs: list[SimLab] = []
    for number, line in enumerate(values.get("labs", "").splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Laboratuvar {number}. satır 'Tetkik | Sonuç | Birim | Referans' biçiminde olmalı.")
        parts += [""] * (4 - len(parts))
        labs.append(SimLab("", parts[0][:120], parts[1][:40], parts[2][:30] or None, parts[3][:80] or None))
    if len(labs) > 60:
        raise ValueError("En fazla 60 laboratuvar satırı girilebilir.")
    radiology: list[SimRadiology] = []
    modality = values.get("modality", "")
    if modality not in _MODALITIES:
        raise ValueError("Geçerli bir radyoloji türü seçin.")
    if modality:
        findings, impression = values.get("findings", "").strip(), values.get("impression", "").strip()
        if not findings and not impression:
            raise ValueError("Radyoloji için bulgu veya sonuç yazın.")
        radiology.append(SimRadiology(modality, values.get("body_region", "").strip()[:60] or "Belirtilmemiş",
                                      findings[:3000], impression[:1000]))
    return {
        "given_name": given, "family_name": family, "sex": sex, "birth_date": born,
        "phone": values.get("phone", "").strip()[:20], "address": values.get("address", "").strip()[:200],
        "department": department, "doctor": values.get("doctor", "").strip()[:80] or "Dr. Sentetik Hekim",
        "complaints": _split(values.get("complaints", "")), "history": _split(values.get("history", "")),
        "medications": _split(values.get("medications", "")),
        "diagnoses": [(code, diagnosis_text)] if code or diagnosis_text else [],
        "vitals": vitals, "labs": labs, "radiology": radiology,
    }


@app.post("/ui/new", response_class=HTMLResponse)
async def ui_create(request: Request, _: UiLogin):
    _same_origin(request)
    body = await request.body()
    if len(body) > 30_000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Form çok büyük.")
    values = {key: items[0] for key, items in parse_qs(body.decode("utf-8"), keep_blank_values=True).items()}
    try:
        parsed = _parse_form(values)
    except ValueError as exc:
        return _form_page(values, str(exc))
    encounter = records.add_patient_with_encounter(**parsed)
    return RedirectResponse(f"/ui/encounter/{encounter.id}", status_code=status.HTTP_303_SEE_OTHER)
