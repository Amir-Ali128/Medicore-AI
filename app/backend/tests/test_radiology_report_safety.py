from __future__ import annotations

import unittest

from app.domain.radiology_report_safety import analyze_radiology_report_safely


class RadiologyReportSafetyTests(unittest.TestCase):
    def test_indication_only_term_is_not_reported_as_current_finding(self) -> None:
        report = """
        TORAKS BT ANJİYOGRAFİ
        Klinik bilgi: Pulmoner emboli şüphesi ile inceleme yapılmıştır.
        Bulgular: Pulmoner arter dallarında dolum defekti saptanmamıştır.
        Sonuç: Pulmoner emboli lehine bulgu yoktur.
        """

        result = analyze_radiology_report_safely(report)

        self.assertNotIn("Pulmoner emboli", result["critical_findings"])
        self.assertTrue(
            any("suppressed unsupported critical mentions" in item for item in result["warnings"])
        )

    def test_history_only_critical_term_is_suppressed(self) -> None:
        report = """
        KRANİYAL BT
        Öykü: İki yıl önce subdural hematom nedeniyle opere edilmiş.
        Bulgular: Güncel incelemede intrakraniyal kanama saptanmamıştır.
        Sonuç: Akut intrakraniyal patoloji yoktur.
        """

        result = analyze_radiology_report_safely(report)

        self.assertNotIn("İntrakraniyal kanama", result["critical_findings"])

    def test_positive_finding_in_active_section_remains_critical(self) -> None:
        report = """
        TORAKS BT
        Endikasyon: Göğüs ağrısı.
        Bulgular: Sol hemitoraksta pnömotoraks mevcuttur.
        Sonuç: Sol pnömotoraks.
        """

        result = analyze_radiology_report_safely(report)

        self.assertIn("Pnömotoraks", result["critical_findings"])

    def test_negation_does_not_leak_across_adversative_clause(self) -> None:
        report = """
        TORAKS BT
        Bulgular: Pnömotoraks saptanmadı, ancak pulmoner emboli ile uyumlu dolum defekti vardır.
        """

        result = analyze_radiology_report_safely(report)

        self.assertNotIn("Pnömotoraks", result["critical_findings"])
        self.assertIn("Pulmoner emboli", result["critical_findings"])


if __name__ == "__main__":
    unittest.main()
