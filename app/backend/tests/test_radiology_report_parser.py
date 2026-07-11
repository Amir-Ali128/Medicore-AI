from __future__ import annotations

import unittest

from app.domain.radiology_report_parser import analyze_radiology_report


class RadiologyReportParserTests(unittest.TestCase):
    def test_extracts_modality_body_part_measurements_and_critical_finding(self) -> None:
        report = """
        TORAKS BT İNCELEMESİ
        Bulgular:
        Sağ alt lobda 18 mm nodüler lezyon izlenmiştir.
        Sol hemitoraksta pnömotoraks mevcuttur.
        Sonuç:
        Sol pnömotoraks ve sağ akciğerde nodüler lezyon.
        """
        result = analyze_radiology_report(report)

        self.assertEqual(result["modality"], "CT")
        self.assertEqual(result["body_part"], "CHEST")
        self.assertIn("Pnömotoraks", result["critical_findings"])
        self.assertTrue(any(item["value"] == "18" for item in result["measurements"]))

    def test_negated_critical_term_is_not_flagged(self) -> None:
        report = """
        PA Akciğer Grafisi
        Bulgular: Pnömotoraks saptanmadı. Fokal konsolidasyon izlenmedi.
        Sonuç: Akut kardiyopulmoner patoloji yoktur.
        """
        result = analyze_radiology_report(report)
        self.assertEqual(result["modality"], "XRAY")
        self.assertNotIn("Pnömotoraks", result["critical_findings"])

    def test_short_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze_radiology_report("MR")


if __name__ == "__main__":
    unittest.main()
