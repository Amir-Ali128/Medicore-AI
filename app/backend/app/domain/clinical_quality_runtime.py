"""Deterministic clinical quality layer for compact multisource evaluation.

This runtime enriches the existing physician-review workflow without giving the LLM
new authority. It computes reproducible scores, emits conservative cross-source
consistency flags, explains the 1-3 risk scale inputs, and filters follow-up tests
that are already present in the case.

All calculations are informational decision-support artifacts. They never create a
diagnosis, treatment plan, or automatic order.
"""

from __future__ import annotations

import contextvars
import math
import re
import unicodedata
from datetime import date, datetime
from typing import Any

from app.domain import multisource_summary_runtime as multisource_runtime
from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


_original_generate = ClaudeClinicalHypothesisService.generate_for_analysis_run
_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis

_QUALITY_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "medicore_clinical_quality_context",
    default=None,
)

QUALITY_FLAG_LABELS: dict[str, str] = {
    "FIB4_HIGH_REVIEW": "FIB-4: yüksek bant",
    "APRI_HIGH_REVIEW": "APRI: yüksek bant",
    "TRANSFERRIN_SATURATION_LOW": "Transferrin satürasyonu: düşük bant",
    "TRANSFERRIN_SATURATION_HIGH": "Transferrin satürasyonu: yüksek bant",
    "SERUM_URINE_GLUCOSE_UNEXPECTED": "Serum–idrar glukozu birlikte beklenmedik",
    "IRON_PANEL_INTERNAL_MISMATCH": "Demir paneli: hesaplanan ve raporlanan satürasyon uyumsuz",
    "TEMPORAL_GAP_GT_90_DAYS": "Kaynaklar arasında 90 günden uzun zaman farkı",
}

# Allow the existing bounded multisource prompt adapter to pass these deterministic
# routing flags through the same gate as ultrasound flags.
multisource_runtime._ALLOWED_CONTEXT_FLAGS.update(QUALITY_FLAG_LABELS)


def _fold(value: object) -> str:
    text = str(value or "")
    translated = text.translate(
        str.maketrans(
            {
                "ı": "i",
                "İ": "i",
                "ş": "s",
                "Ş": "s",
                "ğ": "g",
                "Ğ": "g",
                "ü": "u",
                "Ü": "u",
                "ö": "o",
                "Ö": "o",
                "ç": "c",
                "Ç": "c",
            }
        )
    )
    normalized = unicodedata.normalize("NFKD", translated)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).strip().lower()


def _status(result: Any) -> str:
    raw = getattr(result, "result_status", None)
    return str(getattr(raw, "value", raw) or "unknown").lower()


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _date(value: object) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _result_name(result: Any) -> str:
    return " ".join(
        str(
            getattr(result, "canonical_name", None)
            or getattr(result, "parameter_code", None)
            or getattr(result, "raw_parameter_name", None)
            or ""
        ).split()
    )


def _is_urine(result: Any) -> bool:
    name = _fold(
        " ".join(
            str(item or "")
            for item in (
                getattr(result, "raw_parameter_name", None),
                getattr(result, "canonical_name", None),
                getattr(result, "parameter_code", None),
            )
        )
    )
    return "idrar" in name or "urine" in name or "urinalysis" in name


def _matches(result: Any, aliases: tuple[str, ...], *, urine: bool | None = None) -> bool:
    if urine is not None and _is_urine(result) is not urine:
        return False
    name = _fold(
        " ".join(
            str(item or "")
            for item in (
                getattr(result, "parameter_code", None),
                getattr(result, "canonical_name", None),
                getattr(result, "raw_parameter_name", None),
            )
        )
    )
    padded = f" {name} "
    for alias in aliases:
        candidate = _fold(alias)
        if not candidate:
            continue
        if len(candidate) <= 5 and " " not in candidate:
            if f" {candidate} " in padded:
                return True
        elif candidate in name:
            return True
    return False


def _find_result(
    results: list[Any],
    aliases: tuple[str, ...],
    *,
    urine: bool | None = None,
) -> Any | None:
    candidates = [result for result in results if _matches(result, aliases, urine=urine)]
    if not candidates:
        return None

    # Prefer a numeric, mapped result with a usable measurement.
    candidates.sort(
        key=lambda result: (
            _number(getattr(result, "normalized_value", None)) is not None,
            getattr(result, "parameter_code", None) is not None,
            _date(getattr(result, "measured_at", None)) or date.min,
        ),
        reverse=True,
    )
    return candidates[0]


