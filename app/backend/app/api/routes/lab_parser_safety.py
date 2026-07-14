"""Safety normalization for common Turkish e-Nabız laboratory PDFs.

This layer runs after the existing parser. It fixes high-risk alias collisions,
normalizes g/L protein results to g/dL, and adds common calculated/hemogram
markers without replacing the core analysis pipeline.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.api.routes import lab_analysis

EXTRA_PARAMETERS: dict[str, dict[str, Any]] = {
    "Albumin / Globulin Oranı": {"aliases": ["ALBUMIN / GLOBULIN", "ALBÜMİN / GLOBÜLİN", "A/G RATIO", "AG RATIO"], "default_unit": ""},
    "Anyon Açığı": {"aliases": ["ANION GAP", "ANİYON GAP", "ANYON AÇIĞI"], "default_unit": "mEq/L"},
    "Bikarbonat": {"aliases": ["BIKARBONAT (HCO3)", "BİKARBONAT (HCO3)", "BICARBONATE", "HCO3"], "default_unit": "mEq/L"},
    "Globulin": {"aliases": ["GLOBULIN, SERUM", "GLOBÜLİN, SERUM", "GLOBULIN", "GLOBÜLİN"], "default_unit": "g/dL"},
    "FIB-4 Skoru": {"aliases": ["FIBROZIS-4 (FIB-4) SKORU", "FİBROZİS-4 (FIB-4) SKORU", "FIB-4", "FIB4"], "default_unit": ""},
    "Kalsiyum / Fosfor Oranı": {"aliases": ["KALSIYUM/FOSFOR", "KALSİYUM/FOSFOR", "CALCIUM/PHOSPHORUS"], "default_unit": ""},
    "NRBC %": {"aliases": ["NRBC (CEKIRDEKLI ERITROSIT ) %", "NRBC (ÇEKİRDEKLİ ERİTROSİT ) %", "NRBC %"], "default_unit": "/100WBC"},
    "NRBC Mutlak": {"aliases": ["NRBC (CEKIRDEKLI ERITROSIT)", "NRBC (ÇEKİRDEKLİ ERİTROSİT)", "NRBC ABSOLUTE"], "default_unit": "K/mm3"},
    "PDW": {"aliases": ["PDW", "PLATELET DISTRIBUTION WIDTH"], "default_unit": "fL"},
    "RDW-SD": {"aliases": ["RDW-SD", "RDW SD"], "default_unit": "fL"},
    "UIBC": {"aliases": ["UIBC", "UNSATURATED IRON BINDING CAPACITY", "DOYMAMIS DEMIR BAGLAMA KAPASITESI", "DOYMAMIŞ DEMİR BAĞLAMA KAPASİTESİ"], "default_unit": "ug/dL"},
    "CK": {"aliases": ["KREATIN KINAZ", "KREATİN KİNAZ", "CREATINE KINASE", "CK"], "default_unit": "U/L"},
    "BNP": {"aliases": ["BNP", "B-TYPE NATRIURETIC PEPTIDE"], "default_unit": "pg/mL"},
    "NT-proBNP": {"aliases": ["NT-PROBNP", "NT PROBNP", "N-TERMINAL PROBNP"], "default_unit": "pg/mL"},
    "Çinko": {"aliases": ["CINKO", "ÇİNKO", "ZINC", "ZN"], "default_unit": "ug/dL"},
    "Bakır": {"aliases": ["BAKIR", "COPPER", "CU"], "default_unit": "ug/dL"},
}

for _name, _config in EXTRA_PARAMETERS.items():
    lab_analysis.LAB_PARAMETER_ALIASES.setdefault(_name, _config)

_original_parse = lab_analysis._parse_lab_values_from_text


def _fold(value: str) -> str:
    table = str.maketrans({"İ": "I", "ı": "I", "Ş": "S", "ş": "S", "Ğ": "G", "ğ": "G", "Ü": "U", "ü": "U", "Ö": "O", "ö": "O", "Ç": "C", "ç": "C"})
    return re.sub(r"\s+", " ", value.translate(table).upper().replace(",", ".")).strip()


def _exact_row(text: str, labels: list[str]) -> tuple[float, str, float | None, float | None] | None:
    folded_labels = [_fold(label) for label in labels]
    for raw_line in text.splitlines():
        line = _fold(raw_line)
        matched = next((label for label in folded_labels if line.startswith(label + " ") or line == label), None)
        if matched is None:
            continue
        tail = line[len(matched):].strip()
        value_match = re.search(r"[<>]?\s*(-?\d+(?:\.\d+)?)", tail)
        if value_match is None:
            continue
        value = float(value_match.group(1))
        after_value = tail[value_match.end():].strip()
        range_match = re.search(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$", after_value)
        ref_min = float(range_match.group(1)) if range_match else None
        ref_max = float(range_match.group(2)) if range_match else None
        unit_part = after_value[: range_match.start()].strip() if range_match else after_value
        unit = unit_part.split()[0] if unit_part and unit_part != "-" else ""
        return value, unit, ref_min, ref_max
    return None


def _item(name: str, value: float, unit: str, low: float | None, high: float | None) -> dict[str, Any]:
    return {"raw_parameter_name": name, "raw_value": str(value), "normalized_value": value, "unit": unit, "extracted_reference_min": low, "extracted_reference_max": high, "extracted_unit": unit, "measured_at": date.today().isoformat()}


def _replace(values: list[dict[str, Any]], item: dict[str, Any]) -> None:
    name = item["raw_parameter_name"]
    values[:] = [current for current in values if current.get("raw_parameter_name") != name]
    values.append(item)


def _normalize_exact_problem_rows(text: str, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    albumin = _exact_row(text, ["ALBUMIN, SERUM", "ALBÜMİN, SERUM"])
    if albumin:
        value, unit, low, high = albumin
        if unit.upper() == "G/L" or value > 20:
            value /= 10
            low = low / 10 if low is not None else None
            high = high / 10 if high is not None else None
            unit = "g/dL"
        _replace(values, _item("Albumin", round(value, 3), unit or "g/dL", low, high))

    ag_ratio = _exact_row(text, ["ALBUMIN / GLOBULIN", "ALBÜMİN / GLOBÜLİN"])
    if ag_ratio:
        value, _, low, high = ag_ratio
        _replace(values, _item("Albumin / Globulin Oranı", value, "", low, high))

    total_protein = _exact_row(text, ["TOTAL PROTEIN, SERUM", "TOTAL PROTEİN, SERUM", "TOPLAM PROTEIN, SERUM"])
    if total_protein:
        value, unit, low, high = total_protein
        if unit.upper() == "G/L" or value > 20:
            value /= 10
            low = low / 10 if low is not None else None
            high = high / 10 if high is not None else None
            unit = "g/dL"
        _replace(values, _item("Total Protein", round(value, 3), unit or "g/dL", low, high))

    globulin = _exact_row(text, ["GLOBULIN, SERUM", "GLOBÜLİN, SERUM"])
    if globulin:
        value, unit, low, high = globulin
        if unit.upper() == "G/L" or value > 15:
            value /= 10
            low = low / 10 if low is not None else None
            high = high / 10 if high is not None else None
            unit = "g/dL"
        _replace(values, _item("Globulin", round(value, 3), unit or "g/dL", low, high))

    exact_specs = {
        "Potasyum": (["POTASYUM, SERUM", "POTASYUM"], "mmol/L"),
        "Magnezyum": (["MAGNEZYUM, (SERUM),AAS", "MAGNEZYUM, SERUM", "MAGNEZYUM"], "mg/dL"),
        "Sodyum": (["SODYUM, SERUM", "SODYUM"], "mmol/L"),
        "Klor": (["KLORUR, SERUM", "KLORÜR, SERUM", "KLOR"], "mmol/L"),
        "Kalsiyum": (["KALSIYUM, SERUM", "KALSİYUM, SERUM", "KALSIYUM"], "mg/dL"),
        "Fosfor": (["FOSFOR, SERUM", "FOSFOR"], "mg/dL"),
        "Ürik Asit": (["URIK ASIT, SERUM", "ÜRİK ASİT, SERUM", "URIK ASIT"], "mg/dL"),
    }
    for name, (labels, default_unit) in exact_specs.items():
        parsed = _exact_row(text, labels)
        if parsed:
            value, unit, low, high = parsed
            _replace(values, _item(name, value, unit or default_unit, low, high))

    return values


def _parse_with_safety_normalization(text: str) -> list[dict[str, Any]]:
    return _normalize_exact_problem_rows(text, _original_parse(text))


lab_analysis._parse_lab_values_from_text = _parse_with_safety_normalization
