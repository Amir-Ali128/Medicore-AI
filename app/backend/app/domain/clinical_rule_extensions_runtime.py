"""Deterministic clinical-rule extensions for the compact case review.

Adds physician-verifiable derived scores, cross-panel consistency checks, temporal
context, performed-study filtering and transparent risk inputs without sending raw
reports or direct identifiers to Claude.

This layer is decision support only. It never establishes a diagnosis or treatment.
"""

from __future__ import annotations

import re
import unicodedata
from contextvars import ContextVar
from datetime import date, datetime
from math import sqrt
from typing import Any

from app.domain import multisource_summary_runtime as multisource_module
from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


_request_context: ContextVar[dict[str, Any]] = ContextVar(
    "medicore_clinical_rule_context", default={}
)

_original_generate = ClaudeClinicalHypothesisService.generate_for_analysis_run
_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------
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


def _name(result: Any) -> str:
    return str(
        getattr(result, "raw_parameter_name", None)
        or getattr(result, "canonical_name", None)
        or getattr(result, "parameter_code", None)
        or ""
    ).strip()


def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not (-1e12 < parsed < 1e12):
        return None
    return parsed


def _status(result: Any) -> str:
    raw = getattr(result, "result_status", None)
    return str(getattr(raw, "value", raw) or "unknown").lower()


def _find_result(
    results: list[Any],
    aliases: tuple[str, ...],
    *,
    exclude_tokens: tuple[str, ...] = (),
) -> Any | None:
    folded_aliases = tuple(_fold(alias) for alias in aliases)
    for result in results:
        folded = _fold(_name(result))
        if not folded:
            continue
        if any(token in folded for token in exclude_tokens):
            continue
        padded = f" {folded} "
        for alias in folded_aliases:
            if not alias:
                continue
            if len(alias) <= 5 and " " not in alias:
                if f" {alias} " in padded:
                    return result
            elif alias in folded:
                return result
    return None


def _value(result: Any | None) -> float | None:
    return _number(getattr(result, "normalized_value", None)) if result is not None else None


def _meaningful_upper(result: Any | None) -> float | None:
    if result is None:
        return None
    value = _number(getattr(result, "reference_max", None))
    if value is None or abs(value) >= 999_999_999:
        return None
    return value


def _age_from_metadata(metadata: dict[str, Any]) -> float | None:
    direct = _number(metadata.get("patient_age"))
    if direct is not None:
        return direct
    context = metadata.get("clinical_context")
    if isinstance(context, dict):
        patient = context.get("patient_information")
        if isinstance(patient, dict):
            return _number(patient.get("age"))
    return None


def _score_unavailable(code: str, name: str, formula: str, missing: list[str]) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "status": "unavailable",
        "value": None,
        "band": "hesaplanamadı",
        "formula": formula,
        "inputs": {},
        "missing": missing,
        "note": "Eksik parametre nedeniyle tahmin yapılmadı.",
    }


def _score(
    *,
    code: str,
    name: str,
    value: float,
    band: str,
    formula: str,
    inputs: dict[str, Any],
    thresholds: str,
    source_reference: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "status": "computed",
        "value": round(value, 3),
        "band": band,
        "formula": formula,
        "inputs": inputs,
        "thresholds": thresholds,
        "source_reference": source_reference,
        "note": "Bu hesap karar desteğidir; klinik bağlam olmadan tanı koydurmaz.",
    }


