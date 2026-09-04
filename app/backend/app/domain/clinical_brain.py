"""Backend-owned deterministic clinical brain.

This module migrates browser-side clinical logic into Python. It prepares bounded
case summaries, selects the active ultrasound report, creates conservative doctor-
language lab interpretations, and calculates a rule-based evidence compatibility
score for acute calculous cholecystitis.

No score in this module is a disease probability and no output is a diagnosis.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import math
import re
import unicodedata
from typing import Iterable

from app.schemas.clinical_brain import (
    ClinicalBrainPerformedStudy,
    ClinicalBrainRequest,
    ClinicalBrainResult,
    ClinicalBrainSourceAvailability,
    ClinicalBrainSourceDates,
    ClinicalBrainSourceSummaries,
    ClinicalCompatibilityScore,
    CompatibilityBreakdown,
    CompatibilityEvidence,
    DoctorInterpretationItem,
    DoctorInterpretationSummary,
)
from app.schemas.lab_analysis import StructuredLabResultOutput
from app.schemas.radiology_report import RadiologyReportResponse


_DOMAIN_LABELS = {
    "clinical_findings": "Klinik bulgular",
    "laboratory_findings": "Laboratuvar bulguları",
    "imaging_findings": "Görüntüleme bulguları",
    "cross_modal_consistency": "Bulgular arası tutarlılık",
}

_RESULT_HEADING = re.compile(
    r"(?:^|\s)(?:SONUÇ|SONUC|İZLENİM|IZLENIM|DEĞERLENDİRME|DEGERLENDIRME|KANAAT|IMPRESSION|CONCLUSION)\s*[:\-–—]?\s*",
    re.IGNORECASE,
)
_NEXT_SECTION_HEADING = re.compile(
    r"\s(?:BULGU|BULGULAR|FINDINGS|TEKNİK|TEKNIK|TECHNIQUE|KLİNİK|KLINIK|ENDİKASYON|ENDIKASYON|ÖNERİLER|ONERILER)\s*[:\-–—]?\s*",
    re.IGNORECASE,
)


def _clean(value: object, max_chars: int = 240) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    if len(text) > max_chars:
        return f"{text[: max_chars - 1]}…"
    return text


def _fold(value: object) -> str:
    text = str(value or "").lower().replace("ı", "i")
    normalized = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(text.split()).strip()


def _has_any(text: str, terms: Iterable[str]) -> bool:
    return any(_fold(term) in text for term in terms)


def _status(result: StructuredLabResultOutput) -> str:
    value = result.result_status
    return str(getattr(value, "value", value)).lower()


def _lab_name(result: StructuredLabResultOutput) -> str:
    return result.raw_parameter_name or result.canonical_name or "Laboratuvar parametresi"


def _value_text(result: StructuredLabResultOutput) -> str:
    value = result.raw_value if _is_semiquantitative(result.raw_value) else result.normalized_value
    value_text = "" if value is None else str(value)
    return f"{value_text}{f' {result.unit}' if result.unit else ''}".strip()


def _is_semiquantitative(value: str | None) -> bool:
    normalized = _fold(value)
    if not normalized:
        return False
    return bool(re.fullmatch(r"\+{1,4}", normalized)) or normalized in {
        "negatif",
        "negative",
        "pozitif",
        "positive",
        "normal",
        "eser",
        "trace",
    }


def _meaningful_reference(value: Decimal | None) -> str | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or abs(numeric) >= 999_999_999:
        return None
    return str(value)


def _lab_reference(result: StructuredLabResultOutput) -> str | None:
    low = _meaningful_reference(result.reference_min)
    high = _meaningful_reference(result.reference_max)
    unit = f" {result.unit}" if result.unit else ""
    if low is not None and high is not None:
        return f"{low}-{high}{unit}"
    if high is not None:
        return f"<{high}{unit}"
    if low is not None:
        return f">{low}{unit}"
    return None


def _clinical_text(request: ClinicalBrainRequest) -> str:
    context = request.clinical_context
    if context is None:
        return ""
    return _fold(
        " ".join(
            str(item)
            for item in (
                context.presenting_complaint.reason_for_visit,
                context.presenting_complaint.chief_complaint,
                context.presenting_complaint.complaint_duration,
                context.presenting_complaint.associated_symptoms,
                context.clinical_history_details.history_of_present_illness,
                context.clinical_history_details.current_medical_conditions,
                context.physical_exam.examination_findings,
                context.imaging_results.ultrasound,
            )
            if item
        )
    )


def _has_meaningful_clinical_data(request: ClinicalBrainRequest) -> bool:
    context = request.clinical_context
    if context is None:
        return False
    complaint = context.presenting_complaint
    exam = context.physical_exam
    complaint_values = (
        complaint.reason_for_visit,
        complaint.chief_complaint,
        complaint.complaint_duration,
        complaint.severity_score,
        complaint.associated_symptoms,
    )
    exam_values = (
        exam.blood_pressure_systolic,
        exam.blood_pressure_diastolic,
        exam.pulse_bpm,
        exam.temperature_c,
        exam.respiratory_rate,
        exam.oxygen_saturation_percent,
        exam.examination_findings,
    )
    return any(value not in (None, "") for value in complaint_values + exam_values)


def build_clinical_summary(request: ClinicalBrainRequest) -> str:
    context = request.clinical_context
    if context is None:
        return "Klinik bilgi bulunamadı."
    complaint = context.presenting_complaint
    exam = context.physical_exam
    parts: list[str] = []

    chief = _clean(complaint.chief_complaint)
    duration = _clean(complaint.complaint_duration, 80)
    associated = _clean(complaint.associated_symptoms)
    exam_finding = _clean(exam.examination_findings)
    if chief:
        parts.append(f"{chief} ({duration})" if duration else chief)
    if associated:
        parts.append(f"Eşlik eden: {associated}")
    if exam_finding:
        parts.append(f"Muayene: {exam_finding}")

    vitals: list[str] = []
    if exam.blood_pressure_systolic is not None and exam.blood_pressure_diastolic is not None:
        vitals.append(f"TA {exam.blood_pressure_systolic}/{exam.blood_pressure_diastolic}")
    if exam.pulse_bpm is not None:
        vitals.append(f"Nabız {exam.pulse_bpm}")
    if exam.temperature_c is not None:
        vitals.append(f"Ateş {exam.temperature_c}°C")
    if exam.oxygen_saturation_percent is not None:
        vitals.append(f"SpO₂ %{exam.oxygen_saturation_percent}")
    if vitals:
        parts.append(" · ".join(vitals))
    return " | ".join(parts) or "Klinik bilgi girilmiş ancak kısa özet oluşturulamadı."


def build_clinical_ai_summary(request: ClinicalBrainRequest) -> str:
    context = request.clinical_context
    if context is None:
        return "Klinik bilgi bulunamadı."
    complaint = context.presenting_complaint
    exam = context.physical_exam
    parts = [
        _clean(complaint.chief_complaint),
        _clean(complaint.complaint_duration, 80),
        _clean(complaint.associated_symptoms),
        _clean(exam.examination_findings),
    ]
    text = " | ".join(item for item in parts if item)
    return text[:320] if text else "Kısa klinik özet yok."


def _abnormal_labs(results: list[StructuredLabResultOutput]) -> list[StructuredLabResultOutput]:
    return [item for item in results if _status(item) in {"high", "low"}]


def build_laboratory_summary(results: list[StructuredLabResultOutput]) -> str:
    if not results:
        return "Laboratuvar sonucu bulunamadı."
    abnormal = _abnormal_labs(results)
    if not abnormal:
        return "Yüksek veya düşük laboratuvar bulgusu yok."
    preview: list[str] = []
    for result in abnormal[:10]:
        direction = "yüksek" if _status(result) == "high" else "düşük"
        reference = _lab_reference(result)
        preview.append(
            f"{_lab_name(result)}: {_value_text(result)}"
            f"{f' · ref {reference}' if reference else ''} ({direction})"
        )
    suffix = f" +{len(abnormal) - len(preview)} yüksek/düşük bulgu" if len(abnormal) > len(preview) else ""
    return f"{'; '.join(preview)}{suffix}"


def build_laboratory_ai_summary(results: list[StructuredLabResultOutput]) -> str:
    abnormal = _abnormal_labs(results)
    if not abnormal:
        return "Yüksek veya düşük laboratuvar bulgusu yok."
    chunks: list[str] = []
    for result in abnormal:
        direction = "yüksek" if _status(result) == "high" else "düşük"
        reference = _lab_reference(result)
        chunks.append(
            f"{_lab_name(result)} {_value_text(result)}"
            f"{f' (ref {reference})' if reference else ''}: {direction}"
        )
    return "; ".join(chunks)[:1100]


def _metadata_text(report: RadiologyReportResponse, key: str) -> str:
    value = report.metadata_json.get(key)
    return value if isinstance(value, str) else ""


def _normalized_modality(report: RadiologyReportResponse) -> str:
    values = [
        report.modality,
        _metadata_text(report, "modality"),
        _metadata_text(report, "requested_modality"),
        _metadata_text(report, "detected_modality"),
        _metadata_text(report, "supported_modality"),
    ]
    return " ".join(value for value in values if value).upper().strip()


def is_ultrasound_report(report: RadiologyReportResponse) -> bool:
    modality = _normalized_modality(report)
    tokens = modality.split()
    filename = _fold(report.file_name)
    return (
        "ULTRASOUND" in modality
        or "ULTRASON" in modality
        or "USG" in modality
        or "US" in tokens
        or "ultrason" in filename
        or "ultrasound" in filename
        or "usg" in filename
    )


def _extract_ultrasound_result_text(report: RadiologyReportResponse) -> str | None:
    impression = _clean(report.impression, 1200)
    if impression:
        return impression
    original = " ".join((report.original_text or "").split()).strip()
    if not original:
        return None
    heading = _RESULT_HEADING.search(original)
    if heading is None:
        return None
    remainder = original[heading.end() :]
    next_heading = _NEXT_SECTION_HEADING.search(remainder)
    result_text = remainder[: next_heading.start()] if next_heading else remainder
    return _clean(result_text, 1200)


def _report_timestamp(report: RadiologyReportResponse) -> float:
    for value in (report.updated_at, report.created_at, report.report_date):
        if isinstance(value, datetime):
            return value.timestamp()
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day).timestamp()
    return 0.0


def get_latest_ultrasound_report(reports: list[RadiologyReportResponse]) -> RadiologyReportResponse | None:
    ultrasound = [report for report in reports if is_ultrasound_report(report)]
    if not ultrasound:
        return None
    ultrasound.sort(
        key=lambda report: (
            1 if _extract_ultrasound_result_text(report) else 0,
            _report_timestamp(report),
        ),
        reverse=True,
    )
    return ultrasound[0]


def build_ultrasound_summary(report: RadiologyReportResponse | None) -> str:
    if report is None:
        return "Ultrason raporu bulunamadı."
    result = _extract_ultrasound_result_text(report)
    if result:
        return result
    return "Ultrason kaydı bulundu ancak Sonuç/İzlenim metni çıkarılamadı."


def build_ultrasound_context_flags(report: RadiologyReportResponse | None) -> list[str]:
    if report is None:
        return []
    critical = bool(report.critical_findings) or any(
        finding.is_critical or finding.classification == "critical"
        for finding in report.findings
    )
    if critical:
        return ["ULTRASOUND_CRITICAL_REVIEW"]
    abnormal = any(finding.classification == "abnormal" for finding in report.findings)
    return ["ULTRASOUND_ABNORMAL_REVIEW"] if abnormal else []


def _study_evidence(report: RadiologyReportResponse) -> str:
    return _fold(
        " ".join(
            value
            for value in (
                report.modality,
                report.body_part,
                report.file_name,
                report.summary,
                report.impression,
                report.original_text,
            )
            if isinstance(value, str) and value
        )
    )


def build_performed_studies(reports: list[RadiologyReportResponse]) -> list[ClinicalBrainPerformedStudy]:
    output: list[ClinicalBrainPerformedStudy] = []
    seen: set[str] = set()

    def add(report: RadiologyReportResponse, code: str, name: str) -> None:
        key = f"{report.id}:{code}"
        if key in seen:
            return
        seen.add(key)
        output.append(
            ClinicalBrainPerformedStudy(
                canonical_code=code,
                name=name,
                date=report.report_date.isoformat() if report.report_date else None,
                source_report_id=str(report.id),
            )
        )

    for report in reports:
        text = _study_evidence(report)
        ultrasound = is_ultrasound_report(report)
        if "elastograf" in text or "fibroscan" in text:
            add(report, "liver_elastography", "Karaciğer elastografisi")
        if ultrasound and (
            "hepatobilier" in text
            or "safra" in text
            or "portal ven" in text
            or "karaciger" in text
        ):
            add(report, "hepatobiliary_ultrasound", "Hepatobilier ultrasonografi")
        if ultrasound and (
            "ust abdomen" in text
            or "upper abdomen" in text
            or "pankreas" in text
            or ("karaciger" in text and "safra" in text)
        ):
            add(report, "upper_abdominal_ultrasound", "Üst abdomen ultrasonografisi")
    return output


def _latest_lab_date(results: list[StructuredLabResultOutput]) -> str | None:
    dates = sorted(item.measured_at.isoformat() for item in results if item.measured_at)
    return dates[-1] if dates else None


def _source_dates(results: list[StructuredLabResultOutput], ultrasound: RadiologyReportResponse | None) -> ClinicalBrainSourceDates:
    return ClinicalBrainSourceDates(
        laboratory=_latest_lab_date(results),
        ultrasound=ultrasound.report_date.isoformat() if ultrasound and ultrasound.report_date else None,
    )


def _temporal_gap_days(dates: ClinicalBrainSourceDates) -> int | None:
    if not dates.laboratory or not dates.ultrasound:
        return None
    try:
        lab = date.fromisoformat(dates.laboratory)
        ultrasound = date.fromisoformat(dates.ultrasound)
    except ValueError:
        return None
    return abs((ultrasound - lab).days)


# ---------------------------------------------------------------------------
# Doctor-language lab interpretation migrated from clinicalInterpreter.ts.
# ---------------------------------------------------------------------------

def _normalized_lab_name(result: StructuredLabResultOutput) -> str:
    text = (result.canonical_name or result.raw_parameter_name or "").upper()
    translated = text.translate(str.maketrans({"İ": "I", "Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "Ç": "C", "ı": "I"}))
    return re.sub(r"[^A-Z0-9]+", "_", translated).strip("_")


def _lookup(results: list[StructuredLabResultOutput]) -> list[tuple[StructuredLabResultOutput, str, str]]:
    return [(item, _normalized_lab_name(item), _status(item)) for item in results]


def _find_by_any(lookup: list[tuple[StructuredLabResultOutput, str, str]], names: set[str]):
    return next((item for item in lookup if item[1] in names), None)


def _abnormal_within(lookup, names: set[str]):
    return [item for item in lookup if item[1] in names and item[2] in {"low", "high"}]


def _has_normal(lookup, names: set[str]) -> bool:
    item = _find_by_any(lookup, names)
    return bool(item and item[2] == "normal")


def _markers(items) -> list[str]:
    return [f"{_lab_name(item[0])} {_value_text(item[0])}".strip() for item in items]


def _generic_doctor_item(item) -> DoctorInterpretationItem:
    result, normalized_name, status = item
    marker_name = _lab_name(result)
    direction = "yüksek" if status == "high" else "düşük"
    return DoctorInterpretationItem(
        id=f"generic-{normalized_name}",
        title=f"{marker_name} {direction} saptandı",
        system="Genel laboratuvar değerlendirmesi",
        severity="moderate",
        markers=_markers([item]),
        interpretation=f"{marker_name} değeri referans aralığın {direction} tarafında saptanmıştır. Bu bulgu tek başına tanı koydurmaz; klinik öykü, muayene bulguları ve varsa önceki sonuçlarla birlikte değerlendirilmelidir.",
        clinical_context="İzole laboratuvar sapmaları örnek alma zamanı, geçici fizyolojik değişkenlik, ilaç kullanımı, yakın dönem enfeksiyon veya altta yatan klinik durumlarla ilişkili olabilir.",
        suggested_doctor_action="Hekim tarafından klinik bağlamla birlikte değerlendirilmesi, gerekirse önceki testlerle karşılaştırılması ve uygun görülürse kontrol tetkiki planlanması önerilir.",
    )


def build_doctor_interpretation(results: list[StructuredLabResultOutput]) -> DoctorInterpretationSummary:
    lookup = _lookup(results)
    abnormal = [item for item in lookup if item[2] in {"low", "high"}]
    used: set[str] = set()
    items: list[DoctorInterpretationItem] = []

    def add(item: DoctorInterpretationItem, sources) -> None:
        items.append(item)
        used.update(source[1] for source in sources)

    lipid = _abnormal_within(lookup, {"TOTAL_KOLESTEROL", "HDL", "TRIGLISERIT", "LDL", "NON_HDL"})
    if lipid:
        hdl = _find_by_any(lookup, {"HDL"})
        low_hdl = bool(hdl and hdl[2] == "low")
        add(
            DoctorInterpretationItem(
                id="lipid-profile",
                title="HDL kolesterol düşüklüğü" if low_hdl else "Lipid profilinde referans dışı bulgu",
                system="Kardiyometabolik risk",
                severity="moderate" if low_hdl and len(lipid) == 1 else "high",
                markers=_markers(lipid),
                interpretation=(
                    "HDL kolesterol referans aralığın altında saptanmıştır. HDL düşüklüğü kardiyometabolik risk değerlendirmesinde dikkate alınmalıdır."
                    if low_hdl
                    else "Lipid profilinde referans dışı değerler saptanmıştır. Bulgular kardiyovasküler risk profili içinde birlikte değerlendirilmelidir."
                ),
                clinical_context="Total kolesterol, LDL, HDL ve trigliserit değerleri tek tek değil, hastanın yaşı, aile öyküsü, tansiyon, sigara, diyabet ve diğer risk faktörleriyle birlikte yorumlanmalıdır.",
                suggested_doctor_action="Yaşam tarzı, beslenme, fiziksel aktivite ve kardiyovasküler risk skorlaması açısından hekim değerlendirmesi önerilir. Gerekirse lipid profili takibi planlanabilir.",
            ),
            lipid,
        )

    bilirubin = _abnormal_within(lookup, {"TOTAL_BILIRUBIN", "DIREKT_BILIRUBIN", "BILIRUBIN_TOTAL", "DIRECT_BILIRUBIN"})
    if bilirubin:
        enzymes_normal = all(_has_normal(lookup, {name}) for name in ("ALT", "AST", "ALP", "GGT"))
        add(
            DoctorInterpretationItem(
                id="bilirubin",
                title="Bilirubin yüksekliği",
                system="Karaciğer / safra yolları",
                severity="moderate",
                markers=_markers(bilirubin),
                interpretation="Total ve/veya direkt bilirubin referans aralığın üzerinde saptanmıştır. Bu bulgu bilirubin metabolizması, karaciğer fonksiyonları veya safra akımı ile ilişkili süreçler açısından değerlendirilmelidir.",
                clinical_context=(
                    "ALT, AST, ALP ve GGT değerlerinin normal olması, bulgunun izole veya hafif bilirubin yüksekliği şeklinde ele alınabileceğini düşündürür; yine de klinik bağlam önemlidir."
                    if enzymes_normal
                    else "Karaciğer enzimleriyle birlikte değerlendirme gereklidir. Eşlik eden enzim yüksekliği varsa hepatobiliyer süreçler açısından dikkatli yorumlanmalıdır."
                ),
                suggested_doctor_action="Semptomlar, ilaç kullanımı, sarılık öyküsü, açlık durumu ve önceki bilirubin sonuçlarıyla birlikte hekim değerlendirmesi önerilir. Gerekirse kontrol biyokimya paneli istenebilir.",
            ),
            bilirubin,
        )

    cbc_names = {"LOKOSIT", "WBC", "NOTROFIL_MUTLAK", "NOTROFIL", "LENFOSIT_MUTLAK", "LENFOSIT", "MONOSIT_MUTLAK", "EOZINOFIL_MUTLAK", "BAZOFIL_MUTLAK", "HEMOGLOBIN", "HEMATOKRIT", "ERITROSIT", "TROMBOSIT"}
    cbc = _abnormal_within(lookup, cbc_names)
    if cbc:
        wbc = _find_by_any(lookup, {"LOKOSIT", "WBC"})
        low_wbc = bool(wbc and wbc[2] == "low")
        add(
            DoctorInterpretationItem(
                id="cbc",
                title="Hafif lökopeni" if low_wbc else "Hemogramda referans dışı bulgu",
                system="Hemogram / kan hücreleri",
                severity="moderate",
                markers=_markers(cbc),
                interpretation=(
                    "Lökosit değeri referans aralığın hafif altında saptanmıştır. Bu durum hafif lökopeni olarak değerlendirilebilir."
                    if low_wbc
                    else "Hemogram parametrelerinde referans dışı değer saptanmıştır. Bulgular hücre serileri ve diferansiyel dağılım ile birlikte yorumlanmalıdır."
                ),
                clinical_context="Hafif hemogram sapmaları yakın dönem viral enfeksiyon, ilaç kullanımı, bireysel varyasyon veya geçici kemik iliği yanıtları ile ilişkili olabilir. Tek ölçümle kesin klinik çıkarım yapılmamalıdır.",
                suggested_doctor_action="Hastanın semptomları, ateş/enfeksiyon bulguları, ilaç öyküsü ve önceki hemogramları ile birlikte değerlendirme önerilir. Gerekirse kontrol hemogram planlanabilir.",
            ),
            cbc,
        )

    platelet = _abnormal_within(lookup, {"P_LCR", "PCT", "MPV"})
    if platelet:
        platelet_normal = _has_normal(lookup, {"TROMBOSIT", "PLATELET", "PLT"})
        mpv_normal = _has_normal(lookup, {"MPV"})
        add(
            DoctorInterpretationItem(
                id="platelet-indices",
                title="Trombosit indekslerinde referans dışı bulgu",
                system="Trombosit parametreleri",
                severity="low",
                markers=_markers(platelet),
                interpretation="P-LCR veya diğer trombosit indekslerinde referans dışı değer saptanmıştır. Bu parametreler trombosit boyutu ve dağılımı hakkında yardımcı bilgi verir.",
                clinical_context=(
                    "Trombosit sayısı ve MPV normal aralıkta olduğunda P-LCR düşüklüğünün tek başına klinik anlamı sınırlı olabilir."
                    if platelet_normal and mpv_normal
                    else "Trombosit sayısı, MPV ve diğer hemogram parametreleriyle birlikte değerlendirilmelidir."
                ),
                suggested_doctor_action="Tek başına karar verdirici değildir. Hemogram bütünlüğü, klinik bulgular ve gerekirse takip sonucu ile birlikte hekim tarafından yorumlanmalıdır.",
            ),
            platelet,
        )

    folate = _abnormal_within(lookup, {"FOLIK_ASIT", "FOLATE", "FOLIC_ACID"})
    if folate:
        low = any(item[2] == "low" for item in folate)
        add(
            DoctorInterpretationItem(
                id="folate",
                title="Folik asit düşüklüğü" if low else "Folik asit yüksekliği",
                system="Vitamin / beslenme durumu",
                severity="moderate",
                markers=_markers(folate),
                interpretation=(
                    "Folik asit değeri referans aralığın altında saptanmıştır. Bu bulgu folat eksikliği açısından değerlendirilmelidir."
                    if low
                    else "Folik asit değeri referans aralığın üzerinde saptanmıştır. Takviye kullanımı veya yakın dönem alım öyküsü ile birlikte yorumlanmalıdır."
                ),
                clinical_context="Folik asit sonucu hemoglobin, MCV, B12 düzeyi, beslenme öyküsü ve varsa takviye kullanımıyla birlikte değerlendirilmelidir.",
                suggested_doctor_action="Eksiklik şüphesinde hekim değerlendirmesi, beslenme/takviye öyküsünün sorgulanması ve gerekirse takip veya ek tetkik planlanması önerilir.",
            ),
            folate,
        )

    inflammation = _abnormal_within(lookup, {"CRP", "SEDIMENTASYON", "ESR"})
    if inflammation:
        add(
            DoctorInterpretationItem(
                id="inflammation",
                title="İnflamasyon belirteçlerinde artış",
                system="İnflamasyon / enfeksiyon",
                severity="moderate",
                markers=_markers(inflammation),
                interpretation="CRP ve/veya sedimentasyon değerinde yükseklik saptanmıştır. Bu bulgular inflamasyon veya enfeksiyon süreçleriyle ilişkili olabilir.",
                clinical_context="Bu belirteçler özgül değildir; enfeksiyon, inflamatuvar durumlar, travma veya başka klinik süreçlerde yükselebilir.",
                suggested_doctor_action="Ateş, ağrı, enfeksiyon bulguları ve muayene ile birlikte değerlendirme önerilir. Gerekirse klinik odağa göre ek tetkik planlanabilir.",
            ),
            inflammation,
        )

    thyroid = _abnormal_within(lookup, {"TSH", "FT3", "FT4"})
    if thyroid:
        add(
            DoctorInterpretationItem(
                id="thyroid",
                title="Tiroid fonksiyon testlerinde referans dışı bulgu",
                system="Endokrin / tiroid",
                severity="moderate",
                markers=_markers(thyroid),
                interpretation="TSH, FT3 veya FT4 parametrelerinden en az biri referans aralığın dışında saptanmıştır. Tiroid fonksiyonları eksen halinde yorumlanmalıdır.",
                clinical_context="TSH tek başına değil, serbest hormon düzeyleri, ilaç kullanımı, biyotin/takviye öyküsü ve klinik belirtilerle birlikte değerlendirilmelidir.",
                suggested_doctor_action="Hekim tarafından tiroid semptomları ve ilaç/takviye öyküsüyle birlikte değerlendirilmesi, gerekirse tekrar test veya ek inceleme planlanması önerilir.",
            ),
            thyroid,
        )

    kidney = _abnormal_within(lookup, {"KREATININ", "GFR", "BUN"})
    if kidney:
        add(
            DoctorInterpretationItem(
                id="kidney",
                title="Böbrek fonksiyon parametrelerinde referans dışı bulgu",
                system="Böbrek fonksiyonu",
                severity="high",
                markers=_markers(kidney),
                interpretation="Kreatinin, BUN veya GFR parametrelerinde referans dışı değer saptanmıştır. Böbrek fonksiyonları hidrasyon, kas kütlesi ve klinik durumla birlikte değerlendirilmelidir.",
                clinical_context="Tek ölçüm akut/kronik ayrımı yapmaz. Önceki sonuçlar, idrar bulguları, tansiyon ve ilaç kullanımı önemlidir.",
                suggested_doctor_action="Hekim değerlendirmesi ve gerekirse böbrek fonksiyon testlerinin tekrarı, idrar analizi veya ek inceleme önerilir.",
            ),
            kidney,
        )

    for item in abnormal:
        if item[1] not in used:
            add(_generic_doctor_item(item), [item])

    return DoctorInterpretationSummary(
        abnormal_count=len(abnormal),
        low_count=sum(1 for item in abnormal if item[2] == "low"),
        high_count=sum(1 for item in abnormal if item[2] == "high"),
        items=items,
        safety_note="Bu bölüm klinik karar destek amaçlı ön yorumdur; tanı, tedavi veya nihai karar yerine geçmez. Son değerlendirme hekim tarafından yapılmalıdır.",
    )


# ---------------------------------------------------------------------------
# Rule-based compatibility migrated from clinicalCompatibilityScore.ts.
# ---------------------------------------------------------------------------

def _imaging_text(reports: list[RadiologyReportResponse]) -> str:
    chunks: list[str] = []
    for report in reports:
        chunks.extend([report.original_text, report.summary, report.impression or ""])
        chunks.extend(finding.text for finding in report.findings)
    return _fold(" ".join(chunk for chunk in chunks if chunk))


def _has_positive_murphy(text: str) -> bool:
    if "murphy" not in text:
        return False
    return re.search(r"murphy.{0,32}(negatif|negative|yok|saptanmadi|izlenmedi)", text) is None


def _find_lab(results: list[StructuredLabResultOutput], aliases: Iterable[str]) -> StructuredLabResultOutput | None:
    folded_aliases = [_fold(alias) for alias in aliases]
    for result in results:
        haystack = _fold(" ".join(str(value) for value in (result.parameter_code, result.canonical_name, result.raw_parameter_name) if value))
        if any(alias in haystack for alias in folded_aliases):
            return result
    return None


def _is_high(result: StructuredLabResultOutput | None) -> bool:
    return result is not None and _status(result) == "high"


def _duration_hours(request: ClinicalBrainRequest, clinical: str) -> float | None:
    explicit = _fold(request.clinical_context.presenting_complaint.complaint_duration) if request.clinical_context else ""
    candidate = f"{explicit} {clinical}"
    hour = re.search(r"(\d+(?:[.,]\d+)?)\s*(saat|hour)", candidate)
    if hour:
        return float(hour.group(1).replace(",", "."))
    day = re.search(r"(\d+(?:[.,]\d+)?)\s*(gun|day)", candidate)
    if day:
        return float(day.group(1).replace(",", ".")) * 24
    return None


def _wall_thickening(text: str) -> bool:
    match = re.search(r"(?:safra kesesi\s+)?duvar kalinligi\s*(?:[:=]|olarak)?\s*(\d+(?:[.,]\d+)?)\s*mm", text)
    return bool(match and float(match.group(1).replace(",", ".")) > 3)


def _evidence(code: str, label: str, domain: str, points: int, maximum: int, matched: bool, detail: str) -> CompatibilityEvidence:
    return CompatibilityEvidence(
        code=code,
        label=label,
        domain=domain,
        points=points if matched else 0,
        maximum_points=maximum,
        matched=matched,
        detail=detail,
    )


def _compatibility_level(score: int) -> tuple[str, str]:
    if score >= 85:
        return "very_high", "Çok yüksek uyum"
    if score >= 70:
        return "high", "Yüksek uyum"
    if score >= 50:
        return "moderate", "Orta uyum"
    if score >= 25:
        return "low", "Düşük uyum"
    return "very_low", "Çok düşük uyum"


def calculate_acute_cholecystitis_compatibility(request: ClinicalBrainRequest) -> ClinicalCompatibilityScore:
    clinical = _clinical_text(request)
    imaging = _imaging_text(request.radiology_reports)
    duration = _duration_hours(request, clinical)
    temperature = request.clinical_context.physical_exam.temperature_c if request.clinical_context else None

    wbc = _find_lab(request.lab_results, ["wbc", "lökosit", "lokosit", "leukocyte"])
    neutrophil = _find_lab(request.lab_results, ["neutrophil", "nötrofil", "notrofil", "neu", "parçalı mutlak", "parcali mutlak"])
    crp = _find_lab(request.lab_results, ["crp", "c-reaktif", "c reaktif"])
    pct = _find_lab(request.lab_results, ["prokalsitonin", "procalcitonin"])
    esr = _find_lab(request.lab_results, ["esr", "sedim", "sedimentasyon"])
    bilirubin = _find_lab(request.lab_results, ["total bilirubin", "bilirubin total", "tbil"])
    direct_bilirubin = _find_lab(request.lab_results, ["direkt bilirubin", "direct bilirubin", "dbil"])
    alp = _find_lab(request.lab_results, ["alp", "alkalen fosfataz"])
    ggt = _find_lab(request.lab_results, ["ggt", "gama glutamil", "gamma glutamyl"])

    ruq = _has_any(clinical, ["sağ üst kadran", "sag ust kadran", "right upper quadrant", "ruq", "sağ subkostal", "sag subkostal"])
    murphy = _has_positive_murphy(clinical)
    fever = (temperature is not None and float(temperature) >= 38) or _has_any(clinical, ["ateş", "ates", "fever"])
    duration_over_six = duration is not None and duration > 6
    duration_points = 5 if duration is not None and duration > 24 else 4

    impacted = _has_any(imaging, ["impakte", "hareketsiz yerleşimli", "hareketsiz yerlesimli"]) and _has_any(imaging, ["kese boynu", "safra kesesi boynu", "gallbladder neck"]) and _has_any(imaging, ["taş", "tas", "kalkül", "kalkul", "stone"])
    wall = _wall_thickening(imaging) or _has_any(imaging, ["duvar kalınlaş", "duvar kalinlas", "duvar kalınlığı art", "duvar kalinligi art", "wall thickening"])
    sono_murphy = _has_positive_murphy(imaging) and _has_any(imaging, ["sonografik", "ultrason", "prob"])
    perichole = bool(re.search(r"perikolesistik.{0,45}(sivi|serbest sivi)", imaging) or re.search(r"pericholecystic.{0,45}fluid", imaging))
    minimal_fluid = perichole and _has_any(imaging, ["minimal", "ince tabaka", "az miktarda"])
    distension = _has_any(imaging, ["safra kesesi distandü", "safra kesesi distandu", "safra kesesi distansiyonu", "gallbladder distension"])
    no_dilatation = _has_any(imaging, ["safra yollarında dilatasyon saptanmamıştır", "safra yollarinda dilatasyon saptanmamistir", "koledok normal sınırlarda", "koledok normal sinirlarda", "bile duct dilatation yok"])
    no_cbd_stone = _has_any(imaging, ["koledok içerisinde kalkül saptanmamıştır", "koledok icerisinde kalkul saptanmamistir", "koledokta taş saptanmadı", "koledokta tas saptanmadi", "common bile duct stone yok"])
    dilatation = not no_dilatation and ((
        _has_any(imaging, ["koledok", "safra yolu", "safra yollari"])
        and _has_any(imaging, ["dilate", "dilatasyon", "geniş", "genis", "belirgin"])
    ) or bool(re.search(r"koledok.{0,30}\b([7-9]|\d{2,})(?:[.,]\d+)?\s*mm", imaging)))

    inflammatory = _is_high(wbc) or _is_high(neutrophil) or _is_high(crp)
    key_imaging = impacted or wall or sono_murphy or perichole or distension
    cholestatic = _is_high(bilirubin) or _is_high(direct_bilirubin) or _is_high(alp) or _is_high(ggt)
    additional_points = 3 if _is_high(pct) else 2 if _is_high(esr) else 0

    evidence = [
        _evidence("ruq_pain", "Sağ üst kadran ağrısı veya hassasiyeti", "clinical_findings", 8, 8, ruq, "Klinik metinde sağ üst kadran ağrısı/hassasiyeti bulundu." if ruq else "Sağ üst kadran ağrısı açıkça bulunamadı."),
        _evidence("clinical_murphy", "Klinik Murphy bulgusu", "clinical_findings", 12, 12, murphy, "Murphy bulgusu pozitif olarak yorumlandı." if murphy else "Pozitif Murphy bulgusu bulunamadı."),
        _evidence("fever", "Ateş", "clinical_findings", 5, 5, fever, f"Ateş desteği bulundu{f' ({temperature} °C)' if temperature is not None else ''}." if fever else "Ateş desteği bulunamadı."),
        _evidence("pain_duration", "Ağrının altı saatten uzun sürmesi", "clinical_findings", duration_points, 5, duration_over_six, f"Semptom süresi yaklaşık {duration} saat." if duration_over_six else "Altı saati aşan semptom süresi doğrulanamadı."),
        _evidence("leukocytosis", "Lökositoz", "laboratory_findings", 8, 8, _is_high(wbc), f"Lökosit yüksek ({_value_text(wbc)})." if _is_high(wbc) and wbc else "Yüksek lökosit sonucu bulunamadı."),
        _evidence("neutrophilia", "Nötrofili", "laboratory_findings", 4, 4, _is_high(neutrophil), f"Nötrofil yüksek ({_value_text(neutrophil)})." if _is_high(neutrophil) and neutrophil else "Nötrofili bulunamadı."),
        _evidence("elevated_crp", "CRP yüksekliği", "laboratory_findings", 10, 10, _is_high(crp), f"CRP yüksek ({_value_text(crp)})." if _is_high(crp) and crp else "Yüksek CRP sonucu bulunamadı."),
        _evidence("additional_inflammation", "Ek inflamasyon desteği", "laboratory_findings", additional_points, 3, additional_points > 0, f"Prokalsitonin yüksek ({_value_text(pct)})." if _is_high(pct) and pct else f"Sedimentasyon yüksek ({_value_text(esr)})." if _is_high(esr) and esr else "Ek inflamasyon belirteci desteği bulunamadı."),
        _evidence("impacted_neck_stone", "Safra kesesi boynunda impakte taş", "imaging_findings", 10, 10, impacted, "Kese boynunda impakte/hareketsiz kalkül ifadesi bulundu." if impacted else "Kese boynunda impakte taş doğrulanamadı."),
        _evidence("wall_thickening", "Safra kesesi duvar kalınlaşması", "imaging_findings", 8, 8, wall, "Duvar kalınlığı 3 mm üzerinde veya kalınlaşmış olarak raporlandı." if wall else "Duvar kalınlaşması bulunamadı."),
        _evidence("sonographic_murphy", "Sonografik Murphy bulgusu", "imaging_findings", 8, 8, sono_murphy, "Sonografik Murphy bulgusu pozitif." if sono_murphy else "Pozitif sonografik Murphy bulgusu bulunamadı."),
        _evidence("pericholecystic_fluid", "Perikolesistik sıvı", "imaging_findings", 6 if minimal_fluid else 7, 7, perichole, f"{'Minimal ' if minimal_fluid else ''}perikolesistik sıvı bulundu." if perichole else "Perikolesistik sıvı bulunamadı."),
        _evidence("gallbladder_distension", "Safra kesesi distansiyonu", "imaging_findings", 5, 5, distension, "Safra kesesi distansiyonu raporlandı." if distension else "Safra kesesi distansiyonu bulunamadı."),
        _evidence("normal_bile_duct", "Koledokta taş veya dilatasyon olmaması", "imaging_findings", (1 if no_dilatation else 0) + (1 if no_cbd_stone else 0), 2, no_dilatation or no_cbd_stone, " ".join(item for item in ["Safra yolu dilatasyonu yok." if no_dilatation else "", "Koledok taşı yok." if no_cbd_stone else ""] if item) or "Koledok için destekleyici negatif bulgu bulunamadı."),
        _evidence("clinical_lab_agreement", "Klinik inflamasyon ile laboratuvar uyumu", "cross_modal_consistency", 2, 2, (fever or ruq or murphy) and inflammatory, "Klinik inflamasyon bulgularına lökosit/nötrofil/CRP yüksekliği eşlik ediyor." if inflammatory else "Klinik ve inflamatuvar laboratuvar uyumu doğrulanamadı."),
        _evidence("clinical_imaging_agreement", "Klinik lokalizasyon ile görüntüleme uyumu", "cross_modal_consistency", 2, 2, (ruq or murphy) and key_imaging, "Sağ üst kadran/Murphy bulguları safra kesesi görüntüleme bulgularıyla aynı odağı destekliyor." if key_imaging else "Klinik lokalizasyon ile görüntüleme uyumu doğrulanamadı."),
        _evidence("cholestatic_imaging_agreement", "Kolestatik laboratuvar ile safra yolu uyumu", "cross_modal_consistency", 1, 1, cholestatic and dilatation, "Kolestatik laboratuvar yüksekliği ile koledok/safra yolu genişliği birlikte bulundu." if cholestatic and dilatation else "Kolestatik laboratuvar ve safra yolu görüntüleme uyumu doğrulanamadı."),
    ]

    grouped: dict[str, list[CompatibilityEvidence]] = defaultdict(list)
    for item in evidence:
        grouped[item.domain].append(item)
    breakdown = [
        CompatibilityBreakdown(
            domain=domain,
            label=_DOMAIN_LABELS[domain],
            score=sum(item.points for item in grouped[domain]),
            maximum_score=sum(item.maximum_points for item in grouped[domain]),
        )
        for domain in ("clinical_findings", "laboratory_findings", "imaging_findings", "cross_modal_consistency")
    ]
    score = max(0, min(100, sum(item.score for item in breakdown)))

    clinical_available = bool(clinical)
    labs_available = bool(request.lab_results)
    imaging_available = bool(imaging)
    cross_available = sum((clinical_available, labs_available, imaging_available)) >= 2
    completeness = (30 if clinical_available else 0) + (25 if labs_available else 0) + (40 if imaging_available else 0) + (5 if cross_available else 0)
    missing: list[str] = []
    if not clinical_available:
        missing.append("Klinik öykü ve fizik muayene bulguları")
    if not labs_available:
        missing.append("Yapılandırılmış laboratuvar sonuçları")
    if not imaging_available:
        missing.append("Ultrason veya görüntüleme raporu")
    level, level_label = _compatibility_level(score)

    return ClinicalCompatibilityScore(
        score=score,
        level=level,
        level_label=level_label,
        data_completeness_percent=completeness,
        breakdown=breakdown,
        evidence=evidence,
        supporting_evidence=[item for item in evidence if item.matched and item.points > 0],
        missing_data=missing,
        disclaimer="Bu puan tanı olasılığı değildir. Yapılandırılmış bulguların akut kalkülöz kolesistit hipoteziyle uyumunu gösterir ve hekim değerlendirmesinin yerine geçmez.",
    )


def evaluate_clinical_brain(request: ClinicalBrainRequest) -> ClinicalBrainResult:
    ultrasound = get_latest_ultrasound_report(request.radiology_reports)
    clinical_ready = _has_meaningful_clinical_data(request)
    lab_ready = bool(request.lab_results)
    ultrasound_ready = ultrasound is not None

    source_summaries = ClinicalBrainSourceSummaries(
        clinical=build_clinical_summary(request),
        laboratory=build_laboratory_summary(request.lab_results),
        ultrasound=build_ultrasound_summary(ultrasound),
    )
    ai_summaries = ClinicalBrainSourceSummaries(
        clinical=build_clinical_ai_summary(request) if clinical_ready else "",
        laboratory=build_laboratory_ai_summary(request.lab_results) if lab_ready else "",
        ultrasound=build_ultrasound_summary(ultrasound) if ultrasound_ready else "",
    )
    dates = _source_dates(request.lab_results, ultrasound)

    return ClinicalBrainResult(
        source_summaries=source_summaries,
        ai_source_summaries=ai_summaries,
        source_availability=ClinicalBrainSourceAvailability(
            clinical=clinical_ready,
            laboratory=lab_ready,
            ultrasound=ultrasound_ready,
        ),
        source_dates=dates,
        temporal_gap_days=_temporal_gap_days(dates),
        performed_studies=build_performed_studies([ultrasound] if ultrasound else []),
        ultrasound_context_flags=build_ultrasound_context_flags(ultrasound),
        selected_ultrasound_report_id=ultrasound.id if ultrasound else None,
        doctor_interpretation=build_doctor_interpretation(request.lab_results),
        compatibility=calculate_acute_cholecystitis_compatibility(request),
        disclaimer="MediCore Clinical Brain çıktıları klinik karar desteğidir; tanı veya tedavi kararı değildir ve hekim tarafından doğrulanmalıdır.",
    )
