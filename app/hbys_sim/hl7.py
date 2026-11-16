"""HL7 v2.5 ORU^R01 lab result message for the virtual HBYS."""

from __future__ import annotations

from datetime import datetime

from .data import PATIENTS_BY_ID, SimEncounter


def _escape(value: str) -> str:
    # HL7 v2 escape sequences for the default delimiters |^~\&
    return (value.replace("\\", "\\E\\").replace("|", "\\F\\").replace("^", "\\S\\")
            .replace("~", "\\R\\").replace("&", "\\T\\"))


def _ts(value: datetime) -> str:
    return value.strftime("%Y%m%d%H%M%S")


def oru_r01(encounter: SimEncounter, *, now: datetime | None = None) -> str:
    patient = PATIENTS_BY_ID[encounter.patient_id]
    sent = now or datetime(2026, 11, 15, 12, 0)
    sex = {"female": "F", "male": "M"}.get(patient.sex, "U")
    segments = [
        f"MSH|^~\\&|SANAL_HBYS|SANAL_HASTANE|MEDICORE|MEDICORE|{_ts(sent)}||ORU^R01^ORU_R01|"
        f"{encounter.id}|P|2.5|||AL|NE||UNICODE UTF-8",
        f"PID|1||{patient.tckn}^^^SANAL_HBYS^NI||{_escape(patient.family_name)}^{_escape(patient.given_name)}"
        f"||{patient.birth_date.strftime('%Y%m%d')}|{sex}|||{_escape(patient.address)}||{patient.phone}",
        f"PV1|1|{'E' if 'Acil' in encounter.department else 'O'}|{_escape(encounter.department)}"
        f"||||||||||||||||{encounter.protocol_no}",
        f"OBR|1|{encounter.protocol_no}||LAB^Laboratuvar paneli|||{_ts(encounter.specimen_at)}",
    ]
    for index, lab in enumerate(encounter.labs, start=1):
        segments.append(
            f"OBX|{index}|ST|{lab.loinc}^{_escape(lab.name)}^LN||{_escape(lab.value)}|"
            f"{_escape(lab.unit or '')}|{_escape(lab.reference or '')}|{lab.flag or ''}|||F|||"
            f"{_ts(encounter.specimen_at)}"
        )
    return "\r".join(segments) + "\r"