# ---------------------------------------------------------------------------
# Deterministic scores
# ---------------------------------------------------------------------------
def compute_deterministic_scores(results: list[Any], patient_age: float | None) -> list[dict[str, Any]]:
    ast = _find_result(results, ("AST", "aspartat aminotransferaz"))
    alt = _find_result(results, ("ALT", "alanin aminotransferaz"))
    plt = _find_result(results, ("PLT", "trombosit", "platelet"))
    iron = _find_result(results, ("serum demir", "demir", "iron"), exclude_tokens=("baglama", "ferritin"))
    uibc = _find_result(
        results,
        ("doymamis demir baglama kapasitesi", "ddbk", "uibc"),
    )
    total_chol = _find_result(results, ("total kolesterol", "total cholesterol"))
    hdl = _find_result(results, ("HDL", "hdl kolesterol", "hdl cholesterol"))

    ast_v = _value(ast)
    alt_v = _value(alt)
    plt_v = _value(plt)
    iron_v = _value(iron)
    uibc_v = _value(uibc)
    total_chol_v = _value(total_chol)
    hdl_v = _value(hdl)

    scores: list[dict[str, Any]] = []

    fib4_missing = [
        label
        for label, value in (("yaş", patient_age), ("AST", ast_v), ("ALT", alt_v), ("PLT", plt_v))
        if value is None
    ]
    if fib4_missing or patient_age is None or ast_v is None or alt_v is None or plt_v in {None, 0} or alt_v <= 0:
        scores.append(
            _score_unavailable(
                "FIB4",
                "FIB-4",
                "(yaş × AST) / (PLT × √ALT)",
                fib4_missing or ["geçerli pozitif ALT/PLT"],
            )
        )
    else:
        fib4 = (patient_age * ast_v) / (plt_v * sqrt(alt_v))
        low_cut = 2.0 if patient_age >= 65 else 1.3
        band = "düşük" if fib4 < low_cut else "belirsiz" if fib4 <= 2.67 else "yüksek"
        scores.append(
            _score(
                code="FIB4",
                name="FIB-4",
                value=fib4,
                band=band,
                formula="(yaş × AST) / (PLT × √ALT)",
                inputs={"yaş": patient_age, "AST": ast_v, "ALT": alt_v, "PLT": plt_v},
                thresholds=f"<{low_cut:g} düşük · {low_cut:g}-2.67 belirsiz · >2.67 yüksek",
                source_reference="Sterling et al., FIB-4; yaş ≥65 için yüksek özgüllük amacıyla 2.0 alt eşiği kullanılabilir.",
            )
        )

    ast_uln = _meaningful_upper(ast)
    apri_missing = [
        label
        for label, value in (("AST", ast_v), ("AST üst referans sınırı", ast_uln), ("PLT", plt_v))
        if value is None
    ]
    if apri_missing or ast_v is None or ast_uln in {None, 0} or plt_v in {None, 0}:
        scores.append(
            _score_unavailable(
                "APRI",
                "APRI",
                "(AST / AST_ULN) / PLT × 100",
                apri_missing,
            )
        )
    else:
        apri = (ast_v / ast_uln) / plt_v * 100.0
        band = "düşük" if apri < 0.5 else "belirsiz" if apri <= 1.5 else "yüksek"
        scores.append(
            _score(
                code="APRI",
                name="APRI",
                value=apri,
                band=band,
                formula="(AST / AST_ULN) / PLT × 100",
                inputs={"AST": ast_v, "AST_ULN": ast_uln, "PLT": plt_v},
                thresholds="<0.5 düşük · 0.5-1.5 belirsiz · >1.5 yüksek",
                source_reference="Wai et al., APRI; eşikler karar desteği amaçlıdır ve klinik bağlama göre yorumlanır.",
            )
        )

    if ast_v is None or alt_v in {None, 0}:
        scores.append(
            _score_unavailable("AST_ALT", "AST/ALT oranı", "AST / ALT", ["AST" if ast_v is None else "ALT"])
        )
    else:
        ratio = ast_v / alt_v
        band = "düşük" if ratio < 1 else "belirsiz" if ratio <= 2 else "yüksek"
        scores.append(
            _score(
                code="AST_ALT",
                name="AST/ALT oranı",
                value=ratio,
                band=band,
                formula="AST / ALT",
                inputs={"AST": ast_v, "ALT": alt_v},
                thresholds="<1 düşük oran · 1-2 ara oran · >2 yüksek oran (nedene özgü değildir)",
                source_reference="Genel hepatoloji oranı; tek başına hastalık tanısı için kullanılmaz.",
            )
        )

    if iron_v is None or uibc_v is None or (iron_v + uibc_v) <= 0:
        missing = [label for label, value in (("Demir", iron_v), ("DDBK/UIBC", uibc_v)) if value is None]
        scores.append(
            _score_unavailable(
                "TSAT",
                "Transferrin satürasyonu",
                "Demir / (Demir + DDBK) × 100",
                missing or ["geçerli Demir + DDBK"],
            )
        )
    else:
        tsat = iron_v / (iron_v + uibc_v) * 100.0
        band = "düşük" if tsat < 20 else "belirsiz" if tsat <= 45 else "yüksek"
        scores.append(
            _score(
                code="TSAT",
                name="Transferrin satürasyonu",
                value=tsat,
                band=band,
                formula="Demir / (Demir + DDBK) × 100",
                inputs={"Demir": iron_v, "DDBK": uibc_v},
                thresholds="<%20 düşük · %20-45 ara · >%45 yüksek; laboratuvarın kendi aralığı önceliklidir",
                source_reference="Standart demir paneli hesaplaması; laboratuvar-spesifik referans aralığı önceliklidir.",
            )
        )

    if total_chol_v is None or hdl_v in {None, 0}:
        missing = [label for label, value in (("Total kolesterol", total_chol_v), ("HDL", hdl_v)) if value is None]
        scores.append(
            _score_unavailable(
                "TOTAL_HDL",
                "Total kolesterol / HDL oranı",
                "Total kolesterol / HDL",
                missing,
            )
        )
    else:
        lipid_ratio = total_chol_v / hdl_v
        band = "düşük" if lipid_ratio < 4 else "belirsiz" if lipid_ratio <= 5 else "yüksek"
        scores.append(
            _score(
                code="TOTAL_HDL",
                name="Total kolesterol / HDL oranı",
                value=lipid_ratio,
                band=band,
                formula="Total kolesterol / HDL",
                inputs={"Total kolesterol": total_chol_v, "HDL": hdl_v},
                thresholds="<4 düşük oran · 4-5 ara oran · >5 yüksek oran; mutlak kardiyovasküler risk yerine geçmez",
                source_reference="Genel lipid oranı karar desteği; formal kardiyovasküler risk skorunun yerine geçmez.",
            )
        )

    return scores


