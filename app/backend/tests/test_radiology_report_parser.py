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

    def test_formal_turkish_negation_does_not_flag_free_air(self) -> None:
        report = """
        KONTRASTLI ÜST ABDOMEN BT İNCELEMESİ
        Karaciğer parankiminde fokal kitle lezyonu saptanmamıştır.
        Pankreas başında kitle saptanmamıştır.
        Patolojik boyutta lenf nodu izlenmemiştir.
        Serbest hava veya serbest sıvı saptanmamıştır.
        Sonuç: Distal koledok düzeyinde kalküle bağlı obstrüksiyon ile uyumlu görünüm.
        """
        result = analyze_radiology_report(report)

        self.assertNotIn("Serbest hava", result["critical_findings"])
        free_air_finding = next(
            item for item in result["findings"] if "Serbest hava" in item["text"]
        )
        self.assertEqual(free_air_finding["classification"], "observation")
        self.assertFalse(free_air_finding["is_critical"])

        negated_mass_findings = [
            item
            for item in result["findings"]
            if "kitle" in item["text"].lower()
        ]
        self.assertTrue(negated_mass_findings)
        self.assertTrue(
            all(item["classification"] == "observation" for item in negated_mass_findings)
        )

    def test_positive_free_air_is_still_critical(self) -> None:
        report = """
        ABDOMEN BT İNCELEMESİ
        Batın içinde yaygın serbest hava izlenmektedir.
        Perforasyon açısından acil değerlendirme önerilir.
        """
        result = analyze_radiology_report(report)
        self.assertIn("Serbest hava", result["critical_findings"])

    def test_extracts_labelled_dexa_metrics_and_score_bands(self) -> None:
        report = """
        DEXA KEMİK MİNERAL YOĞUNLUĞU
        L1-L4 BMD: 0.812 g/cm² T-score: -2.6 Z-score: -1.4
        Femur boynu BMD: 0.721 g/cm2 T skoru: -1.8 Z skoru: -0.9
        Sonuç: Lomber bölgede düşük kemik mineral yoğunluğu.
        """
        result = analyze_radiology_report(report)

        self.assertEqual(result["modality"], "DEXA")
        self.assertEqual(result["body_part"], "BONE_DENSITY")
        self.assertEqual(len(result["dexa_metrics"]), 2)
        lumbar = result["dexa_metrics"][0]
        self.assertEqual(lumbar["site"], "LUMBAR_SPINE_L1_L4")
        self.assertEqual(lumbar["bmd"], 0.812)
        self.assertEqual(lumbar["t_score"], -2.6)
        self.assertEqual(lumbar["z_score"], -1.4)
        self.assertEqual(lumbar["t_score_band"], "osteoporosis_range")
        self.assertEqual(lumbar["z_score_band"], "within_expected_for_age")

    def test_extracts_unlabelled_dexa_table_scores(self) -> None:
        report = """
        DXA Bone Density
        AP Spine L1-L4 1.005 g/cm2 -0.8 -0.2
        Femoral Neck 0.650 g/cm2 -2.7 -2.1
        """
        result = analyze_radiology_report(report)

        self.assertEqual(result["modality"], "DEXA")
        self.assertEqual(result["dexa_metrics"][0]["t_score_band"], "normal_range")
        self.assertEqual(result["dexa_metrics"][1]["t_score_band"], "osteoporosis_range")
        self.assertEqual(result["dexa_metrics"][1]["z_score_band"], "below_expected_for_age")

    def test_short_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            analyze_radiology_report("MR")


if __name__ == "__main__":
    unittest.main()
