"""Aggregate abnormal-lab clinical associations and possible follow-up tests.

This runtime keeps the per-parameter card focused on the abnormal value and its
clinical meaning, while placing broader possible conditions and tests at the end of
the combined evaluation. Suggestions are conservative, non-diagnostic and always
require physician correlation with the full clinical context.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis


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


def _contains(name: str, *aliases: str) -> bool:
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


def _test(name: str, rationale: str, priority: str = "routine") -> dict[str, str]:
    return {"name": name, "rationale": rationale, "priority": priority}


def _suggestions_for_finding(name: str, status: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    folded = _fold(name)
    laboratory: list[dict[str, str]] = []
    imaging: list[dict[str, str]] = []

    if _contains(folded, "ALT", "AST", "ALP", "GGT", "bilirubin", "albumin", "total protein", "toplam protein", "IgG"):
        laboratory.extend(
            [
                _test("Karaciğer fonksiyon panelinin tekrarı", "ALT, AST, ALP, GGT, bilirubin ve albumin paternini doğrulamak için.", "soon"),
                _test("PT/INR", "Karaciğer sentetik fonksiyonunun klinik olarak uygun olduğunda değerlendirilmesi için.", "soon"),
                _test("Hepatit serolojileri", "Persistan karaciğer enzimi yüksekliğinde viral nedenlerin hekim tarafından dışlanmasına yardımcı olabilir.", "routine"),
            ]
        )
        if _contains(folded, "IgG", "ALT", "AST") and status == "high":
            laboratory.append(
                _test("ANA / SMA ve total IgG", "Persistan hepatoselüler patern varsa otoimmün karaciğer hastalığı açısından hekim değerlendirmesinde düşünülebilir.", "routine")
            )
        imaging.extend(
            [
                _test("Hepatobilier ultrasonografi", "Karaciğer, safra yolları ve portal sistemin mevcut laboratuvar paternine göre değerlendirilmesi için.", "soon"),
                _test("Karaciğer elastografisi", "Kronik karaciğer hastalığı veya fibrozis şüphesi sürerse hekim tarafından değerlendirilebilir.", "routine"),
            ]
        )

    if _contains(folded, "lipaz", "lipase", "amilaz", "amylase"):
        laboratory.extend(
            [
                _test("Lipaz / amilaz tekrarı", "Enzim yüksekliğinin kalıcı olup olmadığını ve klinik semptomlarla ilişkisini değerlendirmek için.", "soon"),
                _test("Kapsamlı metabolik panel", "Eşlik eden karaciğer, böbrek ve elektrolit değişikliklerini değerlendirmek için.", "soon"),
            ]
        )
        imaging.extend(
            [
                _test("Üst abdomen ultrasonografisi", "Safra kesesi, safra yolları ve pankreas çevresinin klinik olarak uygun olduğunda değerlendirilmesi için.", "soon"),
                _test("Kontrastlı abdomen BT/MR", "Belirgin veya persistan pankreatik bulgular ve uyumlu semptomlar varsa hekim tarafından ileri görüntüleme olarak düşünülebilir.", "routine"),
            ]
        )

    if _contains(folded, "PLT", "trombosit", "platelet", "MPV", "PDW", "PCT", "RDW", "hemoglobin", "HGB", "hematokrit", "HCT", "WBC", "lokosit", "leukocyte"):
        laboratory.extend(
            [
                _test("Tam kan sayımının tekrarı", "Hematolojik sapmanın kalıcı olup olmadığını doğrulamak için.", "soon"),
                _test("Periferik yayma", "Trombosit ve eritrosit morfolojisinin manuel olarak değerlendirilmesine yardımcı olabilir.", "soon"),
            ]
        )
        if _contains(folded, "RDW", "hemoglobin", "HGB", "hematokrit", "HCT", "trombosit", "PLT"):
            laboratory.extend(
                [
                    _test("Ferritin ve demir paneli", "Demir eksikliği veya demir dağılım bozukluğunu değerlendirmek için.", "routine"),
                    _test("Vitamin B12 ve folat", "Sitopeni veya eritrosit indeks değişikliklerinde eksiklik nedenlerini değerlendirmek için.", "routine"),
                ]
            )

    if _contains(folded, "ferritin", "serum demir", "iron", "demir"):
        laboratory.extend(
            [
                _test("Transferrin / TDBK ve transferrin satürasyonu", "Demir eksikliği ile inflamatuvar veya yüklenme paternlerini ayırmaya yardımcı olabilir.", "soon"),
                _test("Tam kan sayımı ve retikülosit", "Demir durumunun eritropoez üzerindeki etkisini birlikte değerlendirmek için.", "soon"),
            ]
        )
        if status == "low":
            laboratory.append(
                _test("Gaitada gizli kan", "Demir eksikliği doğrulanır ve klinik olarak uygunsa gastrointestinal kan kaybı değerlendirmesinin bir parçası olabilir.", "routine")
            )

    if _contains(folded, "glukoz", "glucose", "HbA1c", "hemoglobin a1c"):
        laboratory.extend(
            [
                _test("Açlık plazma glukozu", "Hipergliseminin açlık koşullarında doğrulanması için.", "soon"),
                _test("HbA1c", "Son haftalar-aylardaki glisemik yükü değerlendirmek için.", "soon"),
                _test("İdrar albumin/kreatinin oranı", "Kalıcı diyabetik patern doğrulanırsa böbrek etkileniminin taranmasında değerlendirilebilir.", "routine"),
            ]
        )

    if _contains(folded, "HDL", "LDL", "trigliserid", "triglyceride", "kolesterol", "cholesterol"):
        laboratory.extend(
            [
                _test("Açlık lipid paneli", "Lipid paternini LDL, HDL ve trigliserid fraksiyonlarıyla doğrulamak için.", "routine"),
                _test("HbA1c / açlık glukozu", "Metabolik sendrom veya insülin direnciyle birlikte değerlendirmek için.", "routine"),
                _test("TSH", "Sekonder dislipidemi nedenlerinden hipotiroidiyi klinik olarak uygun olduğunda değerlendirmek için.", "routine"),
            ]
        )

    if _contains(folded, "kreatinin", "creatinine", "eGFR", "glomeruler", "ure", "urea", "BUN"):
        laboratory.extend(
            [
                _test("Kreatinin / eGFR tekrarı", "Böbrek filtrasyon değişikliğinin kalıcı olup olmadığını değerlendirmek için.", "soon"),
                _test("Tam idrar tahlili", "Protein, kan veya diğer renal ipuçlarını değerlendirmek için.", "soon"),
                _test("İdrar albumin/kreatinin oranı", "Kalıcı renal risk paterninde albuminürinin değerlendirilmesi için.", "routine"),
            ]
        )
        imaging.append(
            _test("Renal ultrasonografi", "Persistan böbrek fonksiyon bozukluğu veya üriner sistem şüphesinde yapısal nedenlerin değerlendirilmesi için.", "routine")
        )

    if _contains(folded, "sodyum", "sodium", "Na", "potasyum", "potassium", "K", "magnezyum", "magnesium", "Mg"):
        laboratory.extend(
            [
                _test("Elektrolit panelinin tekrarı", "Elektrolit sapmasının gerçek ve kalıcı olup olmadığını doğrulamak için.", "soon"),
                _test("Kreatinin / eGFR", "Renal atılımın elektrolit değişikliğine katkısını değerlendirmek için.", "soon"),
            ]
        )
        if _contains(folded, "sodyum", "sodium", "Na"):
            laboratory.append(
                _test("Serum ve idrar osmolalitesi", "Belirgin sodyum bozukluğunda su dengesi mekanizmasını ayırmaya yardımcı olabilir.", "routine")
            )

    if _contains(folded, "kalsiyum", "calcium", "Ca"):
        laboratory.extend(
            [
                _test("Düzeltilmiş / iyonize kalsiyum", "Albuminden bağımsız kalsiyum durumunu doğrulamak için.", "soon"),
                _test("PTH ve 25-OH vitamin D", "Paratiroid ve vitamin D eksenini değerlendirmek için.", "routine"),
                _test("Fosfor ve magnezyum", "Kalsiyum homeostazını birlikte değerlendirmek için.", "routine"),
            ]
        )

    if _contains(folded, "CRP", "sedimantasyon", "ESR") and status == "high":
        laboratory.extend(
            [
                _test("CRP / sedimentasyon tekrarı", "İnflamatuvar belirteçlerin seyrini değerlendirmek için.", "routine"),
                _test("Tam kan sayımı", "Enfeksiyon veya inflamasyonla ilişkili hematolojik paterni değerlendirmek için.", "routine"),
            ]
        )

    return laboratory, imaging


def _dedupe_tests(items: list[dict[str, str]], *, limit: int) -> list[dict[str, str]]:
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for item in items:
        key = _fold(item.get("name"))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def _build_hypothesis_with_end_sections(
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

    metadata = dict(hypothesis.metadata_json or {})
    findings = list(metadata.get("pathological_findings") or [])
    possible_conditions: list[str] = []
    laboratory_tests: list[dict[str, str]] = []
    imaging_tests: list[dict[str, str]] = []

    for finding in findings:
        if not isinstance(finding, dict) or finding.get("source") != "laboratory":
            continue
        status = str(finding.get("status") or "").lower()
        if status not in {"high", "low"}:
            continue

        causes = finding.get("possible_causes")
        if isinstance(causes, list):
            for cause in causes:
                if isinstance(cause, str) and cause.strip() and cause not in possible_conditions:
                    possible_conditions.append(cause.strip())

        labs, images = _suggestions_for_finding(str(finding.get("name") or ""), status)
        laboratory_tests.extend(labs)
        imaging_tests.extend(images)

    metadata["possible_conditions"] = possible_conditions[:18]
    metadata["recommended_laboratory_tests"] = _dedupe_tests(laboratory_tests, limit=12)
    metadata["recommended_imaging_tests"] = _dedupe_tests(imaging_tests, limit=8)
    metadata["follow_up_suggestion_mode"] = "possible_only_physician_review"
    metadata["follow_up_note"] = (
        "Bu olası durumlar ve ileri tetkikler tanı veya otomatik istem değildir; "
        "klinik öykü, muayene ve mevcut sonuçlarla birlikte hekim tarafından seçilmelidir."
    )
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_end_sections