# ---------------------------------------------------------------------------
# Cross-panel consistency checks
# ---------------------------------------------------------------------------
def _raw_positive(result: Any | None) -> bool:
    if result is None:
        return False
    raw = str(getattr(result, "raw_value", None) or "").strip().lower()
    if "+" in raw or "pozitif" in raw or "positive" in raw:
        return True
    return (_value(result) or 0) > 0 and "idrar" in _fold(_name(result))


def compute_cross_consistency(results: list[Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    serum_glucose = _find_result(
        results,
        ("glukoz", "glucose", "kan sekeri"),
        exclude_tokens=("idrar", "urine"),
    )
    urine_glucose = _find_result(results, ("idrar glukoz", "urine glucose", "idrar glucose"))
    serum_glucose_v = _value(serum_glucose)
    if serum_glucose_v is not None and _raw_positive(urine_glucose) and serum_glucose_v < 180:
        checks.append(
            {
                "code": "SERUM_URINE_GLUCOSE_DISCORDANCE",
                "severity": "review",
                "title": "Serum-idrar glukoz uyumsuzluğu",
                "message": (
                    f"Serum glukoz {serum_glucose_v:g} mg/dL iken idrar glukozu pozitif. "
                    "Yaklaşık 180 mg/dL renal eşik genel bir referanstır; bireysel eşik değişebilir. "
                    "İki sonuç farklı zamanlarda alınmışsa veya SGLT2 inhibitörü gibi klinik etkenler varsa ayrıca değerlendirilmelidir."
                ),
                "inputs": {
                    "serum_glucose": serum_glucose_v,
                    "urine_glucose": str(getattr(urine_glucose, "raw_value", None) or _value(urine_glucose)),
                },
            }
        )

    iron = _find_result(results, ("serum demir", "demir", "iron"), exclude_tokens=("baglama", "ferritin"))
    uibc = _find_result(results, ("doymamis demir baglama kapasitesi", "ddbk", "uibc"))
    tibc = _find_result(results, ("total demir baglama kapasitesi", "tdbk", "tibc"))
    iron_v, uibc_v, tibc_v = _value(iron), _value(uibc), _value(tibc)
    if None not in (iron_v, uibc_v, tibc_v) and tibc_v:
        expected = float(iron_v) + float(uibc_v)
        relative_error = abs(expected - float(tibc_v)) / abs(float(tibc_v))
        if relative_error > 0.15:
            checks.append(
                {
                    "code": "IRON_PANEL_ARITHMETIC_MISMATCH",
                    "severity": "review",
                    "title": "Demir paneli iç tutarlılık uyarısı",
                    "message": "Demir + DDBK ile raporlanan total demir bağlama kapasitesi arasında %15'ten büyük fark var; birim, örnek zamanı veya rapor satırı kontrol edilmeli.",
                    "inputs": {"Demir": iron_v, "DDBK": uibc_v, "TDBK": tibc_v},
                }
            )

    albumin = _find_result(results, ("albumin",))
    density = _find_result(results, ("idrar dansite", "urine specific gravity", "idrar yogunluk"))
    albumin_v, density_v = _value(albumin), _value(density)
    if albumin is not None and density is not None:
        if _status(albumin) == "high" and _status(density) == "high":
            checks.append(
                {
                    "code": "CONCENTRATION_PATTERN_SUPPORT",
                    "severity": "context",
                    "title": "Konsantrasyon/hidrasyon paterni",
                    "message": "Yüksek albumin ile yüksek idrar dansitesi aynı yönde konsantrasyon/dehidratasyon etkisiyle uyumlu olabilir; bu tanı değildir.",
                    "inputs": {"albumin": albumin_v, "urine_specific_gravity": density_v},
                }
            )
        elif _status(albumin) == "high" and density_v is not None and density_v < 1.010:
            checks.append(
                {
                    "code": "ALBUMIN_DENSITY_PATTERN_REVIEW",
                    "severity": "review",
                    "title": "Albumin-dansite paterni beklenmedik",
                    "message": "Albumin yüksekken idrar dansitesinin düşük olması basit konsantrasyon açıklamasıyla tam uyumlu değildir; örnek zamanı ve klinik bağlam kontrol edilmeli.",
                    "inputs": {"albumin": albumin_v, "urine_specific_gravity": density_v},
                }
            )

    ast = _find_result(results, ("AST", "aspartat aminotransferaz"))
    alt = _find_result(results, ("ALT", "alanin aminotransferaz"))
    albumin = _find_result(results, ("albumin",))
    if any(item is not None and _status(item) == "high" for item in (ast, alt)) and albumin is not None:
        if _status(albumin) == "low":
            checks.append(
                {
                    "code": "LIVER_ENZYME_SYNTHETIC_FUNCTION_REVIEW",
                    "severity": "review",
                    "title": "Karaciğer enzimi-sentetik fonksiyon birlikte değerlendirmesi",
                    "message": "Transaminaz yüksekliği ile düşük albumin birlikte mevcut; zamanlama, beslenme/inflamasyon ve karaciğer sentetik fonksiyonu hekim tarafından birlikte değerlendirilmelidir.",
                    "inputs": {"AST": _value(ast), "ALT": _value(alt), "albumin": _value(albumin)},
                }
            )

    return checks


# ---------------------------------------------------------------------------
# Temporal context and study canonicalization
# ---------------------------------------------------------------------------
def _extract_date(value: object) -> date | None:
    text = str(value or "")
    for pattern, fmt in (
        (r"\b(\d{2}\.\d{2}\.\d{4})\b", "%d.%m.%Y"),
        (r"\b(\d{4}-\d{2}-\d{2})\b", "%Y-%m-%d"),
    ):
        match = re.search(pattern, text)
        if match:
            try:
                return datetime.strptime(match.group(1), fmt).date()
            except ValueError:
                pass
    return None


def _canonical_study_codes(text: object) -> set[str]:
    folded = _fold(text)
    codes: set[str] = set()
    if not folded:
        return codes

    if any(token in folded for token in ("elastografi", "elastography", "metavir", "fibroscan")):
        codes.add("LIVER_ELASTOGRAPHY")
    if any(token in folded for token in ("ultrason", "ultrasound", "usg")):
        if any(token in folded for token in ("karaciger", "hepat", "safra", "portal", "dalak", "splen", "pankreas", "abdomen", "abdominal", "mezenterik")):
            codes.add("US_ABDOMEN")
        if any(token in folded for token in ("bobrek", "renal", "uriner")):
            codes.add("US_RENAL")
        if any(token in folded for token in ("tiroid", "thyroid")):
            codes.add("US_THYROID")
        if any(token in folded for token in ("meme", "breast")):
            codes.add("US_BREAST")
    if any(token in folded for token in ("hepatobilier", "hepatobiliary", "ust abdomen", "upper abdomen")):
        codes.add("US_ABDOMEN")
    if any(token in folded for token in ("bt", "computed tomography", "bilgisayarli tomografi")) and "abdomen" in folded:
        codes.add("CT_ABDOMEN")
    if any(token in folded for token in ("mr", "mri", "manyetik rezonans")) and "abdomen" in folded:
        codes.add("MRI_ABDOMEN")
    return codes


def _suggested_study_code(name: object) -> str | None:
    folded = _fold(name)
    if any(token in folded for token in ("elastografi", "elastography", "fibroscan")):
        return "LIVER_ELASTOGRAPHY"
    if any(token in folded for token in ("hepatobilier ultrason", "hepatobiliary ultrasound", "ust abdomen ultrason", "upper abdomen ultrasound", "abdomen ultrason", "abdominal ultrasound")):
        return "US_ABDOMEN"
    if "renal" in folded and any(token in folded for token in ("ultrason", "ultrasound")):
        return "US_RENAL"
    if "tiroid" in folded and any(token in folded for token in ("ultrason", "ultrasound")):
        return "US_THYROID"
    if "meme" in folded and any(token in folded for token in ("ultrason", "ultrasound")):
        return "US_BREAST"
    if "abdomen" in folded and any(token in folded for token in ("bt", "ct", "tomografi")):
        return "CT_ABDOMEN"
    if "abdomen" in folded and any(token in folded for token in ("mr", "mri", "manyetik")):
        return "MRI_ABDOMEN"
    return None


def _temporal_context(metadata: dict[str, Any]) -> dict[str, Any]:
    summaries = metadata.get("source_summaries")
    summaries = summaries if isinstance(summaries, dict) else {}
    lab_date = _extract_date(summaries.get("laboratory"))
    ultrasound_date = _extract_date(summaries.get("ultrasound"))
    output: dict[str, Any] = {
        "laboratory_date": lab_date.isoformat() if lab_date else None,
        "ultrasound_date": ultrasound_date.isoformat() if ultrasound_date else None,
        "gap_days": None,
        "warning": None,
    }
    if lab_date and ultrasound_date:
        gap = abs((ultrasound_date - lab_date).days)
        output["gap_days"] = gap
        if gap > 90:
            output["warning"] = (
                f"Laboratuvar ve ultrason verileri arasında {gap} gün var; eşzamanlı veri gibi yorumlanmamalı."
            )
    return output


def _performed_studies(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = metadata.get("source_summaries")
    summaries = summaries if isinstance(summaries, dict) else {}
    ultrasound = str(summaries.get("ultrasound") or "")
    ultrasound_date = _extract_date(ultrasound)
    codes = _canonical_study_codes(ultrasound)
    return [
        {
            "code": code,
            "name": {
                "LIVER_ELASTOGRAPHY": "Karaciğer elastografisi",
                "US_ABDOMEN": "Abdominal / hepatobilier ultrasonografi",
                "US_RENAL": "Renal ultrasonografi",
                "US_THYROID": "Tiroid ultrasonografisi",
                "US_BREAST": "Meme ultrasonografisi",
            }.get(code, code),
            "date": ultrasound_date.isoformat() if ultrasound_date else None,
        }
        for code in sorted(codes)
    ]


# ---------------------------------------------------------------------------
# Clinical-meaning extensions for previously uncovered abnormal parameters
# ---------------------------------------------------------------------------
_EXTRA_INTERPRETATIONS: list[dict[str, Any]] = [
    {
        "aliases": ("MPV", "mean platelet volume", "ortalama trombosit hacmi"),
        "high": "MPV yüksekliği dolaşımdaki trombositlerin ortalama hacminin arttığını gösterir; artmış trombosit dönüşümü veya daha genç/büyük trombositlerin dolaşıma çıkmasıyla ilişkili olabilir ancak tek başına özgül değildir.",
        "low": "MPV düşüklüğü ortalama trombosit hacminin daha küçük olduğunu gösterir; trombosit sayısı, örnekleme koşulları ve cihazla birlikte yorumlanmalıdır.",
        "causes_high": ("Artmış trombosit dönüşümü", "İnflamatuvar/reaktif süreçler", "Trombositopeniye eşlik eden kemik iliği yanıtı"),
        "causes_low": ("Azalmış trombosit üretimiyle ilişkili bazı durumlar", "Ölçüm/örnekleme etkileri"),
        "source": "ICSH/hematoloji indeksleri; MPV tek başına tanısal değildir.",
    },
    {
        "aliases": ("PDW", "platelet distribution width", "trombosit dagilim genisligi"),
        "high": "PDW yüksekliği trombosit boyutlarında heterojenliğin arttığını gösterir; trombosit aktivasyonu veya dönüşüm değişiklikleriyle ilişkili olabilir fakat özgül değildir.",
        "low": "PDW düşüklüğü trombosit boyut dağılımının daha homojen olduğunu gösterir; tek başına klinik tanı değeri sınırlıdır.",
        "causes_high": ("Trombosit aktivasyonu", "Reaktif/inflamatuvar süreçler", "Heterojen trombosit üretimi"),
        "causes_low": ("Daha homojen trombosit popülasyonu",),
        "source": "Genel hematoloji indeksleri; PDW klinik bağlamla yorumlanır.",
    },
    {
        "aliases": ("PCT", "plateletcrit", "trombositkrit"),
        "high": "Plateletcrit (PCT) toplam dolaşımdaki trombosit kütlesini yansıtır; yüksekliği trombosit sayısı ve/veya MPV artışıyla oluşabilir.",
        "low": "Plateletcrit (PCT) toplam dolaşımdaki trombosit kütlesini yansıtır; düşüklüğü çoğunlukla düşük trombosit sayısı ve/veya küçük trombosit hacmiyle birlikte değerlendirilir.",
        "causes_high": ("Trombositoz", "Artmış MPV ile birlikte artmış trombosit kütlesi"),
        "causes_low": ("Trombositopeni", "Azalmış trombosit üretimi veya artmış tüketim/yıkım paternleri"),
        "source": "CBC platelet indices; PCT, PLT ve MPV ile birlikte yorumlanır.",
    },
    {
        "aliases": ("RDW", "RDW-CV", "red cell distribution width", "eritrosit dagilim genisligi"),
        "high": "RDW yüksekliği eritrosit boyut değişkenliğinin (anizositozun) arttığını gösterir; demir, B12/folat eksikliği veya karışık eritrosit popülasyonlarında görülebilir.",
        "low": "RDW düşüklüğü genellikle eritrosit boyutlarının daha homojen olduğunu gösterir ve tek başına çoğu zaman klinik olarak özgül değildir.",
        "causes_high": ("Demir eksikliği", "Vitamin B12/folat eksikliği", "Karışık anemi paternleri", "Kan kaybı/tedavi sonrası eritrosit popülasyonu değişimi"),
        "causes_low": ("Homojen eritrosit boyut dağılımı",),
        "source": "Standart tam kan sayımı/RDW yorumlaması.",
    },
    {
        "aliases": ("DDBK", "doymamis demir baglama kapasitesi", "UIBC"),
        "high": "DDBK/UIBC yüksekliği transferrinin kullanılmamış demir bağlama kapasitesinin arttığını gösterir; serum demiri ve ferritinle birlikte demir eksikliği paterninde görülebilir.",
        "low": "DDBK/UIBC düşüklüğü transferrin kapasitesinin azalması veya bağlanma bölgelerinin daha fazla demirle dolu olmasıyla ilişkili olabilir; inflamasyon, karaciğer durumu ve demir yüküyle birlikte yorumlanır.",
        "causes_high": ("Demir eksikliği paterni", "Artmış transferrin düzeyi"),
        "causes_low": ("İnflamatuvar/kronik hastalık paterni", "Demir yüklenmesi", "Karaciğer sentez bozukluğu"),
        "source": "Standart demir paneli (serum demir, UIBC/TIBC, ferritin, transferrin satürasyonu).",
    },
    {
        "aliases": ("IgG", "immunoglobulin g", "immunglobulin g"),
        "high": "IgG yüksekliği poliklonal immün aktivasyon veya daha nadiren monoklonal immünoglobulin artışıyla ilişkili olabilir; serum protein elektroforezi ve klinik bağlam belirleyicidir.",
        "low": "IgG düşüklüğü humoral immün yetmezlik, protein kaybı veya bazı tedavi/hematolojik durumlarla ilişkili olabilir.",
        "causes_high": ("Kronik inflamasyon/enfeksiyon", "Otoimmün hastalıklar", "Kronik karaciğer hastalıkları", "Monoklonal gammopati"),
        "causes_low": ("Primer/sekonder immün yetmezlik", "Protein kaybettiren durumlar", "İmmünsüpresif tedavi etkisi"),
        "source": "Standart serum immünoglobulin değerlendirmesi; elektroforez/immünfiksasyon gerektiğinde hekim seçer.",
    },
    {
        "aliases": ("lipaz", "lipase"),
        "high": "Lipaz yüksekliği pankreatik enzim salınımının arttığını gösterebilir; akut pankreatit ile ilişkili olabilse de böbrek fonksiyonu ve diğer abdominal durumlar da lipazı yükseltebilir.",
        "low": "Düşük lipaz tek başına genellikle özgül değildir; belirgin pankreas ekzokrin yetersizliği şüphesi varsa klinik bağlamla değerlendirilir.",
        "causes_high": ("Akut pankreatit", "Biliyer/pankreatik hastalıklar", "Böbrek fonksiyon bozukluğu", "Diğer gastrointestinal/inflamatuvar durumlar"),
        "causes_low": ("İleri pankreas ekzokrin yetersizliğiyle ilişkili bazı durumlar",),
        "source": "Genel pankreatik enzim değerlendirmesi; pankreatit tanısı klinik ve görüntüleme ile birlikte konur.",
    },
    {
        "aliases": ("total protein", "toplam protein", "t protein"),
        "high": "Total protein yüksekliği albumin ve/veya globulin fraksiyonlarının artışından kaynaklanabilir; dehidratasyon, kronik inflamasyon veya immünoglobulin artışıyla ilişkili olabilir.",
        "low": "Total protein düşüklüğü yetersiz protein alımı/sentezi veya renal/gastrointestinal protein kaybıyla ilişkili olabilir.",
        "causes_high": ("Dehidratasyon", "Kronik inflamasyon", "Poliklonal/monoklonal gammopati"),
        "causes_low": ("Malnütrisyon", "Karaciğer sentez bozukluğu", "Böbrek veya gastrointestinal protein kaybı"),
        "source": "Standart total protein/albumin-globulin değerlendirmesi.",
    },
]


def _interpretation_for(name: str, direction: str) -> tuple[str | None, list[str], str | None]:
    folded = _fold(name)
    padded = f" {folded} "
    for entry in _EXTRA_INTERPRETATIONS:
        for alias in entry["aliases"]:
            candidate = _fold(alias)
            if (len(candidate) <= 5 and " " not in candidate and f" {candidate} " in padded) or (
                len(candidate) > 5 and candidate in folded
            ):
                text = entry.get(direction)
                causes = list(entry.get(f"causes_{direction}") or ())
                return str(text) if text else None, causes, str(entry.get("source") or "") or None
    return None, [], None


# ---------------------------------------------------------------------------
# Risk explanation and previous-value deltas
# ---------------------------------------------------------------------------
def _risk_baseline(flags: list[str]) -> int:
    if any("CRITICAL" in flag for flag in flags):
        return 3
    if len(flags) >= 3:
        return 2
    return 1


def _risk_details(results: list[Any], extra: dict[str, Any], flags: list[str]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for result in results:
        status = _status(result)
        if status not in {"high", "low"}:
            continue
        details.append(
            {
                "source": "laboratory",
                "flag": re.sub(r"[^A-Z0-9]+", "_", _name(result).upper()).strip("_") + f"_{status.upper()}",
                "title": _name(result),
                "detail": f"{getattr(result, 'normalized_value', None)} {getattr(result, 'unit', None) or ''} · {status}",
                "rule": str(getattr(result, "rule_applied", None) or "PDF reference comparison"),
            }
        )
    for score in extra.get("scores", []):
        if score.get("status") == "computed":
            details.append(
                {
                    "source": "derived_score",
                    "flag": f"SCORE_{score['code']}_{str(score.get('band') or '').upper()}",
                    "title": score.get("name"),
                    "detail": f"{score.get('value')} · {score.get('band')}",
                    "rule": score.get("formula"),
                }
            )
    for check in extra.get("cross_checks", []):
        if check.get("severity") == "review":
            details.append(
                {
                    "source": "cross_check",
                    "flag": check.get("code"),
                    "title": check.get("title"),
                    "detail": check.get("message"),
                    "rule": "Deterministic cross-panel consistency rule",
                }
            )
    temporal = extra.get("temporal") or {}
    if temporal.get("warning"):
        details.append(
            {
                "source": "temporal",
                "flag": "TEMPORAL_SOURCE_GAP_GT_90D",
                "title": "Veri tarihleri arasında belirgin fark",
                "detail": temporal.get("warning"),
                "rule": ">90 gün kaynak farkı",
            }
        )
    return details[:40]


def _trend_deltas(results: list[Any]) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    for result in results:
        previous = _number(getattr(result, "previous_value", None))
        current = _number(getattr(result, "normalized_value", None))
        if previous is None or current is None:
            continue
        deltas.append(
            {
                "name": _name(result),
                "previous": previous,
                "current": current,
                "absolute_difference": _number(getattr(result, "absolute_difference", None)),
                "percentage_difference": _number(getattr(result, "percentage_difference", None)),
                "time_difference_days": getattr(result, "time_difference_days", None),
                "direction": "up" if current > previous else "down" if current < previous else "same",
            }
        )
    return deltas[:30]


async def _generate_with_rule_context(
    self: ClaudeClinicalHypothesisService,
    analysis_run_id: Any,
    request: Any,
):
    results = list(await self._lab_results.list_for_analysis_run(analysis_run_id))
    metadata = dict(getattr(request, "metadata_json", None) or {})
    age = _age_from_metadata(metadata)
    scores = compute_deterministic_scores(results, age)
    cross_checks = compute_cross_consistency(results)
    temporal = _temporal_context(metadata)
    performed = _performed_studies(metadata)

    context_flags = [str(flag) for flag in metadata.get("context_flags", []) if str(flag)]
    for score in scores:
        if score.get("status") == "computed":
            flag = f"SCORE_{score['code']}_{str(score.get('band') or '').upper()}"
            context_flags.append(flag)
            multisource_module._ALLOWED_CONTEXT_FLAGS.add(flag)
    for check in cross_checks:
        if check.get("severity") == "review":
            flag = str(check.get("code"))
            context_flags.append(flag)
            multisource_module._ALLOWED_CONTEXT_FLAGS.add(flag)
    if temporal.get("warning"):
        context_flags.append("TEMPORAL_SOURCE_GAP_GT_90D")
        multisource_module._ALLOWED_CONTEXT_FLAGS.add("TEMPORAL_SOURCE_GAP_GT_90D")

    metadata["context_flags"] = list(dict.fromkeys(context_flags))
    metadata["deterministic_scores"] = scores
    metadata["cross_consistency"] = cross_checks
    metadata["temporal_context"] = temporal
    metadata["performed_studies"] = performed

    copied = request.model_copy(update={"metadata_json": metadata})
    extra = {
        "scores": scores,
        "cross_checks": cross_checks,
        "temporal": temporal,
        "performed_studies": performed,
        "all_results": results,
    }
    token = _request_context.set(extra)
    try:
        return await _original_generate(self, analysis_run_id, copied)
    finally:
        _request_context.reset(token)


def _build_hypothesis_with_rule_extensions(
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
    extra = dict(_request_context.get() or {})
    metadata = dict(hypothesis.metadata_json or {})
    results = list(extra.get("all_results") or [])

    # Keep semiquantitative raw values (e.g. urine glucose ++++) visible in the UI.
    result_by_name = {_fold(_name(item)): item for item in results}
    findings = list(metadata.get("pathological_findings") or [])
    possible_conditions = list(metadata.get("possible_conditions") or [])
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("source") != "laboratory":
            continue
        matching = result_by_name.get(_fold(finding.get("name")))
        if matching is not None:
            raw = str(getattr(matching, "raw_value", None) or "").strip()
            if raw and ("+" in raw or raw.lower() in {"pozitif", "negatif", "eser", "trace"}):
                finding["value"] = raw
                finding["display"] = f"{finding.get('name')}: {raw} ({finding.get('status_label')})"

        if not finding.get("clinical_interpretation"):
            interpretation, causes, source = _interpretation_for(
                str(finding.get("name") or ""), str(finding.get("status") or "")
            )
            if interpretation:
                finding["clinical_interpretation"] = interpretation
                finding["clinical_source"] = source
                finding["clinical_note"] = (
                    "Bu açıklama genel laboratuvar ilişkisidir; tek başına tanı koydurmaz ve diğer bulgularla birlikte doğrulanmalıdır."
                )
                finding["possible_causes"] = causes
                for cause in causes:
                    if cause not in possible_conditions:
                        possible_conditions.append(cause)

    metadata["pathological_findings"] = findings
    metadata["possible_conditions"] = possible_conditions[:24]

    performed = list(extra.get("performed_studies") or [])
    performed_by_code = {str(item.get("code")): item for item in performed if item.get("code")}
    kept_imaging: list[dict[str, Any]] = []
    already_performed: list[dict[str, Any]] = []
    for suggestion in list(metadata.get("recommended_imaging_tests") or []):
        if not isinstance(suggestion, dict):
            continue
        code = _suggested_study_code(suggestion.get("name"))
        if code and code in performed_by_code:
            performed_item = performed_by_code[code]
            already_performed.append(
                {
                    "code": code,
                    "name": suggestion.get("name") or performed_item.get("name"),
                    "performed_name": performed_item.get("name"),
                    "date": performed_item.get("date"),
                    "rationale": "Bu tetkik vaka girdisinde zaten mevcut olduğu için yeni öneri listesinden çıkarıldı.",
                }
            )
        else:
            kept_imaging.append(suggestion)
    metadata["recommended_imaging_tests"] = kept_imaging
    metadata["already_performed_studies"] = already_performed
    metadata["performed_studies"] = performed

    scores = list(extra.get("scores") or [])
    cross_checks = list(extra.get("cross_checks") or [])
    temporal = dict(extra.get("temporal") or {})
    metadata["deterministic_scores"] = scores
    metadata["cross_consistency"] = cross_checks
    metadata["temporal_context"] = temporal
    metadata["trend_deltas"] = _trend_deltas(results)
    metadata["risk_explanation"] = {
        "displayed_risk": risk,
        "deterministic_baseline": _risk_baseline(flags),
        "scale": {
            "1": "düşük öncelik / rutin hekim doğrulaması",
            "2": "orta öncelik / birden fazla dikkat sinyali",
            "3": "yüksek öncelik / kritik inceleme sinyali",
        },
        "flags": _risk_details(results, extra, flags),
        "all_flag_codes": flags,
        "note": "AI çağrıldıysa gösterilen 1-3 risk düzeyi kısa kaynak özetleri ve bu deterministik sinyaller üzerinden üretilir; kesin tanı veya prognoz skoru değildir.",
    }
    return hypothesis.model_copy(update={"metadata_json": metadata}) if hasattr(hypothesis, "model_copy") else _assign_metadata(hypothesis, metadata)


def _assign_metadata(hypothesis: Any, metadata: dict[str, Any]):
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService.generate_for_analysis_run = _generate_with_rule_context
ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_rule_extensions