def _input(result: Any | None, label: str) -> dict[str, Any]:
    if result is None:
        return {"name": label, "value": None, "unit": None}
    parsed_date = _date(getattr(result, "measured_at", None))
    return {
        "name": label,
        "value": _number(getattr(result, "normalized_value", None)),
        "raw_value": getattr(result, "raw_value", None),
        "unit": getattr(result, "unit", None),
        "reference_max": _number(getattr(result, "reference_max", None)),
        "measured_at": parsed_date.isoformat() if parsed_date else None,
    }


def _score(
    *,
    code: str,
    label: str,
    formula: str,
    inputs: list[dict[str, Any]],
    value: float | None = None,
    band: str | None = None,
    band_label: str | None = None,
    missing: list[str] | None = None,
    flag: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    missing = missing or []
    return {
        "code": code,
        "label": label,
        "status": "unavailable" if missing else "calculated",
        "value": round(value, 3) if value is not None and not missing else None,
        "band": band if not missing else "hesaplanamadı",
        "band_label": band_label if not missing else "Eksik veri",
        "formula": formula,
        "inputs": inputs,
        "missing": missing,
        "flag": flag if not missing else None,
        "note": note,
    }


def _derive_scores(results: list[Any], patient_age: float | None) -> list[dict[str, Any]]:
    ast = _find_result(results, ("AST", "aspartat aminotransferaz"), urine=False)
    alt = _find_result(results, ("ALT", "alanin aminotransferaz"), urine=False)
    platelets = _find_result(results, ("PLT", "trombosit", "platelet"), urine=False)
    iron = _find_result(results, ("serum demir", "demir", "iron", "Fe"), urine=False)
    uibc = _find_result(
        results,
        (
            "doymamis demir baglama kapasitesi",
            "doymamış demir bağlama kapasitesi",
            "UIBC",
            "DDBK",
        ),
        urine=False,
    )
    total_cholesterol = _find_result(
        results,
        ("total kolesterol", "total cholesterol", "kolesterol"),
        urine=False,
    )
    hdl = _find_result(results, ("HDL", "hdl kolesterol"), urine=False)

    ast_v = _number(getattr(ast, "normalized_value", None))
    alt_v = _number(getattr(alt, "normalized_value", None))
    plt_v = _number(getattr(platelets, "normalized_value", None))
    ast_uln = _number(getattr(ast, "reference_max", None))
    iron_v = _number(getattr(iron, "normalized_value", None))
    uibc_v = _number(getattr(uibc, "normalized_value", None))
    total_v = _number(getattr(total_cholesterol, "normalized_value", None))
    hdl_v = _number(getattr(hdl, "normalized_value", None))

    scores: list[dict[str, Any]] = []

    fib_inputs = [
        {"name": "Yaş", "value": patient_age, "unit": "yıl"},
        _input(ast, "AST"),
        _input(alt, "ALT"),
        _input(platelets, "PLT"),
    ]
    fib_missing = [
        name
        for name, value in (
            ("yaş", patient_age),
            ("AST", ast_v),
            ("ALT", alt_v),
            ("PLT", plt_v),
        )
        if value is None
    ]
    if alt_v is not None and alt_v <= 0:
        fib_missing.append("ALT > 0")
    if plt_v is not None and plt_v <= 0:
        fib_missing.append("PLT > 0")
    fib_value = None
    fib_band = None
    fib_band_label = None
    fib_flag = None
    if not fib_missing:
        fib_value = float(patient_age) * float(ast_v) / (float(plt_v) * math.sqrt(float(alt_v)))
        low_cut = 2.0 if patient_age is not None and patient_age > 65 else 1.3
        if fib_value < low_cut:
            fib_band, fib_band_label = "low", "Düşük"
        elif fib_value <= 2.67:
            fib_band, fib_band_label = "indeterminate", "Belirsiz"
        else:
            fib_band, fib_band_label = "high", "Yüksek"
            fib_flag = "FIB4_HIGH_REVIEW"
    fib_note = (
        "FIB-4 yaşa ve klinik bağlama duyarlıdır; özellikle <35 ve >65 yaşta "
        "eşikler/yorum farklılaşabilir. Tek başına tanı koydurmaz."
    )
    scores.append(
        _score(
            code="FIB4",
            label="FIB-4",
            formula="(yaş × AST) / (PLT × √ALT)",
            inputs=fib_inputs,
            value=fib_value,
            band=fib_band,
            band_label=fib_band_label,
            missing=fib_missing,
            flag=fib_flag,
            note=fib_note,
        )
    )

    apri_inputs = [
        _input(ast, "AST"),
        {
            "name": "AST üst normal sınırı",
            "value": ast_uln,
            "unit": getattr(ast, "unit", None) if ast else None,
        },
        _input(platelets, "PLT"),
    ]
    apri_missing = [
        name
        for name, value in (("AST", ast_v), ("AST_ULN", ast_uln), ("PLT", plt_v))
        if value is None
    ]
    if ast_uln is not None and ast_uln <= 0:
        apri_missing.append("AST_ULN > 0")
    if plt_v is not None and plt_v <= 0:
        apri_missing.append("PLT > 0")
    apri_value = None
    apri_band = None
    apri_band_label = None
    apri_flag = None
    if not apri_missing:
        apri_value = (float(ast_v) / float(ast_uln)) / float(plt_v) * 100.0
        if apri_value <= 0.5:
            apri_band, apri_band_label = "low", "Düşük"
        elif apri_value <= 1.0:
            apri_band, apri_band_label = "indeterminate", "Belirsiz"
        else:
            apri_band, apri_band_label = "high", "Yüksek"
            apri_flag = "APRI_HIGH_REVIEW"
    scores.append(
        _score(
            code="APRI",
            label="APRI",
            formula="(AST / AST_ULN) / PLT × 100",
            inputs=apri_inputs,
            value=apri_value,
            band=apri_band,
            band_label=apri_band_label,
            missing=apri_missing,
            flag=apri_flag,
            note=(
                "Gösterilen 0.5/1.0 bantları WHO'nun viral hepatit bağlamındaki "
                "non-invaziv fibrozis eşiklerinden türetilmiştir; hastalık bağlamına göre yorumlanmalıdır."
            ),
        )
    )

    ratio_inputs = [_input(ast, "AST"), _input(alt, "ALT")]
    ratio_missing = [
        name for name, value in (("AST", ast_v), ("ALT", alt_v)) if value is None
    ]
    if alt_v is not None and alt_v <= 0:
        ratio_missing.append("ALT > 0")
    ratio_value = None if ratio_missing else float(ast_v) / float(alt_v)
    scores.append(
        _score(
            code="AST_ALT_RATIO",
            label="AST/ALT oranı",
            formula="AST / ALT",
            inputs=ratio_inputs,
            value=ratio_value,
            band="context_dependent" if not ratio_missing else None,
            band_label="Klinik bağlama bağlı" if not ratio_missing else None,
            missing=ratio_missing,
            note="AST/ALT oranı için tek, hastalıktan bağımsız düşük/yüksek eşiği kullanılmaz.",
        )
    )

    tsat_inputs = [_input(iron, "Demir"), _input(uibc, "DDBK/UIBC")]
    tsat_missing = [
        name for name, value in (("Demir", iron_v), ("DDBK/UIBC", uibc_v)) if value is None
    ]
    tibc = None
    tsat_value = None
    tsat_band = None
    tsat_band_label = None
    tsat_flag = None
    if not tsat_missing:
        tibc = float(iron_v) + float(uibc_v)
        if tibc <= 0:
            tsat_missing.append("TDBK > 0")
        else:
            tsat_value = float(iron_v) / tibc * 100.0
            if tsat_value < 20:
                tsat_band, tsat_band_label = "low", "Düşük"
                tsat_flag = "TRANSFERRIN_SATURATION_LOW"
            elif tsat_value > 45:
                tsat_band, tsat_band_label = "high", "Yüksek"
                tsat_flag = "TRANSFERRIN_SATURATION_HIGH"
            else:
                tsat_band, tsat_band_label = "reference_like", "Ara bant"
    tsat_inputs.append({"name": "Hesaplanan TDBK", "value": tibc, "unit": "µg/dL"})
    scores.append(
        _score(
            code="TRANSFERRIN_SATURATION",
            label="Transferrin satürasyonu",
            formula="Demir / (Demir + DDBK) × 100",
            inputs=tsat_inputs,
            value=tsat_value,
            band=tsat_band,
            band_label=tsat_band_label,
            missing=tsat_missing,
            flag=tsat_flag,
            note="Genel tarama bantlarıdır; laboratuvarın kendi referans aralığı önceliklidir.",
        )
    )

    lipid_inputs = [_input(total_cholesterol, "Total kolesterol"), _input(hdl, "HDL")]
    lipid_missing = [
        name
        for name, value in (("Total kolesterol", total_v), ("HDL", hdl_v))
        if value is None
    ]
    if hdl_v is not None and hdl_v <= 0:
        lipid_missing.append("HDL > 0")
    lipid_value = None if lipid_missing else float(total_v) / float(hdl_v)
    scores.append(
        _score(
            code="TOTAL_HDL_RATIO",
            label="Total/HDL oranı",
            formula="Total kolesterol / HDL",
            inputs=lipid_inputs,
            value=lipid_value,
            band="context_dependent" if not lipid_missing else None,
            band_label="Klinik bağlama bağlı" if not lipid_missing else None,
            missing=lipid_missing,
            note="Tek başına tanısal bir eşik olarak kullanılmaz; toplam kardiyovasküler risk bağlamında yorumlanır.",
        )
    )
    return scores


def _urine_semiquant_level(result: Any | None) -> int | None:
    if result is None:
        return None
    raw = str(getattr(result, "raw_value", None) or "").strip().lower()
    pluses = raw.count("+")
    if pluses:
        return pluses
    if raw in {"pozitif", "positive"}:
        return 1
    value = _number(getattr(result, "normalized_value", None))
    if value is None:
        return None
    return int(round(value))


def _cross_checks(results: list[Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    serum_glucose = _find_result(
        results,
        ("glukoz", "glucose", "kan sekeri", "kan şekeri"),
        urine=False,
    )
    urine_glucose = _find_result(
        results,
        ("idrar glukoz", "urine glucose", "glukoz"),
        urine=True,
    )
    serum_value = _number(getattr(serum_glucose, "normalized_value", None))
    urine_level = _urine_semiquant_level(urine_glucose)
    if (
        serum_value is not None
        and serum_value < 180
        and urine_level is not None
        and urine_level >= 3
    ):
        checks.append(
            {
                "code": "SERUM_URINE_GLUCOSE_UNEXPECTED",
                "severity": "review",
                "kind": "unexpected",
                "label": "Serum–idrar glukoz uyumsuzluğu",
                "message": (
                    "Serum glukozu 180 mg/dL altında iken idrarda belirgin glukoz pozitifliği "
                    "birlikte beklenmedik olabilir. Renal glukoz eşiği kişiye, zamana ve bazı "
                    "ilaçlara göre değişebildiğinden tanı çıkarılmaz; örnek zamanları ve klinik "
                    "bağlam doğrulanmalıdır."
                ),
                "values": [
                    _input(serum_glucose, "Serum glukoz"),
                    _input(urine_glucose, "İdrar glukoz"),
                ],
                "flag": "SERUM_URINE_GLUCOSE_UNEXPECTED",
            }
        )

    iron = _find_result(results, ("serum demir", "demir", "iron", "Fe"), urine=False)
    uibc = _find_result(
        results,
        ("doymamis demir baglama kapasitesi", "UIBC", "DDBK"),
        urine=False,
    )
    reported_sat = _find_result(
        results,
        ("transferrin saturasyonu", "transferrin saturation", "TSAT"),
        urine=False,
    )
    iron_v = _number(getattr(iron, "normalized_value", None))
    uibc_v = _number(getattr(uibc, "normalized_value", None))
    sat_v = _number(getattr(reported_sat, "normalized_value", None))
    if iron_v is not None and uibc_v is not None and sat_v is not None:
        tibc = iron_v + uibc_v
        if tibc > 0:
            computed = iron_v / tibc * 100.0
            if abs(computed - sat_v) > 5.0:
                checks.append(
                    {
                        "code": "IRON_PANEL_INTERNAL_MISMATCH",
                        "severity": "review",
                        "kind": "unexpected",
                        "label": "Demir paneli iç tutarlılık kontrolü",
                        "message": (
                            "Demir + DDBK üzerinden hesaplanan transferrin satürasyonu ile raporlanan "
                            "satürasyon arasında >5 yüzde puan fark var; birim, örnek zamanı veya veri "
                            "aktarımı doğrulanmalıdır."
                        ),
                        "values": [
                            _input(iron, "Demir"),
                            _input(uibc, "DDBK/UIBC"),
                            _input(reported_sat, "Raporlanan satürasyon"),
                            {"name": "Hesaplanan satürasyon", "value": round(computed, 2), "unit": "%"},
                        ],
                        "flag": "IRON_PANEL_INTERNAL_MISMATCH",
                    }
                )

    albumin = _find_result(results, ("albumin",), urine=False)
    urine_density = _find_result(
        results,
        ("idrar dansite", "dansite", "specific gravity", "urine density"),
        urine=True,
    )
    albumin_v = _number(getattr(albumin, "normalized_value", None))
    density_v = _number(getattr(urine_density, "normalized_value", None))
    if (
        albumin is not None
        and _status(albumin) == "high"
        and albumin_v is not None
        and density_v is not None
        and density_v >= 1.030
    ):
        checks.append(
            {
                "code": "ALBUMIN_DENSITY_HEMOCONCENTRATION_CONTEXT",
                "severity": "info",
                "kind": "supportive",
                "label": "Albumin–idrar dansitesi bağlamı",
                "message": (
                    "Yüksek albumin ile yüksek idrar dansitesi aynı yönde konsantrasyon/hidrasyon "
                    "bağlamını destekleyebilir; bu bir tanı veya nedensellik çıkarımı değildir."
                ),
                "values": [_input(albumin, "Albumin"), _input(urine_density, "İdrar dansitesi")],
                "flag": None,
            }
        )

    return checks


def _lab_dates(results: list[Any]) -> list[date]:
    return sorted(
        {
            parsed
            for result in results
            if (parsed := _date(getattr(result, "measured_at", None))) is not None
        }
    )


def _temporal_context(results: list[Any], metadata: dict[str, Any]) -> dict[str, Any]:
    dates = _lab_dates(results)
    lab_date = dates[-1] if dates else None
    source_dates = metadata.get("source_dates")
    ultrasound_date = None
    if isinstance(source_dates, dict):
        ultrasound_date = _date(source_dates.get("ultrasound"))

    gap_days = None
    warning = False
    if lab_date is not None and ultrasound_date is not None:
        gap_days = abs((ultrasound_date - lab_date).days)
        warning = gap_days > 90

    return {
        "laboratory_date": lab_date.isoformat() if lab_date else None,
        "laboratory_date_range": (
            {"from": dates[0].isoformat(), "to": dates[-1].isoformat()}
            if len(dates) > 1
            else None
        ),
        "ultrasound_date": ultrasound_date.isoformat() if ultrasound_date else None,
        "gap_days": gap_days,
        "threshold_days": 90,
        "warning": warning,
        "flag": "TEMPORAL_GAP_GT_90_DAYS" if warning else None,
        "message": (
            f"Laboratuvar ve ultrason verileri arasında {gap_days} gün var; eşzamanlı "
            "veri gibi yorumlanmamalıdır."
            if warning and gap_days is not None
            else None
        ),
    }


def _canonical_study_code(value: object) -> str | None:
    name = _fold(value)
    if not name:
        return None
    if "elastograf" in name or "fibroscan" in name:
        return "liver_elastography"
    if "hepatobilier" in name and ("ultrason" in name or "usg" in name):
        return "hepatobiliary_ultrasound"
    if ("ust abdomen" in name or "upper abdomen" in name) and (
        "ultrason" in name or "usg" in name
    ):
        return "upper_abdominal_ultrasound"
    if "renal" in name and ("ultrason" in name or "usg" in name):
        return "renal_ultrasound"
    if "kontrastli abdomen" in name and ("bt" in name or "mr" in name):
        return "contrast_abdominal_cross_sectional"
    return None


def _performed_lab_codes(results: list[Any]) -> set[str]:
    codes: set[str] = set()
    if (
        _find_result(results, ("ferritin",), urine=False) is not None
        and _find_result(results, ("serum demir", "demir", "iron", "Fe"), urine=False)
        is not None
    ):
        codes.add("ferritin_iron_panel")

    if (
        _find_result(results, ("serum demir", "demir", "iron", "Fe"), urine=False)
        is not None
        and _find_result(
            results,
            ("doymamis demir baglama kapasitesi", "UIBC", "DDBK"),
            urine=False,
        )
        is not None
    ):
        codes.add("iron_binding_panel")

    lipid_aliases = (
        ("total kolesterol", "total cholesterol"),
        ("HDL",),
        ("LDL",),
        ("trigliserid", "triglyceride"),
    )
    if all(_find_result(results, aliases, urine=False) is not None for aliases in lipid_aliases):
        codes.add("full_lipid_panel")

    return codes


def _canonical_lab_recommendation(value: object) -> str | None:
    name = _fold(value)
    if "ferritin" in name and "demir" in name and "panel" in name:
        return "ferritin_iron_panel"
    if (
        ("transferrin" in name or "tdbk" in name)
        and ("saturasyon" in name or "saturation" in name)
    ):
        return "iron_binding_panel"
    if "aclik lipid" in name and "panel" in name:
        return "full_lipid_panel"
    return None


def _filter_recommendations(
    metadata: dict[str, Any],
    results: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    performed_raw = metadata.get("performed_studies")
    performed_studies = (
        [item for item in performed_raw if isinstance(item, dict)]
        if isinstance(performed_raw, list)
        else []
    )

    imaging_codes: dict[str, dict[str, Any]] = {}
    for study in performed_studies:
        code = str(study.get("canonical_code") or "").strip() or _canonical_study_code(
            study.get("name")
        )
        if code:
            imaging_codes.setdefault(code, study)

    lab_codes = _performed_lab_codes(results)
    kept_lab: list[dict[str, Any]] = []
    kept_imaging: list[dict[str, Any]] = []
    already: list[dict[str, Any]] = []
    dates = _lab_dates(results)
    latest_lab_date = dates[-1].isoformat() if dates else None

    for test in metadata.get("recommended_laboratory_tests") or []:
        if not isinstance(test, dict):
            continue
        code = _canonical_lab_recommendation(test.get("name"))
        if code and code in lab_codes:
            already.append(
                {
                    **test,
                    "canonical_code": code,
                    "source": "laboratory",
                    "performed_date": latest_lab_date,
                    "reason": "Mevcut laboratuvar verilerinde bu panelin gerekli bileşenleri zaten bulunuyor.",
                }
            )
        else:
            kept_lab.append(test)

    for test in metadata.get("recommended_imaging_tests") or []:
        if not isinstance(test, dict):
            continue
        code = _canonical_study_code(test.get("name"))
        performed = imaging_codes.get(code or "")
        if code and performed is not None:
            already.append(
                {
                    **test,
                    "canonical_code": code,
                    "source": "imaging",
                    "performed_date": performed.get("date"),
                    "source_report_id": performed.get("source_report_id"),
                    "reason": "Bu tetkik vaka girdisinde zaten mevcut.",
                }
            )
        else:
            kept_imaging.append(test)

    return kept_lab, kept_imaging, already


def _risk_trigger_entries(
    flags: list[str],
    results: list[Any],
    quality_flags: set[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    by_base: dict[str, Any] = {}
    for result in results:
        code = (
            getattr(result, "parameter_code", None)
            or getattr(result, "canonical_name", None)
            or getattr(result, "raw_parameter_name", None)
        )
        if not code:
            continue
        base = re.sub(r"[^A-Z0-9]+", "_", str(code).upper()).strip("_")
        if base:
            by_base[base] = result

    for flag in flags:
        label = QUALITY_FLAG_LABELS.get(flag)
        rule = "deterministic_context_rule" if flag in quality_flags else None
        parameters: list[dict[str, Any]] = []

        if label is None:
            for suffix in ("_HIGH", "_LOW", "_REVIEW", "_NEEDS_REVIEW"):
                if flag.endswith(suffix):
                    base = flag[: -len(suffix)]
                    result = by_base.get(base)
                    if result is not None:
                        label = f"{_result_name(result)}: {_status(result)}"
                        rule = getattr(result, "rule_applied", None) or "reference_comparison"
                        parameters = [
                            {
                                "name": _result_name(result),
                                "value": _number(getattr(result, "normalized_value", None)),
                                "unit": getattr(result, "unit", None),
                                "reference_min": _number(getattr(result, "reference_min", None)),
                                "reference_max": _number(getattr(result, "reference_max", None)),
                            }
                        ]
                    break

        if label is None:
            if flag == "ULTRASOUND_CRITICAL_REVIEW":
                label = "Ultrason: kritik değerlendirme flag'i"
                rule = "radiology_context_flag"
            elif flag == "ULTRASOUND_ABNORMAL_REVIEW":
                label = "Ultrason: dikkat gerektiren bulgu flag'i"
                rule = "radiology_context_flag"
            else:
                label = flag.replace("_", " ").lower()
                rule = rule or "backend_review_flag"

        entries.append(
            {
                "flag": flag,
                "label": label,
                "rule": rule,
                "parameters": parameters,
            }
        )
    return entries


async def _generate_with_quality(
    self: ClaudeClinicalHypothesisService,
    analysis_run_id: Any,
    request: Any,
):
    results = list(await self._lab_results.list_for_analysis_run(analysis_run_id))
    metadata = dict(request.metadata_json or {})
    patient_age = _number(metadata.get("patient_age"))

    scores = _derive_scores(results, patient_age)
    cross_checks = _cross_checks(results)
    temporal = _temporal_context(results, metadata)

    quality_flags: list[str] = []
    for score in scores:
        flag = score.get("flag")
        if isinstance(flag, str) and flag:
            quality_flags.append(flag)
    for check in cross_checks:
        flag = check.get("flag")
        if isinstance(flag, str) and flag:
            quality_flags.append(flag)
    if isinstance(temporal.get("flag"), str):
        quality_flags.append(temporal["flag"])

    existing_flags = metadata.get("context_flags")
    context_flags = (
        [str(item) for item in existing_flags if isinstance(item, str)]
        if isinstance(existing_flags, list)
        else []
    )
    for flag in quality_flags:
        if flag not in context_flags:
            context_flags.append(flag)

    metadata["context_flags"] = context_flags
    metadata["deterministic_score_flags"] = quality_flags
    enriched_request = request.model_copy(update={"metadata_json": metadata})

    token = _QUALITY_CONTEXT.set(
        {
            "scores": scores,
            "cross_checks": cross_checks,
            "temporal": temporal,
            "results": results,
            "quality_flags": set(quality_flags),
            "request_metadata": metadata,
        }
    )
    try:
        return await _original_generate(self, analysis_run_id, enriched_request)
    finally:
        _QUALITY_CONTEXT.reset(token)


def _build_hypothesis_with_quality(
    self: ClaudeClinicalHypothesisService,
    run: Any,
    *,
    risk: int,
    summary: str,
    flags: list[str],
    symptoms: list[str],
    evidence: list[dict[str, Any]],
    ai_called: bool,
):
    hypothesis = _original_build_hypothesis(
        self,
        run,
        risk=risk,
        summary=summary,
        flags=flags,
        symptoms=symptoms,
        evidence=evidence,
        ai_called=ai_called,
    )
    context = _QUALITY_CONTEXT.get()
    if not context:
        return hypothesis

    metadata = dict(hypothesis.metadata_json or {})
    results = list(context.get("results") or [])
    request_metadata = dict(context.get("request_metadata") or {})

    kept_lab, kept_imaging, already = _filter_recommendations(
        {
            **request_metadata,
            "recommended_laboratory_tests": metadata.get("recommended_laboratory_tests") or [],
            "recommended_imaging_tests": metadata.get("recommended_imaging_tests") or [],
        },
        results,
    )
    metadata["recommended_laboratory_tests"] = kept_lab
    metadata["recommended_imaging_tests"] = kept_imaging
    metadata["already_performed_tests"] = already
    metadata["recommendation_filter_mode"] = "canonical_code_and_available_components"

    metadata["derived_scores"] = context.get("scores") or []
    metadata["cross_consistency_checks"] = context.get("cross_checks") or []
    metadata["temporal_context"] = context.get("temporal") or {}
    metadata["risk_explanation"] = {
        "score": risk,
        "scale_min": 1,
        "scale_max": 3,
        "scale_label": "1 düşük · 2 orta · 3 yüksek",
        "basis": (
            "AI sınıflaması; yalnızca deterministik backend flag'leri ve kısa kaynak özetleri üzerinden"
            if ai_called
            else "Deterministik fallback; backend flag'leri üzerinden"
        ),
        "triggers": _risk_trigger_entries(
            flags,
            results,
            set(context.get("quality_flags") or set()),
        ),
        "note": "Bu ölçek tanı veya otomatik tedavi/istem kararı değildir; hekim doğrulaması gerekir.",
    }
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService.generate_for_analysis_run = _generate_with_quality
ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_quality
