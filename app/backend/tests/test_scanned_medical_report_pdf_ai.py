from __future__ import annotations

from app.domain.scanned_medical_report_pdf_ai import ScannedMedicalReportExtraction


def test_scanned_report_extraction_contract() -> None:
    extraction = ScannedMedicalReportExtraction(
        deidentified_text="Bulgular: Örnek klinik rapor metni.",
        document_type="Tıbbi rapor",
        warnings=(),
        confidence=0.9,
        model="test-model",
    )

    assert extraction.deidentified_text.startswith("Bulgular")
    assert extraction.confidence == 0.9
