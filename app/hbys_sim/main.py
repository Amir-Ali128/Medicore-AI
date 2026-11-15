"""Sanal HBYS: a small hospital information system simulator for Medicore.

It mimics the parts of a Turkish HBYS that Medicore integrates with: hasta kabul
(patients + visit protocol numbers), poliklinik/acil visits (complaints, vitals,
ICD-10 diagnoses, medications), laboratory results and radiology reports. Data is
exposed through standard interfaces (FHIR R4 JSON and HL7 v2.5 ORU^R01) and
Medicore can post its physician-review AI report back as a FHIR DiagnosticReport.

Run from the ``app`` directory:  uvicorn hbys_sim.main:app --port 8100
All records are synthetic; see data.py.
"""

from __future__ import annotations

import hmac
import html
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse, PlainTextResponse

from .data import ENCOUNTERS, ENCOUNTERS_BY_ID, PATIENTS_BY_ID
from .fhir import capability_statement, encounter_bundle, encounter_search_bundle
from .hl7 import oru_r01

_MAX_REPORT_CHARS = 20_000
_DEV_KEY = "dev-hbys-key"

app = FastAPI(title="Sanal HBYS", version="1.0", docs_url="/docs", redoc_url=None)

# Reports received from Medicore, newest last. In-memory: the simulator is stateless.
RECEIVED_REPORTS: list[dict[str, Any]] = []


def _api_key() -> str:
    key = os.environ.get("HBYS_SIM_API_KEY", "").strip()
    if key:
        return key
    if os.environ.get("HBYS_SIM_ENV", "development") != "development":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "HBYS_SIM_API_KEY tanımlı değil.")
    return _DEV_KEY


def require_api_key(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = _api_key()
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Geçersiz HBYS API anahtarı.",
                            headers={"WWW-Authenticate": "Bearer"})


Authorized = Annotated[None, Depends(require_api_key)]


def _encounter_or_404(encounter_id: str):
    encounter = ENCOUNTERS_BY_ID.get(encounter_id)
    if encounter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Muayene kaydı bulunamadı.")
    return encounter


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
        "meta": {"lastUpdated": datetime.now(UTC).isoformat()},
    }
    RECEIVED_REPORTS.append(stored)
    return {"id": stored["id"], "encounter": f"Encounter/{encounter.id}", "status": "accepted"}


# ---------------------------------------------------------------- simple HBYS UI
_STYLE = """
:root{--bg:#f4f6f8;--card:#fff;--ink:#14202b;--muted:#5b6b7a;--line:#dde3e9;--brand:#0f5c8c;--hi:#b42318;--lo:#175cd3}
@media (prefers-color-scheme:dark){:root{--bg:#0f1720;--card:#16212c;--ink:#e6edf3;--muted:#9aa9b6;--line:#26333f;--brand:#5fb0e6;--hi:#ff8a80;--lo:#8ab4ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
header{background:var(--brand);color:#fff;padding:14px 16px}header h1{margin:0;font-size:18px}header p{margin:2px 0 0;opacity:.85;font-size:13px}
main{max-width:1100px;margin:0 auto;padding:16px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:14px;overflow-x:auto}
h2{font-size:16px;margin:0 0 10px}table{border-collapse:collapse;width:100%;min-width:560px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:13px}.tag{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;border:1px solid var(--line)}
.H{color:var(--hi);font-weight:600}.L{color:var(--lo);font-weight:600}a{color:var(--brand)}.muted{color:var(--muted)}pre{white-space:pre-wrap;margin:0}
.warn{border-left:4px solid #f79009;padding:8px 12px;background:var(--card);margin-bottom:14px;border-radius:6px}
"""


_VITAL_LABELS = {
    "systolic_bp": "Sistolik KB (mmHg)", "diastolic_bp": "Diyastolik KB (mmHg)", "heart_rate": "Nabız (/dk)",
    "respiratory_rate": "Solunum (/dk)", "temperature": "Ateş (°C)", "spo2": "SpO₂ (%)",
    "height_cm": "Boy (cm)", "weight_kg": "Kilo (kg)",
}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='tr'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
        f"<style>{_STYLE}</style></head><body><header><h1>Sanal HBYS</h1>"
        f"<p>Hastane Bilgi Yönetim Sistemi simülasyonu · tüm kayıtlar sentetiktir</p></header>"
        f"<main><div class='warn'>Bu ekran yalnızca test içindir. Hastalar, T.C. numaraları "
        f"(geçersiz checksum), telefonlar ve adresler hayalidir.</div>{body}</main></body></html>"
    )


