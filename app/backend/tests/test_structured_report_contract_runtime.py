from app.domain.medical_report_summary_ai import MedicalReportReview
from app.domain.structured_report_contract_runtime import (
    _merge_review_metadata_structured,
    _structured_result_text,
)


def _review() -> MedicalReportReview:
    return MedicalReportReview(
        report_category="GENETIC",
        report_type="Moleküler genetik raporu",
        specialty="Tıbbi Genetik",
        modality="OTHER",
        body_part="OTHER",
        main_result=(
            "CDKL5 geninde heterozigot c.54dup, p.(Val19CysfsTer3) varyantı "
            "saptanmış ve raporda yüksek olasılıkla patojenik olarak sınıflandırılmıştır."
        ),
        technical_findings=(
            "CDKL5 c.54dup, p.(Val19CysfsTer3)",
            "Heterozigot; frameshift",
            "ACMG: yüksek olasılıkla patojenik",
        ),
        clinical_interpretation=(
            "Rapor varyantı CDKL5 ilişkili gelişimsel ve epileptik ensefalopati ile "
            "ilişkilendiriyor; ebeveynlerde saptanmaması de novo oluşumu destekliyor."
        ),
        doctor_summary="Kaynak raporun yoğun hekim özeti.",
        brief_summary="CDKL5 frameshift varyantı klinik tabloyu açıklayabilecek genetik neden olarak değerlendiriliyor.",
        conclusion="Varyant yüksek olasılıkla patojenik olarak değerlendirilmiştir.",
        key_findings=("Anne ve babada varyant saptanmamıştır.",),
        abnormal_findings=("CDKL5 varyantı saptandı.",),
        reassuring_findings=(),
        recommendations=("Genetik danışmanlık önerilmiştir.",),
        critical_flags=(),
        comparison_text="",
        limitations=(),
        confidence=0.96,
        model="test-model",
    )


def test_structured_result_has_fixed_medical_sections() -> None:
    text = _structured_result_text(_review())
    assert "ANA SONUÇ:" in text
    assert "KLİNİK YORUM:" in text
    assert "KISACA:" in text
    assert "istersen" not in text.lower()


def test_metadata_keeps_structured_fields_and_source_recommendation() -> None:
    metadata = _merge_review_metadata_structured({}, _review())
    assert metadata["report_contract_version"] == "physician-report-v2"
    assert metadata["main_result"].startswith("CDKL5")
    assert len(metadata["technical_findings"]) == 3
    assert metadata["clinical_interpretation"]
    assert metadata["brief_summary"]
    assert any(item.startswith("Rapordaki öneri:") for item in metadata["key_findings"])
