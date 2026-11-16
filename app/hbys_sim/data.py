"""Synthetic hospital data for the virtual HBYS (Hastane Bilgi Yönetim Sistemi).

Every person here is fictional. National ID numbers deliberately FAIL the
T.C. kimlik checksum so they can never belong to a real citizen, phone numbers
use a reserved-looking 0555 000 xx xx block, and addresses are invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class SimPatient:
    id: str
    tckn: str
    given_name: str
    family_name: str
    sex: str  # FHIR administrative gender: male | female | other | unknown
    birth_date: date
    phone: str
    address: str


@dataclass
class SimLab:
    loinc: str
    name: str
    value: str
    unit: str | None
    reference: str | None
    flag: str | None = None  # HBYS abnormal flag as sent by the lab device (L/H/N)


@dataclass
class SimRadiology:
    modality: str
    body_region: str
    findings: str
    impression: str


@dataclass
class SimEncounter:
    id: str
    protocol_no: str
    patient_id: str
    department: str
    doctor: str
    admitted_at: datetime
    status: str  # in-progress | finished
    complaints: list[str]
    history: list[str]
    medications: list[str]
    diagnoses: list[tuple[str, str]]  # (ICD-10 code, text)
    vitals: dict[str, float]
    labs: list[SimLab]
    specimen_at: datetime
    radiology: list[SimRadiology] = field(default_factory=list)


def _invalid_tckn(prefix: str) -> str:
    """Return an 11-digit number that deliberately fails the TCKN checksum."""
    digits = [int(c) for c in prefix[:9].ljust(9, "1")]
    tenth = ((sum(digits[0:9:2]) * 7) - sum(digits[1:8:2])) % 10
    eleventh = (sum(digits) + tenth) % 10
    return "".join(map(str, digits)) + str(tenth) + str((eleventh + 1) % 10)


PATIENTS: list[SimPatient] = [
    SimPatient("p-1001", _invalid_tckn("100000001"), "Deniz", "Örnekoğlu", "female",
               date(1958, 4, 12), "0555 000 10 01", "Sentetik Mah. Deneme Sok. No:1 Çankaya/Ankara"),
    SimPatient("p-1002", _invalid_tckn("100000002"), "Kerem", "Testoğlu", "male",
               date(1979, 9, 3), "0555 000 10 02", "Örnek Mah. Simülasyon Cad. No:7 Yenimahalle/Ankara"),
    SimPatient("p-1003", _invalid_tckn("100000003"), "Elif", "Sanalkaya", "female",
               date(1991, 1, 27), "0555 000 10 03", "Hayal Mah. Prova Sok. No:3 Keçiören/Ankara"),
    SimPatient("p-1004", _invalid_tckn("100000004"), "Murat", "Demoğlu", "male",
               date(1965, 11, 30), "0555 000 10 04", "Model Mah. Taslak Sok. No:12 Etimesgut/Ankara"),
    SimPatient("p-1005", _invalid_tckn("100000005"), "Zeynep", "Kurmacaer", "female",
               date(1948, 6, 18), "0555 000 10 05", "Kurgu Mah. Örnek Cad. No:9 Mamak/Ankara"),
    SimPatient("p-1006", _invalid_tckn("100000006"), "Ali", "Denemeci", "male",
               date(2001, 3, 8), "0555 000 10 06", "Sentez Mah. Pilot Sok. No:4 Gölbaşı/Ankara"),
]


def _lab(loinc, name, value, unit, reference, flag=None) -> SimLab:
    return SimLab(loinc, name, value, unit, reference, flag)


ENCOUNTERS: list[SimEncounter] = [
    SimEncounter(
        id="e-2001", protocol_no="HBYS-2026-100201", patient_id="p-1001",
        department="Dahiliye Polikliniği", doctor="Uzm. Dr. Sentetik Hekim",
        admitted_at=datetime(2026, 11, 14, 9, 20), status="in-progress",
        complaints=["halsizlik", "sık idrara çıkma", "ağız kuruluğu"],
        history=["tip 2 diyabet", "hipertansiyon"], medications=["metformin 1000 mg", "ramipril 5 mg"],
        diagnoses=[("E11.9", "Tip 2 diabetes mellitus, komplikasyonsuz")],
        vitals={"systolic_bp": 148, "diastolic_bp": 92, "heart_rate": 84, "temperature": 36.7,
                "spo2": 97, "weight_kg": 82, "height_cm": 162},
        specimen_at=datetime(2026, 11, 14, 9, 45),
        labs=[
            _lab("1558-6", "Açlık Kan Şekeri", "186", "mg/dL", "70 - 100", "H"),
            _lab("4548-4", "HbA1c", "8,4", "%", "4 - 6", "H"),
            _lab("2160-0", "Kreatinin", "1,32", "mg/dL", "0,51 - 0,95", "H"),
            _lab("98979-8", "eGFR", "41", "mL/dk/1.73m²", "> 60", "L"),
            _lab("2823-3", "Potasyum", "5,1", "mmol/L", "3,5 - 5,1", "N"),
            _lab("2951-2", "Sodyum", "138", "mmol/L", "136 - 145", "N"),
            _lab("2093-3", "Total Kolesterol", "236", "mg/dL", "< 200", "H"),
            _lab("13457-7", "LDL Kolesterol", "158", "mg/dL", "< 130", "H"),
            _lab("14959-1", "İdrar Mikroalbumin/Kreatinin", "142", "mg/g", "< 30", "H"),
        ],
    ),
    SimEncounter(
        id="e-2002", protocol_no="HBYS-2026-100202", patient_id="p-1002",
        department="Acil Servis", doctor="Dr. Sentetik Acil",
        admitted_at=datetime(2026, 11, 14, 23, 5), status="in-progress",
        complaints=["göğüs ağrısı", "terleme", "sol kola yayılan ağrı"],
        history=["sigara kullanımı"], medications=[],
        diagnoses=[("R07.4", "Göğüs ağrısı, tanımlanmamış")],
        vitals={"systolic_bp": 162, "diastolic_bp": 98, "heart_rate": 108, "respiratory_rate": 22,
                "temperature": 36.9, "spo2": 94},
        specimen_at=datetime(2026, 11, 14, 23, 20),
        labs=[
            _lab("89579-7", "Troponin I (yüksek duyarlıklı)", "312", "ng/L", "< 34", "H"),
            _lab("2157-6", "CK-MB", "38", "U/L", "0 - 24", "H"),
            _lab("6690-2", "Lökosit", "12.400", "/µL", "4.500 - 11.000", "H"),
            _lab("718-7", "Hemoglobin", "14,6", "g/dL", "13,5 - 17,5", "N"),
            _lab("777-3", "Trombosit", "248.000", "/µL", "150.000 - 400.000", "N"),
            _lab("2160-0", "Kreatinin", "0,98", "mg/dL", "0,67 - 1,17", "N"),
            _lab("2823-3", "Potasyum", "4,2", "mmol/L", "3,5 - 5,1", "N"),
        ],
        radiology=[SimRadiology(
            "DX", "Akciğer", "Kardiyotorasik oran normal sınırlarda. Akciğer parankiminde aktif infiltrasyon izlenmedi.",
            "Akut kardiyopulmoner patoloji saptanmadı.",
        )],
    ),
    SimEncounter(
        id="e-2003", protocol_no="HBYS-2026-100203", patient_id="p-1003",
        department="Kadın Hastalıkları ve Doğum Polikliniği", doctor="Op. Dr. Sentetik Jinekolog",
        admitted_at=datetime(2026, 11, 13, 14, 10), status="finished",
        complaints=["yorgunluk", "baş dönmesi", "saç dökülmesi"],
        history=[], medications=[],
        diagnoses=[("D50.9", "Demir eksikliği anemisi, tanımlanmamış")],
        vitals={"systolic_bp": 104, "diastolic_bp": 66, "heart_rate": 96, "temperature": 36.5, "spo2": 99},
        specimen_at=datetime(2026, 11, 13, 14, 40),
        labs=[
            _lab("718-7", "Hemoglobin", "9,6", "g/dL", "12 - 15,5", "L"),
            _lab("787-2", "MCV", "71", "fL", "80 - 100", "L"),
            _lab("2498-4", "Serum Demir", "28", "µg/dL", "50 - 170", "L"),
            _lab("2502-3", "Transferrin Satürasyonu", "6", "%", "20 - 50", "L"),
            _lab("2276-4", "Ferritin", "4", "ng/mL", "13 - 150", "L"),
            _lab("2132-9", "Vitamin B12", "312", "pg/mL", "197 - 771", "N"),
            _lab("3016-3", "TSH", "2,1", "mIU/L", "0,27 - 4,2", "N"),
        ],
    ),
    SimEncounter(
        id="e-2004", protocol_no="HBYS-2026-100204", patient_id="p-1004",
        department="Nefroloji Polikliniği", doctor="Doç. Dr. Sentetik Nefrolog",
        admitted_at=datetime(2026, 11, 14, 11, 0), status="in-progress",
        complaints=["bacaklarda şişlik", "idrar miktarında azalma"],
        history=["kronik böbrek hastalığı", "hipertansiyon"], medications=["amlodipin 10 mg", "furosemid 40 mg"],
        diagnoses=[("N18.4", "Kronik böbrek hastalığı, evre 4")],
        vitals={"systolic_bp": 158, "diastolic_bp": 94, "heart_rate": 78, "temperature": 36.6,
                "spo2": 96, "weight_kg": 91},
        specimen_at=datetime(2026, 11, 14, 11, 25),
        labs=[
            _lab("3094-0", "Üre (BUN)", "68", "mg/dL", "6 - 20", "H"),
            _lab("2160-0", "Kreatinin", "3,9", "mg/dL", "0,67 - 1,17", "H"),
            _lab("98979-8", "eGFR", "17", "mL/dk/1.73m²", "> 60", "L"),
            _lab("2823-3", "Potasyum", "6,1", "mmol/L", "3,5 - 5,1", "H"),
            _lab("17861-6", "Kalsiyum", "8,1", "mg/dL", "8,6 - 10,2", "L"),
            _lab("2777-1", "Fosfor", "6,2", "mg/dL", "2,5 - 4,5", "H"),
            _lab("1751-7", "Albümin", "3,1", "g/dL", "3,5 - 5,2", "L"),
            _lab("718-7", "Hemoglobin", "9,9", "g/dL", "13,5 - 17,5", "L"),
            _lab("2731-8", "Parathormon", "286", "pg/mL", "15 - 65", "H"),
        ],
        radiology=[SimRadiology(
            "US", "Üriner sistem",
            "Her iki böbrek boyutu küçük, parankim ekojenitesi artmış, kortikomedüller ayrım silik. Hidronefroz izlenmedi.",
            "Bilateral kronik parankimal böbrek hastalığı ile uyumlu görünüm.",
        )],
    ),
    SimEncounter(
        id="e-2005", protocol_no="HBYS-2026-100205", patient_id="p-1005",
        department="Endokrinoloji Polikliniği", doctor="Prof. Dr. Sentetik Endokrinolog",
        admitted_at=datetime(2026, 11, 12, 10, 30), status="finished",
        complaints=["kilo alımı", "üşüme", "kabızlık"],
        history=["osteoporoz"], medications=["kalsiyum + D vitamini"],
        diagnoses=[("E03.9", "Hipotiroidi, tanımlanmamış")],
        vitals={"systolic_bp": 132, "diastolic_bp": 78, "heart_rate": 58, "temperature": 36.1, "spo2": 97},
        specimen_at=datetime(2026, 11, 12, 10, 50),
        labs=[
            _lab("3016-3", "TSH", "14,8", "mIU/L", "0,27 - 4,2", "H"),
            _lab("3024-7", "Serbest T4", "0,62", "ng/dL", "0,93 - 1,7", "L"),
            _lab("2093-3", "Total Kolesterol", "254", "mg/dL", "< 200", "H"),
            _lab("1989-3", "25-OH Vitamin D", "14", "ng/mL", "30 - 100", "L"),
            _lab("2951-2", "Sodyum", "134", "mmol/L", "136 - 145", "L"),
        ],
    ),
    SimEncounter(
        id="e-2006", protocol_no="HBYS-2026-100206", patient_id="p-1006",
        department="Göğüs Hastalıkları Polikliniği", doctor="Uzm. Dr. Sentetik Göğüsçü",
        admitted_at=datetime(2026, 11, 15, 8, 40), status="in-progress",
        complaints=["öksürük", "ateş", "balgam"],
        history=[], medications=[],
        diagnoses=[("J18.9", "Pnömoni, tanımlanmamış")],
        vitals={"systolic_bp": 118, "diastolic_bp": 72, "heart_rate": 104, "respiratory_rate": 24,
                "temperature": 38.6, "spo2": 92},
        specimen_at=datetime(2026, 11, 15, 9, 0),
        labs=[
            _lab("6690-2", "Lökosit", "16.800", "/µL", "4.500 - 11.000", "H"),
            _lab("751-8", "Nötrofil", "13.900", "/µL", "1.800 - 7.700", "H"),
            _lab("1988-5", "CRP", "148", "mg/L", "< 5", "H"),
            _lab("33959-8", "Prokalsitonin", "1,9", "ng/mL", "< 0,5", "H"),
            _lab("718-7", "Hemoglobin", "14,2", "g/dL", "13,5 - 17,5", "N"),
        ],
        radiology=[SimRadiology(
            "DX", "Akciğer",
            "Sağ akciğer alt zonda havabronkogramları içeren konsolidasyon alanı izlendi. Plevral efüzyon saptanmadı.",
            "Sağ alt lob pnömoni ile uyumlu konsolidasyon.",
        )],
    ),
]


PATIENTS_BY_ID = {patient.id: patient for patient in PATIENTS}
ENCOUNTERS_BY_ID = {encounter.id: encounter for encounter in ENCOUNTERS}