@app.get("/", response_class=HTMLResponse)
def ui_home() -> HTMLResponse:
    rows = []
    for encounter in sorted(ENCOUNTERS, key=lambda item: item.admitted_at, reverse=True):
        patient = PATIENTS_BY_ID[encounter.patient_id]
        state = "Açık" if encounter.status == "in-progress" else "Kapandı"
        rows.append(
            f"<tr><td><a href='/ui/encounter/{encounter.id}'>{html.escape(encounter.protocol_no)}</a></td>"
            f"<td>{html.escape(patient.given_name)} {html.escape(patient.family_name)}</td>"
            f"<td>{html.escape(encounter.department)}</td><td>{encounter.admitted_at:%d.%m.%Y %H:%M}</td>"
            f"<td><span class='tag'>{state}</span></td><td>{len(encounter.labs)} tetkik</td></tr>"
        )
    reports = "".join(
        f"<tr><td>{html.escape(item['encounter']['reference'])}</td><td>{html.escape(item.get('status', ''))}</td>"
        f"<td>{html.escape(item['meta']['lastUpdated'][:19])}</td></tr>" for item in reversed(RECEIVED_REPORTS)
    ) or "<tr><td colspan='3' class='muted'>Henüz Medicore'dan rapor gelmedi.</td></tr>"
    return _page("Sanal HBYS", (
        "<div class='card'><h2>Hasta Kabul · Muayene Listesi</h2><table><tr><th>Protokol No</th><th>Hasta</th>"
        "<th>Birim</th><th>Kabul</th><th>Durum</th><th>Laboratuvar</th></tr>" + "".join(rows) + "</table></div>"
        "<div class='card'><h2>Medicore'dan Gelen AI Raporları</h2><table><tr><th>Muayene</th><th>Durum</th>"
        "<th>Alındı</th></tr>" + reports + "</table></div>"
    ))


@app.get("/ui/encounter/{encounter_id}", response_class=HTMLResponse)
def ui_encounter(encounter_id: str) -> HTMLResponse:
    encounter = _encounter_or_404(encounter_id)
    patient = PATIENTS_BY_ID[encounter.patient_id]
    esc = html.escape
    labs = "".join(
        f"<tr><td>{esc(lab.name)}</td><td class='{lab.flag or ''}'>{esc(lab.value)}</td>"
        f"<td>{esc(lab.unit or '')}</td><td>{esc(lab.reference or '')}</td><td>{esc(lab.flag or '')}</td></tr>"
        for lab in encounter.labs
    )
    vitals = ", ".join(
        f"{_VITAL_LABELS.get(key, esc(key))}: {value:g}" for key, value in encounter.vitals.items()
    )
    radiology = "".join(
        f"<p><b>{esc(study.modality)} · {esc(study.body_region)}</b><br>{esc(study.findings)}<br>"
        f"<i>Sonuç:</i> {esc(study.impression)}</p>" for study in encounter.radiology
    ) or "<p class='muted'>Radyoloji istemi yok.</p>"
    reports = "".join(
        f"<div class='card'><h2>Medicore AI raporu · {esc(item['meta']['lastUpdated'][:19])}</h2>"
        f"<pre>{esc(item['conclusion'])}</pre></div>"
        for item in RECEIVED_REPORTS if item["encounter"]["reference"] == f"Encounter/{encounter.id}"
    )
    return _page(encounter.protocol_no, (
        "<p><a href='/'>← Muayene listesi</a></p>"
        f"<div class='card'><h2>Hasta Kimlik (HBYS'de kalır, Medicore'a gönderilmez)</h2>"
        f"<p>{esc(patient.given_name)} {esc(patient.family_name)} · T.C. {esc(patient.tckn)} · "
        f"{patient.birth_date:%d.%m.%Y} · {esc(patient.phone)}<br><span class='muted'>{esc(patient.address)}</span></p></div>"
        f"<div class='card'><h2>Poliklinik · {esc(encounter.department)}</h2>"
        f"<p><b>Hekim:</b> {esc(encounter.doctor)}<br><b>Şikâyet:</b> {esc(', '.join(encounter.complaints))}<br>"
        f"<b>Özgeçmiş:</b> {esc(', '.join(encounter.history) or '-')}<br>"
        f"<b>İlaçlar:</b> {esc(', '.join(encounter.medications) or '-')}<br>"
        f"<b>Tanı (ICD-10):</b> {esc('; '.join(f'{c} {t}' for c, t in encounter.diagnoses))}<br>"
        f"<b>Vital bulgular:</b> {vitals}</p></div>"
        f"<div class='card'><h2>Laboratuvar · numune {encounter.specimen_at:%d.%m.%Y %H:%M}</h2>"
        f"<table><tr><th>Tetkik</th><th>Sonuç</th><th>Birim</th><th>Referans</th><th>Bayrak</th></tr>{labs}</table></div>"
        f"<div class='card'><h2>Radyoloji</h2>{radiology}</div>{reports}"
    ))
